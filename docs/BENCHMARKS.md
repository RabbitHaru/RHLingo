# RH Lingo benchmarks (v1.0.0-beta.1)

🇰🇷 한국어: [BENCHMARKS.ko.md](BENCHMARKS.ko.md)

Measured with the reproducible script [`tools/bench.py`](../tools/bench.py) (raw numbers: [`bench_results.json`](bench_results.json)).

## How to read these numbers

- **One PC, one run.** AMD Ryzen 7 9800X3D (8 cores / 16 threads), 64 GB RAM, Windows 11, CPU only (no GPU used). Normal desktop apps were open at the same time. Weaker PCs will be slower; the app picks a smaller speech model automatically on PCs with fewer cores (not measured here).
- **Synthetic speech.** Audio comes from Windows' built-in voices (Korean "Heami", English "Zira") with seeded noise mixed in, so every re-run is identical. Real voices and real microphones differ. Use the numbers to compare settings and to get the order of magnitude, not as promises.
- **No Japanese speech test**: Windows has no Japanese voice installed by default. Japanese is covered in the translation test only.
- Speech model: `small` (the default on 8+ cores). Translation: offline M2M100 "standard" (418M, int8).

## 1. Lightness

| What | Result |
|---|---|
| Installer | 66.6 MB |
| Installed size (app, without models) | 251 MB |
| Time from launching the exe to the window | 0.7 s |
| Memory, app idle | about 70 MB |
| CPU, app idle | 0.8% of one core |
| CPU while listening (silence) | 0.16% of one core |
| Speech model `small` | download 464 MB · loads in 1.8 s (warm) · +307 MB RAM |
| Offline translation model | download 494 MB · loads in 0.5 s · +513 MB RAM |

The speech model and the translation model are downloaded only after you approve it, and the app works without the translation model (transcription only, or an online service you enable).

## 2. Speed (end-to-end latency)

Time from **the last syllable of speech to the text arriving** (24 utterances each, real-time audio feed). It includes the 0.4 s of silence the app waits to be sure you finished.

| Condition | median | p90 | max |
|---|---|---|---|
| Speech → text, idle PC | 0.53 s | 0.60 s | 0.61 s |
| Speech → translated text (ko→ja, offline), idle PC | 0.74 s | 0.81 s | 0.87 s |
| Speech → text while 8 CPU-hog processes run | 0.57 s | 0.66 s | 0.70 s |

Parts: speech recognition alone takes about 0.17–0.20 s for a 3–4 s sentence; offline translation of one sentence takes about 0.18–0.21 s (p90 up to 0.47 s for ko→ja).

## 3. Speech-recognition accuracy

Character error rate (CER, lower is better) over the whole pipeline (detection → recognition), 8 Korean and 8 English sentences, 2 noise seeds. "Detected" = share of utterances the app picked up at all.

| Condition | CER Korean | CER English | CER all | Detected |
|---|---|---|---|---|
| Clean | 4.2% | 1.7% | 2.9% | 100% |
| Fan, SNR 10 dB | 16.4% | 2.1% | 9.3% | 100% |
| Mains hum, SNR 5 dB | 7.2% | 3.3% | 5.3% | 97% |
| Keyboard clicks, SNR 3 dB | 15.4% | 25.5% | 20.4% | 81% |
| Background voices, SNR 8 dB | 11.7% | 38.2% | 25.0% | 94% |
| Very quiet voice (10% volume) | – | – | – | **0%** |

Known weak spots, honestly:
- A **very quiet voice is not picked up** at the default sensitivity (40). Settings → Audio → "Auto-tune" fixes this for your microphone.
- Loud **keyboard clicks** and **other people talking nearby** raise the error rate a lot (English suffers most). A close-talking microphone helps more than any software filter; the built-in noise reduction is off by default because earlier tests showed it lowers accuracy.

## 4. Translation quality (offline "standard")

chrF score (0–100, higher is better; character n-gram overlap with a hand-written reference) on 8 parallel sentences per direction. A single human reference under-rates good paraphrases, so read this as a relative indicator: the absolute values look low even when the meaning is right.

| Direction | chrF |
|---|---|
| Japanese → English | 41.3 |
| English → Japanese | 38.3 |
| Korean → Japanese | 37.5 |
| Korean → English | 37.2 |
| Japanese → Korean | 23.6 |
| English → Korean | 22.5 |

Example (Korean → English): "안녕하세요, 오늘 처음 왔는데 월드가 정말 예뻐요." → "Hello, I came here for the first time today and world is really nice."

Into Korean the offline model is weakest (stiff wording, dropped particles); DeepL or Gemini with your own key translate better, and the "high quality" offline model (1.2 GB) is available in Settings (not benchmarked here).

## Reproduce

```bash
python tools/bench.py                       # everything (nothing is downloaded without your approval)
python tools/bench.py footprint speed       # only some parts
python tools/bench.py --mt-dir D:/tmp/mt --download-mt translate   # downloads the 494 MB translation model into a temp folder (only if you approve)
```
