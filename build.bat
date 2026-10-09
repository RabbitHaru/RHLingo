@echo off
rem RHLingo 배포용 빌드: dist\RHLingo\ (exe 폴더) + dist\RHLingo-Setup-v버전-win64.exe (설치 마법사, Inno Setup 6 필요)
cd /d "%~dp0"
set PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
if not exist "%PY%" set PY=python
"%PY%" -m pip install pyinstaller
"%PY%" -m PyInstaller --noconfirm --clean --windowed --name RHLingo --icon installer\RHLingo.ico --add-data "installer\RHLingo.ico;." --add-data "installer\RHLingo_logo.png;." --add-data "installer\RHLingo_logo_s.png;." ^
  --add-data "CHANGELOG.md;." --add-data "CHANGELOG.ko.md;." ^
  --add-data "PRIVACY.ko.md;." --add-data "PRIVACY.en.md;." --add-data "PRIVACY.ja.md;." --add-data "THIRD_PARTY_NOTICES.txt;." ^
  --collect-all customtkinter ^
  --collect-all faster_whisper ^
  --collect-all ctranslate2 ^
  --collect-binaries onnxruntime --collect-binaries sentencepiece ^
  --exclude-module matplotlib --exclude-module scipy --exclude-module pandas --exclude-module torch ^
  RHLingo.py
for /f %%v in ('"%PY%" installer\version.py full') do set VER=%%v
for /f %%v in ('"%PY%" installer\version.py num') do set VERNUM=%%v
set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if exist "%ISCC%" ("%ISCC%" "/DAppVersion=%VER%" "/DAppVersionNum=%VERNUM%" installer\RHLingo.iss) else echo Inno Setup 6 not found - skipping installer
pause
