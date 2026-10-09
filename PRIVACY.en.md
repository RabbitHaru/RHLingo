Privacy notice (RH Lingo by RabbitHaru)

■ The developer does not collect, store or receive any personal data.
The app has no accounts, analytics, ads or remote logging.

■ Stays on your PC
- Microphone audio: recognized locally (Whisper). It is never saved to a file or uploaded anywhere.
- Recognized text (chat history): shown on screen only and gone when you close the app. Never saved to a file.

■ Network connections (only after your consent / approval)
1) Translation - the default offline translator sends nothing. The following applies only if you choose an online service and agree.
   - Sent: the recognized sentence as text (never your voice)
   - To: the ONE translation service you pick in Settings (all official APIs)
       · MyMemory (no key, daily usage limit)
       · DeepL (your own API key)
       · Google Gemini API (your own Google AI Studio key). Content sent with a free quota may be used by Google to improve its products and reviewed by humans, and Google asks you not to send personal or confidential information (paid use with billing enabled is treated differently)
     Servers may be abroad. If a request fails, the text is never silently sent to another service.
   - Purpose: translation. The developer stores nothing; each service has its own privacy policy.
   - If you don't agree, the app only transcribes. You can withdraw any time in Settings → Privacy.
   - API keys are stored encrypted on this PC (tied to your Windows account) and sent only to the service you chose.
2) Model downloads (speech recognition model, offline translation model) - you are told the size and asked every time (huggingface.co). Downloaded files are verified by checksum (SHA-256).
   - Using an already downloaded model needs no internet access.
3) Update check - optional (off by default). When on, or when you press "Check for updates now", it asks github.com for the list of releases. Installing an update is never automatic: the app asks every time, shows the download size, downloads the installer from this project's GitHub releases, verifies its SHA-256 checksum (a file that fails is discarded), and only then runs it.
4) Sending to VRChat - only to VRChat on the same PC (127.0.0.1). Text shown in the VRChat chatbox is visible to others in your world, so what you say is your responsibility.
5) Feedback - the button opens a GitHub issue form in your browser; you review and submit it yourself. App version, Windows version and model name are pre-filled, so check before submitting.

■ Stored on your PC (in %APPDATA%\RabbitHaru)
- config.json: settings (selected microphone name, languages, consent choices, encrypted API keys)
- log.txt: error log (no conversation content)
- models\: downloaded speech and translation models
- Settings → Privacy → "Delete all local data" removes everything at once.

■ Contact: Issues on the GitHub repository
