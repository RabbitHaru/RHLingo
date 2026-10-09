"""전역 단축키 (VRChat 화면을 보고 있어도 일시정지/재개). 추가 패키지 없이 Windows API 로 처리해요."""
import ctypes
import threading
from ctypes import wintypes

MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x1, 0x2, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012

# 설정에 저장되는 값 -> (수정키, 가상 키 코드). 다른 프로그램과 잘 겹치지 않는 조합만 골랐어요.
HOTKEYS = {
    "ctrl+alt+m": (MOD_CONTROL | MOD_ALT, ord("M")),
    "ctrl+alt+p": (MOD_CONTROL | MOD_ALT, ord("P")),
    "ctrl+alt+space": (MOD_CONTROL | MOD_ALT, 0x20),
    "f9": (0, 0x78),
}
LABELS = {"ctrl+alt+m": "Ctrl + Alt + M", "ctrl+alt+p": "Ctrl + Alt + P", "ctrl+alt+space": "Ctrl + Alt + Space", "f9": "F9"}


class Hotkey:
    def __init__(self, on_press):
        self.on_press = on_press
        self._tid = None
        self._thread = None
        self.ok = False

    def start(self, name):
        """등록에 성공하면 True (다른 프로그램이 이미 쓰고 있으면 False)."""
        self.stop()
        spec = HOTKEYS.get(name)
        if spec is None:
            return True
        ready = threading.Event()

        def run():
            u32 = ctypes.windll.user32
            self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
            self.ok = bool(u32.RegisterHotKey(None, 1, spec[0] | MOD_NOREPEAT, spec[1]))
            ready.set()
            if not self.ok:
                return
            msg = wintypes.MSG()
            while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    try:
                        self.on_press()
                    except Exception:
                        pass
            u32.UnregisterHotKey(None, 1)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        ready.wait(2)
        return self.ok

    def stop(self):
        if self._thread is not None and self._thread.is_alive() and self._tid:
            ctypes.windll.user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            self._thread.join(1)
        self._thread, self._tid, self.ok = None, None, False
