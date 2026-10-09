"""설정 저장/불러오기. 사용자 데이터는 %APPDATA%\\RabbitHaru 에 저장 (exe로 배포해도 안전)."""
import json
import os
import time
from pathlib import Path

APP_NAME = "RabbitHaru Translator"
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
    "source": "auto",         # auto / ko / ja / en
    "target": "ja",           # ko / ja / en
    "model": "small",         # tiny / base / small / medium / large-v3-turbo
    "device_type": "auto",    # auto / cuda / cpu
    "sensitivity": 60,        # 0~100 (높을수록 작은 소리도 인식)
    "silence_sec": 0.6,       # 이 시간 이상 조용하면 발화 종료
    "max_sec": 12.0,          # 발화 최대 길이
    "show_original": True,    # 채팅박스에 원문도 같이 표시
    "vrc_mute_sync": True,    # VRChat 뮤트 상태 연동
    "osc_ip": "127.0.0.1",
    "osc_port": 9000,         # VRChat 입력 포트
    "osc_in_port": 9001,      # VRChat 출력 포트 (뮤트 감지용)
    "last_seen_version": "",  # 업데이트 내역 자동 표시용
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    except Exception:
        pass
    if cfg["ui_lang"] not in ("ko", "ja", "en"):
        cfg["ui_lang"] = _system_ui_lang()
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
