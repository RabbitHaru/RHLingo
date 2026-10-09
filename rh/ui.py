"""화면: 메인(인식) 창 / 설정 창 / 정보 창(업데이트 내역·피드백·후원)."""
import json
import os
import platform
import queue
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

import customtkinter as ctk

from . import i18n, links
from .config import APP_NAME, APP_VERSION, DATA_DIR, load_config, save_config
from .engine import Engine, Output, format_chatbox, list_mics, translate_text
from .i18n import LANGS, NATIVE, T, lang_label

FONT = "Malgun Gothic"
PURPLE, PURPLE_H = ("#7C6BF2", "#8B7CFF"), ("#6A59E0", "#7A69F5")
PINK, PINK_H = ("#F25577", "#FF6B8A"), ("#E04466", "#F25577")
BG, CARD, FIELD = ("#F4F2FF", "#1A1A2A"), ("#FFFFFF", "#232336"), ("#ECE9FF", "#2E2E48")
TEXT, SUB = ("#2A2650", "#EDEAFF"), ("#7B7799", "#9A98B8")
GREEN, ORANGE, RED = ("#1FA971", "#6EE7A8"), ("#D98A1F", "#FFC46B"), ("#D93A5C", "#FF8AA0")
MAX_BUBBLES = 40
RESTART_KEYS = {"mic", "model", "device_type", "vrc_mute_sync", "osc_ip", "osc_port", "osc_in_port"}


def resource_path(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / name


def f(size=13, bold=False):
    return ctk.CTkFont(family=FONT, size=size, weight="bold" if bold else "normal")


# ====================================================================== 메인 창
class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.cfg = load_config()
        i18n.set_lang(self.cfg["ui_lang"])
        ctk.set_appearance_mode(self.cfg["theme"])
        self.geometry("460x720")
        self.minsize(420, 600)
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
        if self.cfg["last_seen_version"] != APP_VERSION:
            self.after(700, lambda: self.open_info("tab_new"))
        if links.GITHUB_REPO:
            threading.Thread(target=self._check_update, daemon=True).start()

    # -- 화면 구성 ------------------------------------------------------
    def build(self):
        for w in self.winfo_children():
            w.destroy()
        self.bubbles = []
        self._shown_state = None
        self.title(T("title"))

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(18, 0))
        ctk.CTkLabel(top, text="🐰 " + T("title"), font=f(20, True), text_color=TEXT).pack(side="left")
        for txt, cmd in (("⚙", self.open_settings), ("♥", lambda: self.open_info("tab_new"))):
            ctk.CTkButton(top, text=txt, width=36, height=36, corner_radius=18, font=f(16),
                          fg_color=CARD, hover_color=FIELD, text_color=TEXT,
                          command=cmd).pack(side="right", padx=(6, 0))

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
            card, values=[NATIVE[c] for c in LANGS], command=self._on_target, height=36,
            corner_radius=18, font=f(13, True), selected_color=PURPLE, selected_hover_color=PURPLE_H,
            unselected_color=FIELD, unselected_hover_color=FIELD)
        self.target_btn.set(NATIVE[self.cfg["target"]])
        self.target_btn.pack(fill="x", padx=14, pady=(0, 10))
        meter_row = ctk.CTkFrame(card, fg_color="transparent")
        meter_row.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkLabel(meter_row, text="🎤", font=f(14)).pack(side="left")
        self.meter = ctk.CTkProgressBar(meter_row, height=10, corner_radius=5, progress_color=PURPLE, fg_color=FIELD)
        self.meter.set(0)
        self.meter.pack(side="left", fill="x", expand=True, padx=10)
        self.pause_btn = ctk.CTkButton(meter_row, text=T("pause"), width=84, height=28, corner_radius=14, font=f(12),
                                       fg_color=FIELD, hover_color=("#DDD8FF", "#3A3A5C"), text_color=TEXT,
                                       command=self.toggle_pause)
        self.pause_btn.pack(side="right")

        self.btn = ctk.CTkButton(self, text=T("start"), height=48, corner_radius=24, font=f(16, True),
                                 fg_color=PURPLE, hover_color=PURPLE_H, command=self.toggle)
        self.btn.pack(fill="x", padx=20, pady=12)

        self.hist = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.hist.pack(fill="both", expand=True, padx=10)
        self.empty = ctk.CTkLabel(self.hist, text=T("empty"), font=f(13), text_color=SUB, justify="center")
        self.empty.pack(pady=40)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=20, pady=(6, 16))
        self.entry = ctk.CTkEntry(bar, placeholder_text=T("type_hint"), height=40, corner_radius=20, font=f(13),
                                  fg_color=CARD, border_width=0)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.send_manual())
        ctk.CTkButton(bar, text=T("send"), width=64, height=40, corner_radius=20, font=f(13, True),
                      fg_color=PURPLE, hover_color=PURPLE_H, command=self.send_manual).pack(side="left", padx=(8, 0))

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
        if state != self._shown_state:
            self._apply_state(state)
        self.meter.set(min(1.0, (e.level / 0.05) ** 0.5) if e and e.ready and state in ("listening",) else 0)
        self.after(80, self._tick)

    def _handle(self, ev):
        kind = ev[0]
        if kind == "result":
            _, src, tgt, text, out = ev
            tag = f"{NATIVE.get(src, src)} → {NATIVE[tgt]}" if src != tgt else NATIVE[tgt]
            self.add_bubble(out, f"{tag}  ·  {text}" if src != tgt else tag)
        elif kind == "info":
            self.add_bubble(T(ev[1]), kind="sys")
        elif kind == "error":
            self.add_bubble(f"{T('err')}: {ev[1]}", kind="err")
        elif kind == "update":
            self.update_info = (ev[1], ev[2])
            self._show_update()

    def _apply_state(self, state):
        self._shown_state = state
        text, color = {
            "idle": (T("st_idle"), SUB), "loading": (T("st_loading"), ORANGE),
            "listening": (T("st_listening"), GREEN), "paused": (T("st_paused"), ORANGE),
            "muted": (T("st_muted"), ORANGE), "stopping": (T("stopping"), SUB)}[state]
        self.status.configure(text="● " + text, text_color=color)
        running = state not in ("idle", "stopping")
        self.btn.configure(text=T("stop") if running else T("stopping") if state == "stopping" else T("start"),
                           fg_color=PINK if running else PURPLE, hover_color=PINK_H if running else PURPLE_H,
                           state="disabled" if state == "stopping" else "normal")
        paused = state == "paused"
        self.pause_btn.configure(text=T("resume") if paused else T("pause"),
                                 state="normal" if state in ("listening", "paused", "muted") else "disabled")

    # -- 동작 -----------------------------------------------------------
    def start_engine(self):
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

    def _on_target(self, label):
        self.set_cfg("target", next(c for c in LANGS if NATIVE[c] == label))

    def set_cfg(self, key, value):
        self.cfg[key] = value
        save_config(self.cfg)
        if key in RESTART_KEYS and self.engine is not None:
            self.restart_pending = True
            self.engine.stop()
        if key == "target" and self.settings is None:
            pass

    def send_manual(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        tgt = self.cfg["target"]

        def run():
            try:
                out = translate_text(text, "auto", tgt)
                self.output.send(format_chatbox(out, text, self.cfg["show_original"]))
                self.events.put(("result", tgt, tgt, text, out) if out == text else ("result", "auto", tgt, text, out))
            except Exception as e:
                self.events.put(("error", f"{T('tr_failed')}: {e}"))
        threading.Thread(target=run, daemon=True).start()

    # -- 업데이트 확인 ----------------------------------------------------
    def _check_update(self):
        try:
            url = f"https://api.github.com/repos/{links.GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "RabbitHaru-Translator"})
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
        self.geometry("440x680")
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
        ctk.CTkButton(self.mic_menu.master, text="⟳ " + T("refresh"), height=28, corner_radius=14, font=f(12),
                      fg_color=FIELD, hover_color=("#DDD8FF", "#3A3A5C"), text_color=TEXT,
                      command=self._refresh_mics).pack(anchor="w", padx=14, pady=(0, 10))
        self.option("source", T("speech_lang"), [("auto", T("auto"))] + [(c, lang_label(c)) for c in LANGS])
        self.option("model", T("model"), [(m, T("m_" + m)) for m in
                                          ("auto", "tiny", "base", "small", "medium", "large-v3-turbo")])
        self.option("device_type", T("device"), [("auto", T("dev_auto")), ("cuda", T("dev_gpu")), ("cpu", T("dev_cpu"))])
        self.slider("sensitivity", T("sensitivity"), 0, 100, 100, fmt="{:.0f}")
        self.slider("silence_sec", T("silence"), 0.3, 1.5, 24, fmt="{:.1f}s")
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

        ctk.CTkLabel(body, text=f"{APP_NAME} v{APP_VERSION}", font=f(11), text_color=SUB).pack(pady=(14, 4))

    # -- 위젯 도우미 ------------------------------------------------------
    def section(self, text):
        ctk.CTkLabel(self.body, text=text, font=f(14, True), text_color=TEXT, anchor="w").pack(fill="x", padx=10, pady=(14, 4))

    def card(self):
        c = ctk.CTkFrame(self.body, fg_color=CARD, corner_radius=20)
        c.pack(fill="x", padx=4, pady=4)
        return c

    def _change(self, key, value, ui=False):
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
        self.mic_menu._items = {l: c for c, l in items}
        self.mic_menu.configure(command=lambda l: self._change("mic", self.mic_menu._items[l]))

    def switch(self, key, label, ui=False):
        card = self.card()
        var = ctk.BooleanVar(value=bool(self.cfg[key]))
        ctk.CTkSwitch(card, text=label, variable=var, font=f(13), progress_color=PURPLE, text_color=TEXT,
                      command=lambda: self._change(key, var.get(), ui)).pack(anchor="w", padx=14, pady=12)

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
        s = ctk.CTkSlider(card, from_=lo, to=hi, number_of_steps=steps, command=on, progress_color=PURPLE,
                          button_color=PURPLE, button_hover_color=PURPLE_H, fg_color=FIELD)
        s.set(self.cfg[key])
        s.pack(fill="x", padx=14, pady=(4, 12))

    def _save_port(self, _=None):
        try:
            p = int(self.port.get())
            if 1 <= p <= 65535 and p != self.cfg["osc_port"]:
                self.app.set_cfg("osc_port", p)
        except ValueError:
            self.port.delete(0, "end")
            self.port.insert(0, str(self.cfg["osc_port"]))


# ====================================================================== 정보 창
class InfoWindow(ctk.CTkToplevel):
    def __init__(self, app, tab):
        super().__init__(app, fg_color=BG)
        self.app = app
        self.title(f"{T('title')} · {T('about')}")
        self.geometry("460x600")
        self.minsize(400, 480)
        self.attributes("-topmost", app.cfg["always_on_top"])
        self.after(150, self.lift)
        tabs = ctk.CTkTabview(self, corner_radius=20, fg_color=CARD, segmented_button_selected_color=PURPLE,
                              segmented_button_selected_hover_color=PURPLE_H, segmented_button_unselected_color=FIELD,
                              text_color=TEXT)
        tabs.pack(fill="both", expand=True, padx=14, pady=14)
        names = {k: T(k) for k in ("tab_new", "tab_fb", "tab_support")}
        for n in names.values():
            tabs.add(n)
        self._changelog(tabs.tab(names["tab_new"]))
        self._feedback(tabs.tab(names["tab_fb"]))
        self._support(tabs.tab(names["tab_support"]))
        tabs.set(names[tab])
        app.cfg["last_seen_version"] = APP_VERSION
        save_config(app.cfg)

    def _changelog(self, tab):
        try:
            text = resource_path("CHANGELOG.md").read_text(encoding="utf-8")
        except Exception:
            text = T("no_changelog")
        box = ctk.CTkTextbox(tab, fg_color="transparent", font=f(12), text_color=TEXT, wrap="word")
        box.pack(fill="both", expand=True)
        box.insert("1.0", f"{T('version')} {APP_VERSION}\n\n{text}")
        box.configure(state="disabled")

    def _feedback(self, tab):
        ctk.CTkLabel(tab, text=T("fb_hint"), font=f(13, True), text_color=TEXT, anchor="w").pack(fill="x", pady=(4, 6))
        self.fb = ctk.CTkTextbox(tab, height=170, corner_radius=16, font=f(12), fg_color=FIELD, text_color=TEXT, wrap="word")
        self.fb.pack(fill="x")
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", pady=10)
        if links.GITHUB_REPO:
            self._btn(row, T("fb_github"), self._send_github, PURPLE).pack(side="left", padx=(0, 8))
        elif links.FEEDBACK_FORM_URL:
            self._btn(row, T("fb_form"), lambda: webbrowser.open(links.FEEDBACK_FORM_URL), PURPLE).pack(side="left", padx=(0, 8))
        else:
            ctk.CTkLabel(row, text=T("fb_none"), font=f(12), text_color=SUB).pack(side="left", padx=(0, 8))
        self._btn(row, T("fb_log"), lambda: (DATA_DIR.mkdir(parents=True, exist_ok=True), os.startfile(DATA_DIR)),
                  FIELD, TEXT).pack(side="left")

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
            self._btn(tab, "♥  " + name, lambda u=url: webbrowser.open(u), PINK, height=42).pack(fill="x", pady=4)

    @staticmethod
    def _btn(parent, text, cmd, color, text_color="#FFFFFF", height=36):
        return ctk.CTkButton(parent, text=text, command=cmd, height=height, corner_radius=height // 2, font=f(13, True),
                             fg_color=color, hover_color=PURPLE_H if color == PURPLE else (PINK_H if color == PINK else ("#DDD8FF", "#3A3A5C")),
                             text_color=text_color)
