"""설정 저장/불러오기. 사용자 데이터는 %APPDATA%\\RabbitHaru 에 저장 (exe로 배포해도 안전)."""
import copy
import json
import os
import time
from pathlib import Path

APP_NAME = "HaruMimi"  # 앱 이름은 여기와 i18n.py 의 title/tagline 에서만 바꾸면 됩니다
APP_VERSION = "1.0.0"

DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "RabbitHaru"
CONFIG_PATH = DATA_DIR / "config.json"
MODEL_DIR = DATA_DIR / "models"
LOG_PATH = DATA_DIR / "log.txt"


def _system_ui_lang():
    try:
        import ctypes
        primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return {0x12: "ko", 0x11: "ja"}.get(primary, "en")
    except Exception:
        return "en"


DEFAULTS = {
    "ui_lang": None,          # None = 시스템 언어 따라감 (ko/ja/en)
    "theme": "system",        # system / light / dark
    "always_on_top": False,
    "mic": None,              # None = 기본 장치
    "source": None,           # None = 앱 언어와 같게 / auto / ko / ja / en
    "target": None,           # None = 앱 언어에 따라 자동 (ko->ja, ja->ko, en->ja) / ko / ja / en
    "model": "auto",          # auto(PC 사양에 맞게) / tiny / base / small / medium / large-v3-turbo
    "device_type": "auto",    # auto / cuda / cpu
    "sensitivity": 50,        # 0~100 (높을수록 작은 소리도 인식)
    "silence_sec": 0.4,       # 이 시간 이상 조용하면 발화 종료
    "max_sec": 12.0,          # 발화 최대 길이
    "show_original": True,    # 채팅박스에 원문도 같이 표시
    "vrc_mute_sync": True,    # VRChat 뮤트 상태 연동
    "osc_ip": "127.0.0.1",
    "osc_port": 9000,         # VRChat 입력 포트
    "osc_in_port": 9001,      # VRChat 출력 포트 (뮤트 감지용)
    "noise_reduction": "low", # off / low / high (소음 제거)
    "keep_model": True,       # 모델을 메모리에 유지 -> 시작 즉시
    "live_preview": None,     # None = PC 사양에 따라 자동 (말하는 중 미리보기)
    "vocab": "",              # 자주 쓰는 단어(이름 등) - 인식 도우미
    "translator": "local",    # local(오프라인·한도 없음, 기본) / mymemory / deepl / google (사용자 본인의 공식 API 키)
    "mt_quality": "standard", # 오프라인 번역 품질: standard(가볍고 빠름) / high(더 자연스러움, 1.25GB)
    "api_keys": {},           # {서비스: DPAPI로 암호화된 키}
    "consent_done": False,    # 첫 실행 개인정보 안내를 봤는지
    "consent_translate": False,  # 번역을 위해 인식된 문장을 Google 번역 서버로 전송하는 것에 동의
    "consent_update": False,  # 새 버전 확인(github.com 접속)에 동의
    "last_seen_version": "",  # 업데이트 내역 자동 표시용
}


def load_config():
    cfg = copy.deepcopy(DEFAULTS)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))  # 메모장 등이 붙인 BOM도 허용
        cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    except Exception:
        pass
    if cfg["ui_lang"] not in ("ko", "ja", "en"):
        cfg["ui_lang"] = _system_ui_lang()
    if cfg["source"] not in ("auto", "ko", "ja", "en"):
        cfg["source"] = cfg["ui_lang"]  # 내가 쓰는 언어로 말한다고 가정 (작은 모델도 정확해짐)
    if cfg["target"] not in ("ko", "ja", "en", "off"):  # off = 번역 없이 받아쓰기만
        cfg["target"] = {"ko": "ja", "ja": "ko"}.get(cfg["ui_lang"], "ja")
    return cfg


def save_config(cfg):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(CONFIG_PATH)
    except Exception as e:
        log_error(f"save_config: {e}")


def log_error(msg):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 200_000:
            LOG_PATH.unlink()
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass
