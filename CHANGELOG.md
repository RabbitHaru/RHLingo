# Changelog

🇰🇷 한국어: [CHANGELOG.ko.md](CHANGELOG.ko.md)

## v1.0.0 — First release

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
