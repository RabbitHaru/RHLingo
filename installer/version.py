"""build.bat 에서 설치 마법사에 넘길 버전 값을 출력: `python installer\\version.py full` -> 1.0.0-beta.1, `num` -> 1.0.0.0"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rh.config import APP_VERSION  # noqa: E402

if sys.argv[1:] == ["num"]:
    print(".".join((re.findall(r"\d+", APP_VERSION.split("-")[0]) + ["0"] * 4)[:4]))
else:
    print(APP_VERSION)
