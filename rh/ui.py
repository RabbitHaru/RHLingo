"""화면: 메인(인식) 창 / 설정 창 / 정보 창 / 개인정보 동의 창 / 허락 대화상자."""
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

from . import i18n, links
from .config import APP_NAME, APP_VERSION, DATA_DIR, load_config, log_error, save_config
from .engine import (MODEL_SIZES_MB, Engine, MicMonitor, Output, format_chatbox, get_model, list_mics,
                     meter_value, model_cached, model_name, preview_default, release_model, threshold_for,
                     translate_text)
from .i18n import LANGS, NATIVE, T, lang_label

FONT = "Malgun Gothic"
PURPLE, PURPLE_H = ("#7C6BF2", "#8B7CFF"), ("#6A59E0", "#7A69F5")
PINK, PINK_H = ("#F25577", "#FF6B8A"), ("#E04466", "#F25577")
BG, CARD, FIELD = ("#F4F2FF", "#1A1A2A"), ("#FFFFFF", "#232336"), ("#ECE9FF", "#2E2E48")
FIELD_H = ("#DDD8FF", "#3A3A5C")
TEXT, SUB = ("#2A2650", "#EDEAFF"), ("#7B7799", "#9A98B8")
GREEN, ORANGE, RED = ("#1FA971", "#6EE7A8"), ("#D98A1F", "#FFC46B"), ("#D93A5C", "#FF8AA0")
MAX_BUBBLES = 40
RESTART_KEYS = {"mic", "model", "device_type", "vrc_mute_sync", "osc_ip", "osc_port", "osc_in_port"}


def resource_path(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / name


def f(size=13, bold=False):
    return ctk.CTkFont(family=FONT, size=size, weight="bold" if bold else "normal")


def pill_button(parent, text, cmd, color=PURPLE, hover=PURPLE_H, text_color="#FFFFFF", height=36, **kw):
    return ctk.CTkButton(parent, text=text, command=cmd, height=height, corner_radius=height // 2,
                         font=f(13, True), fg_color=color, hover_color=hover, text_color=text_color, **kw)


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
        ctk.CTkLabel(self, text=title, font=f(16, True), text_color=TEXT).pack(anchor="w", padx=24, pady=(22, 8))
        ctk.CTkLabel(self, text=body, font=f(13), text_color=TEXT, wraplength=360, justify="left").pack(
            anchor="w", padx=24)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=22)
        pill_button(row, yes, lambda: self._done(True), width=150).pack(side="right")
        pill_button(row, no, lambda: self._done(False), FIELD, FIELD_H, TEXT, width=110).pack(side="right", padx=8)
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
        ctk.CTkLabel(self, text="🔒 " + T("priv_title"), font=f(17, True), text_color=TEXT).pack(
            anchor="w", padx=24, pady=(22, 10))
        for key in ("priv_audio", "priv_models", "priv_none"):
            ctk.CTkLabel(self, text=T(key), font=f(13), text_color=TEXT, wraplength=380, justify="left").pack(
                anchor="w", padx=24, pady=3)
        card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=18)
        card.pack(fill="x", padx=20, pady=14)
        self.v_tr, self.v_up = ctk.BooleanVar(value=False), ctk.BooleanVar(value=False)
        ctk.CTkSwitch(card, text=T("priv_translate"), variable=self.v_tr, font=f(12), progress_color=PURPLE,
                      text_color=TEXT).pack(anchor="w", padx=16, pady=(14, 8))
        ctk.CTkSwitch(card, text=T("priv_update"), variable=self.v_up, font=f(12), progress_color=PURPLE,
                      text_color=TEXT).pack(anchor="w", padx=16, pady=(0, 14))
        for sw in card.winfo_children():  # 긴 문구 줄바꿈
            sw._text_label.configure(wraplength=330, justify="left")
        ctk.CTkLabel(self, text=T("priv_later"), font=f(11), text_color=SUB).pack(anchor="w", padx=24)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=18)
        pill_button(row, T("priv_ok"), self._ok, width=120).pack(side="right")
        pill_button(row, T("policy"), lambda: app.open_info("tab_privacy"), FIELD, FIELD_H, TEXT, width=150).pack(side="right", padx=8)
        self.protocol("WM_DELETE_WINDOW", self._ok)

    def _ok(self):
        self.app.cfg.update(consent_done=True, consent_translate=self.v_tr.get(), consent_update=self.v_up.get())
        save_config(self.app.cfg)
        self.grab_release()
        self.destroy()


# ====================================================================== 메인 창
class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.cfg = load_config()
        i18n.set_lang(self.cfg["ui_lang"])
        ctk.set_appearance_mode(self.cfg["theme"])
        self.geometry("460x740")
        self.minsize(420, 620)
        self.attributes("-topmost", self.cfg["always_on_top"])
        self.events = queue.Queue()
        self.output = Output(self.cfg)
        self.engine = None
        self.restart_pending = False
        self.settings = self.info = None
        self.bubbles = []
        self._shown_state = None
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

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(18, 0))
        ctk.CTkLabel(top, text="🐰 " + T("title"), font=f(20, True), text_color=TEXT).pack(side="left")
        for txt, cmd in (("⚙", self.open_settings), ("♥", lambda: self.open_info("tab_new"))):
            ctk.CTkButton(top, text=txt, width=36, height=36, corner_radius=18, font=f(16),
                          fg_color=CARD, hover_color=FIELD, text_color=TEXT, command=cmd).pack(side="right", padx=(6, 0))

        ctk.CTkLabel(self, text=T("tagline"), font=f(12), text_color=SUB, anchor="w").pack(fill="x", padx=24)
        self.status = ctk.CTkLabel(self, text="", font=f(12), text_color=SUB, anchor="w")
        self.status.pack(fill="x", padx=24, pady=(2, 0))
        self.update_lbl = ctk.CTkLabel(self, text="", font=f(12, True), text_color=PURPLE, cursor="hand2", anchor="w")
        self.update_lbl.pack(fill="x", padx=24)
        self.update_lbl.bind("<Button-1>", lambda e: self.update_info and webbrowser.open(self.update_info[1]))
        self._show_update()

        card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=24)
        card.pack(fill="x", padx=20, pady=(10, 0))
        ctk.CTkLabel(card, text=T("translate_to"), font=f(12), text_color=SUB).pack(anchor="w", padx=18, pady=(12, 4))
        self.target_btn = ctk.CTkSegmentedButton(
            card, values=[T("stt_only")] + [NATIVE[c] for c in LANGS], command=self._on_target, height=36,
            corner_radius=18, font=f(13, True), selected_color=PURPLE, selected_hover_color=PURPLE_H,
            unselected_color=FIELD, unselected_hover_color=FIELD)
        self.target_btn.pack(fill="x", padx=14, pady=(0, 10))
        self.refresh_target()
        meter_row = ctk.CTkFrame(card, fg_color="transparent")
        meter_row.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkLabel(meter_row, text="🎤", font=f(14)).pack(side="left")
        self.meter = ctk.CTkProgressBar(meter_row, height=10, corner_radius=5, progress_color=PURPLE, fg_color=FIELD)
        self.meter.set(0)
        self.meter.pack(side="left", fill="x", expand=True, padx=10)
        self.mmarker = ctk.CTkFrame(meter_row, width=3, height=18, corner_radius=1, fg_color=PINK)
        self.pause_btn = ctk.CTkButton(meter_row, text=T("pause"), width=84, height=28, corner_radius=14, font=f(12),
                                       fg_color=FIELD, hover_color=FIELD_H, text_color=TEXT, command=self.toggle_pause)
        self.pause_btn.pack(side="right")

        self.btn = ctk.CTkButton(self, text=T("start"), height=48, corner_radius=24, font=f(16, True),
                                 fg_color=PURPLE, hover_color=PURPLE_H, command=self.toggle)
        self.btn.pack(fill="x", padx=20, pady=12)

        # 아래쪽 입력줄 + 실시간 미리보기 (먼저 pack 해야 history 가 남는 공간을 채움)
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=20, pady=(4, 16))
        self.entry = ctk.CTkEntry(bar, placeholder_text=T("type_hint"), height=40, corner_radius=20, font=f(13),
                                  fg_color=CARD, border_width=0)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.send_manual())
        pill_button(bar, T("send"), self.send_manual, height=40, width=64).pack(side="left", padx=(8, 0))
        self.partial_lbl = ctk.CTkLabel(self, text="", font=f(12), text_color=SUB, wraplength=400, justify="left",
                                        anchor="w")
        self.partial_lbl.pack(side="bottom", fill="x", padx=26, pady=(0, 2))

        self.hist = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.hist.pack(fill="both", expand=True, padx=10)
        self.empty = ctk.CTkLabel(self.hist, text=T("empty"), font=f(13), text_color=SUB, justify="center")
        self.empty.pack(pady=40)

    # -- 번역 동의 / 대상 언어 --------------------------------------------
    def eff_target(self):
        return self.cfg["target"] if self.cfg["consent_translate"] else "off"

    def refresh_target(self):
        t = self.eff_target()
        self.target_btn.set(T("stt_only") if t == "off" else NATIVE[t])

    def _on_target(self, label):
        code = next((c for c in LANGS if NATIVE[c] == label), "off")
        if code != "off" and not self.cfg["consent_translate"]:
            if ask(self, T("priv_title"), T("ask_translate"), T("allow"), T("deny")):
                self.cfg["consent_translate"] = True
            else:
                self.refresh_target()
                return
        self.set_cfg("target", code)

    # -- 말풍선 ---------------------------------------------------------
    def add_bubble(self, title, body="", kind="result"):
        if self.empty is not None and self.empty.winfo_exists():
            self.empty.destroy()
            self.empty = None
        color = {"result": CARD, "sys": FIELD, "err": ("#FFE3EA", "#4A2434")}[kind]
        b = ctk.CTkFrame(self.hist, fg_color=color, corner_radius=18)
        b.pack(fill="x", padx=6, pady=4)
        tcolor = RED if kind == "err" else (SUB if kind == "sys" else TEXT)
        ctk.CTkLabel(b, text=title, font=f(14 if kind == "result" else 12, kind == "result"), text_color=tcolor,
                     wraplength=340, justify="left", anchor="w").pack(fill="x", padx=14, pady=(10, 2 if body else 10))
        if body:
            ctk.CTkLabel(b, text=body, font=f(11), text_color=SUB, wraplength=340, justify="left",
                         anchor="w").pack(fill="x", padx=14, pady=(0, 10))
        self.bubbles.append(b)
        while len(self.bubbles) > MAX_BUBBLES:
            self.bubbles.pop(0).destroy()
        self.after(50, lambda: self.hist._parent_canvas.yview_moveto(1.0))

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
        key = (state, e.dl_pct if e is not None and state == "loading" else None)
        if key != self._shown_state:
            self._apply_state(*key)
        src = e if (e is not None and e.ready) else None
        lvl = e.level if src is not None and state == "listening" else 0.0
        sens = self.cfg["sensitivity"]
        thr = src.nf.threshold(sens) if src is not None else threshold_for(sens)
        self.meter.set(meter_value(lvl))
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

    def _apply_state(self, state, pct=None):
        self._shown_state = (state, pct)
        loading = f"{T('dl_progress')} {pct}%" if pct is not None else T("st_loading")
        text, color = {
            "idle": (T("st_idle"), SUB), "loading": (loading, ORANGE),
            "listening": (T("st_listening"), GREEN), "paused": (T("st_paused"), ORANGE),
            "muted": (T("st_muted"), ORANGE), "stopping": (T("stopping"), SUB)}[state]
        self.status.configure(text="● " + text, text_color=color)
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
        self.engine = Engine(self.cfg, self.output, self.events)
        self.engine.start()

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
                out = text if tgt == "off" else translate_text(text, "auto", tgt)
                self.output.send(format_chatbox(out, text, self.cfg["show_original"] and tgt != "off"))
                self.events.put(("result", "", tgt, text, out))
            except Exception as e:
                self.events.put(("error", f"{T('tr_failed')}: {e}"))
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
    def open_settings(self):
        if self.settings is not None and self.settings.winfo_exists():
            self.settings.focus()
            return
        self.settings = SettingsWindow(self)

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
        """설정·로그·모델 전부 삭제하고 종료."""
        if self.engine is not None:
            self.engine.stop()
        release_model()
        shutil.rmtree(DATA_DIR, ignore_errors=True)
        os._exit(0)

    def on_close(self):
        if self.engine is not None:
            self.engine.stop()
        self.destroy()


# ====================================================================== 설정 창
class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app, fg_color=BG)
        self.app, self.cfg = app, app.cfg
        self.title(T("settings"))
        self.geometry("440x720")
        self.minsize(400, 480)
        self.attributes("-topmost", self.cfg["always_on_top"])
        self.after(150, self.lift)
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=8)
        self.body = body

        self.section(T("sec_general"))
        self.option("ui_lang", T("ui_lang"), [(c, NATIVE[c]) for c in LANGS], ui=True)
        self.option("theme", T("theme"), [("system", T("theme_system")), ("light", T("theme_light")),
                                          ("dark", T("theme_dark"))], ui=True)
        self.switch("always_on_top", T("always_on_top"), ui=True)

        self.section(T("sec_audio"))
        self.mic_menu = self.option("mic", T("mic"), self._mic_items())
        pill_button(self.mic_menu.master, "⟳ " + T("refresh"), self._refresh_mics, FIELD, FIELD_H, TEXT,
                    height=28).pack(anchor="w", padx=14, pady=(0, 10))
        self.option("source", T("speech_lang"), [("auto", T("auto"))] + [(c, lang_label(c)) for c in LANGS])
        self.option("model", T("model"), [(m, T("m_" + m)) for m in
                                          ("auto", "tiny", "base", "small", "medium", "large-v3-turbo")])
        self.option("device_type", T("device"), [("auto", T("dev_auto")), ("cuda", T("dev_gpu")), ("cpu", T("dev_cpu"))])
        self._build_meter()
        self.slider("sensitivity", T("sensitivity"), 0, 100, 100, fmt="{:.0f}")
        self.slider("silence_sec", T("silence"), 0.2, 1.5, 26, fmt="{:.1f}s")
        self.option("noise_reduction", T("noise"), [("off", T("nr_off")), ("low", T("nr_low")), ("high", T("nr_high"))])
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
        ctk.CTkLabel(body, text=T("restart_note"), font=f(11), text_color=SUB, anchor="w").pack(fill="x", padx=14)

        self.section(T("sec_vrc"))
        self.switch("show_original", T("show_original"))
        self.switch("vrc_mute_sync", T("vrc_mute"))
        card = self.card()
        ctk.CTkLabel(card, text=T("osc_port"), font=f(12), text_color=SUB).pack(anchor="w", padx=14, pady=(10, 2))
        self.port = ctk.CTkEntry(card, width=100, height=34, corner_radius=17, font=f(13), fg_color=FIELD, border_width=0)
        self.port.insert(0, str(self.cfg["osc_port"]))
        self.port.pack(anchor="w", padx=14, pady=(0, 12))
        self.port.bind("<FocusOut>", self._save_port)
        self.port.bind("<Return>", self._save_port)

        self.section(T("sec_privacy"))
        self.switch("consent_translate", T("sw_translate"), cb=lambda v: self.app.refresh_target())
        self.switch("consent_update", T("sw_update"), cb=lambda v: v and self.app.check_update_if_allowed())
        pcard = self.card()
        pill_button(pcard, T("policy"), lambda: self.app.open_info("tab_privacy"), FIELD, FIELD_H, TEXT,
                    height=34).pack(fill="x", padx=14, pady=(12, 6))
        pill_button(pcard, T("delete_data"), self._delete_data, PINK, PINK_H, height=34).pack(fill="x", padx=14, pady=(0, 12))

        ctk.CTkLabel(body, text=f"{APP_NAME} v{APP_VERSION}", font=f(11), text_color=SUB).pack(pady=(14, 4))

    # -- 위젯 도우미 ------------------------------------------------------
    def section(self, text):
        ctk.CTkLabel(self.body, text=text, font=f(14, True), text_color=TEXT, anchor="w").pack(fill="x", padx=10, pady=(14, 4))

    def card(self):
        c = ctk.CTkFrame(self.body, fg_color=CARD, corner_radius=20)
        c.pack(fill="x", padx=4, pady=4)
        return c

    def _change(self, key, value, ui=False):
        if key == "mic":
            self._stop_monitor()  # 다음 틱에 새 마이크로 다시 열림
        (self.app.apply_ui_change if ui else self.app.set_cfg)(key, value)

    def option(self, key, label, items, ui=False):
        card = self.card()
        ctk.CTkLabel(card, text=label, font=f(12), text_color=SUB).pack(anchor="w", padx=14, pady=(10, 2))
        by_label = {l: c for c, l in items}
        cur = next((l for c, l in items if c == self.cfg[key]), items[0][1])
        menu = ctk.CTkOptionMenu(card, values=[l for _, l in items], corner_radius=16, height=34, font=f(13),
                                 dropdown_font=f(13), fg_color=FIELD, text_color=TEXT, button_color=PURPLE,
                                 button_hover_color=PURPLE_H, dynamic_resizing=False,
                                 command=lambda l: self._change(key, by_label[l], ui))
        menu.set(cur)
        menu.pack(fill="x", padx=14, pady=(0, 12 if key != "mic" else 8))
        menu._items = by_label
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
        sw.pack(anchor="w", padx=14, pady=12)
        sw._text_label.configure(wraplength=330, justify="left")

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
        self.monitor = None
        self._place_marker()
        self.after(80, self._tick_meter)

    def _src(self):
        e = self.app.engine
        return e if (e is not None and e.ready) else self.monitor

    def _place_marker(self):
        src = self._src()
        thr = src.nf.threshold(self.cfg["sensitivity"]) if src is not None else threshold_for(self.cfg["sensitivity"])
        self.marker.place(in_=self.mbar, relx=meter_value(thr), rely=0.5, anchor="center")

    def _stop_monitor(self):
        if getattr(self, "monitor", None) is not None:
            self.monitor.stop()
            self.monitor = None

    def _tick_meter(self):
        if not self.winfo_exists():
            return
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
        self.geometry("460x620")
        self.minsize(400, 480)
        self.attributes("-topmost", app.cfg["always_on_top"])
        self.after(150, self.lift)
        tabs = ctk.CTkTabview(self, corner_radius=20, fg_color=CARD, segmented_button_selected_color=PURPLE,
                              segmented_button_selected_hover_color=PURPLE_H, segmented_button_unselected_color=FIELD,
                              text_color=TEXT)
        tabs.pack(fill="both", expand=True, padx=14, pady=14)
        names = {k: T(k) for k in ("tab_new", "tab_fb", "tab_support", "tab_privacy")}
        for n in names.values():
            tabs.add(n)
        self._text(tabs.tab(names["tab_new"]), f"{T('version')} {APP_VERSION}\n\n" + self._read("CHANGELOG.md"))
        self._feedback(tabs.tab(names["tab_fb"]))
        self._support(tabs.tab(names["tab_support"]))
        self._text(tabs.tab(names["tab_privacy"]), self._read(f"PRIVACY.{self._lang()}.md", "PRIVACY.en.md"))
        tabs.set(names[tab])
        app.cfg["last_seen_version"] = APP_VERSION
        save_config(app.cfg)

    @staticmethod
    def _lang():
        return i18n._lang

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
        ctk.CTkLabel(tab, text=T("fb_hint"), font=f(13, True), text_color=TEXT, anchor="w").pack(fill="x", pady=(4, 6))
        self.fb = ctk.CTkTextbox(tab, height=170, corner_radius=16, font=f(12), fg_color=FIELD, text_color=TEXT, wrap="word")
        self.fb.pack(fill="x")
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", pady=10)
        if links.GITHUB_REPO:
            pill_button(row, T("fb_github"), self._send_github).pack(side="left", padx=(0, 8))
        elif links.FEEDBACK_FORM_URL:
            pill_button(row, T("fb_form"), lambda: webbrowser.open(links.FEEDBACK_FORM_URL)).pack(side="left", padx=(0, 8))
        else:
            ctk.CTkLabel(row, text=T("fb_none"), font=f(12), text_color=SUB).pack(side="left", padx=(0, 8))
        pill_button(row, T("fb_log"), lambda: (DATA_DIR.mkdir(parents=True, exist_ok=True), os.startfile(DATA_DIR)),
                    FIELD, FIELD_H, TEXT).pack(side="left")

    def _send_github(self):
        msg = self.fb.get("1.0", "end").strip()
        env = f"\n\n---\nv{APP_VERSION} · Windows {platform.version()} · model {self.app.cfg['model']}"
        q = urllib.parse.urlencode({"title": msg.split("\n")[0][:60] or "Feedback", "body": (msg + env)[:1500]})
        webbrowser.open(f"https://github.com/{links.GITHUB_REPO}/issues/new?{q}")

    def _support(self, tab):
        ctk.CTkLabel(tab, text=T("support_text"), font=f(13), text_color=TEXT, wraplength=340,
                     justify="left", anchor="w").pack(fill="x", pady=(8, 14))
        shown = [(n, u) for n, u in links.DONATE_LINKS if u]
        if not shown:
            ctk.CTkLabel(tab, text=T("support_none"), font=f(12), text_color=SUB).pack(anchor="w")
        for name, url in shown:
            pill_button(tab, "♥  " + name, lambda u=url: webbrowser.open(u), PINK, PINK_H, height=42).pack(fill="x", pady=4)
