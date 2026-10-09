@echo off
rem HaruMimi 배포용 exe 빌드 -> dist\HaruMimi\ 폴더를 zip으로 묶어 배포하세요.
cd /d "%~dp0"
set PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
if not exist "%PY%" set PY=python
"%PY%" -m pip install pyinstaller
"%PY%" -m PyInstaller --noconfirm --clean --windowed --name HaruMimi ^
  --add-data "CHANGELOG.md;." --add-data "CHANGELOG.ko.md;." ^
  --add-data "PRIVACY.ko.md;." --add-data "PRIVACY.en.md;." --add-data "PRIVACY.ja.md;." --add-data "THIRD_PARTY_NOTICES.txt;." ^
  --collect-all customtkinter ^
  --collect-all faster_whisper ^
  --collect-all ctranslate2 ^
  --collect-binaries onnxruntime --collect-binaries sentencepiece ^
  --exclude-module matplotlib --exclude-module scipy --exclude-module pandas --exclude-module torch ^
  HaruMimi.py
pause
