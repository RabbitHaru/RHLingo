"""음성 인식 + 번역 + VRChat OSC 전송 엔진 (UI와 독립). 무거운 모듈은 필요할 때만 불러옵니다."""
import collections
import gc
import os
import queue
import sys
import threading
import time
from pathlib import Path

import numpy as np
from pythonosc.udp_client import SimpleUDPClient

from .config import MODEL_DIR, log_error

SR = 16000
CHUNK_SEC = 0.05
CHATBOX_LIMIT = 144
CHATBOX_INTERVAL = 1.3  # VRChat 채팅박스 전송 최소 간격(초)
MM_CODES = {"ko": "ko-KR", "ja": "ja-JP", "en": "en-US"}

# Whisper가 무음/잡음에서 자주 내뱉는 환각 문구
HALLUCINATIONS = (
    "ご視聴ありがとうございました", "ご視聴ありがとうございます", "チャンネル登録",
    "시청해 주셔서 감사합니다", "시청해주셔서 감사합니다", "구독과 좋아요", "자막 제공",
    "thanks for watching", "thank you for watching", "subtitles by", "please subscribe",
)


# ---------------------------------------------------------------- GPU(CUDA) 라이브러리 경로
def _add_cuda_dll_dirs():
    """pip로 설치된 nvidia-cublas/cudnn DLL(또는 exe에 포함된 것)을 찾아 등록. 없으면 CPU로 동작."""
    roots = [Path(getattr(sys, "_MEIPASS", "")) / "nvidia"] if hasattr(sys, "_MEIPASS") else []
    roots += [Path(p) / "nvidia" for p in sys.path if p]
    for root in roots:
        for bin_dir in root.glob("*/bin") if root.is_dir() else []:
            try:
                os.add_dll_directory(str(bin_dir))
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
            except OSError:
                pass


# ---------------------------------------------------------------- 마이크 목록
def _input_devices():
    import sounddevice as sd
    try:
        host = sd.query_devices(kind="input")["hostapi"]
    except Exception:
        host = None
    out = []
    for i, d in enumerate(sd.query_devices()):
        name = d["name"]
        if d["max_input_channels"] <= 0 or (host is not None and d["hostapi"] != host):
            continue
        if "Sound Mapper" in name or "사운드 매퍼" in name or name in [n for _, n in out]:
            continue
        out.append((i, name))
    return out


def list_mics():
    try:
        return [n for _, n in _input_devices()]
    except Exception as e:
        log_error(f"list_mics: {e}")
        return []


def _resolve_mic(name):
    if not name:
        return None
    for i, n in _input_devices():
        if n == name:
            return i
    return None


# ---------------------------------------------------------------- 번역
def translate_text(text, src, tgt):
    from deep_translator import GoogleTranslator, MyMemoryTranslator
    s = src if src in MM_CODES else "auto"
    last = None
    for _ in range(2):
        try:
            r = GoogleTranslator(source=s, target=tgt).translate(text)
            if r:
                return r
        except Exception as e:
            last = e
            time.sleep(0.3)
    if s in MM_CODES:  # 구글 실패 시 예비 번역기
        try:
            return MyMemoryTranslator(source=MM_CODES[s], target=MM_CODES[tgt]).translate(text)
        except Exception as e:
            last = e
    raise last or RuntimeError("translate failed")


def format_chatbox(out, orig, show_original):
    if show_original and orig and orig != out:
        full = f"{out}\n({orig})"
        if len(full) <= CHATBOX_LIMIT:
            return full
    return out if len(out) <= CHATBOX_LIMIT else out[:CHATBOX_LIMIT - 1] + "…"


# ---------------------------------------------------------------- VRChat 전송
class Output:
    """VRChat 채팅박스로 보내는 창구. 전송 간격 제한을 지키며 별도 스레드에서 보냅니다."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.q = queue.Queue()
        self._client, self._key = None, None
        threading.Thread(target=self._run, daemon=True).start()

    def _get(self):
        key = (self.cfg["osc_ip"], int(self.cfg["osc_port"]))
        if key != self._key:
            self._client, self._key = SimpleUDPClient(*key), key
        return self._client

    def send(self, text):
        while self.q.qsize() >= 3:  # 밀리면 오래된 것 버림
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        self.q.put(text)

    def typing(self, on):
        try:
            self._get().send_message("/chatbox/typing", bool(on))
        except Exception:
            pass

    def _run(self):
        last = 0.0
        while True:
            msg = self.q.get()
            wait = CHATBOX_INTERVAL - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
            try:
                self._get().send_message("/chatbox/input", [msg, True, False])
            except Exception as e:
                log_error(f"osc send: {e}")
            last = time.time()


# ---------------------------------------------------------------- 엔진
class Engine:
    """start() 하면 모델 로딩 -> 마이크 수신 -> 인식 -> 번역 -> 전송.
    UI와는 events 큐(("result"|"error"|"info", ...))로만 통신합니다."""

    def __init__(self, cfg, output, events):
        self.cfg, self.out, self.events = cfg, output, events
        self.running = False
        self.ready = False
        self.paused = False
        self.vrc_muted = False
        self.level = 0.0
        self.model = None
        self.in_sr = SR
        self.audio_q = queue.Queue()
        self.utt_q = queue.Queue()
        self._osc_server = None
        self._thread = None

    @property
    def alive(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False

    # -- 모델 -------------------------------------------------------------
    def _model_name(self, device):
        """auto: GPU면 small, CPU면 코어 수에 맞춰 가볍게 선택 (가벼움 우선)."""
        name = self.cfg["model"]
        if name != "auto":
            return name
        cores = os.cpu_count() or 4
        return "small" if device == "cuda" or cores >= 8 else "base" if cores >= 4 else "tiny"

    def _load_model(self):
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        _add_cuda_dll_dirs()
        from faster_whisper import WhisperModel
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        dev = self.cfg["device_type"]
        tries = ([("cuda", "float16")] if dev in ("auto", "cuda") else []) + [("cpu", "int8")]
        last = None
        for device, compute in tries:
            try:
                m = WhisperModel(self._model_name(device), device=device, compute_type=compute,
                                 download_root=str(MODEL_DIR), cpu_threads=4)
                # 워밍업: GPU 라이브러리가 없으면 여기서 실패 -> CPU로 자동 전환
                list(m.transcribe(np.zeros(SR, dtype=np.float32), language="en")[0])
                return m, device
            except Exception as e:
                last = e
                log_error(f"load_model {device}: {e}")
        raise last

    # -- 메인 스레드 ------------------------------------------------------
    def _run(self):
        stream = None
        try:
            self.model, device = self._load_model()
            self.events.put(("info", "info_gpu" if device == "cuda" else "info_cpu"))
            threading.Thread(target=self._worker, daemon=True).start()
            self._start_mute_listener()
            stream = self._open_stream()
            self.ready = True
            self._capture_loop()
        except Exception as e:
            log_error(f"engine: {e!r}")
            self.events.put(("error", str(e)))
        finally:
            self.running = False
            self.ready = False
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            if self._osc_server is not None:
                threading.Thread(target=self._osc_server.shutdown, daemon=True).start()
            self.model = None
            gc.collect()

    def _open_stream(self):
        import sounddevice as sd
        dev = _resolve_mic(self.cfg["mic"])
        err = None
        for rate in (SR, None):
            if rate is None:
                rate = int(sd.query_devices(dev, "input")["default_samplerate"])
            try:
                s = sd.InputStream(samplerate=rate, channels=1, dtype="float32", device=dev,
                                   callback=self._callback, blocksize=int(rate * CHUNK_SEC))
                s.start()
                self.in_sr = rate
                return s
            except Exception as e:
                err = e
        raise err

    def _callback(self, indata, frames, t, status):
        x = indata[:, 0]
        if self.in_sr != SR:
            n = int(len(x) * SR / self.in_sr)
            x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
        else:
            x = x.copy()
        self.audio_q.put(x)

    # -- VRChat 뮤트 연동 -------------------------------------------------
    def _start_mute_listener(self):
        if not self.cfg["vrc_mute_sync"]:
            return
        try:
            from pythonosc.dispatcher import Dispatcher
            from pythonosc.osc_server import ThreadingOSCUDPServer
            d = Dispatcher()
            d.map("/avatar/parameters/MuteSelf", lambda addr, *a: setattr(self, "vrc_muted", bool(a and a[0])))
            self._osc_server = ThreadingOSCUDPServer((self.cfg["osc_ip"], int(self.cfg["osc_in_port"])), d)
            threading.Thread(target=self._osc_server.serve_forever, daemon=True).start()
        except OSError:
            self._osc_server = None
            self.events.put(("info", "info_osc_busy"))

    # -- 음성 구간 자르기 -------------------------------------------------
    def _capture_loop(self):
        c = self.cfg
        pre = collections.deque(maxlen=6)  # 말 시작 직전 0.3초 (첫 음절 잘림 방지)
        buf, speaking, silent, voiced = [], False, 0.0, 0.0
        while self.running:
            try:
                chunk = self.audio_q.get(timeout=0.2)
            except queue.Empty:
                continue
            dur = len(chunk) / SR
            rms = float(np.sqrt(np.mean(chunk ** 2)))
            self.level = rms
            if self.paused or self.vrc_muted:
                buf, speaking, silent, voiced = [], False, 0.0, 0.0
                pre.clear()
                continue
            threshold = 0.002 + 0.05 * (1 - c["sensitivity"] / 100) ** 2
            if rms > threshold:
                if not speaking:
                    speaking, buf, voiced = True, list(pre), 0.0
                silent = 0.0
                voiced += dur
            elif speaking:
                silent += dur
            if speaking:
                buf.append(chunk)
                total = sum(len(b) for b in buf) / SR
                if silent >= c["silence_sec"] or total >= c["max_sec"]:
                    if voiced >= 0.25:
                        while self.utt_q.qsize() >= 3:
                            try:
                                self.utt_q.get_nowait()
                            except queue.Empty:
                                break
                        self.utt_q.put(np.concatenate(buf))
                    buf, speaking, silent, voiced = [], False, 0.0, 0.0
            else:
                pre.append(chunk)

    # -- 인식 + 번역 ------------------------------------------------------
    def _worker(self):
        while self.running:
            try:
                audio = self.utt_q.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._process(audio)
            except Exception as e:
                log_error(f"process: {e!r}")
                self.events.put(("error", str(e)))

    def _process(self, audio):
        c = self.cfg
        self.out.typing(True)
        lang = None if c["source"] == "auto" else c["source"]
        segs, info = self.model.transcribe(
            audio, language=lang, beam_size=1, vad_filter=True, condition_on_previous_text=False)
        text = "".join(s.text for s in segs if s.no_speech_prob < 0.6 and s.avg_logprob > -1.2).strip()
        low = text.lower()
        if not text or any(h in low and len(low) < len(h) + 12 for h in HALLUCINATIONS):
            self.out.typing(False)
            return
        src, tgt = info.language, c["target"]
        out = text
        if src != tgt:
            try:
                out = translate_text(text, src, tgt)
            except Exception as e:
                log_error(f"translate: {e!r}")
                self.events.put(("error", f"translate: {e}"))
                self.out.typing(False)
                return
        self.out.send(format_chatbox(out, text, c["show_original"]))
        self.events.put(("result", src, tgt, text, out))
