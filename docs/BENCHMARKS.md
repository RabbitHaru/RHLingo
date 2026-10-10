# RH Lingo benchmarks (v1.0.0-beta.3)

🇰🇷 한국어: [BENCHMARKS.ko.md](BENCHMARKS.ko.md)

Sections 1, 2 and 4 were measured on beta.2 (idle PC); sections 3 and 5 on the beta.3 engine. Measured with the reproducible script [`tools/bench.py`](../tools/bench.py) (raw numbers: [`bench_results.json`](bench_results.json)).

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

## 3. Speech-recognition accuracy (`small`, beta.3 engine)

Character error rate (CER, lower is better) over the whole pipeline (detection → recognition), 8 Korean and 8 English sentences, 2 noise seeds. "Detected" = share of utterances the app picked up at all.

| Condition | CER Korean | CER English | CER all | Detected |
|---|---|---|---|---|
| Clean | 3.2% | 0.5% | 1.9% | 100% |
| Fan, SNR 10 dB | 13.1% | 1.0% | 7.0% | 100% |
| Mains hum, SNR 5 dB | 2.6% | 0.5% | 1.5% | 100% |
| Keyboard clicks, SNR 3 dB | 14.8% | 25.5% | 20.2% | 81% |
| Background voices, SNR 8 dB | 9.1% | 3.2% | 6.1% | 100% |
| Very quiet voice (10% volume) | – | – | – | **0%** |

beta.3 changes (same corpus, small model): a wider search (beam 5) cut the error rate on background voices from 25% to 10%, and accepting very short speech (0.15 s instead of 0.35 s, with a call-word hint for one-word clips) raised recognition of short calls such as "야", "네", "Hey" from 11 of 27 to 27 of 27 without false triggers on fan, hum, keyboard or silence.

Known weak spots, honestly:
- A **very quiet voice is not picked up** at the default sensitivity (40). Settings → Microphone → "Auto-tune" fixes this for your microphone.
- Loud **keyboard clicks** raise the error rate (and 19% of utterances are missed). A close-talking microphone helps more than any software filter; the built-in noise reduction is off by default because earlier tests showed it lowers accuracy.

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

## 5. Which model? (value comparison)

Same corpus and noise conditions for every model (beta.3 engine, CPU only). CER is the mean of the five audible conditions above (clean, fan, hum, keyboard, background voices). "Recognition step" is the time Whisper needs for a 3–4 s sentence; it was measured **while VRChat and Unity were running** on this PC, so it is slower than on an idle PC (small: about 190 ms idle) and is only meant for comparing models.

| Speech model | Download | CER (mean) | Clean | Fan | Keyboard | Background voices | Recognition step |
|---|---|---|---|---|---|---|---|
| tiny | 75 MB | 23.5% | 7.8% | 28.1% | 33.7% | 33.0% | 90 ms |
| base | 145 MB | 16.8% | 8.0% | 19.1% | 30.5% | 21.3% | 138 ms |
| **small** | 480 MB | **10.0%** | 1.2% | 14.6% | 26.8% | 7.1% | 439 ms |
| medium | 1.5 GB | 7.1% | 0.2% | 3.6% | 25.2% | 6.4% | 1178 ms |
| large-v3-turbo | 1.6 GB | 9.5% | 3.8% | 8.1% | 27.1% | 5.6% | 1098 ms |

- **small is the best value**: base is 6.8 points worse, medium is only 2.9 points better but 3× the download and about 2.7× slower, and large-v3-turbo is not better than small on a CPU.
- **base** is the fallback for low-end PCs (4–7 cores); **tiny** is too inaccurate to recommend; **medium / large-v3-turbo** only make sense with a GPU.
- The app's *auto* setting follows this: small on 8+ cores, base on 4+, tiny otherwise.

| Offline translation model | Download | RAM | chrF (mean of 6 directions) | ko→en | ja→ko | ko→ja | One sentence (busy PC) |
|---|---|---|---|---|---|---|---|
| **Standard** (M2M100 418M) | 494 MB | +513 MB | 33.4 | 37.2 | 23.6 | 37.5 | 0.49 s |
| High quality (M2M100 1.2B) | 1.25 GB | +1236 MB | 36.6 | 44.2 | 38.2 | 30.5 | 0.81 s |

- **Standard is the better default**: the high-quality model is +3.2 chrF on average but needs 2.5× the memory, is slower, and is worse for Korean → Japanese. It helps mostly for Japanese → Korean (+14.6) and Korean → English (+7.0).

## 6. GPU (NVIDIA RTX 5080, optional acceleration pack)

Same corpus and conditions as section 5, speech models on the GPU (float16) with the optional pack (cuBLAS 12.9 + cuDNN 9.27, 1.24 GB download). Measured while VRChat was running.

| Speech model | Device | Recognition step | CER (mean) | Clean | Fan | Keyboard | Background voices |
|---|---|---|---|---|---|---|---|
| small | CPU | 439 ms | 10.0% | 1.2% | 14.6% | 26.8% | 7.1% |
| small | **GPU** | 85 ms | 9.3% | 0.9% | 12.2% | 27.1% | 5.2% |
| large-v3-turbo | CPU | 1098 ms | 9.5% | 3.8% | 8.1% | 27.1% | 5.6% |
| large-v3-turbo | **GPU** | **59 ms** | **8.0%** | 0.2% | 8.5% | 27.6% | 2.9% |

- With an NVIDIA GPU, **large-v3-turbo on the GPU is the best choice**: about 18× faster than the same model on the CPU, and the most accurate of the models measured on a GPU or CPU except medium on the CPU (7.1%, but about 20× slower).
- Without a GPU, small stays the best value.
