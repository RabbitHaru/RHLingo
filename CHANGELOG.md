# Changelog

🇰🇷 한국어: [CHANGELOG.ko.md](CHANGELOG.ko.md)

## Unreleased

### Added
- **Pause / resume hotkey** (Settings → General, off by default): a global shortcut that works while VRChat is in front, with a short beep so you know the state. It tells you if another program already uses the key.
- Your X (Twitter) link on the *About me* page.

## v1.0.0-beta.2 — New name, installer, one-click update

### Added
- Google **Gemini** as an optional translation service (your own Google AI Studio key, official Gemini API). The key goes in a header, not the URL. The model name defaults to an always-latest alias and can be changed in Settings → Translation; if the model is retired the app finds a current one automatically. Settings and the privacy notice explain that content sent with a free quota may be used by Google to improve its products and reviewed by humans.
- **Setup wizard** (Inno Setup): per-user install without admin rights, Start Menu/desktop shortcuts, a rounded purple Windows 11-style look that follows light/dark mode, English/Korean/Japanese, and an uninstaller that asks before deleting your settings and models.

- **One-click update**: "Check for updates now" (Settings → Privacy) and the optional startup check find newer releases, including betas if you run a beta. Installing asks every time, shows the size, verifies the installer's SHA-256 checksum, then updates and reopens the app (installed version only; the portable zip opens the release page instead).
- **About me** tab (inside ♥ About) with a small profile card, a note from the developer, links and a Special Thanks list.
- `tools/bench.py`: a reproducible benchmark (footprint, latency, speech-recognition accuracy, translation quality).

### Changed
- **Redesigned main screen**: languages are grouped in one card, then Start and status, with the mic level at the bottom. The developer's name is no longer on the main window or the title bar.
- **Far fewer startup popups**: the first run shows only the one privacy window (your choice is remembered and never asked again unless you reset it). After an update, a one-line note appears in the chat instead of opening a window.
- **About window** now uses a readable left menu instead of small tabs, and the update notes are formatted with headings and bullets.
- The meter no longer redraws when the level hasn't changed (lower idle CPU).
- The app is now called **RH Lingo** (was HaruMimi) to match its new simple **RH** bunny-ear icon, used for the window, taskbar, exe and installer. Settings and models in your user folder are unchanged.

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
