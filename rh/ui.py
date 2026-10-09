"""화면: 메인(가로형) / 설정 / 정보 / 개인정보 동의 / 허락 대화상자."""
import json
import math
import os
import platform
import queue
import shutil
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

import customtkinter as ctk

from . import i18n, links, secret
from .config import APP_NAME, APP_VERSION, DATA_DIR, load_config, log_error, save_config
from .engine import (MODEL_SIZES_MB, MT_DIR, MT_SIZE_MB, Engine, MicMonitor, Output, TranslateError, download_mt,
                     format_chatbox, get_model, list_mics, meter_value, model_cached, model_name, mt_cached,
                     preview_default, release_model, release_mt, threshold_for, translate_text,
                     translation_allowed)
from .i18n import LANGS, NATIVE, T, lang_label

FONT = "Malgun Gothic"
PURPLE, PURPLE_H = ("#7C6BF2", "#8B7CFF"), ("#6A59E0", "#7A69F5")
PINK, PINK_H = ("#F25577", "#FF6B8A"), ("#E04466", "#F25577")
BG, CARD, FIELD = ("#EEEBFA", "#14141F"), ("#FFFFFF", "#1E1E2E"), ("#F1EFFC", "#2A2A40")
FIELD_H = ("#E0DBFA", "#363652")
TEXT, SUB = ("#26224A", "#ECE9FF"), ("#7B7799", "#9593B5")
GREEN, ORANGE, RED = ("#1FA971", "#6EE7A8"), ("#D98A1F", "#FFC46B"), ("#D93A5C", "#FF8AA0")
MAX_BUBBLES = 60
RESTART_KEYS = {"mic", "model", "device_type", "vrc_mute_sync", "osc_ip", "osc_port", "osc_in_port"}
KEY_URLS = {"deepl": "https://www.deepl.com/pro-api", "google": "https://cloud.google.com/translate/docs/setup"}


def resource_path(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / name


def f(size=13, bold=False):
    return ctk.CTkFont(family=FONT, size=size, weight="bold" if bold else "normal")


def pill_button(parent, text, cmd, color=PURPLE, hover=PURPLE_H, text_color="#FFFFFF", height=36, **kw):
    return ctk.CTkButton(parent, text=text, command=cmd, height=height, corner_radius=height // 2,
                         font=f(13, True), fg_color=color, hover_color=hover, text_color=text_color, **kw)


def soft_button(parent, text, cmd, height=34, **kw):
    return pill_button(parent, text, cmd, FIELD, FIELD_H, TEXT, height=height, **kw)


# ====================================================================== 대화상자
class _Modal(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent, fg_color=BG)
        self.resizable(False, False)
        self.transient(parent)
        self.attributes("-topmost", True)
        self.after(150, self._grab)

    def _grab(self):
        try:
            self.lift()
            self.focus()
            self.grab_set()
        except Exception:
            pass


class AskDialog(_Modal):
    """예/아니오 허락 대화상자."""

    def __init__(self, parent, title, body, yes, no):
        super().__init__(parent)
        self.result = False
        self.title(title)
        ctk.CTkLabel(self, text=title, font=f(16, True), text_color=TEXT).pack(anchor="w", padx=26, pady=(24, 8))
        ctk.CTkLabel(self, text=body, font=f(13), text_color=TEXT, wraplength=440, justify="left").pack(
            anchor="w", padx=26)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=26, pady=24)
        pill_button(row, yes, lambda: self._done(True), width=150).pack(side="right")
        soft_button(row, no, lambda: self._done(False), width=110).pack(side="right", padx=8)
        self.protocol("WM_DELETE_WINDOW", lambda: self._done(False))

    def _done(self, value):
        self.result = value
        self.grab_release()
        self.destroy()


def ask(parent, title, body, yes, no):
    d = AskDialog(parent, title, body, yes, no)
    parent.wait_window(d)
    return d.result


class ConsentWindow(_Modal):
    """첫 실행 개인정보 안내. 체크하지 않은 항목은 동의하지 않은 것으로 처리."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(T("priv_title"))
        ctk.CTkLabel(self, text="🔒 " + T("priv_title"), font=f(18, True), text_color=TEXT).pack(
            anchor="w", padx=26, pady=(24, 10))
        for key in ("priv_audio", "priv_models", "priv_none"):
            ctk.CTkLabel(self, text=T(key), font=f(13), text_color=TEXT, wraplength=520, justify="left").pack(
                anchor="w", padx=26, pady=3)
        card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=18)
        card.pack(fill="x", padx=22, pady=14)
        self.v_tr, self.v_up = ctk.BooleanVar(value=False), ctk.BooleanVar(value=False)
        for var, key, pad in ((self.v_tr, "priv_translate", (14, 8)), (self.v_up, "priv_update", (0, 14))):
            sw = ctk.CTkSwitch(card, text=T(key), variable=var, font=f(12), progress_color=PURPLE, text_color=TEXT)
            sw.pack(anchor="w", padx=16, pady=pad)
            sw._text_label.configure(wraplength=450, justify="left")
        ctk.CTkLabel(self, text=T("priv_later"), font=f(11), text_color=SUB).pack(anchor="w", padx=26)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=26, pady=20)
        pill_button(row, T("priv_ok"), self._ok, width=130).pack(side="right")
        soft_button(row, T("policy"), lambda: app.open_info("tab_privacy"), width=170).pack(side="right", padx=8)
        self.protocol("WM_DELETE_WINDOW", self._ok)

    def _ok(self):
        self.app.cfg.update(consent_done=True, consent_translate=self.v_tr.get(), consent_update=self.v_up.get())
        save_config(self.app.cfg)
        self.grab_release()
        self.destroy()


# ====================================================================== 메인 창 (가로형)
class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.cfg = load_config()
        i18n.set_lang(self.cfg["ui_lang"])
        ctk.set_appearance_mode(self.cfg["theme"])
        self.geometry("1000x620")
        self.minsize(900, 560)
        self.attributes("-topmost", self.cfg["always_on_top"])
        self.events = queue.Queue()
        self.output = Output(self.cfg)
        self.engine = None
        self.restart_pending = False
        self.settings = self.info = None
        self.bubbles = []
        self._wrap = 460
        self._wrap_job = None
        self._shown_state = None
        self._mt_pct = None  # 오프라인 번역 모델 다운로드 진행률
        self.update_info = None
        self.build()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self._tick)
        self.after(300, self._startup)

    def _startup(self):
        if not self.cfg["consent_done"]:
            c = ConsentWindow(self)
            self.wait_window(c)
            self.refresh_target()
        if self.cfg["last_seen_version"] != APP_VERSION:
            self.open_info("tab_new")
        self.check_update_if_allowed()
        self._preload()

    def _preload(self):
        """이미 받아둔 모델이 있으면 미리 메모리에 올려 '시작'을 즉시 되게 함 (다운로드는 하지 않음)."""
        if not self.cfg["keep_model"] or not model_cached(model_name(self.cfg)):
            return

        def run():
            try:
                get_model(self.cfg)
            except Exception as e:
                log_error(f"preload: {type(e).__name__}")
        threading.Thread(target=run, daemon=True).start()

    # -- 화면 구성 ------------------------------------------------------
    def build(self):
        for w in self.winfo_children():
            w.destroy()
        self.bubbles = []
        self._shown_state = None
        self._mpos = self._meter_on = None
        self.title(f"{T('title')} · by RabbitHaru")
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # ── 왼쪽: 컨트롤 패널 ──
        side = ctk.CTkFrame(self, fg_color=CARD, corner_radius=26, width=350)
        side.grid(row=0, column=0, sticky="ns", padx=(16, 8), pady=16)
        side.pack_propagate(False)

        bottom = ctk.CTkFrame(side, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=20, pady=(0, 20))
        soft_button(bottom, "⚙  " + T("settings"), self.open_settings).pack(side="left", expand=True, fill="x", padx=(0, 6))
        soft_button(bottom, "♥  " + T("about"), lambda: self.open_info("tab_new")).pack(side="left", expand=True, fill="x", padx=(6, 0))

        ctk.CTkLabel(side, text="🐰 " + T("title"), font=f(24, True), text_color=TEXT, anchor="w").pack(
            fill="x", padx=24, pady=(24, 0))
        ctk.CTkLabel(side, text=T("tagline"), font=f(11), text_color=SUB, anchor="w").pack(fill="x", padx=26)
        self.update_lbl = ctk.CTkLabel(side, text="", font=f(11, True), text_color=PURPLE, cursor="hand2", anchor="w")
        self.update_lbl.pack(fill="x", padx=26)
        self.update_lbl.bind("<Button-1>", lambda e: self.update_info and webbrowser.open(self.update_info[1]))
        self._show_update()

        self.status = ctk.CTkLabel(side, text="", font=f(12, True), text_color=SUB, fg_color=FIELD,
                                   corner_radius=14, height=30, anchor="w")
        self.status.pack(fill="x", padx=22, pady=(14, 12))
        self.btn = ctk.CTkButton(side, text=T("start"), height=54, corner_radius=27, font=f(17, True),
                                 fg_color=PURPLE, hover_color=PURPLE_H, command=self.toggle)
        self.btn.pack(fill="x", padx=22)

        mic = ctk.CTkFrame(side, fg_color=FIELD, corner_radius=18)
        mic.pack(fill="x", padx=22, pady=(16, 0))
        head = ctk.CTkFrame(mic, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(12, 6))
        ctk.CTkLabel(head, text="🎤  " + T("level"), font=f(12), text_color=SUB).pack(side="left")
        self.db_lbl = ctk.CTkLabel(head, text="", font=f(12, True), text_color=SUB)
        self.db_lbl.pack(side="right")
        self.meter = ctk.CTkProgressBar(mic, height=12, corner_radius=6, progress_color=PURPLE, fg_color=CARD)
        self.meter.set(0)
        self.meter.pack(fill="x", padx=16)
        self.mmarker = ctk.CTkFrame(mic, width=3, height=20, corner_radius=1, fg_color=PINK)
        self.pause_btn = ctk.CTkButton(mic, text=T("pause"), height=30, corner_radius=15, font=f(12, True),
                                       fg_color=CARD, hover_color=FIELD_H, text_color=TEXT, command=self.toggle_pause)
        self.pause_btn.pack(fill="x", padx=16, pady=(10, 14))

        ctk.CTkLabel(side, text=T("speech_lang"), font=f(12), text_color=SUB, anchor="w").pack(fill="x", padx=26, pady=(16, 4))
        items = [("auto", T("auto"))] + [(c, lang_label(c)) for c in LANGS]
        by_label = {l: c for c, l in items}
        self.src_menu = ctk.CTkOptionMenu(
            side, values=[l for _, l in items], corner_radius=16, height=36, font=f(13), dropdown_font=f(13),
            fg_color=FIELD, text_color=TEXT, button_color=PURPLE, button_hover_color=PURPLE_H,
            dynamic_resizing=False, command=lambda l: self.set_cfg("source", by_label[l]))
        self.src_menu.set(next(l for c, l in items if c == self.cfg["source"]))
        self.src_menu.pack(fill="x", padx=22)

        ctk.CTkLabel(side, text=T("translate_to"), font=f(12), text_color=SUB, anchor="w").pack(fill="x", padx=26, pady=(14, 4))
        self.target_btn = ctk.CTkSegmentedButton(
            side, values=[T("stt_only")] + [NATIVE[c] for c in LANGS], command=self._on_target, height=36,
            corner_radius=18, font=f(11, True), text_color=TEXT, selected_color=PURPLE, selected_hover_color=PURPLE_H,
            unselected_color=FIELD, unselected_hover_color=FIELD_H)
        self.target_btn.pack(fill="x", padx=22)
        self.refresh_target()

        # ── 오른쪽: 대화 ──
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
        head = ctk.CTkFrame(main, fg_color="transparent")
        head.pack(fill="x", padx=6, pady=(0, 8))
        ctk.CTkLabel(head, text=T("history"), font=f(16, True), text_color=TEXT).pack(side="left")
        ctk.CTkButton(head, text=T("clear"), width=70, height=28, corner_radius=14, font=f(12), fg_color="transparent",
                      hover_color=FIELD_H, text_color=SUB, command=self.clear_history).pack(side="right")

        bar = ctk.CTkFrame(main, fg_color="transparent")
        bar.pack(side="bottom", fill="x", pady=(10, 0))
        self.entry = ctk.CTkEntry(bar, placeholder_text=T("type_hint"), height=44, corner_radius=22, font=f(13),
                                  fg_color=CARD, border_width=0)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.send_manual())
        pill_button(bar, T("send"), self.send_manual, height=44, width=84).pack(side="left", padx=(10, 0))
        self.partial_lbl = ctk.CTkLabel(main, text="", font=f(12), text_color=SUB, wraplength=560, justify="left", anchor="w")
        self.partial_lbl.pack(side="bottom", fill="x", padx=14, pady=(8, 0))

        self.hist = ctk.CTkScrollableFrame(main, fg_color=CARD, corner_radius=26)
        self.hist.pack(fill="both", expand=True)
        self.hist.bind("<Configure>", self._on_hist_resize)
        self.empty = ctk.CTkLabel(self.hist, text=T("empty"), font=f(14), text_color=SUB, justify="center")
        self.empty.pack(pady=80)

    def _on_hist_resize(self, e):
        if self._wrap_job is not None:
            self.after_cancel(self._wrap_job)
        self._wrap_job = self.after(150, self._apply_wrap)

    def _apply_wrap(self):
        self._wrap_job = None
        self._wrap = max(260, self.hist.winfo_width() - 110)
        for b in self.bubbles:
            for lbl in getattr(b, "_labels", []):
                lbl.configure(wraplength=self._wrap)
        self.partial_lbl.configure(wraplength=self._wrap + 60)

    # -- 번역 동의 / 대상 언어 --------------------------------------------
    def eff_target(self):
        return self.cfg["target"] if translation_allowed(self.cfg) else "off"

    def refresh_target(self):
        t = self.eff_target()
        self.target_btn.set(T("stt_only") if t == "off" else NATIVE[t])

    def _on_target(self, label):
        code = next((c for c in LANGS if NATIVE[c] == label), "off")
        if code != "off" and not translation_allowed(self.cfg):  # 온라인 번역 서비스는 동의 필요
            if ask(self, T("priv_title"), T("ask_translate"), T("allow"), T("deny")):
                self.cfg["consent_translate"] = True
            else:
                self.refresh_target()
                return
        if code != "off" and not self.ensure_mt():  # 오프라인 모델이 없으면 허락받고 다운로드
            code = "off"
        self.set_cfg("target", code)
        self.refresh_target()

    # -- 말풍선 ---------------------------------------------------------
    def add_bubble(self, title, body="", kind="result"):
        if self.empty is not None and self.empty.winfo_exists():
            self.empty.destroy()
            self.empty = None
        color = {"result": FIELD, "sys": "transparent", "err": ("#FFE3EA", "#47233A")}[kind]
        b = ctk.CTkFrame(self.hist, fg_color=color, corner_radius=18)
        b.pack(fill="x", padx=8, pady=5)
        tcolor = RED if kind == "err" else (SUB if kind == "sys" else TEXT)
        t = ctk.CTkLabel(b, text=title, font=f(15 if kind == "result" else 12, kind == "result"), text_color=tcolor,
                         wraplength=self._wrap, justify="left", anchor="w")
        t.pack(fill="x", padx=16, pady=(12, 2 if body else 12))
        b._labels = [t]
        if body:
            s = ctk.CTkLabel(b, text=body, font=f(11), text_color=SUB, wraplength=self._wrap, justify="left", anchor="w")
            s.pack(fill="x", padx=16, pady=(0, 12))
            b._labels.append(s)
        self.bubbles.append(b)
        while len(self.bubbles) > MAX_BUBBLES:
            self.bubbles.pop(0).destroy()
        self.after(50, lambda: self.hist._parent_canvas.yview_moveto(1.0))

    def clear_history(self):
        for b in self.bubbles:
            b.destroy()
        self.bubbles = []
        self.partial_lbl.configure(text="")

    # -- 주기 처리 (80ms) -------------------------------------------------
    def _tick(self):
        try:
            while True:
                self._handle(self.events.get_nowait())
        except queue.Empty:
            pass
        e = self.engine
        if e is not None and not e.alive:
            self.engine = e = None
            if self.restart_pending:
                self.restart_pending = False
                self.start_engine()
        state = "idle"
        if e is not None:
            state = ("stopping" if not e.running else "loading" if not e.ready else
                     "paused" if e.paused else "muted" if e.vrc_muted else "listening")
        key = (state, e.dl_pct if e is not None and state == "loading" else None, self._mt_pct)
        if key != self._shown_state:
            self._apply_state(*key)
        src = e if (e is not None and e.ready) else None
        lvl = e.level if src is not None and state == "listening" else 0.0
        sens = self.cfg["sensitivity"]
        thr = src.nf.threshold(sens) if src is not None else threshold_for(sens)
        self.meter.set(meter_value(lvl))
        db_text = f"{20 * math.log10(max(lvl, 1e-5)):.0f} dB" if state == "listening" else "— dB"
        if db_text != self.db_lbl.cget("text"):
            self.db_lbl.configure(text=db_text)
        if (lvl > thr) != self._meter_on:
            self._meter_on = lvl > thr
            self.meter.configure(progress_color=GREEN if self._meter_on else PURPLE)
        if meter_value(thr) != self._mpos:
            self._mpos = meter_value(thr)
            self.mmarker.place(in_=self.meter, relx=self._mpos, rely=0.5, anchor="center")
        self.after(80, self._tick)

    def _handle(self, ev):
        kind = ev[0]
        if kind == "partial":
            self.partial_lbl.configure(text="💬 " + ev[1])
        elif kind == "result":
            self.partial_lbl.configure(text="")
            _, src, tgt, text, out = ev
            name = NATIVE.get(src, src or "✎")
            if tgt == "off" or src == tgt:
                self.add_bubble(out, f"{name} · {T('stt_only')}" if tgt == "off" else name)
            else:
                self.add_bubble(out, f"{name} → {NATIVE[tgt]}  ·  {text}")
        elif kind == "info":
            self.add_bubble(T(ev[1]), kind="sys")
        elif kind == "error":
            self.add_bubble(f"{T('err')}: {ev[1]}", kind="err")
        elif kind == "update":
            self.update_info = (ev[1], ev[2])
            self._show_update()

    def _apply_state(self, state, pct=None, mtp=None):
        self._shown_state = (state, pct, mtp)
        loading = f"{T('dl_progress')} {pct}%" if pct is not None else T("st_loading")
        text, color = {
            "idle": (T("st_idle"), SUB), "loading": (loading, ORANGE),
            "listening": (T("st_listening"), GREEN), "paused": (T("st_paused"), ORANGE),
            "muted": (T("st_muted"), ORANGE), "stopping": (T("stopping"), SUB)}[state]
        if mtp is not None:  # 오프라인 번역 모델 다운로드 중
            text, color = f"{T('dl_mt_progress')} {mtp}%", ORANGE
        self.status.configure(text="   ●  " + text, text_color=color)
        running = state not in ("idle", "stopping")
        self.btn.configure(text=T("stop") if running else T("stopping") if state == "stopping" else T("start"),
                           fg_color=PINK if running else PURPLE, hover_color=PINK_H if running else PURPLE_H,
                           state="disabled" if state == "stopping" else "normal")
        self.pause_btn.configure(text=T("resume") if state == "paused" else T("pause"),
                                 state="normal" if state in ("listening", "paused", "muted") else "disabled")
        if state != "listening":
            self.partial_lbl.configure(text="")

    # -- 동작 -----------------------------------------------------------
    def start_engine(self):
        name = model_name(self.cfg)
        if not model_cached(name):  # 다운로드 전에 크기를 알리고 허락받기
            body = T("dl_body").format(mb=MODEL_SIZES_MB[name], name=name)
            if not ask(self, T("dl_title"), body, T("dl_yes"), T("dl_no")):
                return
        if self.eff_target() != "off":
            self.ensure_mt()
        self.engine = Engine(self.cfg, self.output, self.events)
        self.engine.start()

    def ensure_mt(self, force=False):
        """오프라인 번역 모델이 필요하면 크기를 알리고 허락받아 백그라운드로 내려받음. False = 거절."""
        if (self.cfg["translator"] != "local" and not force) or mt_cached() or self._mt_pct is not None:
            return True
        body = T("dl_body").format(mb=MT_SIZE_MB, name=T("mt_name"))
        if not ask(self, T("dl_title"), body, T("dl_yes"), T("dl_no")):
            return False
        self._mt_pct = 0

        def run():
            try:
                download_mt(lambda p: setattr(self, "_mt_pct", p))
                self.events.put(("info", "info_mt_ready"))
            except Exception as e:
                log_error(f"mt download: {type(e).__name__}")
                self.events.put(("error", f"{T('dl_mt_progress')}: {e}"))
            finally:
                self._mt_pct = None
        threading.Thread(target=run, daemon=True).start()
        return True

    def toggle(self):
        if self.engine is not None:
            self.restart_pending = False
            self.engine.stop()
        else:
            self.start_engine()

    def toggle_pause(self):
        if self.engine is not None:
            self.engine.paused = not self.engine.paused

    def set_cfg(self, key, value):
        self.cfg[key] = value
        save_config(self.cfg)
        if key in RESTART_KEYS and self.engine is not None:
            self.restart_pending = True
            self.engine.stop()

    def send_manual(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        tgt = self.eff_target()

        def run():
            try:
                out = text if tgt == "off" else translate_text(self.cfg, text, "auto", tgt)
                self.output.send(format_chatbox(out, text, self.cfg["show_original"] and tgt != "off"))
                self.events.put(("result", "", tgt, text, out))
            except TranslateError as e:
                self.events.put(("error", f"{T('tr_failed')}: {e}"))
            except Exception as e:
                self.events.put(("error", f"{T('tr_failed')}: {type(e).__name__}"))
        threading.Thread(target=run, daemon=True).start()

    # -- 업데이트 확인 (동의한 경우에만) ------------------------------------
    def check_update_if_allowed(self):
        if links.GITHUB_REPO and self.cfg["consent_update"]:
            threading.Thread(target=self._check_update, daemon=True).start()

    def _check_update(self):
        try:
            url = f"https://api.github.com/repos/{links.GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "HaruMimi"})
            data = json.loads(urllib.request.urlopen(req, timeout=8).read().decode("utf-8"))
            tag = data.get("tag_name", "").lstrip("v")
            if tag and tuple(map(int, tag.split("."))) > tuple(map(int, APP_VERSION.split("."))):
                self.events.put(("update", tag, data.get("html_url", "")))
        except Exception:
            pass

    def _show_update(self):
        if self.update_info:
            self.update_lbl.configure(text=f"✨ {T('update_avail')}: v{self.update_info[0]}")
        else:
            self.update_lbl.configure(text="")

    # -- 하위 창 ----------------------------------------------------------
    def open_settings(self, page="general"):
        if self.settings is not None and self.settings.winfo_exists():
            self.settings.focus()
            return
        self.settings = SettingsWindow(self, page)

    def open_info(self, tab="tab_new"):
        if self.info is not None and self.info.winfo_exists():
            self.info.focus()
            return
        self.info = InfoWindow(self, tab)

    def apply_ui_change(self, key, value):
        """언어/테마/항상위 같이 화면에 바로 반영해야 하는 설정."""
        self.set_cfg(key, value)
        if key == "theme":
            ctk.set_appearance_mode(value)
        elif key == "always_on_top":
            self.attributes("-topmost", value)
            if self.settings is not None and self.settings.winfo_exists():
                self.settings.attributes("-topmost", value)
        elif key == "ui_lang":
            i18n.set_lang(value)
            self.build()
            for w in (self.settings, self.info):
                if w is not None and w.winfo_exists():
                    w.destroy()
            self.settings = None
            self.after(100, self.open_settings)

    def wipe_data_and_exit(self):
        """설정·로그·모델·키 전부 삭제하고 종료."""
        if self.engine is not None:
            self.engine.stop()
        release_model()
        release_mt()
        shutil.rmtree(DATA_DIR, ignore_errors=True)
        os._exit(0)

    def on_close(self):
        if self.engine is not None:
            self.engine.stop()
        self.destroy()


# ====================================================================== 설정 창 (왼쪽 메뉴 + 오른쪽 내용)
class SettingsWindow(ctk.CTkToplevel):
    PAGES = (("general", "sec_general"), ("audio", "sec_audio"), ("translate", "sec_translate"),
             ("vrc", "sec_vrc"), ("privacy", "sec_privacy"))

    def __init__(self, app, page="general"):
        super().__init__(app, fg_color=BG)
        self.app, self.cfg = app, app.cfg
        self._test_result = None
        self.monitor = None
        self.title(T("settings"))
        self.geometry("820x600")
        self.minsize(760, 520)
        self.attributes("-topmost", self.cfg["always_on_top"])
        self.after(150, self.lift)

        nav = ctk.CTkFrame(self, fg_color=CARD, corner_radius=22, width=190)
        nav.pack(side="left", fill="y", padx=(14, 8), pady=14)
        nav.pack_propagate(False)
        ctk.CTkLabel(nav, text="⚙  " + T("settings"), font=f(16, True), text_color=TEXT, anchor="w").pack(
            fill="x", padx=20, pady=(22, 14))
        self.nav_btns, self.pages = {}, {}
        for key, label in self.PAGES:
            b = ctk.CTkButton(nav, text=T(label), height=40, corner_radius=20, font=f(13, True), anchor="w",
                              fg_color="transparent", hover_color=FIELD_H, text_color=TEXT,
                              command=lambda k=key: self.show(k))
            b.pack(fill="x", padx=12, pady=2)
            self.nav_btns[key] = b
        ctk.CTkLabel(nav, text=f"{APP_NAME} v{APP_VERSION}\nby RabbitHaru", font=f(11), text_color=SUB,
                     justify="left").pack(side="bottom", anchor="w", padx=20, pady=18)

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(side="left", fill="both", expand=True, padx=(0, 14), pady=14)
        for key, _ in self.PAGES:
            self.body = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
            self.pages[key] = self.body
            getattr(self, f"_page_{key}")()
        self.show(page)
        self.after(80, self._tick_meter)

    def show(self, key):
        for k, p in self.pages.items():
            p.pack_forget()
            self.nav_btns[k].configure(fg_color="transparent", text_color=TEXT)
        self.pages[key].pack(fill="both", expand=True)
        self.nav_btns[key].configure(fg_color=PURPLE, text_color="#FFFFFF", hover_color=PURPLE_H)

    # -- 페이지 -----------------------------------------------------------
    def _page_general(self):
        self.section(T("sec_general"))
        self.option("ui_lang", T("ui_lang"), [(c, NATIVE[c]) for c in LANGS], ui=True)
        self.option("theme", T("theme"), [("system", T("theme_system")), ("light", T("theme_light")),
                                          ("dark", T("theme_dark"))], ui=True)
        self.switch("always_on_top", T("always_on_top"), ui=True)

    def _page_audio(self):
        self.section(T("sec_audio"))
        self.mic_menu = self.option("mic", T("mic"), self._mic_items())
        soft_button(self.mic_menu.master, "⟳ " + T("refresh"), self._refresh_mics, height=28).pack(
            anchor="w", padx=14, pady=(0, 10))
        self._build_meter()
        self.slider("sensitivity", T("sensitivity"), 0, 100, 100, fmt="{:.0f}")
        self.slider("silence_sec", T("silence"), 0.2, 1.5, 26, fmt="{:.1f}s")
        self.option("noise_reduction", T("noise"), [("off", T("nr_off")), ("low", T("nr_low")), ("high", T("nr_high"))])
        self.option("model", T("model"), [(m, T("m_" + m)) for m in
                                          ("auto", "tiny", "base", "small", "medium", "large-v3-turbo")])
        self.option("device_type", T("device"), [("auto", T("dev_auto")), ("cuda", T("dev_gpu")), ("cpu", T("dev_cpu"))])
        vcard = self.card()
        ctk.CTkLabel(vcard, text=T("vocab"), font=f(12), text_color=SUB).pack(anchor="w", padx=14, pady=(10, 2))
        self.vocab = ctk.CTkEntry(vcard, placeholder_text=T("vocab_hint"), height=34, corner_radius=17, font=f(13),
                                  fg_color=FIELD, border_width=0)
        self.vocab.insert(0, self.cfg["vocab"])
        self.vocab.pack(fill="x", padx=14, pady=(0, 12))
        self.vocab.bind("<FocusOut>", self._save_vocab)
        self.vocab.bind("<Return>", self._save_vocab)
        self.switch("keep_model", T("keep_model"))
        self.switch("live_preview", T("live_preview"),
                    initial=preview_default() if self.cfg["live_preview"] is None else self.cfg["live_preview"])
        ctk.CTkLabel(self.body, text=T("restart_note"), font=f(11), text_color=SUB, anchor="w").pack(fill="x", padx=14, pady=(2, 10))

    def _page_translate(self):
        self.section(T("sec_translate"))
        self.option("translator", T("tr_provider"),
                    [("local", T("tp_local")), ("mymemory", T("tp_mymemory")), ("deepl", T("tp_deepl")),
                     ("google", T("tp_google"))], cb=lambda v: self._refresh_key_ui())
        self._build_mt_card()
        card = self.card()
        ctk.CTkLabel(card, text=T("tr_key"), font=f(12), text_color=SUB).pack(anchor="w", padx=14, pady=(10, 2))
        self.key_entry = ctk.CTkEntry(card, show="•", height=36, corner_radius=18, font=f(13), fg_color=FIELD,
                                      border_width=0)
        self.key_entry.pack(fill="x", padx=14)
        self.key_entry.bind("<Return>", self._save_key)
        self.key_entry.bind("<FocusOut>", self._save_key)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(10, 4))
        self.get_key_btn = soft_button(row, "↗ " + T("tr_get_key"), self._open_key_page, height=32)
        self.get_key_btn.pack(side="left", padx=(0, 8))
        self.rm_key_btn = soft_button(row, T("tr_key_remove"), self._remove_key, height=32)
        self.rm_key_btn.pack(side="left", padx=(0, 8))
        pill_button(row, T("tr_test"), self._test_translation, height=32).pack(side="left")
        self.test_lbl = ctk.CTkLabel(card, text="", font=f(12), text_color=SUB, anchor="w", justify="left", wraplength=530)
        self.test_lbl.pack(fill="x", padx=16, pady=(2, 0))
        ctk.CTkLabel(card, text=T("tr_key_note"), font=f(11), text_color=SUB, anchor="w", justify="left",
                     wraplength=530).pack(fill="x", padx=16, pady=(4, 12))
        tip = ctk.CTkFrame(self.body, fg_color=FIELD, corner_radius=16)
        tip.pack(fill="x", padx=4, pady=6)
        ctk.CTkLabel(tip, text="💡 " + T("tr_tip"), font=f(12), text_color=TEXT, anchor="w", justify="left",
                     wraplength=530).pack(fill="x", padx=16, pady=12)
        self._refresh_key_ui()

    def _page_vrc(self):
        self.section(T("sec_vrc"))
        self.switch("show_original", T("show_original"))
        self.switch("vrc_mute_sync", T("vrc_mute"))
        card = self.card()
        ctk.CTkLabel(card, text=T("osc_port"), font=f(12), text_color=SUB).pack(anchor="w", padx=14, pady=(10, 2))
        self.port = ctk.CTkEntry(card, width=110, height=34, corner_radius=17, font=f(13), fg_color=FIELD, border_width=0)
        self.port.insert(0, str(self.cfg["osc_port"]))
        self.port.pack(anchor="w", padx=14, pady=(0, 12))
        self.port.bind("<FocusOut>", self._save_port)
        self.port.bind("<Return>", self._save_port)

    def _page_privacy(self):
        self.section(T("sec_privacy"))
        self.switch("consent_translate", T("sw_translate"), cb=lambda v: self.app.refresh_target())
        self.switch("consent_update", T("sw_update"), cb=lambda v: v and self.app.check_update_if_allowed())
        pcard = self.card()
        soft_button(pcard, T("policy"), lambda: self.app.open_info("tab_privacy")).pack(fill="x", padx=14, pady=(14, 6))
        pill_button(pcard, T("delete_data"), self._delete_data, PINK, PINK_H, height=34).pack(fill="x", padx=14, pady=(0, 14))

    # -- 위젯 도우미 ------------------------------------------------------
    def section(self, text):
        ctk.CTkLabel(self.body, text=text, font=f(18, True), text_color=TEXT, anchor="w").pack(fill="x", padx=8, pady=(6, 8))

    def card(self):
        c = ctk.CTkFrame(self.body, fg_color=CARD, corner_radius=20)
        c.pack(fill="x", padx=4, pady=5)
        return c

    def _change(self, key, value, ui=False):
        if key == "mic":
            self._stop_monitor()  # 다음 틱에 새 마이크로 다시 열림
        (self.app.apply_ui_change if ui else self.app.set_cfg)(key, value)

    def option(self, key, label, items, ui=False, cb=None):
        card = self.card()
        ctk.CTkLabel(card, text=label, font=f(12), text_color=SUB).pack(anchor="w", padx=14, pady=(10, 2))
        by_label = {l: c for c, l in items}
        cur = next((l for c, l in items if c == self.cfg[key]), items[0][1])

        def on(l):
            self._change(key, by_label[l], ui)
            if cb:
                cb(by_label[l])
        menu = ctk.CTkOptionMenu(card, values=[l for _, l in items], corner_radius=16, height=34, font=f(13),
                                 dropdown_font=f(13), fg_color=FIELD, text_color=TEXT, button_color=PURPLE,
                                 button_hover_color=PURPLE_H, dynamic_resizing=False, command=on)
        menu.set(cur)
        menu.pack(fill="x", padx=14, pady=(0, 12 if key != "mic" else 8))
        return menu

    def _mic_items(self):
        mics = list_mics()
        if self.cfg["mic"] and self.cfg["mic"] not in mics:
            mics.append(self.cfg["mic"])
        return [(None, T("mic_default"))] + [(m, m) for m in mics]

    def _refresh_mics(self):
        items = self._mic_items()
        self.mic_menu.configure(values=[l for _, l in items])
        by_label = {l: c for c, l in items}
        self.mic_menu.configure(command=lambda l: self._change("mic", by_label[l]))

    def switch(self, key, label, ui=False, initial=None, cb=None):
        card = self.card()
        var = ctk.BooleanVar(value=bool(self.cfg[key] if initial is None else initial))

        def on():
            self._change(key, var.get(), ui)
            if cb:
                cb(var.get())
        sw = ctk.CTkSwitch(card, text=label, variable=var, font=f(13), progress_color=PURPLE, text_color=TEXT, command=on)
        sw.pack(anchor="w", padx=14, pady=14)
        sw._text_label.configure(wraplength=530, justify="left")

    def slider(self, key, label, lo, hi, steps, fmt):
        card = self.card()
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(10, 0))
        ctk.CTkLabel(row, text=label, font=f(12), text_color=SUB).pack(side="left")
        val = ctk.CTkLabel(row, text=fmt.format(self.cfg[key]), font=f(12, True), text_color=TEXT)
        val.pack(side="right")

        def on(v):
            v = round(v, 2)
            val.configure(text=fmt.format(v))
            self.cfg[key] = v  # 엔진이 바로 읽음 (재시작 불필요)
            save_config(self.cfg)
            if key == "sensitivity":
                self._place_marker()
        s = ctk.CTkSlider(card, from_=lo, to=hi, number_of_steps=steps, command=on, progress_color=PURPLE,
                          button_color=PURPLE, button_hover_color=PURPLE_H, fg_color=FIELD)
        s.set(self.cfg[key])
        s.pack(fill="x", padx=14, pady=(4, 12))

    # -- 마이크 레벨 미터 -------------------------------------------------
    def _build_meter(self):
        card = self.card()
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(row, text=T("level"), font=f(12), text_color=SUB).pack(side="left")
        self.lvl_txt = ctk.CTkLabel(row, text="", font=f(12, True), text_color=SUB)
        self.lvl_txt.pack(side="right")
        self.mbar = ctk.CTkProgressBar(card, height=14, corner_radius=7, progress_color=PURPLE, fg_color=FIELD)
        self.mbar.set(0)
        self.mbar.pack(fill="x", padx=14, pady=(0, 4))
        self.marker = ctk.CTkFrame(card, width=3, height=22, corner_radius=1, fg_color=PINK)
        ctk.CTkLabel(card, text=T("level_hint"), font=f(11), text_color=SUB, anchor="w").pack(fill="x", padx=14, pady=(0, 10))
        self._place_marker()

    def _src(self):
        e = self.app.engine
        return e if (e is not None and e.ready) else self.monitor

    def _place_marker(self):
        src = self._src()
        thr = src.nf.threshold(self.cfg["sensitivity"]) if src is not None else threshold_for(self.cfg["sensitivity"])
        self.marker.place(in_=self.mbar, relx=meter_value(thr), rely=0.5, anchor="center")

    def _stop_monitor(self):
        if self.monitor is not None:
            self.monitor.stop()
            self.monitor = None

    def _tick_meter(self):
        if not self.winfo_exists():
            return
        if self._test_result is not None:
            ok, msg = self._test_result
            self._test_result = None
            self.test_lbl.configure(text=f"{T('tr_test_ok') if ok else T('tr_test_fail')}: {msg}",
                                    text_color=GREEN if ok else RED)
        self._n = getattr(self, "_n", 0) + 1
        if self._n % 12 == 0 and hasattr(self, "mt_lbl"):
            self._refresh_mt()
        e = self.app.engine
        if e is not None and e.ready:  # 인식 중이면 엔진의 음량을 그대로 사용
            self._stop_monitor()
            src, lvl = e, e.level
        else:
            if self.monitor is None:
                self.monitor = MicMonitor(self.cfg["mic"])
                self.monitor.start()
            src, lvl = self.monitor, self.monitor.level
        thr = src.nf.threshold(self.cfg["sensitivity"])  # 주변 소음에 따라 자동으로 오르는 실제 기준
        on = lvl > thr
        db = 20 * math.log10(max(lvl, 1e-5))
        self.mbar.set(meter_value(lvl))
        self.mbar.configure(progress_color=GREEN if on else PURPLE)
        self.marker.place(in_=self.mbar, relx=meter_value(thr), rely=0.5, anchor="center")
        self.lvl_txt.configure(text=f"{db:.0f} dB · " + (T("lvl_on") if on else T("lvl_off")),
                               text_color=GREEN if on else SUB)
        self.after(60, self._tick_meter)

    def destroy(self):
        self._stop_monitor()
        super().destroy()

    # -- 번역 서비스 / API 키 ---------------------------------------------
    def _provider(self):
        return self.cfg["translator"]

    def _refresh_key_ui(self):
        p = self._provider()
        needs = p not in ("local", "mymemory")
        saved = bool(self.cfg["api_keys"].get(p))
        self.key_entry.configure(state="normal")
        self.key_entry.delete(0, "end")
        self.key_entry.configure(placeholder_text=T("tr_key_saved") if saved else T("tr_key_hint"),
                                 state="normal" if needs else "disabled")
        self.get_key_btn.configure(state="normal" if needs else "disabled")
        self.rm_key_btn.configure(state="normal" if needs and saved else "disabled")
        self.test_lbl.configure(text="")

    def _save_key(self, _=None):
        text = self.key_entry.get().strip()
        if not text or self._provider() in ("local", "mymemory"):
            return
        keys = dict(self.cfg["api_keys"])
        keys[self._provider()] = secret.encrypt(text)
        self.app.set_cfg("api_keys", keys)
        self._refresh_key_ui()

    def _remove_key(self):
        keys = dict(self.cfg["api_keys"])
        keys.pop(self._provider(), None)
        self.app.set_cfg("api_keys", keys)
        self._refresh_key_ui()

    def _open_key_page(self):
        url = KEY_URLS.get(self._provider())
        if url:
            webbrowser.open(url)

    def _test_translation(self):
        self._save_key()
        if not self.cfg["consent_translate"]:
            if not ask(self, T("priv_title"), T("ask_translate"), T("allow"), T("deny")):
                return
            self.cfg["consent_translate"] = True
            save_config(self.cfg)
            self.app.refresh_target()
        self.test_lbl.configure(text="…", text_color=SUB)

        def run():
            try:
                self._test_result = (True, translate_text(self.cfg, "안녕하세요", "ko", "en"))
            except TranslateError as e:
                self._test_result = (False, str(e))
            except Exception as e:
                self._test_result = (False, type(e).__name__)
        threading.Thread(target=run, daemon=True).start()

    # -- 오프라인 번역 모델 카드 ------------------------------------------
    def _build_mt_card(self):
        card = self.card()
        ctk.CTkLabel(card, text=T("mt_card_title"), font=f(12), text_color=SUB).pack(anchor="w", padx=14, pady=(10, 2))
        self.mt_lbl = ctk.CTkLabel(card, text="", font=f(13), text_color=TEXT, anchor="w", justify="left", wraplength=530)
        self.mt_lbl.pack(fill="x", padx=14)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(8, 12))
        self.mt_get = pill_button(row, "⬇ " + T("mt_get"), lambda: self.app.ensure_mt(force=True), height=32)
        self.mt_get.pack(side="left", padx=(0, 8))
        self.mt_rm = soft_button(row, T("mt_remove"), self._mt_remove, height=32)
        self.mt_rm.pack(side="left")
        self._refresh_mt()

    def _refresh_mt(self):
        ok = mt_cached()
        self.mt_lbl.configure(text=T("mt_status_ok") if ok else T("mt_status_none"), text_color=GREEN if ok else SUB)
        self.mt_get.configure(state="normal" if not ok and self.app._mt_pct is None else "disabled")
        self.mt_rm.configure(state="normal" if ok else "disabled")

    def _mt_remove(self):
        release_mt()
        shutil.rmtree(MT_DIR, ignore_errors=True)
        self._refresh_mt()

    def _save_vocab(self, _=None):
        self.cfg["vocab"] = self.vocab.get().strip()[:300]
        save_config(self.cfg)

    def _save_port(self, _=None):
        try:
            p = int(self.port.get())
            if 1 <= p <= 65535 and p != self.cfg["osc_port"]:
                self.app.set_cfg("osc_port", p)
        except ValueError:
            self.port.delete(0, "end")
            self.port.insert(0, str(self.cfg["osc_port"]))

    def _delete_data(self):
        if ask(self, T("delete_data"), T("delete_body"), T("delete_yes"), T("dl_no")):
            self.app.wipe_data_and_exit()


# ====================================================================== 정보 창
class InfoWindow(ctk.CTkToplevel):
    def __init__(self, app, tab):
        super().__init__(app, fg_color=BG)
        self.app = app
        self.title(f"{T('title')} · {T('about')}")
        self.geometry("860x560")
        self.minsize(760, 480)
        self.attributes("-topmost", app.cfg["always_on_top"])
        self.after(150, self.lift)
        tabs = ctk.CTkTabview(self, corner_radius=22, fg_color=CARD, segmented_button_selected_color=PURPLE,
                              segmented_button_selected_hover_color=PURPLE_H, segmented_button_unselected_color=FIELD,
                              segmented_button_unselected_hover_color=FIELD_H, text_color=TEXT)
        tabs.pack(fill="both", expand=True, padx=14, pady=14)
        names = {k: T(k) for k in ("tab_new", "tab_fb", "tab_support", "tab_privacy")}
        for n in names.values():
            tabs.add(n)
        self._text(tabs.tab(names["tab_new"]), f"{T('version')} {APP_VERSION}\n\n" + self._read("CHANGELOG.md"))
        self._feedback(tabs.tab(names["tab_fb"]))
        self._support(tabs.tab(names["tab_support"]))
        self._text(tabs.tab(names["tab_privacy"]), self._read(f"PRIVACY.{i18n._lang}.md", "PRIVACY.en.md"))
        tabs.set(names[tab])
        app.cfg["last_seen_version"] = APP_VERSION
        save_config(app.cfg)

    @staticmethod
    def _read(name, fallback=None):
        for n in (name, fallback):
            try:
                if n:
                    return resource_path(n).read_text(encoding="utf-8")
            except Exception:
                pass
        return T("no_changelog")

    def _text(self, tab, text):
        box = ctk.CTkTextbox(tab, fg_color="transparent", font=f(12), text_color=TEXT, wrap="word")
        box.pack(fill="both", expand=True)
        box.insert("1.0", text)
        box.configure(state="disabled")

    def _feedback(self, tab):
        ctk.CTkLabel(tab, text=T("fb_hint"), font=f(14, True), text_color=TEXT, anchor="w").pack(fill="x", pady=(4, 6))
        self.fb = ctk.CTkTextbox(tab, height=200, corner_radius=16, font=f(12), fg_color=FIELD, text_color=TEXT, wrap="word")
        self.fb.pack(fill="x")
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", pady=10)
        if links.GITHUB_REPO:
            pill_button(row, T("fb_github"), self._send_github).pack(side="left", padx=(0, 8))
        elif links.FEEDBACK_FORM_URL:
            pill_button(row, T("fb_form"), lambda: webbrowser.open(links.FEEDBACK_FORM_URL)).pack(side="left", padx=(0, 8))
        else:
            ctk.CTkLabel(row, text=T("fb_none"), font=f(12), text_color=SUB).pack(side="left", padx=(0, 8))
        soft_button(row, T("fb_log"), lambda: (DATA_DIR.mkdir(parents=True, exist_ok=True), os.startfile(DATA_DIR)),
                    height=36).pack(side="left")

    def _send_github(self):
        msg = self.fb.get("1.0", "end").strip()
        env = f"\n\n---\nv{APP_VERSION} · Windows {platform.version()} · model {self.app.cfg['model']}"
        q = urllib.parse.urlencode({"title": msg.split("\n")[0][:60] or "Feedback", "body": (msg + env)[:1500]})
        webbrowser.open(f"https://github.com/{links.GITHUB_REPO}/issues/new?{q}")

    def _support(self, tab):
        ctk.CTkLabel(tab, text=T("support_text"), font=f(13), text_color=TEXT, wraplength=620,
                     justify="left", anchor="w").pack(fill="x", pady=(8, 14))
        shown = [(n, u) for n, u in links.DONATE_LINKS if u]
        if not shown:
            ctk.CTkLabel(tab, text=T("support_none"), font=f(12), text_color=SUB).pack(anchor="w")
        for name, url in shown:
            pill_button(tab, "♥  " + name, lambda u=url: webbrowser.open(u), PINK, PINK_H, height=42).pack(fill="x", pady=4)
