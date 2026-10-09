# 🐰 HaruMimi — by RabbitHaru

🇰🇷 한국어: [README.ko.md](README.ko.md)

> ⚠️ **Beta** (v1.0.0-beta.1): the basics are verified, but real-world feedback is very welcome. [Open an issue](https://github.com/RabbitHaru/HaruMimi/issues)

Speech-to-text and translator for the VRChat chatbox. Speak into your microphone → it recognizes your speech → (translates) → sends it to your VRChat chatbox via OSC. Korean / Japanese / English. Built for **accuracy, speed and a light footprint**.

## Quick start
1. In VRChat: Action Menu → Options → OSC → **Enabled**.
2. Run `HaruMimi.exe`, read the first-run privacy notice, pick a language to translate to (or "Transcribe only"), then press **Start**.
3. The first time, the app asks before downloading a speech model (it shows the size). You can also manage models in Settings → Speech recognition.

## Features
- Local speech recognition (faster-whisper): no usage limits, and your voice never leaves your PC.
- Offline translation (M2M100): no limits, about 0.2 s per sentence, and sentences stay on your PC. You can also connect DeepL / Google Cloud with your own API key.
- About 0.9 s from the end of your speech to the translated text (16-core PC, `small` model; varies by PC).
- Protects VRChat terms and your names in translation; Korean particle fix.
- Noise reduction, voice-band detection (ignores desk knocks), one-click microphone auto-tune.
- Live preview while you speak, transcribe-only mode, VRChat mute sync, type-to-translate.
- Light / dark theme, UI in Korean / Japanese / English.
- Runs on the CPU by default; GPU acceleration needs the NVIDIA CUDA libraries (not bundled), otherwise the app falls back to the CPU automatically.

## Privacy
The developer collects no personal data. Online translation services and update checks are used **only with your consent**, and every download **asks first**. Details: [English](PRIVACY.en.md) · [한국어](PRIVACY.ko.md) · [日本語](PRIVACY.ja.md)

## Development
```
pip install -r requirements.txt
python HaruMimi.py
```
Build the exe with `build.bat`. Settings and models are stored in `%APPDATA%\RabbitHaru`.
Release notes: [CHANGELOG.md](CHANGELOG.md). Release checklist: [RELEASING.md](RELEASING.md).

## Notices
- This is a personal project, not affiliated with, endorsed by or sponsored by VRChat Inc., OpenAI or Google LLC. "VRChat" is a trademark of VRChat Inc.; "Google" is a trademark of Google LLC.
- Translation runs on an offline model (M2M100, MIT License) by default. Online services (MyMemory / DeepL / Google Cloud) are used through their official APIs, only if you choose them and consent.
- No warranty is given for recognition or translation accuracy. You are responsible for what you send to the VRChat chatbox.
- Be mindful of other people's voices that may be picked up by your microphone, and of the laws and consent rules that apply to you.
- Open-source components and their licenses: [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).
- Licensed under the [MIT License](LICENSE). The software is provided "as is", without warranty of any kind.
