"""음성 인식 + 번역 + VRChat OSC 전송 엔진 (UI와 독립). 무거운 모듈은 필요할 때만 불러옵니다."""
import collections
import gc
import hashlib
import html
import json
import os
import queue
import shutil
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from pythonosc.udp_client import SimpleUDPClient

from . import secret
from .config import MODEL_DIR, log_error

SR = 16000
CHUNK_SEC = 0.05
CHATBOX_LIMIT = 144
CHATBOX_INTERVAL = 1.3  # VRChat 채팅박스 전송 최소 간격(초)
MM_CODES = {"ko": "ko-KR", "ja": "ja-JP", "en": "en-US"}

MODEL_REPOS = {
    "tiny": "Systran/faster-whisper-tiny", "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small", "medium": "Systran/faster-whisper-medium",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}
MODEL_SIZES_MB = {"tiny": 75, "base": 145, "small": 480, "medium": 1500, "large-v3-turbo": 1600}

# Whisper가 무음/잡음에서 자주 내뱉는 환각 문구
HALLUCINATIONS = (
    "ご視聴ありがとうございました", "ご視聴ありがとうございます", "チャンネル登録",
    "시청해 주셔서 감사합니다", "시청해주셔서 감사합니다", "구독과 좋아요", "자막 제공",
    "thanks for watching", "thank you for watching", "subtitles by", "please subscribe",
)

NR_ALPHA = {"off": 0.0, "low": 1.0, "high": 2.0}  # 노이즈 제거 강도


# ---------------------------------------------------------------- GPU(CUDA) 사용 가능 여부
def _add_cuda_dll_dirs():
    """pip로 설치된 nvidia-cublas/cudnn DLL(또는 exe에 포함된 것)을 찾아 등록."""
    roots = [Path(sys._MEIPASS) / "nvidia"] if hasattr(sys, "_MEIPASS") else []
    roots += [Path(p) / "nvidia" for p in sys.path if p]
    for root in roots:
        for bin_dir in root.glob("*/bin") if root.is_dir() else []:
            try:
                os.add_dll_directory(str(bin_dir))
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
            except OSError:
                pass


_cuda_ok = None


def cuda_usable():
    """라이브러리가 실제로 있을 때만 GPU 사용. (없는데 시도하면 재시도 때 멈추는 문제가 있어 미리 확인)"""
    global _cuda_ok
    if _cuda_ok is None:
        try:
            import ctypes
            _add_cuda_dll_dirs()
            ctypes.WinDLL("cublas64_12.dll")
            ctypes.WinDLL("cudnn64_9.dll")
            import ctranslate2
            _cuda_ok = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            _cuda_ok = False
    return _cuda_ok


# ---------------------------------------------------------------- 모델 관리
def model_name(cfg):
    """auto: PC 코어 수에 맞춰 가볍게 선택 (GPU 유무와 무관 -> 예상 못한 추가 다운로드 방지)."""
    name = cfg["model"]
    if name != "auto":
        return name
    cores = os.cpu_count() or 4
    return "small" if cores >= 8 else "base" if cores >= 4 else "tiny"


def model_cached(name):
    snaps = MODEL_DIR / ("models--" + MODEL_REPOS[name].replace("/", "--")) / "snapshots"
    return snaps.is_dir() and any((s / "model.bin").exists() for s in snaps.iterdir())


def preview_default(device="cpu"):
    return device == "cuda" or (os.cpu_count() or 4) >= 8


def _dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    return total


_MODEL_LOCK = threading.Lock()
_MODEL = {"key": None, "model": None, "device": None}


def release_model():
    with _MODEL_LOCK:
        _MODEL.update(key=None, model=None, device=None)
    gc.collect()


def get_model(cfg, progress=None):
    """(모델, 장치) 반환. 같은 설정이면 메모리에 올려둔 모델을 재사용해 시작이 즉시 됩니다."""
    name = model_name(cfg)
    key = (name, cfg["device_type"])
    with _MODEL_LOCK:
        if _MODEL["key"] == key and _MODEL["model"] is not None:
            return _MODEL["model"], _MODEL["device"]
        _MODEL.update(key=None, model=None, device=None)
        gc.collect()
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        from faster_whisper import WhisperModel
        MODEL_DIR.mkdir(parents=True, exist_ok=True)

        cached = model_cached(name)
        stop = threading.Event()
        if progress is not None and not cached:  # 다운로드 진행률(폴더 크기 증가량으로 계산)
            base, expected = _dir_size(MODEL_DIR), MODEL_SIZES_MB[name] * 1e6

            def poll():
                while not stop.is_set():
                    progress(min(99, int((_dir_size(MODEL_DIR) - base) / expected * 100)))
                    stop.wait(0.5)
            threading.Thread(target=poll, daemon=True).start()

        tries = ([("cuda", "float16")] if cfg["device_type"] in ("auto", "cuda") and cuda_usable() else [])
        tries.append(("cpu", "int8"))
        last = None
        try:
            for device, compute in tries:
                try:
                    m = WhisperModel(name, device=device, compute_type=compute, download_root=str(MODEL_DIR),
                                     local_files_only=cached, cpu_threads=min(8, os.cpu_count() or 4))
                    # 워밍업: 첫 인식이 느려지지 않게 미리 한 번 돌려둠 (GPU 오류도 여기서 걸러짐)
                    list(m.transcribe(np.zeros(SR, dtype=np.float32), language="en")[0])
                    _MODEL.update(key=key, model=m, device=device)
                    return m, device
                except Exception as e:
                    last = e
                    log_error(f"load_model {device}: {e!r}")
            raise last
        finally:
            stop.set()
            if progress is not None:
                progress(None)


# ---------------------------------------------------------------- 음량 / 민감도 / 소음
def threshold_for(sensitivity):
    """민감도(0~100) -> 음성 감지 기준 음량(RMS). 높을수록 작은 소리도 감지."""
    return 0.002 + 0.05 * (1 - sensitivity / 100) ** 2


def meter_value(rms):
    """RMS -> 0~1 막대 길이 (작은 소리도 보이게 제곱근 스케일)."""
    return min(1.0, (rms / 0.05) ** 0.5)


class NoiseFloor:
    """최근 6초의 '조용한 순간' 음량을 재서, 주변 소음이 크면 감지 기준을 자동으로 올림."""

    def __init__(self):
        self.hist = collections.deque(maxlen=120)
        self.floor, self._n = 0.0, 0

    def update(self, rms):
        self.hist.append(rms)
        self._n += 1
        if self._n % 10 == 0 and len(self.hist) >= 20:
            self.floor = float(np.percentile(self.hist, 20))

    def threshold(self, sensitivity):
        base = threshold_for(sensitivity)
        return max(base, min(self.floor * 2.5, base * 2.5))  # 자동 상승은 최대 2.5배까지


_N, _HOP = 1024, 256
_WIN = np.hanning(_N).astype(np.float32)


def noise_spectrum(chunk):
    """조용한 구간 한 조각의 크기 스펙트럼 (노이즈 프로필용)."""
    w = np.hanning(len(chunk)).astype(np.float32)
    return np.abs(np.fft.rfft(chunk * w, n=_N)) / (w.sum() / 2)


def denoise(audio, noise_mag, alpha):
    """스펙트럼 게이팅: 조용한 구간에서 측정한 소음 프로필을 빼고, 80Hz 이하 저음 잡음도 제거."""
    if noise_mag is None or alpha <= 0 or len(audio) < _N:
        return audio
    x = np.pad(audio, (_N, _N))
    n_frames = 1 + (len(x) - _N) // _HOP
    idx = np.arange(_N)[None, :] + _HOP * np.arange(n_frames)[:, None]
    spec = np.fft.rfft(x[idx] * _WIN, axis=1)
    mag = np.abs(spec) / (_WIN.sum() / 2)
    mask = np.clip(1 - alpha * noise_mag[None, :] / np.maximum(mag, 1e-8), 0.08, 1.0)
    mask[:, :5] = 0.0  # 80Hz 이하
    frames = np.fft.irfft(spec * mask, n=_N, axis=1) * _WIN
    out = np.zeros(len(x), dtype=np.float32)
    for i in range(n_frames):
        out[i * _HOP:i * _HOP + _N] += frames[i]
    return (out / 1.5)[_N:-_N].astype(np.float32)


class MicMonitor:
    """모델 없이 마이크 음량만 측정 (설정 창에서 민감도 맞출 때 사용)."""

    def __init__(self, mic):
        self.mic, self.level, self._stream = mic, 0.0, None
        self.nf = NoiseFloor()

    def start(self):
        try:
            import sounddevice as sd
            dev = _resolve_mic(self.mic)
            rate = int(sd.query_devices(dev, "input")["default_samplerate"])
            self._stream = sd.InputStream(samplerate=rate, channels=1, dtype="float32", device=dev,
                                          callback=self._cb, blocksize=int(rate * CHUNK_SEC))
            self._stream.start()
        except Exception as e:
            log_error(f"mic monitor: {e}")
            self._stream = None

    def _cb(self, indata, frames, t, status):
        rms = float(np.sqrt(np.mean(indata ** 2)))
        self.nf.update(rms)
        self.level = max(rms, self.level * 0.85)  # 천천히 내려오게 해서 읽기 쉽게

    def stop(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


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


# ---------------------------------------------------------------- 번역 (공식 API 만 사용)
class TranslateError(Exception):
    pass


def _http_json(url, body=None, headers=None, timeout=8):
    data = None if body is None else json.dumps(body).encode("utf-8")
    h = {"User-Agent": "HaruMimi", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=h, method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise TranslateError({401: "invalid API key", 403: "invalid API key", 429: "rate limited",
                              456: "monthly quota exceeded"}.get(e.code, f"HTTP {e.code}"))
    except (urllib.error.URLError, TimeoutError, OSError):
        raise TranslateError("network error")


def _mymemory(text, src, tgt, key=None):
    pair = f"{MM_CODES.get(src, 'autodetect')}|{MM_CODES[tgt]}"
    r = _http_json("https://api.mymemory.translated.net/get?" +
                   urllib.parse.urlencode({"q": text[:450], "langpair": pair}))
    out = (r.get("responseData") or {}).get("translatedText", "")
    if r.get("responseStatus") != 200 or not out or "MYMEMORY WARNING" in out:
        raise TranslateError("daily limit reached (MyMemory)")
    return html.unescape(out)


def _deepl(text, src, tgt, key):
    host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
    body = {"text": [text], "target_lang": {"ko": "KO", "ja": "JA", "en": "EN-US"}[tgt]}
    if src in MM_CODES:
        body["source_lang"] = src.upper()
    r = _http_json(f"https://{host}/v2/translate", body,
                   {"Authorization": f"DeepL-Auth-Key {key}", "Content-Type": "application/json"})
    return r["translations"][0]["text"]


def _google_cloud(text, src, tgt, key):
    body = {"q": text, "target": tgt, "format": "text"}
    if src in MM_CODES:
        body["source"] = src
    r = _http_json("https://translation.googleapis.com/language/translate/v2", body,
                   {"X-goog-api-key": key, "Content-Type": "application/json"})
    return html.unescape(r["data"]["translations"][0]["translatedText"])



# ---------------------------------------------------------------- 오프라인 번역 (M2M100 418M, MIT 라이선스)
# 한도 없음 / 인터넷 불필요 / 문장이 PC 밖으로 나가지 않음. 받은 파일은 SHA-256 으로 검증합니다.
MT_NAME = "m2m100-418m-int8"
MT_BASE_URL = "https://huggingface.co/gn64/M2M100_418M_CTranslate2/resolve/main/"
MT_FILES = {  # 파일명: (SHA-256, 크기)
    "config.json": ("8f6496adfc930cbfecbe8281112197705c488fab47d34b4829b06d7f478909af", 223),
    "sentencepiece.bpe.model": ("d8f7c76ed2a5e0822be39f0a4f95a55eb19c78f4593ce609e2edbc2aea4d380a", 2423393),
    "shared_vocabulary.json": ("7eb5d0ff184c6095c7c10f9911c0aea492250abd12854f9c3d787c64b1c6397e", 2796509),
    "model.bin": ("a1826980fc5c037e69c7ac94fcb56c03001a66f380eb71863cc0a3879e71421b", 490667752),
}
MT_SIZE_MB = 494
MT_DIR = MODEL_DIR / MT_NAME


def mt_cached():
    return all((MT_DIR / n).exists() and (MT_DIR / n).stat().st_size == sz for n, (_, sz) in MT_FILES.items())


def download_mt(progress=None, base_url=MT_BASE_URL, target_dir=None):
    """오프라인 번역 모델 다운로드 (호출 전에 사용자 허락을 받을 것). 해시가 다르면 폐기."""
    d = Path(target_dir or MT_DIR)
    tmp = d.with_name(d.name + ".part")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    total, done = sum(sz for _, sz in MT_FILES.values()), 0
    try:
        for name, (digest, _) in MT_FILES.items():
            h = hashlib.sha256()
            req = urllib.request.Request(base_url + name, headers={"User-Agent": "HaruMimi"})
            with urllib.request.urlopen(req, timeout=30) as r, open(tmp / name, "wb") as out:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(min(99, int(done * 100 / total)))
            if h.hexdigest() != digest:
                raise TranslateError(f"checksum mismatch: {name}")
        shutil.rmtree(d, ignore_errors=True)
        tmp.replace(d)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    finally:
        if progress:
            progress(None)


_mt = {"tr": None, "sp": None}
_mt_lock = threading.Lock()


def release_mt():
    with _mt_lock:
        _mt.update(tr=None, sp=None)
    gc.collect()


def guess_lang(text):
    for ch in text:
        if 0xAC00 <= ord(ch) <= 0xD7A3 or 0x1100 <= ord(ch) <= 0x11FF:
            return "ko"
    for ch in text:
        if 0x3040 <= ord(ch) <= 0x30FF or 0x4E00 <= ord(ch) <= 0x9FFF:
            return "ja"
    return "en"


def _local(text, src, tgt, key=None):
    if not mt_cached():
        raise TranslateError("offline model not downloaded")
    with _mt_lock:
        if _mt["tr"] is None:
            import ctranslate2
            import sentencepiece
            _mt["sp"] = sentencepiece.SentencePieceProcessor(model_file=str(MT_DIR / "sentencepiece.bpe.model"))
            _mt["tr"] = ctranslate2.Translator(str(MT_DIR), device="cpu", compute_type="int8", inter_threads=1,
                                               intra_threads=min(8, os.cpu_count() or 4))
        tr, sp = _mt["tr"], _mt["sp"]
        s = src if src and sp.piece_to_id(f"__{src}__") != sp.unk_id() else guess_lang(text)
        toks = [f"__{s}__"] + sp.encode(text, out_type=str) + ["</s>"]  # M2M100 은 종료 토큰을 직접 붙여야 함
        r = tr.translate_batch([toks], target_prefix=[[f"__{tgt}__"]], beam_size=2, max_decoding_length=96,
                               repetition_penalty=1.15, no_repeat_ngram_size=3)
        out = sp.decode(r[0].hypotheses[0][1:]).strip()
    if not out:
        raise TranslateError("empty translation")
    return out

PROVIDERS = {"local": (_local, False), "mymemory": (_mymemory, False), "deepl": (_deepl, True),
             "google": (_google_cloud, True)}


def translation_allowed(cfg):
    """오프라인 번역은 문장이 PC 밖으로 나가지 않으므로 동의 불필요. 온라인 서비스는 동의 필요."""
    return cfg.get("translator", "local") == "local" or bool(cfg.get("consent_translate"))


def translate_text(cfg, text, src, tgt):
    """사용자가 고른 번역 서비스 하나로만 보냄 (실패해도 다른 서비스로 몰래 보내지 않음)."""
    name = cfg.get("translator", "local")
    fn, needs_key = PROVIDERS.get(name, PROVIDERS["local"])
    key = secret.decrypt(cfg.get("api_keys", {}).get(name, ""))
    if needs_key and not key:
        raise TranslateError("API key not set")
    last = None
    for _ in range(2):
        try:
            return fn(text, src, tgt, key)
        except TranslateError as e:
            last = e
            if "network" not in str(e):
                break
            time.sleep(0.3)
    raise last


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
    """start() 하면 모델 준비 -> 마이크 수신 -> 인식 -> 번역 -> 전송.
    UI와는 events 큐(("result"|"partial"|"error"|"info", ...))로만 통신합니다."""

    def __init__(self, cfg, output, events):
        self.cfg, self.out, self.events = cfg, output, events
        self.running = False
        self.ready = False
        self.paused = False
        self.vrc_muted = False
        self.speaking = False
        self.level = 0.0
        self.dl_pct = None  # 모델 다운로드 진행률 (None = 해당 없음)
        self.device = "cpu"
        self.model = None
        self.in_sr = SR
        self.nf = NoiseFloor()
        self.noise_mag = None
        self.audio_q = queue.Queue()
        self.utt_q = queue.Queue()
        self.partial_q = queue.Queue(maxsize=1)
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

    # -- 메인 스레드 ------------------------------------------------------
    def _run(self):
        stream = None
        try:
            self.model, self.device = get_model(self.cfg, lambda p: setattr(self, "dl_pct", p))
            self.events.put(("info", "info_gpu" if self.device == "cuda" else "info_cpu"))
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
            self.speaking = False
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            if self._osc_server is not None:
                threading.Thread(target=self._osc_server.shutdown, daemon=True).start()
            self.model = None
            if not self.cfg.get("keep_model", True):
                release_model()
                release_mt()

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
    def _preview_on(self):
        p = self.cfg.get("live_preview")
        return preview_default(self.device) if p is None else bool(p)

    def _capture_loop(self):
        c = self.cfg
        pre = collections.deque(maxlen=6)  # 말 시작 직전 0.3초 (첫 음절 잘림 방지)
        buf, silent, voiced, total, last_partial = [], 0.0, 0.0, 0.0, 0.0
        while self.running:
            try:
                chunk = self.audio_q.get(timeout=0.2)
            except queue.Empty:
                continue
            dur = len(chunk) / SR
            rms = float(np.sqrt(np.mean(chunk ** 2)))
            self.level = rms
            self.nf.update(rms)
            if self.paused or self.vrc_muted:
                buf, silent, voiced, total = [], 0.0, 0.0, 0.0
                self.speaking = False
                pre.clear()
                continue
            thr = self.nf.threshold(c["sensitivity"])
            if rms > thr:
                if not self.speaking:
                    self.speaking, buf, voiced = True, list(pre), 0.0
                    total, last_partial = len(buf) * dur, 0.0
                silent = 0.0
                voiced += dur
            elif self.speaking:
                silent += dur
            if self.speaking:
                buf.append(chunk)
                total += dur
                if silent >= c["silence_sec"] or total >= c["max_sec"]:
                    if voiced >= 0.35:
                        while self.utt_q.qsize() >= 3:
                            try:
                                self.utt_q.get_nowait()
                            except queue.Empty:
                                break
                        self.utt_q.put(np.concatenate(buf))
                    buf, silent, voiced, total = [], 0.0, 0.0, 0.0
                    self.speaking = False
                elif (total >= 0.8 and total - last_partial >= 1.0 and self.utt_q.empty()
                      and self.partial_q.empty() and self._preview_on()):
                    last_partial = total
                    self.partial_q.put_nowait(np.concatenate(buf))  # 말하는 중 미리보기용
            else:
                pre.append(chunk)
                if rms < thr:  # 조용한 구간으로 소음 프로필 갱신
                    m = noise_spectrum(chunk)
                    self.noise_mag = m if self.noise_mag is None else 0.95 * self.noise_mag + 0.05 * m

    # -- 인식 + 번역 ------------------------------------------------------
    def _worker(self):
        while self.running:
            try:
                audio = self.utt_q.get(timeout=0.05)
            except queue.Empty:
                try:
                    part = self.partial_q.get_nowait()
                except queue.Empty:
                    continue
                try:
                    self._partial(part)
                except Exception as e:
                    log_error(f"partial: {e!r}")
                continue
            try:
                self._process(audio)
            except Exception as e:
                log_error(f"process: {type(e).__name__}")
                self.events.put(("error", str(e)))

    def _transcribe(self, audio):
        c = self.cfg
        audio = denoise(audio, self.noise_mag, NR_ALPHA.get(c.get("noise_reduction", "low"), 1.0))
        peak = float(np.max(np.abs(audio)))
        if 0.01 < peak < 0.5:  # 작은 마이크 소리를 키워 인식률 향상
            audio = audio * (0.7 / peak)
        lang = None if c["source"] == "auto" else c["source"]
        segs, info = self.model.transcribe(
            audio, language=lang, beam_size=1, vad_filter=True, condition_on_previous_text=False,
            temperature=0.0, without_timestamps=True, hotwords=(c["vocab"].strip() or None))
        text = "".join(s.text for s in segs if s.no_speech_prob < 0.6 and s.avg_logprob > -1.2).strip()
        low = text.lower()
        if any(h in low and len(low) < len(h) + 12 for h in HALLUCINATIONS):
            text = ""
        return text, info.language

    def _partial(self, audio):
        text, _ = self._transcribe(audio)
        if text and self.speaking:  # 이미 말이 끝났으면 버림
            self.events.put(("partial", text))

    def _process(self, audio):
        c = self.cfg
        self.out.typing(True)
        text, src = self._transcribe(audio)
        if not text:
            self.out.typing(False)
            return
        tgt = c["target"] if translation_allowed(c) else "off"  # 온라인 번역은 동의가 있을 때만
        out = text
        if tgt != "off" and src != tgt:
            try:
                out = translate_text(c, text, src, tgt)
            except Exception as e:
                if "not downloaded" in str(e):  # 오프라인 모델이 아직 없음 -> 받아쓰기만, 안내는 한 번
                    if not getattr(self, "_warned_mt", False):
                        self._warned_mt = True
                        self.events.put(("info", "info_need_mt"))
                    out, tgt = text, "off"
                else:
                    log_error(f"translate: {type(e).__name__}")
                    self.events.put(("error", f"translate: {e}"))
                    self.out.typing(False)
                    return
        self.out.send(format_chatbox(out, text, c["show_original"] and tgt != "off"))
        self.events.put(("result", src, tgt, text, out))
