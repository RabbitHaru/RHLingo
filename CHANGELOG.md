# Changelog

🇰🇷 한국어: [CHANGELOG.ko.md](CHANGELOG.ko.md)

## Unreleased

### Added
- Google **Gemini** as an optional translation service (your own Google AI Studio key, official Gemini API). The key goes in a header, not the URL. The model name defaults to an always-latest alias and can be changed in Settings → Translation; if the model is retired the app finds a current one automatically. Settings and the privacy notice explain that content sent with a free quota may be used by Google to improve its products and reviewed by humans.
- **Setup wizard** (Inno Setup): per-user install without admin rights, Start Menu/desktop shortcuts, a rounded purple Windows 11-style look that follows light/dark mode, English/Korean/Japanese, and an uninstaller that asks before deleting your settings and models.

### Changed
- New simple **RH** bunny-ear icon for the app window, taskbar, exe and installer.

## v1.0.0-beta.1 — First beta

> Beta: the basics are verified with synthetic speech and noise tests. Real-world feedback is very welcome (see the Feedback tab or open an issue).

### Highlights
- Speech-to-text and translation for the VRChat chatbox (via OSC): Korean / Japanese / English.
- Local by default: speech recognition (faster-whisper) and translation (M2M100, offline) run on your PC. No usage limits, and your voice and sentences never leave your PC.

### Speech recognition
- 3x faster recognition: Whisper's input is sized to the utterance instead of a fixed 30 s (`small` model: about 0.73 s → 0.22 s). Repeated-sentence glitches are detected and retried automatically.
- About 0.9 s from the end of your speech to the translated text (16-core PC, `small` model; varies by PC).
- Live preview of what is being recognized while you speak. Models preload, so Start is instant.
- Model chosen automatically for your CPU (auto). GPU is used when available, with automatic CPU fallback.
- Custom words (names etc.) improve recognition and are kept as-is in translation.
- Transcribe-only mode (no translation).

### Microphone
- Noise reduction (off / light / strong) and automatic adaptation to background noise.
- Voice-band detection ignores desk knocks and thumps; sounds shorter than 0.1 s are ignored.
- Level meter (dB) with a threshold line, one-click "Auto-tune microphone", and a lower default sensitivity.

### Translation
- Offline translation (M2M100): no limits, about 0.2 s per sentence, no internet needed. The first use asks before downloading about 490 MB (checksum verified). Optional high-quality model (about 1.25 GB).
- Protects VRChat terms (mic, avatar, world, instance, mute) and your custom names. Long speech is split into sentences; Korean particles and Japanese spacing are fixed up.
- Optional online services with your own API key: DeepL and Google Cloud (official APIs), MyMemory (no key, daily limit). Keys are stored encrypted for your Windows account and used only after you consent.

### Models
- Settings → Speech recognition → Speech models: see which models are installed, with a **Download** button (asks first, shows the size and progress) and a **Delete** button for each.
- Choosing a model that is not installed asks before downloading; nothing is downloaded without your approval.

### App
- New landscape layout, separate settings window, light / dark theme, UI in Korean / Japanese / English.
- VRChat mute sync, pause button, type-to-translate box.
- App name changed to HaruMimi (by RabbitHaru).

### Privacy and data
- First-run privacy notice. Nothing leaves your PC without your consent; every download asks first and shows its size.
- Settings → Privacy: withdraw consent, delete all local data, read the privacy notice.
- Settings are stored in `%APPDATA%\RabbitHaru`.
- Third-party licenses are listed in `THIRD_PARTY_NOTICES.txt`.

### Fixes in this beta
- Fixed: the conversation list could not be scrolled, and the mouse wheel did nothing over Settings sliders. Scrolling is now twice as fast, and sliders no longer change when you scroll.
- Noise reduction is now **Off by default**. Our tests showed that filtering audio before Whisper lowered accuracy in most conditions (keyboard, background voices, quiet mics). "Light" and "Strong" remain as options and are marked as possibly lowering accuracy.
- Input sizing now adapts to your PC: it records the actual recognition time per input size and avoids slow ones, and uses 6 CPU threads so latency stays steadier while VRChat is running.
- Fixed: after stopping, the VRChat mute-sync port could stay open, so a restart might disable mute sync.
- Verified the Auto / GPU / CPU choice: without the NVIDIA CUDA libraries the app falls back to the CPU safely, and switching back and forth no longer risks a hang.

### Known limitations
- GPU acceleration needs the NVIDIA CUDA libraries (cuBLAS / cuDNN), which are not bundled. Without them the app runs on the CPU.
- Translation quality of the offline model is limited (DeepL with your own key is more accurate).
- The exe is not code-signed, so Windows SmartScreen may warn you: choose "More info" → "Run anyway".
