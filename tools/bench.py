"""RH Lingo 벤치마크 (재현 가능). 가벼움 · 속도 · 정확도를 재서 JSON 으로 저장해요.

    python tools/bench.py                 # 전부
    python tools/bench.py footprint speed # 일부만 (footprint | speed | stt | translate)
    (Nothing is downloaded unless you pass --download-stt / --download-mt, which you should only do after approving the size.)
    python tools/bench.py --mt-dir D:/tmp/mt --download-mt translate   # 번역 모델이 없으면 (사용자가 허락한 경우에만) 그 폴더에 받아서 측정

- 음성은 Windows 에 기본 설치된 SAPI 합성 음성(ko-KR Heami, en-US Zira)으로 만들어요. 소음은 시드 고정 난수라 다시 돌려도 같아요.
  (일본어 합성 음성이 기본 설치돼 있지 않아 일본어 음성 인식은 재지 않아요. 번역은 일본어도 글자 기준으로 재요.)
- 사람 목소리와 실제 마이크가 아니라 합성 음성이라서, 절대 수치보다 '설정끼리 비교'와 '대략적인 규모'를 보는 용도예요.
- 이 PC 의 설정·모델 폴더(%APPDATA%\\RabbitHaru)는 읽기만 해요 (모델이 없으면 해당 항목은 건너뜀).
"""
import ctypes
import json
import os
import queue
import re
import statistics as st
import subprocess
import sys
import tempfile
import threading
import zlib
import time
import wave
from ctypes import wintypes
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SR = 16000
OUT = ROOT / "docs" / "bench_results.json"
AUDIO_DIR = Path(tempfile.gettempdir()) / "rhl_bench_audio"
RESULT = {}

# ───────────────────────────── 말뭉치 ─────────────────────────────
# 한/영/일 같은 뜻의 문장 (번역 품질 정답으로도 씀). 직접 쓴 문장이라 저작권 문제 없음.
PARALLEL = [
    ("안녕하세요, 오늘 처음 왔는데 월드가 정말 예뻐요.", "Hello, this is my first time here and the world is really beautiful.", "こんにちは、今日初めて来たんですが、このワールドはとても綺麗ですね。"),
    ("이 아바타 어디서 샀어요? 정말 귀엽네요.", "Where did you get this avatar? It's really cute.", "このアバターはどこで買ったんですか?すごくかわいいですね。"),
    ("잠깐만요, 마이크 소리가 잘 들리는지 확인해 볼게요.", "Hold on, let me check whether you can hear my microphone.", "ちょっと待ってください、マイクの音が聞こえるか確認してみます。"),
    ("친구들이 곧 올 거니까 인스턴스에 초대해 드릴게요.", "My friends will be here soon, so I'll invite you to the instance.", "友達がもうすぐ来るので、インスタンスに招待しますね。"),
    ("오늘 밤에 같이 놀 수 있으면 좋겠어요.", "I hope we can hang out together tonight.", "今夜一緒に遊べたらいいですね。"),
    ("일본어를 공부하고 있어서 천천히 말해 주세요.", "I'm studying Japanese, so please speak slowly.", "日本語を勉強中なので、ゆっくり話してください。"),
    ("사진 찍어도 될까요? 포즈 취해 드릴게요.", "May I take a picture? I'll strike a pose.", "写真を撮ってもいいですか?ポーズをとりますね。"),
    ("방금 월드가 렉이 심했는데 다시 들어가 볼게요.", "The world was lagging badly just now, so I'll rejoin.", "さっきワールドがすごくラグかったので、入り直してみます。"),
]
LANG_IDX = {"ko": 0, "en": 1, "ja": 2}
SPEECH = {  # 음성 인식에 쓸 문장 (한국어 8개, 영어 8개) = PARALLEL 의 ko / en
    **{f"ko{i}": ("ko", p[0]) for i, p in enumerate(PARALLEL)},
    **{f"en{i}": ("en", p[1]) for i, p in enumerate(PARALLEL)},
}
BABBLE_TEXT = ["Yeah I was thinking we could go to that new club world later", "그래서 내가 어제 말했잖아 그거 진짜 웃기다니까"]
VOICES = {"ko": "Microsoft Heami Desktop", "en": "Microsoft Zira Desktop"}


# ───────────────────────────── 측정 도구 ─────────────────────────────
class _PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


def _open(pid):
    k = ctypes.windll.kernel32
    k.OpenProcess.restype = wintypes.HANDLE
    return k.OpenProcess(0x1000 | 0x0400 | 0x0010, False, pid)  # QUERY_LIMITED | QUERY_INFORMATION | VM_READ


def rss_mb(pid=None):
    h = _open(pid or os.getpid())
    pmc = _PMC(); pmc.cb = ctypes.sizeof(_PMC)
    ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
    ctypes.windll.kernel32.CloseHandle(h)
    return pmc.WorkingSetSize / 1048576


def cpu_seconds(pid=None):
    h = _open(pid or os.getpid())
    c, e, k, u = (wintypes.FILETIME() for _ in range(4))
    ctypes.windll.kernel32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u))
    ctypes.windll.kernel32.CloseHandle(h)
    t = lambda f: ((f.dwHighDateTime << 32) | f.dwLowDateTime) / 1e7
    return t(k) + t(u)


def tree_rss_mb(pid):
    """자식 프로세스까지 합친 메모리 (PyInstaller 부트로더가 자식을 만들 수 있어서)."""
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"(Get-CimInstance Win32_Process | Where-Object {{ $_.ProcessId -eq {pid} -or $_.ParentProcessId -eq {pid} }}).ProcessId -join ','"],
                         capture_output=True, text=True).stdout.strip()
    return sum(rss_mb(int(p)) for p in out.split(",") if p.isdigit()), [int(p) for p in out.split(",") if p.isdigit()]


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def summarize(xs):
    return {"n": len(xs), "p50": round(pct(xs, 50), 3), "p90": round(pct(xs, 90), 3), "max": round(max(xs), 3), "mean": round(st.mean(xs), 3)}


def norm(t): return re.sub(r"[\s\.,!?'\-、。！？]+", "", t).lower()


def cer(ref, hyp):
    r, h = norm(ref), norm(hyp)
    d = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        prev, d[0] = d[0], i
        for j, hc in enumerate(h, 1):
            cur = d[j]; d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (rc != hc)); prev = cur
    return d[len(h)] / max(1, len(r))


def chrf(ref, hyp, n=6, beta=2.0):
    """chrF (문자 n-gram F-score, 0~100). 공백은 무시."""
    r, h = re.sub(r"\s+", "", ref), re.sub(r"\s+", "", hyp)
    ps, rs = [], []
    for k in range(1, n + 1):
        from collections import Counter
        rc = Counter(r[i:i + k] for i in range(len(r) - k + 1)); hc = Counter(h[i:i + k] for i in range(len(h) - k + 1))
        if not rc or not hc:
            continue
        m = sum((rc & hc).values())
        ps.append(m / sum(hc.values())); rs.append(m / sum(rc.values()))
    if not ps:
        return 0.0
    p, rr = st.mean(ps), st.mean(rs)
    return 0.0 if p + rr == 0 else 100 * (1 + beta ** 2) * p * rr / (beta ** 2 * p + rr)


# ───────────────────────────── 합성 음성 ─────────────────────────────
def make_audio():
    AUDIO_DIR.mkdir(exist_ok=True)
    items = {**SPEECH, "bab0": ("en", BABBLE_TEXT[0]), "bab1": ("ko", BABBLE_TEXT[1])}
    todo = {k: v for k, v in items.items() if not (AUDIO_DIR / f"{k}.wav").exists()}
    if todo:
        man = [{"wav": str(AUDIO_DIR / f"{k}.wav"), "voice": VOICES[l], "text": t} for k, (l, t) in todo.items()]
        (AUDIO_DIR / "man.json").write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")
        ps = (AUDIO_DIR / "tts.ps1")
        ps.write_text('Add-Type -AssemblyName System.Speech\n$m = Get-Content -Raw -Encoding UTF8 "' + str(AUDIO_DIR / "man.json") + '" | ConvertFrom-Json\n'
                      '$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\nforeach ($i in $m) { $s.SelectVoice($i.voice); $s.SetOutputToWaveFile($i.wav); $s.Speak($i.text); $s.SetOutputToNull() }\n',
                      encoding="utf-8-sig")
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps)], check=True)


def load_clip(name):
    w = wave.open(str(AUDIO_DIR / f"{name}.wav")); sr = w.getframerate()
    raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    a = np.interp(np.linspace(0, len(raw) - 1, int(len(raw) * SR / sr)), np.arange(len(raw)), raw).astype(np.float32)
    a *= 0.25 / np.max(np.abs(a))
    rms = np.array([np.sqrt(np.mean(a[i:i + 800] ** 2)) for i in range(0, len(a) - 800, 800)])
    nz = np.nonzero(rms > 0.008)[0]
    return a[int(nz.min()) * 800: int(nz.max()) * 800 + 800]


# ───────────────────────────── 소음 조건 (시드 고정) ─────────────────────────────
rng = np.random.default_rng(1)
def rms_(x): return float(np.sqrt(np.mean(x ** 2)))
def n_fan(n):
    x = rng.standard_normal(n + 400).astype(np.float32)
    return (np.convolve(x, np.ones(8) / 8, "same")[:n] + 0.3 * rng.standard_normal(n)).astype(np.float32)
def n_hum(n):
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 100 * t) + 0.6 * np.sin(2 * np.pi * 200 * t) + 0.4 * np.sin(2 * np.pi * 300 * t) + 0.05 * rng.standard_normal(n)).astype(np.float32)
def n_keys(n):
    x = np.zeros(n, dtype=np.float32)
    for pos in rng.integers(0, max(1, n - 400), max(1, int(6 * n / SR))):
        L = int(rng.integers(80, 200)); x[pos:pos + L] += (rng.standard_normal(L) * np.exp(-np.arange(L) / 30)).astype(np.float32)
    return x + 0.01 * rng.standard_normal(n).astype(np.float32)
_BAB = None
def n_babble(n):
    global _BAB
    if _BAB is None:
        _BAB = np.concatenate([load_clip("bab0"), load_clip("bab1")])
    return np.resize(_BAB, n)

CONDS = [("clean", None, None), ("quiet voice (x0.1)", "quiet", None), ("fan, SNR 10 dB", n_fan, 10), ("mains hum, SNR 5 dB", n_hum, 5),
         ("keyboard, SNR 3 dB", n_keys, 3), ("background voices, SNR 8 dB", n_babble, 8)]


def build(sig, cond):
    name, gen, snr = cond
    if gen == "quiet":
        sig = sig * 0.1
        lead = (rng.standard_normal(SR) * 0.0015).astype(np.float32)
        return sig + (rng.standard_normal(len(sig)) * 0.0015).astype(np.float32), lead, lead[:int(0.4 * SR)]
    if gen is None:
        z = lambda k: (rng.standard_normal(k) * 0.002).astype(np.float32)
        return sig + z(len(sig)), z(SR), z(int(0.4 * SR))
    full = gen(len(sig) + int(1.4 * SR) + 400)
    lead_n, mix_n, tail_n = full[:SR], full[SR:SR + len(sig)], full[SR + len(sig): SR + len(sig) + int(0.4 * SR)]
    sc = rms_(sig) / (10 ** (snr / 20)) / max(rms_(mix_n), 1e-9)
    return sig + mix_n * sc, lead_n * sc, tail_n * sc


# ───────────────────────────── 엔진 실행 도우미 ─────────────────────────────
class TimedQueue(queue.Queue):
    def put(self, item, *a, **k):
        super().put((time.perf_counter(), item), *a, **k)


class FakeOut:
    def send(self, t): pass
    def typing(self, on): pass


def run_engine(cfg, model, stream, realtime=False, speech_end_idx=None, settle=0.8, limit=20):
    """오디오를 엔진에 흘려 보내고 결과 이벤트(텍스트, 번역, 도착시각)를 돌려줘요. realtime 이면 실제 속도로 넣어요."""
    from rh import engine as E
    ev = TimedQueue()
    eng = E.Engine(cfg, FakeOut(), ev); eng.model, eng.device = model, "cpu"; eng.running = True
    threading.Thread(target=eng._worker, daemon=True).start(); threading.Thread(target=eng._capture_loop, daemon=True).start()
    t0 = time.perf_counter()
    step = 800
    if realtime:
        for i in range(0, len(stream), step):
            eng.audio_q.put(stream[i:i + step])
            time.sleep(max(0, t0 + (i + step) / SR - time.perf_counter()))
    else:
        for i in range(0, len(stream), step):
            eng.audio_q.put(stream[i:i + step])
        while time.perf_counter() - t0 < 6 and (not eng.audio_q.empty() or not eng.utt_q.empty()):
            time.sleep(0.02)
    last_n, last_t = 0, time.perf_counter()
    while time.perf_counter() - last_t < settle and time.perf_counter() - t0 < limit + len(stream) / SR:
        if ev.qsize() != last_n:
            last_n, last_t = ev.qsize(), time.perf_counter()
        time.sleep(0.03)
    eng.running = False
    res = []
    while not ev.empty():
        ts, e = ev.get_nowait()
        if e[0] == "result":
            res.append((e[3], e[4], ts))
    return res, t0


def load_stt(cfg):
    """음성 인식 모델을 불러옴. 받아 둔 게 없으면 --download-stt 가 있을 때만 받음 (사용자 허락 없이는 아무것도 받지 않음)."""
    from rh import engine as E
    name = E.model_name(cfg)
    if not E.model_cached(name) and "--download-stt" not in sys.argv:
        sys.exit(f"The speech model '{name}' is not installed, and this benchmark never downloads without your approval. "
                 f"Install it from the app (Start asks first), or re-run with --download-stt if you approve the download (~{E.MODEL_SIZES_MB[name]} MB).")
    return E.get_model(cfg)


def base_cfg(**kw):
    from rh.config import load_config
    cfg = load_config()
    cfg.update(model="small", vocab="", sensitivity=40, silence_sec=0.4, live_preview=False, noise_reduction="off", target="off", translator="local", consent_translate=True)
    cfg.update(kw)
    return cfg


# ───────────────────────────── 1) 가벼움 ─────────────────────────────
def stage_footprint():
    r = {}
    dist = ROOT / "dist"
    inst = next(iter(dist.glob("RHLingo-Setup*.exe")), None)
    folder = dist / "RHLingo"
    if inst:
        r["installer_mb"] = round(inst.stat().st_size / 1048576, 1)
    if folder.exists():
        r["install_folder_mb"] = round(sum(f.stat().st_size for f in folder.rglob("*") if f.is_file()) / 1048576)
        exe = folder / "RHLingo.exe"
        appdata = Path(tempfile.mkdtemp())  # 내 설정은 건드리지 않고, '이미 시작해 본 사용자' 상태의 임시 설정으로 실행
        (appdata / "RabbitHaru").mkdir()
        from rh.config import APP_VERSION as _v
        (appdata / "RabbitHaru" / "config.json").write_text(json.dumps({"consent_done": True, "last_seen_version": _v, "ui_lang": "en"}), encoding="utf-8")
        env = {**os.environ, "APPDATA": str(appdata)}
        t0 = time.perf_counter()
        p = subprocess.Popen([str(exe)], env=env)
        user32 = ctypes.windll.user32
        found = None
        buf = ctypes.create_unicode_buffer(256)
        proc_ids, last_scan = {p.pid}, 0.0
        def cb(h, _):
            nonlocal found
            if user32.IsWindowVisible(h):
                pid = wintypes.DWORD(); user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
                user32.GetWindowTextW(h, buf, 256)
                if pid.value in proc_ids and "RH Lingo" in buf.value:
                    found = time.perf_counter() - t0
            return True
        cbf = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb)
        while time.perf_counter() - t0 < 30 and not found:
            if time.perf_counter() - last_scan > 1.0:  # 자식 프로세스 목록은 1초에 한 번만 갱신
                proc_ids = set(tree_rss_mb(p.pid)[1]) or {p.pid}; last_scan = time.perf_counter()
            user32.EnumWindows(cbf, 0)
            time.sleep(0.05)
        r["startup_to_window_s"] = round(found, 2) if found else None
        time.sleep(5)
        mb, ids = tree_rss_mb(p.pid)
        c0 = sum(cpu_seconds(i) for i in ids); t1 = time.perf_counter()
        time.sleep(10)
        c1 = sum(cpu_seconds(i) for i in ids)
        r["exe_idle_ram_mb"] = round(mb)
        r["exe_idle_cpu_pct_of_one_core"] = round(100 * (c1 - c0) / (time.perf_counter() - t1), 2)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    # 모델 로드/메모리 (이 프로세스 안에서)
    from rh import engine as E
    cfg = base_cfg()
    base = rss_mb()
    t = time.perf_counter(); model, dev = load_stt(cfg); r["stt_load_s"] = round(time.perf_counter() - t, 2)
    r["stt_device"] = dev; r["stt_ram_added_mb"] = round(rss_mb() - base)
    r["stt_model"] = E.model_name(cfg)
    # 듣는 중(무음) CPU. 모델을 올린 직후 몇 초는 워밍업이라 그 뒤부터 잼
    time.sleep(10)
    ev = TimedQueue()
    eng = E.Engine(cfg, FakeOut(), ev); eng.model, eng.device = model, "cpu"; eng.running = True
    threading.Thread(target=eng._worker, daemon=True).start(); threading.Thread(target=eng._capture_loop, daemon=True).start()
    c0, t0 = cpu_seconds(), time.perf_counter()
    z = lambda: (np.random.default_rng(0).standard_normal(800) * 0.002).astype(np.float32)
    for i in range(0, 10 * SR, 800):
        eng.audio_q.put(z()); time.sleep(max(0, t0 + (i + 800) / SR - time.perf_counter()))
    r["listening_silence_cpu_pct_of_one_core"] = round(100 * (cpu_seconds() - c0) / (time.perf_counter() - t0), 2)
    eng.running = False
    if E.mt_cached("standard"):
        base = rss_mb()
        t = time.perf_counter(); E.preload_mt(cfg)
        # preload 는 백그라운드일 수 있어서 첫 번역으로 로드를 끝까지 기다림
        E.translate_text(cfg, "안녕하세요", "ko", "en")
        r["mt_load_s"] = round(time.perf_counter() - t, 2); r["mt_ram_added_mb"] = round(rss_mb() - base)
    RESULT["footprint"] = r
    print("footprint:", json.dumps(r, ensure_ascii=False))


# ───────────────────────────── 2) 속도 ─────────────────────────────
def stage_speed(repeats=3):
    from rh import engine as E
    cfg = base_cfg()
    model, _ = load_stt(cfg)
    global rng
    out = {}

    def measure(label, tgt, load_procs=0):
        procs = [subprocess.Popen([sys.executable, "-c", "while True: pass"]) for _ in range(load_procs)]
        time.sleep(1.0 if procs else 0)
        lat, whisper_only = [], []
        try:
            for rep in range(repeats):
                rng = np.random.default_rng(100 + rep)
                globals()["rng"] = rng
                for i in range(len(PARALLEL)):
                    lang, ref = SPEECH[f"ko{i}"]
                    sig = load_clip(f"ko{i}")
                    mixed, lead, tail = build(sig, CONDS[0])
                    stream = np.concatenate([lead, mixed, tail, np.zeros(int(0.9 * SR), np.float32) + lead[:1]]).astype(np.float32)
                    c = dict(cfg, target=tgt, source="ko")
                    res, t0 = run_engine(c, model, stream, realtime=True, settle=0.5)
                    if res:
                        speech_end = t0 + (len(lead) + len(mixed)) / SR
                        lat.append(res[-1][2] - speech_end)
        finally:
            for p in procs:
                p.kill()
        out[label] = summarize(lat)
        print(f"speed [{label}]:", out[label], flush=True)

    measure("STT only, idle PC", "off")
    measure("STT + offline translation ko->ja, idle PC", "ja")
    measure(f"STT only, {max(4, (os.cpu_count() or 8) // 2)} CPU-hog processes", "off", load_procs=max(4, (os.cpu_count() or 8) // 2))
    # 번역만 (문장 단위)
    if E.mt_cached("standard"):
        cfg2 = base_cfg(source="ko", target="ja")
        E.translate_text(cfg2, "안녕하세요", "ko", "ja")  # 로드
        for src, tgt in (("ko", "ja"), ("ko", "en"), ("en", "ko"), ("ja", "ko")):
            ts = []
            for rep in range(3):
                for p in PARALLEL:
                    t = time.perf_counter(); E.translate_text(cfg2, p[LANG_IDX[src]], src, tgt); ts.append(time.perf_counter() - t)
            out[f"translation only {src}->{tgt}"] = summarize(ts)
            print(f"speed [translation {src}->{tgt}]:", out[f"translation only {src}->{tgt}"], flush=True)
    # Whisper 만 (발화 길이별)
    wl = {}
    for i in range(len(PARALLEL)):
        sig = load_clip(f"ko{i}")
        ts = []
        for _ in range(5):
            t = time.perf_counter()
            E.transcribe_adaptive(model, sig, "ko")
            ts.append(time.perf_counter() - t)
        wl[f"ko{i} ({len(sig) / SR:.1f}s audio)"] = round(st.median(ts), 3)
    out["whisper_only_median_s"] = wl
    RESULT["speed"] = out


# ───────────────────────────── 3) 음성 인식 정확도 ─────────────────────────────
def stage_stt(seeds=(1, 2)):
    from rh import engine as E
    cfg = base_cfg()
    model, _ = load_stt(cfg)
    global rng
    scores = {c[0]: {"ko": [], "en": []} for c in CONDS}
    detected = {c[0]: [0, 0] for c in CONDS}
    for seed in seeds:
        for k, (lang, ref) in SPEECH.items():
            sig = load_clip(k)
            for cond in CONDS:
                globals()["rng"] = np.random.default_rng(seed * 1000 + zlib.crc32(k.encode()) % 997 + len(cond[0]))
                mixed, lead, tail = build(sig, cond)
                stream = np.concatenate([lead, mixed, np.resize(np.concatenate([tail, lead]), int(1.4 * SR))]).astype(np.float32)
                res, _ = run_engine(dict(cfg, source=lang), model, stream)
                text = " ".join(r[0] for r in res)
                detected[cond[0]][0] += bool(res); detected[cond[0]][1] += 1
                scores[cond[0]][lang].append(cer(ref, text))
        print("stt seed", seed, "done", flush=True)
    out = {}
    for name, d in scores.items():
        allv = d["ko"] + d["en"]
        out[name] = {"CER_ko_pct": round(100 * st.mean(d["ko"]), 1), "CER_en_pct": round(100 * st.mean(d["en"]), 1),
                     "CER_all_pct": round(100 * st.mean(allv), 1), "detected_pct": round(100 * detected[name][0] / detected[name][1])}
        print("stt", name, out[name], flush=True)
    RESULT["stt"] = {"model": E.model_name(cfg), "conditions": out}


# ───────────────────────────── 4) 번역 품질 ─────────────────────────────
def stage_translate():
    from rh import engine as E
    if not E.mt_cached("standard"):
        print("offline translation model not installed - skipped"); return
    out = {}
    for tier in ("standard", "high"):
        if not E.mt_cached(tier):
            continue
        cfg = base_cfg(mt_quality=tier)
        E.release_mt()
        E.translate_text(cfg, "안녕하세요", "ko", "en")
        res = {}
        for src, tgt in (("ko", "en"), ("ko", "ja"), ("en", "ko"), ("en", "ja"), ("ja", "ko"), ("ja", "en")):
            scs = []; ex = None
            for p in PARALLEL:
                hyp = E.translate_text(cfg, p[LANG_IDX[src]], src, tgt)
                scs.append(chrf(p[LANG_IDX[tgt]], hyp))
                ex = ex or (p[LANG_IDX[src]], hyp, p[LANG_IDX[tgt]])
            res[f"{src}->{tgt}"] = {"chrF": round(st.mean(scs), 1), "example": ex}
            print("translate", tier, src, tgt, res[f"{src}->{tgt}"]["chrF"], flush=True)
        out[tier] = res
    RESULT["translate"] = out


def main():
    args = sys.argv[1:]
    mt_dir = None
    if "--mt-dir" in args:  # 오프라인 번역 모델을 이 폴더에서 찾고(없으면 --download-mt 일 때만 받음). 내 설정 폴더는 건드리지 않음
        i = args.index("--mt-dir"); mt_dir = Path(args[i + 1]); del args[i:i + 2]
    download = "--download-mt" in args
    args = [a for a in args if a not in ("--download-mt", "--download-stt")]
    stages = args or ["footprint", "speed", "stt", "translate"]
    if OUT.exists():
        try:
            RESULT.update(json.loads(OUT.read_text(encoding="utf-8")))  # 일부 단계만 다시 돌려도 이전 결과를 유지
        except Exception:
            pass
    RESULT["machine"] = {"cpu_threads": os.cpu_count(), "python": sys.version.split()[0]}
    try:
        from rh.config import APP_VERSION
        RESULT["app_version"] = APP_VERSION
    except Exception:
        pass
    if mt_dir is not None:
        from rh import engine as E
        E.mt_dir = lambda tier="standard": mt_dir / E.MT_MODELS[tier]["name"]
        if download and not E.mt_cached("standard"):
            print("downloading offline translation model (user approved) ->", mt_dir, flush=True)
            mt_dir.mkdir(parents=True, exist_ok=True)
            E.download_mt("standard", progress=lambda p: p is not None and p % 20 == 0 and print(f"  {p}%", flush=True))
    make_audio()
    for s in stages:
        print(f"== {s}", flush=True)
        globals()[f"stage_{s}"]()
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(json.dumps(RESULT, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", OUT)


if __name__ == "__main__":
    main()
