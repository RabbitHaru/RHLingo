"""화면: 메인(가로형) / 설정 / 정보 / 개인정보 동의 / 허락 대화상자."""
import json
import math
import os
import platform
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request
import warnings
import webbrowser
from pathlib import Path

import customtkinter as ctk

from . import hotkey, i18n, links, secret, updater
from .config import APP_NAME, APP_VERSION, DATA_DIR, load_config, log_error, save_config
from .engine import (MODEL_SIZES_MB, MT_MODELS, Engine, MicMonitor, Output, TranslateError, calibrate_sensitivity,
                     delete_stt, download_mt, download_stt,
                     format_chatbox, get_model, list_mics, meter_value, model_cached, model_name, mt_cached,
                     mt_dir, mt_tier, preview_default, release_model, release_mt, threshold_for, translate_text,
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
IDLE_RELEASE_MS = 5 * 60 * 1000  # 멈춘 채 이만큼 지나면 모델을 메모리에서 내림
RESTART_KEYS = {"mic", "model", "device_type", "vrc_mute_sync", "osc_ip", "osc_port", "osc_in_port"}
KEY_URLS = {"deepl": "https://www.deepl.com/pro-api", "gemini": "https://aistudio.google.com/apikey"}


warnings.filterwarnings("ignore", message=".*not CTkImage.*")
_version_key = updater.version_key


def resource_path(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / name if (base / name).exists() else base / "installer" / name


def set_icon(win):
    """창/작업표시줄 아이콘. customtkinter 가 200ms 뒤 기본 아이콘으로 덮어써서 그 뒤에 다시 지정."""
    ico = resource_path("RHLingo.ico")
    if not ico.exists():
        return

    def apply():
        try:
            win.iconbitmap(str(ico))
        except Exception:
            pass
    win.after(300, apply)


def f(size=13, bold=False):
    return ctk.CTkFont(family=FONT, size=size, weight="bold" if bold else "normal")


class ScrollFrame(ctk.CTkScrollableFrame):
    """CTkScrollableFrame 개선판: 슬라이더 위에서도 휠로 스크롤되고, 휠 한 칸당 이동량이 기본(20px)의 2배."""

    def _inside(self, widget):
        while widget is not None:
            if widget is self._parent_canvas:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _check_if_valid_scroll(self, widget):
        if isinstance(widget, ctk.CTkSlider):  # 기본 구현은 슬라이더 위에서 스크롤을 막음
            return self._inside(widget)
        return super()._check_if_valid_scroll(widget)

    def _mouse_wheel_all(self, event):
        if sys.platform.startswith("win") and not self._shift_pressed:
            if self._check_if_valid_scroll(event.widget) and self._parent_canvas.yview() != (0.0, 1.0):
                self._parent_canvas.yview("scroll", -int(event.delta / 3), "units")
            return
        super()._mouse_wheel_all(event)


def pill_button(parent, text, cmd, color=PURPLE, hover=PURPLE_H, text_color="#FFFFFF", height=36, **kw):
    return ctk.CTkButton(parent, text=text, command=cmd, height=height, corner_radius=height // 2,
                         font=f(13, True), fg_color=color, hover_color=hover, text_color=text_color, **kw)


def soft_button(parent, text, cmd, height=34, **kw):
    return pill_button(parent, text, cmd, FIELD, FIELD_H, TEXT, height=height, **kw)


# ====================================================================== 대화상자
class _Modal(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent, fg_color=BG)
        set_icon(self)
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
        set_icon(self)
        self.cfg = load_config()
        i18n.set_lang(self.cfg["ui_lang"])
        ctk.set_appearance_mode(self.cfg["theme"])
        self.geometry("1060x640")
        self.minsize(980, 580)
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
        self._stt_pct = None  # 음성 인식 모델 다운로드 진행률
        self._stt_dl = self._mt_dl = None  # 지금 받는 중인 모델 이름
        self.update_info = None
        self.hotkey = hotkey.Hotkey(lambda: self.events.put(("hotkey",)))
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
            first_run = not self.cfg["last_seen_version"]
            self.cfg["last_seen_version"] = APP_VERSION
            save_config(self.cfg)
            if not first_run:  # 새 버전으로 바뀐 뒤 처음 켰을 때: 창을 띄우지 않고 대화창에 한 줄만
                self.add_bubble(T("whats_new").format(v=APP_VERSION), kind="sys")
        self.check_update_if_allowed()
        self.apply_hotkey()
        self._preload()
        self._schedule_idle_release()  # 시작 안 하고 두면 5분 뒤 미리 올려 둔 모델을 내림

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
        self.title(T("title"))
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # ── 왼쪽: 컨트롤 패널 ──
        side = ctk.CTkFrame(self, fg_color=CARD, corner_radius=26, width=380)
        side.grid(row=0, column=0, sticky="ns", padx=(16, 8), pady=16)
        side.pack_propagate(False)

        # 아래쪽부터 쌓는 것들 (pack side=bottom 은 먼저 넣은 게 가장 아래)
        bottom = ctk.CTkFrame(side, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=20, pady=(0, 18))
        for i, (label, cmd) in enumerate((("⚙  " + T("settings"), self.open_settings),
                                          ("♥  " + T("about"), lambda: self.open_info("tab_new")))):
            soft_button(bottom, label, cmd).pack(side="left", expand=True, fill="x", padx=(0 if i == 0 else 4, 0 if i == 1 else 4))

        mic = ctk.CTkFrame(side, fg_color=FIELD, corner_radius=18)
        mic.pack(side="bottom", fill="x", padx=22, pady=(0, 12))
        head = ctk.CTkFrame(mic, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(10, 4))
        ctk.CTkLabel(head, text="🎤  " + T("level"), font=f(12), text_color=SUB).pack(side="left")
        self.db_lbl = ctk.CTkLabel(head, text="", font=f(12, True), text_color=SUB)
        self.db_lbl.pack(side="right")
        mrow = ctk.CTkFrame(mic, fg_color="transparent")
        mrow.pack(fill="x", padx=16, pady=(0, 12))
        self.pause_btn = ctk.CTkButton(mrow, text=T("pause"), width=84, height=28, corner_radius=14, font=f(12, True),
                                       fg_color=CARD, hover_color=FIELD_H, text_color=TEXT, command=self.toggle_pause)
        self.pause_btn.pack(side="right", padx=(10, 0))
        self.meter = ctk.CTkProgressBar(mrow, height=12, corner_radius=6, progress_color=PURPLE, fg_color=CARD)
        self.meter.set(0)
        self.meter.pack(side="left", fill="x", expand=True)
        self.mmarker = ctk.CTkFrame(mrow, width=3, height=20, corner_radius=1, fg_color=PINK)

        # 위쪽부터: 브랜드 → 언어 카드 → 시작 → 상태
        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.pack(fill="x", padx=24, pady=(22, 0))
        try:
            self._logo_s = tk.PhotoImage(file=str(resource_path("RHLingo_logo_s.png")))
            ctk.CTkLabel(brand, image=self._logo_s, text="").pack(side="left", padx=(0, 10))
        except Exception:
            pass
        ctk.CTkLabel(brand, text=T("title"), font=f(24, True), text_color=TEXT, anchor="w").pack(side="left")
        ctk.CTkLabel(brand, text=f"v{APP_VERSION}", font=f(11, True), text_color=SUB, fg_color=FIELD, corner_radius=10,
                     width=10, height=22).pack(side="right", pady=(8, 0))
        ctk.CTkLabel(side, text=T("tagline"), font=f(11), text_color=SUB, anchor="w").pack(fill="x", padx=26, pady=(2, 0))
        self.update_lbl = ctk.CTkLabel(side, text="", font=f(11, True), text_color=PURPLE, cursor="hand2", anchor="w")
        self.update_lbl.pack(fill="x", padx=26)
        self.update_lbl.bind("<Button-1>", lambda e: self.start_update())
        self._show_update()

        langs = ctk.CTkFrame(side, fg_color=FIELD, corner_radius=20)
        langs.pack(fill="x", padx=22, pady=(14, 0))
        ctk.CTkLabel(langs, text=T("speech_lang"), font=f(12), text_color=SUB, anchor="w").pack(fill="x", padx=16, pady=(12, 4))
        items = [("auto", T("auto"))] + [(c, lang_label(c)) for c in LANGS]
        by_label = {l: c for c, l in items}
        self.src_menu = ctk.CTkOptionMenu(
            langs, values=[l for _, l in items], corner_radius=16, height=36, font=f(13), dropdown_font=f(13),
            fg_color=CARD, text_color=TEXT, button_color=PURPLE, button_hover_color=PURPLE_H,
            dynamic_resizing=False, command=lambda l: self.set_cfg("source", by_label[l]))
        self.src_menu.set(next(l for c, l in items if c == self.cfg["source"]))
        self.src_menu.pack(fill="x", padx=14)
        ctk.CTkLabel(langs, text="⇣  " + T("translate_to"), font=f(12), text_color=SUB, anchor="w").pack(fill="x", padx=16, pady=(10, 4))
        self.target_btn = ctk.CTkSegmentedButton(
            langs, values=[T("stt_only")] + [NATIVE[c] for c in LANGS], command=self._on_target, height=36,
            corner_radius=18, font=f(12, True), text_color=TEXT, selected_color=PURPLE, selected_hover_color=PURPLE_H,
            unselected_color=CARD, unselected_hover_color=FIELD_H)
        self.target_btn.pack(fill="x", padx=14, pady=(0, 14))
        self.refresh_target()

        self.btn = ctk.CTkButton(side, text=T("start"), height=54, corner_radius=27, font=f(17, True),
                                 fg_color=PURPLE, hover_color=PURPLE_H, command=self.toggle)
        self.btn.pack(fill="x", padx=22, pady=(14, 0))
        self.status = ctk.CTkLabel(side, text="", font=f(12, True), text_color=SUB, fg_color="transparent",
                                   height=28, anchor="center")
        self.status.pack(fill="x", padx=22, pady=(6, 0))

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

        self.hist = ScrollFrame(main, fg_color=CARD, corner_radius=26)
        self.hist.pack(fill="both", expand=True)
        self.hist.bind("<Configure>", self._on_hist_resize, add="+")  # 내장 스크롤 영역 갱신 이벤트를 덮어쓰면 안 됨
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
        self.after(50, self._scroll_end)

    def _scroll_end(self):
        """맨 아래로. 스크롤 영역 크기를 먼저 다시 계산해서, 지운 뒤에도 새 말풍선이 보이게."""
        cv = self.hist._parent_canvas
        cv.update_idletasks()
        cv.configure(scrollregion=cv.bbox("all"))
        cv.yview_moveto(1.0)

    def clear_history(self):
        for b in self.bubbles:
            b.destroy()
        self.bubbles = []
        self.partial_lbl.configure(text="")
        self.empty = ctk.CTkLabel(self.hist, text=T("empty"), font=f(14), text_color=SUB, justify="center")
        self.empty.pack(pady=80)
        self.hist.update_idletasks()
        self._scroll_end()
        self.hist._parent_canvas.yview_moveto(0.0)

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
            self._schedule_idle_release()
            if self.restart_pending:
                self.restart_pending = False
                self.start_engine()
        state = "idle"
        if e is not None:
            state = ("stopping" if not e.running else "loading" if not e.ready else
                     "paused" if e.paused else "muted" if e.vrc_muted else "listening")
        key = (state, e.dl_pct if e is not None and state == "loading" else None, self._mt_pct, self._stt_pct)
        if key != self._shown_state:
            self._apply_state(*key)
        src = e if (e is not None and e.ready) else None
        lvl = e.level if src is not None and state == "listening" else 0.0
        sens = self.cfg["sensitivity"]
        thr = src.nf.threshold(sens) if src is not None else threshold_for(sens)
        mv = meter_value(lvl)
        if abs(mv - getattr(self, '_mv', -1)) > 0.004:  # 값이 거의 같으면 다시 그리지 않음 (CPU 절약)
            self._mv = mv
            self.meter.set(mv)
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
        elif kind == "start":
            if self.engine is None:
                self.start_engine()
        elif kind == "info":
            self.add_bubble(T(ev[1]), kind="sys")
        elif kind == "error":
            self.add_bubble(f"{T('err')}: {ev[1]}", kind="err")
        elif kind == "update":
            self.update_info = ev[1]
            self._show_update()
            if ev[2]:
                ev[2](T("up_found").format(v=ev[1]["version"]))
        elif kind == "hotkey":
            e = self.engine
            if e is not None and e.running:
                self.toggle_pause()
                self._beep(e.paused)
        elif kind == "update_none":
            if ev[1]:
                ev[1](T("up_latest"))
        elif kind == "update_fail":
            if ev[1]:
                ev[1](T("up_fail"))
        elif kind == "update_prog":
            self.update_lbl.configure(text=f"⬇ {T('up_progress')} {ev[1]}%")
        elif kind == "update_run":
            self.update_lbl.configure(text="✨ " + T("up_installing"))
            self.update()
            try:
                updater.launch_installer(ev[1])
            except Exception:
                self.add_bubble(f"{T('err')}: {T('up_fail')}", kind="err")
                self._show_update()
                return
            self.on_close()
            os._exit(0)
        elif kind == "update_dl_fail":
            self.add_bubble(f"{T('err')}: {T(ev[1])}", kind="err")
            self._show_update()

    def _apply_state(self, state, pct=None, mtp=None, stp=None):
        self._shown_state = (state, pct, mtp, stp)
        loading = f"{T('dl_progress')} {pct}%" if pct is not None else T("st_loading")
        text, color = {
            "idle": (T("st_idle"), SUB), "loading": (loading, ORANGE),
            "listening": (T("st_listening"), GREEN), "paused": (T("st_paused"), ORANGE),
            "muted": (T("st_muted"), ORANGE), "stopping": (T("stopping"), SUB)}[state]
        if stp is not None:  # 음성 인식 모델 다운로드 중
            text, color = f"{T('dl_progress')} {stp}%", ORANGE
        elif mtp is not None:  # 오프라인 번역 모델 다운로드 중
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
    # -- 쓰지 않을 때 메모리 비우기 (멈춘 지 5분 지나면 모델을 내림, 다시 시작해도 2초 안팎) -------
    def _schedule_idle_release(self):
        self._cancel_idle_release()
        self._idle_job = self.after(IDLE_RELEASE_MS, self._release_idle)

    def _cancel_idle_release(self):
        job = getattr(self, "_idle_job", None)
        if job is not None:
            self.after_cancel(job)
            self._idle_job = None

    def _release_idle(self):
        self._idle_job = None
        if self.engine is None:
            release_model()
            release_mt()

    def start_engine(self):
        self._cancel_idle_release()
        name = model_name(self.cfg)
        if not model_cached(name):  # 크기를 알리고 허락 -> 다운로드(진행률 표시) -> 끝나면 자동 시작
            if self._stt_pct is None:
                self.ensure_stt_model(name, then_start=True)
            return
        if self.eff_target() != "off":
            self.ensure_mt()
        self.engine = Engine(self.cfg, self.output, self.events)
        self.engine.start()

    def ensure_stt_model(self, name=None, then_start=False):
        """음성 인식 모델이 없으면 크기를 알리고 허락받아 백그라운드로 내려받음. False = 거절/이미 진행 중."""
        name = name or model_name(self.cfg)
        if model_cached(name):
            return True
        if self._stt_pct is not None:
            return False
        body = T("dl_body").format(mb=MODEL_SIZES_MB[name], name=name)
        if not ask(self, T("dl_title"), body, T("dl_yes"), T("dl_no")):
            return False
        self._stt_pct, self._stt_dl = 0, name

        def run():
            try:
                download_stt(name, lambda p: setattr(self, "_stt_pct", p))
                self.events.put(("info", "info_stt_ready"))
                if then_start:
                    self.events.put(("start",))
            except Exception as e:
                log_error(f"stt download: {type(e).__name__}")
                self.events.put(("error", f"{T('dl_progress')}: {type(e).__name__}"))
            finally:
                self._stt_pct = None
                self._stt_dl = None
        threading.Thread(target=run, daemon=True).start()
        return True

    def ensure_mt(self, force=False):
        """오프라인 번역 모델이 필요하면 크기를 알리고 허락받아 백그라운드로 내려받음. False = 거절."""
        tier = mt_tier(self.cfg)
        if (self.cfg["translator"] != "local" and not force) or mt_cached(tier) or self._mt_pct is not None:
            return True
        body = T("dl_body").format(mb=MT_MODELS[tier]["size_mb"], name=T("mt_name_" + tier))
        if not ask(self, T("dl_title"), body, T("dl_yes"), T("dl_no")):
            return False
        self._mt_pct, self._mt_dl = 0, tier

        def run():
            try:
                download_mt(tier, lambda p: setattr(self, "_mt_pct", p))
                self.events.put(("info", "info_mt_ready"))
            except Exception as e:
                log_error(f"mt download: {type(e).__name__}")
                self.events.put(("error", f"{T('dl_mt_progress')}: {e}"))
            finally:
                self._mt_pct = None
                self._mt_dl = None
        threading.Thread(target=run, daemon=True).start()
        return True

    def toggle(self):
        if self.engine is not None:
            self.restart_pending = False
            self.engine.stop()
        else:
            self.start_engine()

    def apply_hotkey(self):
        """설정의 단축키를 등록 (이미 다른 프로그램이 쓰는 키면 알려줌). 성공 여부를 돌려줘요."""
        name = self.cfg.get("hotkey", "off")
        ok = self.hotkey.start(name)
        if not ok:
            self.add_bubble(T("hk_busy").format(k=hotkey.LABELS.get(name, name)), kind="err")
        return ok

    @staticmethod
    def _beep(paused):
        """화면을 안 보고 있어도 알 수 있게 짧은 소리 (일시정지: 낮은 음, 재개: 높은 음)."""
        def run():
            try:
                import winsound
                winsound.Beep(520 if paused else 880, 70)
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

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
            self.check_update()

    def check_update(self, on_done=None):
        """새 버전 확인. 시작 시(동의한 경우)나 사용자가 버튼을 눌렀을 때만 불러요. 결과 문구는 on_done 으로."""
        def run():
            try:
                info = updater.find_update(APP_VERSION, links.GITHUB_REPO)
                self.events.put(("update", info, on_done) if info else ("update_none", on_done))
            except Exception:
                self.events.put(("update_fail", on_done))
        threading.Thread(target=run, daemon=True).start()

    def start_update(self):
        info = self.update_info
        if not info:
            return
        asset = info.get("installer")
        if not (asset and asset.get("sha256") and updater.is_installed()):
            webbrowser.open(info["page"])  # 설치형이 아니거나 설치 파일이 없으면 릴리스 페이지로
            return
        if getattr(self, "_updating", False):
            return
        mb = max(1, round(asset["size"] / 1048576))
        if not ask(self, T("up_ask_title").format(v=info["version"]), T("up_ask_body").format(mb=mb),
                   T("up_yes"), T("dl_no")):
            return
        self._updating = True

        def run():
            try:
                last = [-1]

                def prog(done, total):
                    pct = int(done * 100 / total) if total else 0
                    if pct != last[0]:
                        last[0] = pct
                        self.events.put(("update_prog", pct))
                path = updater.download_installer(asset, prog)
                self.events.put(("update_run", path))
            except ValueError:
                self.events.put(("update_dl_fail", "up_bad_file"))
            except Exception:
                self.events.put(("update_dl_fail", "up_fail"))
            finally:
                self._updating = False
        threading.Thread(target=run, daemon=True).start()

    def _show_update(self):
        if self.update_info:
            self.update_lbl.configure(text=f"✨ {T('update_avail')}: v{self.update_info['version']}")
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
        self.hotkey.stop()
        if self.engine is not None:
            self.engine.stop()
        self.destroy()


# ====================================================================== 설정 창 (왼쪽 메뉴 + 오른쪽 내용)
class SettingsWindow(ctk.CTkToplevel):
    PAGES = (("general", "sec_general", "🏠"), ("audio", "sec_audio", "🎤"), ("models", "sec_modelpage", "📦"),
             ("translate", "sec_translate", "🌐"), ("vrc", "sec_vrc", "🎮"), ("privacy", "sec_privacy", "🔒"))

    def __init__(self, app, page="general"):
        super().__init__(app, fg_color=BG)
        set_icon(self)
        self.app, self.cfg = app, app.cfg
        self._test_result = None
        self.monitor = None
        self.sliders = {}
        self._cal = None
        self.title(T("settings"))
        self.geometry("860x640")
        self.minsize(780, 540)
        self.attributes("-topmost", self.cfg["always_on_top"])
        self.after(150, self.lift)

        nav = ctk.CTkFrame(self, fg_color=CARD, corner_radius=22, width=200)
        nav.pack(side="left", fill="y", padx=(14, 8), pady=14)
        nav.pack_propagate(False)
        ctk.CTkLabel(nav, text="⚙  " + T("settings"), font=f(17, True), text_color=TEXT, anchor="w").pack(
            fill="x", padx=20, pady=(22, 16))
        self.nav_btns, self.pages = {}, {}
        for key, label, icon in self.PAGES:
            b = ctk.CTkButton(nav, text=f"{icon}   {T(label)}", height=44, corner_radius=22, font=f(14, True), anchor="w",
                              fg_color="transparent", hover_color=FIELD_H, text_color=TEXT,
                              command=lambda k=key: self.show(k))
            b.pack(fill="x", padx=12, pady=2)
            self.nav_btns[key] = b
        ctk.CTkLabel(nav, text=f"{APP_NAME}\nv{APP_VERSION}", font=f(11), text_color=SUB,
                     justify="left").pack(side="bottom", anchor="w", padx=20, pady=18)

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(side="left", fill="both", expand=True, padx=(0, 14), pady=14)
        for key, _, _ in self.PAGES:
            self.body = ScrollFrame(self.content, fg_color="transparent")
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
        hk = self.option("hotkey", T("hotkey"), [("off", T("hk_off"))] + [(k, v) for k, v in hotkey.LABELS.items()],
                         cb=lambda v: self.app.apply_hotkey())
        ctk.CTkLabel(hk.master, text=T("hotkey_hint"), font=f(11), text_color=SUB, anchor="w", justify="left",
                     wraplength=520).pack(fill="x", padx=14, pady=(0, 12))

    def _page_audio(self):
        self.section(T("sec_audio"))
        self.mic_menu = self.option("mic", T("mic"), self._mic_items())
        soft_button(self.mic_menu.master, "⟳ " + T("refresh"), self._refresh_mics, height=28).pack(
            anchor="w", padx=14, pady=(0, 10))
        self._build_meter()
        self.slider("sensitivity", T("sensitivity"), 0, 100, 100, fmt="{:.0f}", extra=self._cal_row)  # 자동 맞춤은 같은 카드 안에
        self.slider("silence_sec", T("silence"), 0.2, 1.5, 26, fmt="{:.1f}s")
        nr = self.option("noise_reduction", T("noise"), [("off", T("nr_off")), ("low", T("nr_low")), ("high", T("nr_high"))])
        ctk.CTkLabel(nr.master, text=T("nr_hint"), font=f(11), text_color=SUB, anchor="w", justify="left",
                     wraplength=520).pack(fill="x", padx=14, pady=(0, 12))
        self.group(T("grp_recog"))
        vcard = self.card()
        ctk.CTkLabel(vcard, text=T("vocab"), font=f(13, True), text_color=TEXT).pack(anchor="w", padx=14, pady=(12, 4))
        self.vocab = ctk.CTkEntry(vcard, placeholder_text=T("vocab_hint"), height=34, corner_radius=17, font=f(13),
                                  fg_color=FIELD, border_width=0)
        self.vocab.insert(0, self.cfg["vocab"])
        self.vocab.pack(fill="x", padx=14, pady=(0, 12))
        self.vocab.bind("<FocusOut>", self._save_vocab)
        self.vocab.bind("<Return>", self._save_vocab)
        self.switch("live_preview", T("live_preview"),
                    initial=preview_default() if self.cfg["live_preview"] is None else self.cfg["live_preview"])
        self.switch("keep_model", T("keep_model"))

    def _cal_row(self, card):
        """민감도 카드 안의 '마이크 자동 맞춤' 줄 (버튼 + 진행/결과 문구)."""
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 12))
        self.cal_btn = pill_button(row, "🎯  " + T("cal_btn"), self._start_cal, height=32)
        self.cal_btn.pack(side="left")
        self.cal_lbl = ctk.CTkLabel(row, text=T("cal_hint"), font=f(12), text_color=SUB, anchor="w", justify="left", wraplength=340)
        self.cal_lbl.pack(side="left", fill="x", expand=True, padx=(12, 0))

    def _page_models(self):
        self.section(T("sec_modelpage"))
        self.group(T("sec_models"))
        self._build_stt_card()
        self.option("device_type", T("device"), [("auto", T("dev_auto")), ("cuda", T("dev_gpu")), ("cpu", T("dev_cpu"))])
        self.group(T("mt_card_title"))
        self._build_mt_card()
        ctk.CTkLabel(self.body, text=T("sm_hint") + "  " + T("restart_note"), font=f(11), text_color=SUB, anchor="w",
                     justify="left", wraplength=540).pack(fill="x", padx=14, pady=(6, 10))

    def _page_translate(self):
        self.section(T("sec_translate"))
        prov = self.option("translator", T("tr_provider"),
                    [("local", T("tp_local")), ("mymemory", T("tp_mymemory")), ("deepl", T("tp_deepl")),
                     ("gemini", T("tp_gemini"))], cb=lambda v: self._refresh_key_ui())
        self._prov_card = prov.master
        # 오프라인을 골랐을 때: 모델 상태 + '모델' 페이지로 가는 버튼 (다운로드 버튼을 찾기 쉽게)
        self.local_card = ctk.CTkFrame(self.body, fg_color=CARD, corner_radius=20)
        self.local_lbl = ctk.CTkLabel(self.local_card, text="", font=f(13), text_color=TEXT, anchor="w", justify="left", wraplength=520)
        self.local_lbl.pack(fill="x", padx=16, pady=(12, 6))
        soft_button(self.local_card, "📦  " + T("mt_goto"), lambda: self.show("models")).pack(anchor="w", padx=14, pady=(0, 14))
        card = self.card()
        ctk.CTkLabel(card, text=T("tr_key"), font=f(13, True), text_color=TEXT).pack(anchor="w", padx=14, pady=(12, 4))
        self._key_card = card
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
        self.test_lbl = ctk.CTkLabel(card, text="", font=f(12), text_color=SUB, anchor="w", justify="left", wraplength=520)
        self.test_lbl.pack(fill="x", padx=16, pady=(2, 0))
        ctk.CTkLabel(card, text=T("tr_key_note"), font=f(11), text_color=SUB, anchor="w", justify="left",
                     wraplength=520).pack(fill="x", padx=16, pady=(4, 12))
        # Gemini 전용: 모델 이름 + 무료 사용량의 데이터 사용 안내 (Gemini 를 골랐을 때만 보임)
        self.gem_card = ctk.CTkFrame(self.body, fg_color=CARD, corner_radius=20)
        ctk.CTkLabel(self.gem_card, text=T("tr_model"), font=f(13, True), text_color=TEXT).pack(anchor="w", padx=14, pady=(12, 4))
        self.gem_entry = ctk.CTkEntry(self.gem_card, placeholder_text=T("tr_model_hint"), height=34, corner_radius=17,
                                      font=f(13), fg_color=FIELD, border_width=0)
        self.gem_entry.insert(0, self.cfg.get("gemini_model", ""))
        self.gem_entry.pack(fill="x", padx=14)
        self.gem_entry.bind("<Return>", self._save_gem_model)
        self.gem_entry.bind("<FocusOut>", self._save_gem_model)
        ctk.CTkLabel(self.gem_card, text="⚠ " + T("tr_gemini_note"), font=f(11), text_color=ORANGE, anchor="w", justify="left",
                     wraplength=520).pack(fill="x", padx=16, pady=(8, 12))
        tip = ctk.CTkFrame(self.body, fg_color=FIELD, corner_radius=16)
        tip.pack(fill="x", padx=4, pady=6)
        ctk.CTkLabel(tip, text="💡 " + T("tr_tip"), font=f(12), text_color=TEXT, anchor="w", justify="left",
                     wraplength=520).pack(fill="x", padx=16, pady=12)
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
        ucard = self.card()
        self.up_lbl = ctk.CTkLabel(ucard, text=f"{T('version')} {APP_VERSION}", font=f(12), text_color=SUB, anchor="w")
        self.up_lbl.pack(fill="x", padx=16, pady=(12, 0))
        soft_button(ucard, "⟳  " + T("up_check"), self._check_now).pack(fill="x", padx=14, pady=(8, 14))
        pcard = self.card()
        soft_button(pcard, T("policy"), lambda: self.app.open_info("tab_privacy")).pack(fill="x", padx=14, pady=(14, 6))
        pill_button(pcard, T("delete_data"), self._delete_data, PINK, PINK_H, height=34).pack(fill="x", padx=14, pady=(0, 14))

    def _check_now(self):
        self.up_lbl.configure(text=T("up_checking"), text_color=SUB)

        def done(msg):
            if self.winfo_exists():
                self.up_lbl.configure(text=msg, text_color=PURPLE)
        self.app.check_update(done)

    # -- 위젯 도우미 ------------------------------------------------------
    def section(self, text):
        ctk.CTkLabel(self.body, text=text, font=f(18, True), text_color=TEXT, anchor="w").pack(fill="x", padx=8, pady=(6, 8))

    def group(self, text):
        """페이지 안의 소제목 (카드 묶음 구분)."""
        ctk.CTkLabel(self.body, text=text, font=f(12, True), text_color=PURPLE, anchor="w").pack(fill="x", padx=10, pady=(14, 2))

    @staticmethod
    def _set(w, **kw):
        """값이 바뀐 것만 위젯에 반영 (같은 값을 계속 넣으면 다시 그려져서 깜빡이는 걸 막음)."""
        last = w.__dict__.setdefault("_last", {})
        changed = {k: v for k, v in kw.items() if k not in last or last[k] != v}
        if changed:
            w.configure(**changed)
            last.update(changed)

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
        ctk.CTkLabel(card, text=label, font=f(13, True), text_color=TEXT).pack(anchor="w", padx=14, pady=(12, 4))
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

    def slider(self, key, label, lo, hi, steps, fmt, extra=None):
        card = self.card()
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(row, text=label, font=f(13, True), text_color=TEXT).pack(side="left")
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
        s.pack(fill="x", padx=14, pady=(4, 10 if extra else 12))
        tk.Misc.unbind(s._canvas, "<MouseWheel>")  # 휠은 페이지 스크롤 전용 (값이 실수로 바뀌는 것 방지)
        self.sliders[key] = (s, on)
        if extra:
            extra(card)

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

    # -- 마이크 자동 맞춤: 2초 조용히 + 3초 말하기 -> 알맞은 민감도 계산 -------------
    def _raw_level(self):
        e = self.app.engine
        if e is not None and e.ready:
            return e.level
        return self.monitor.raw if self.monitor is not None else None

    def _start_cal(self):
        if self._cal is not None:
            return
        self._cal = {"t0": time.time(), "quiet": [], "speak": [], "phase": "quiet"}
        self.cal_btn.configure(state="disabled")
        self.cal_lbl.configure(text=T("cal_quiet"), text_color=ORANGE)
        self.after(50, self._cal_tick)

    def _cal_tick(self):
        cal = self._cal
        if cal is None or not self.winfo_exists():
            return
        lvl, el = self._raw_level(), time.time() - cal["t0"]
        if lvl is not None:
            if el < 2.0:
                cal["quiet"].append(lvl)
            elif el < 5.0:
                if cal["phase"] == "quiet":
                    cal["phase"] = "speak"
                    self.cal_lbl.configure(text=T("cal_speak"))
                cal["speak"].append(lvl)
        if el < 5.0:
            self.after(50, self._cal_tick)
            return
        self._cal = None
        self.cal_btn.configure(state="normal")
        s = calibrate_sensitivity(cal["quiet"], cal["speak"])
        if s is None:
            self.cal_lbl.configure(text=T("cal_fail"), text_color=RED)
            return
        slider, on = self.sliders["sensitivity"]
        slider.set(s)
        on(s)
        self.cal_lbl.configure(text=T("cal_done").format(s=s), text_color=GREEN)

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
        if self._n % 12 == 0 and hasattr(self, "mt_rows"):
            self._refresh_mt()
        if self._n % 12 == 0 and hasattr(self, "stt_rows"):
            self._refresh_stt()
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
        mv = meter_value(lvl)
        if abs(mv - getattr(self, "_smv", -1)) > 0.004:
            self._smv = mv
            self.mbar.set(mv)
        self._set(self.mbar, progress_color=GREEN if on else PURPLE)
        mp = meter_value(thr)
        if mp != getattr(self, "_smp", None):
            self._smp = mp
            self.marker.place(in_=self.mbar, relx=mp, rely=0.5, anchor="center")
        self._set(self.lvl_txt, text=f"{db:.0f} dB · " + (T("lvl_on") if on else T("lvl_off")),
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
        # 고른 서비스에 필요한 카드만: 오프라인 -> 모델 상태 카드 / Gemini -> 모델 이름 + 경고 / 키가 필요한 서비스 -> API 키 카드
        anchor = self._prov_card
        self.local_card.pack_forget()
        self.gem_card.pack_forget()
        if p == "local":
            self.local_card.pack(fill="x", padx=4, pady=5, after=anchor)
            anchor = self.local_card
            self._refresh_local_lbl()
        elif p == "gemini":
            self.gem_card.pack(fill="x", padx=4, pady=5, after=anchor)
            anchor = self.gem_card
        self._key_card.pack_forget()
        if needs:
            self._key_card.pack(fill="x", padx=4, pady=5, after=anchor)
        self.get_key_btn.configure(state="normal" if needs else "disabled")
        self.rm_key_btn.configure(state="normal" if needs and saved else "disabled")
        self.test_lbl.configure(text="")

    def _refresh_local_lbl(self):
        tier = mt_tier(self.cfg)
        ok = mt_cached(tier)
        self._set(self.local_lbl, text=("✓ " + T("mt_status_ok")) if ok else ("⚠ " + T("mt_status_none").format(mb=MT_MODELS[tier]["size_mb"])),
                  text_color=GREEN if ok else ORANGE)

    def _save_gem_model(self, _=None):
        self.app.set_cfg("gemini_model", self.gem_entry.get().strip())

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

    # -- 모델 관리 카드: 줄마다 [고르기 ◉] [이름·크기] [상태] [다운로드/삭제 버튼 하나] ----------
    def _model_row(self, card, text, var, value, on_pick, on_action=None):
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=3)
        row.columnconfigure(0, weight=1)
        rb = ctk.CTkRadioButton(row, text=text, variable=var, value=value, font=f(12), text_color=TEXT,
                                fg_color=PURPLE, hover_color=PURPLE_H, command=on_pick)
        rb.grid(row=0, column=0, sticky="w", padx=(2, 8))
        st = ctk.CTkLabel(row, text="", font=f(12), text_color=SUB, width=96, anchor="e")
        st.grid(row=0, column=1, padx=(0, 8))
        if on_action is None:  # 버튼이 필요 없는 줄 (자동 선택)
            return st, None
        btn = ctk.CTkButton(row, text="", width=104, height=30, corner_radius=15, font=f(12, True), command=on_action)
        btn.grid(row=0, column=2)
        return st, btn

    @staticmethod
    def _action_style(ok, busy):
        """설치돼 있으면 '삭제'(부드러운 버튼), 아니면 '다운로드'(보라색 버튼). 받는 중이면 눌리지 않게."""
        if ok:
            return dict(text=T("sm_delete"), fg_color=FIELD, hover_color=FIELD_H, text_color=TEXT)
        return dict(text="⬇ " + T("sm_download"), fg_color=PURPLE, hover_color=PURPLE_H, text_color="#FFFFFF")

    def _build_stt_card(self):
        card = self.card()
        self.stt_var = ctk.StringVar(value=self.cfg["model"])
        self.stt_rows = {}
        for m in ("auto", "tiny", "base", "small", "medium", "large-v3-turbo"):
            st, btn = self._model_row(card, T("m_" + m), self.stt_var, m, lambda m=m: self._pick_stt(m),
                                      None if m == "auto" else (lambda m=m: self._stt_action(m)))
            self.stt_rows[m] = (st, btn)
        ctk.CTkFrame(card, height=6, fg_color="transparent").pack()
        self._refresh_stt()

    def _pick_stt(self, m):
        self.app.set_cfg("model", m)
        if self.app.engine is None:
            self.app.after(80, self.app.ensure_stt_model)  # 없으면 크기를 알리고 허락받아 다운로드
        self._refresh_stt()

    def _stt_action(self, m):
        if model_cached(m):
            self._stt_delete(m)
        else:
            self.app.ensure_stt_model(m)

    def _refresh_stt(self):
        using, running = model_name(self.cfg), self.app.engine is not None
        if self.stt_var.get() != self.cfg["model"]:
            self.stt_var.set(self.cfg["model"])
        for m, (st, btn) in self.stt_rows.items():
            if m == "auto":
                self._set(st, text="→ " + using, text_color=SUB)
                continue
            ok = model_cached(m)
            if m == self.app._stt_dl and self.app._stt_pct is not None:
                self._set(st, text=f"⏳ {T('dl_progress')} {self.app._stt_pct}%", text_color=ORANGE)
            else:
                label = (T("sm_installed") if ok else T("sm_none")) + ((" · " + T("sm_inuse")) if m == using and ok else "")
                self._set(st, text=label, text_color=GREEN if ok else SUB)
            busy = (not ok and self.app._stt_pct is not None) or (ok and m == using and running)
            self._set(btn, state="disabled" if busy else "normal", **self._action_style(ok, busy))

    def _stt_delete(self, m):
        if ask(self, T("sm_delete"), T("sm_delete_body").format(name=m, mb=MODEL_SIZES_MB[m]), T("delete_yes"), T("dl_no")):
            delete_stt(m)
            self._refresh_stt()

    def _build_mt_card(self):
        card = self.card()
        self._mt_card = card
        self.mt_var = ctk.StringVar(value=self.cfg["mt_quality"])
        self.mt_rows = {}
        for tier in ("standard", "high"):
            st, btn = self._model_row(card, T("mqs_" + tier), self.mt_var, tier, lambda t=tier: self._pick_mt(t),
                                      (lambda t=tier: self._mt_action(t)))
            self.mt_rows[tier] = (st, btn)
        ctk.CTkLabel(card, text=T("mt_scope_note"), font=f(11), text_color=SUB, anchor="w", justify="left",
                     wraplength=520).pack(fill="x", padx=16, pady=(4, 12))
        self._refresh_mt()

    def _pick_mt(self, tier):
        self.app.set_cfg("mt_quality", tier)
        self._refresh_mt()
        self.app.after(80, self.app.ensure_mt)

    def _mt_action(self, tier):
        if mt_cached(tier):
            self._mt_remove(tier)
        else:
            self.mt_var.set(tier)
            self.app.set_cfg("mt_quality", tier)
            self.app.ensure_mt(force=True)
        self._refresh_mt()

    def _refresh_mt(self):
        if self.mt_var.get() != self.cfg["mt_quality"]:
            self.mt_var.set(self.cfg["mt_quality"])
        for tier, (st, btn) in self.mt_rows.items():
            ok = mt_cached(tier)
            if tier == self.app._mt_dl and self.app._mt_pct is not None:
                self._set(st, text=f"⏳ {T('dl_mt_progress')} {self.app._mt_pct}%", text_color=ORANGE)
            else:
                self._set(st, text=T("sm_installed") if ok else T("sm_none"), text_color=GREEN if ok else SUB)
            busy = not ok and self.app._mt_pct is not None
            self._set(btn, state="disabled" if busy else "normal", **self._action_style(ok, busy))
        if hasattr(self, "local_lbl"):
            self._refresh_local_lbl()

    def _mt_remove(self, tier=None):
        tier = tier or mt_tier(self.cfg)
        release_mt()
        shutil.rmtree(mt_dir(tier), ignore_errors=True)

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
        set_icon(self)
        self.app = app
        self.title(f"{T('title')} · {T('about')}")
        self.geometry("860x560")
        self.minsize(760, 480)
        self.attributes("-topmost", app.cfg["always_on_top"])
        self.after(150, self.lift)
        nav = ctk.CTkFrame(self, fg_color=CARD, corner_radius=22, width=190)
        nav.pack(side="left", fill="y", padx=(14, 8), pady=14)
        nav.pack_propagate(False)
        ctk.CTkLabel(nav, text="♥  " + T("about"), font=f(16, True), text_color=TEXT, anchor="w").pack(
            fill="x", padx=20, pady=(22, 14))
        ctk.CTkLabel(nav, text=f"{APP_NAME}\n{T('version')} {APP_VERSION}", font=f(11), text_color=SUB,
                     justify="left").pack(side="bottom", anchor="w", padx=20, pady=18)
        self.content = ctk.CTkFrame(self, fg_color=CARD, corner_radius=22)
        self.content.pack(side="left", fill="both", expand=True, padx=(0, 14), pady=14)
        builders = {
            "tab_new": ("✨", lambda t: self._text(t, self._read(f"CHANGELOG.{i18n._lang}.md", "CHANGELOG.md"), md=True)),
            "tab_fb": ("💬", self._feedback),
            "tab_support": ("♥", self._support),
            "tab_privacy": ("🔒", lambda t: self._text(t, self._read(f"PRIVACY.{i18n._lang}.md", "PRIVACY.en.md"))),
            "tab_dev": ("🐰", self._developer),
        }
        self.nav_btns, self.pages, self.current = {}, {}, None
        for key, (icon, build) in builders.items():
            b = ctk.CTkButton(nav, text=f"{icon}  {T(key)}", height=40, corner_radius=20, font=f(13, True), anchor="w",
                              fg_color="transparent", hover_color=FIELD_H, text_color=TEXT,
                              command=lambda k=key: self.show(k))
            b.pack(fill="x", padx=12, pady=2)
            self.nav_btns[key] = b
            page = ctk.CTkFrame(self.content, fg_color="transparent")
            self.pages[key] = page
            build(page)
        self.show(tab)
        app.cfg["last_seen_version"] = APP_VERSION
        save_config(app.cfg)

    def show(self, key):
        for k, p in self.pages.items():
            p.pack_forget()
            self.nav_btns[k].configure(fg_color="transparent", text_color=TEXT)
        self.pages[key].pack(fill="both", expand=True, padx=16, pady=16)
        self.nav_btns[key].configure(fg_color=PURPLE, text_color="#FFFFFF", hover_color=PURPLE_H)
        self.current = key

    @staticmethod
    def _read(name, fallback=None):
        for n in (name, fallback):
            try:
                if n:
                    return resource_path(n).read_text(encoding="utf-8")
            except Exception:
                pass
        return T("no_changelog")

    def _text(self, tab, text, md=False):
        box = ctk.CTkTextbox(tab, fg_color="transparent", font=f(12), text_color=TEXT, wrap="word")
        box.pack(fill="both", expand=True)
        if md:
            self._insert_md(box, text)
        else:
            box.insert("1.0", text)
        box.configure(state="disabled")

    @staticmethod
    def _insert_md(box, text):
        """CHANGELOG 같은 간단한 마크다운을 제목/목록으로 보여줘요 (기호는 숨김)."""
        import re
        tb = box._textbox
        fg = tb.cget("fg")
        tb.tag_configure("h2", font=(FONT, 15, "bold"), foreground=fg, spacing1=14, spacing3=4)
        tb.tag_configure("h3", font=(FONT, 12, "bold"), foreground="#8B7CFF", spacing1=8, spacing3=2)
        tb.tag_configure("li", foreground=fg, lmargin1=8, lmargin2=22, spacing3=2)
        tb.tag_configure("quote", lmargin1=8, lmargin2=8, foreground="#9A98B8", spacing3=4)
        nl = chr(10)
        for raw in text.split(nl):
            line = raw.rstrip()
            if not line or line.startswith("# ") or re.match(r"^[^\w\s]*\s*(English|한국어|日本語)\s*:", line):
                continue
            line = re.sub(r"\[([^\]]+)\]\([^)]+\)", lambda m: m.group(1), line)
            line = line.replace("**", "").replace("`", "")
            if line.startswith("### "):
                box.insert("end", line[4:] + nl, "h3")
            elif line.startswith("## "):
                box.insert("end", line[3:] + nl, "h2")
            elif line.startswith("- "):
                box.insert("end", "•  " + line[2:] + nl, "li")
            elif line.startswith("> "):
                box.insert("end", line[2:] + nl, "quote")
            else:
                box.insert("end", line + nl)

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

    def _developer(self, tab):
        body = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        body.pack(fill="both", expand=True)
        hero = ctk.CTkFrame(body, fg_color=FIELD, corner_radius=22)
        hero.pack(fill="x", padx=4, pady=(4, 10))
        try:
            self._logo = tk.PhotoImage(file=str(resource_path("RHLingo_logo.png")))
            ctk.CTkLabel(hero, image=self._logo, text="").pack(side="left", padx=(18, 12), pady=14)
        except Exception:
            pass
        col = ctk.CTkFrame(hero, fg_color="transparent")
        col.pack(side="left", fill="x", expand=True, pady=12)
        ctk.CTkLabel(col, text="RabbitHaru", font=f(18, True), text_color=TEXT, anchor="w").pack(fill="x")
        ctk.CTkLabel(col, text=T("dev_role"), font=f(12), text_color=SUB, anchor="w").pack(fill="x")

        card = ctk.CTkFrame(body, fg_color=FIELD, corner_radius=20)
        card.pack(fill="x", padx=4, pady=5)
        ctk.CTkLabel(card, text="💌  " + T("dev_msg_title"), font=f(13, True), text_color=TEXT, anchor="w").pack(fill="x", padx=18, pady=(14, 2))
        ctk.CTkLabel(card, text=T("dev_msg"), font=f(12), text_color=TEXT, anchor="w", justify="left",
                     wraplength=640).pack(fill="x", padx=18, pady=(0, 14))

        shown = [(n, u) for n, u in links.DEV_LINKS if u]
        if links.GITHUB_REPO:
            shown.insert(0, ("GitHub", f"https://github.com/{links.GITHUB_REPO.split('/')[0]}"))
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=5)
        for n, u in shown:
            pill_button(row, n, lambda u=u: webbrowser.open(u), height=38).pack(side="left", padx=(0, 8))
        if not any(n.startswith(("X", "Twitter")) for n, _ in shown):
            ctk.CTkLabel(row, text="X (Twitter): " + T("dev_soon"), font=f(11), text_color=SUB).pack(side="left", padx=6)

        thanks = ctk.CTkFrame(body, fg_color=FIELD, corner_radius=20)
        thanks.pack(fill="x", padx=4, pady=5)
        ctk.CTkLabel(thanks, text="🌸  " + T("dev_thanks"), font=f(13, True), text_color=TEXT, anchor="w").pack(fill="x", padx=18, pady=(14, 4))
        people = [p for p in links.SPECIAL_THANKS if p]
        if people:
            ctk.CTkLabel(thanks, text="  ·  ".join(people), font=f(12), text_color=TEXT, anchor="w", justify="left",
                         wraplength=640).pack(fill="x", padx=18, pady=(0, 8))
        else:
            ctk.CTkLabel(thanks, text=T("dev_thanks_empty"), font=f(12), text_color=SUB, anchor="w").pack(fill="x", padx=18, pady=(0, 8))
        ctk.CTkLabel(thanks, text=T("dev_oss"), font=f(11), text_color=SUB, anchor="w", justify="left",
                     wraplength=640).pack(fill="x", padx=18, pady=(0, 14))

    def _support(self, tab):
        ctk.CTkLabel(tab, text=T("support_text"), font=f(13), text_color=TEXT, wraplength=620,
                     justify="left", anchor="w").pack(fill="x", pady=(8, 14))
        shown = [(n, u) for n, u in links.DONATE_LINKS if u]
        if not shown:
            ctk.CTkLabel(tab, text=T("support_none"), font=f(12), text_color=SUB).pack(anchor="w")
        for name, url in shown:
            pill_button(tab, "♥  " + name, lambda u=url: webbrowser.open(u), PINK, PINK_H, height=42).pack(fill="x", pady=4)
