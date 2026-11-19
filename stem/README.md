# HO-ME stem

HO-ME spreekt met een eigen stem in plaats van de iPhone-stem, zodat je muziek blijft spelen (sinds iOS 27 stopt
élk woord van de iPhone-stem andere audio). Alles wat HO-ME zegt, wordt hier gemaakt en afgespeeld als gewoon
app-geluid (Web Audio).

- **Natuurlijke stem** (sinds v66.2): Piper-stemmen — standaard Nederlands (**Pim**), keuze Belgisch (**Nathalie**).
  HO-ME downloadt ze één keer vanzelf; het rekenen gebeurt in een Web Worker (`piper-worker.js`).
- **Robotstem** (sinds v66.1): eSpeak NG — praat meteen, en als vangnet zolang de natuurlijke stem nog niet klaar is.
  Dezelfde eSpeak maakt ook de fonemen voor de natuurlijke stem (`--ipa`, zoals Piper zelf).

De service worker (`sw.js`) bewaart deze map cache-first in een eigen cache (`home-stem`): de telefoon downloadt alles
maar één keer. **Een nieuwe versie van een bestand = een nieuwe naam**, anders blijft de oude uit de cache komen.
Uitzondering: `piper/stemmen.json` (welke stemmen er zijn) en `proef/` komen altijd eerst van het netwerk.

| Bestand | Wat | Licentie |
|---|---|---|
| `piper/nl_NL-pim-medium.onnx` (+ `.json`) | Piper-stem Pim (Nederlands) — rhasspy/piper-voices | CC0 (dataset), zie `piper/MODEL_CARD-*` |
| `piper/nl_BE-nathalie-medium.onnx` (+ `.json`) | Piper-stem Nathalie (Belgisch) — rhasspy/piper-voices | CC0 (dataset), zie `piper/MODEL_CARD-*` |
| `piper/stemmen.json` | welke stemmen HO-ME downloadt (NL = standaard, BE) — gemaakt door de Stem-fabriek | — |
| `piper-worker.js` | de rekenaar: fonemen (eSpeak) → ids (zoals Piper 1.3.0) → ONNX → geluid | van HO-ME |
| `ort.wasm.min.js`, `ort-wasm-simd-threaded.mjs`, `ort-wasm-simd-threaded.wasm` | ONNX Runtime Web 1.31.1 (npm `onnxruntime-web`), ongewijzigd | MIT, zie `LICENSE-onnxruntime` |
| `espeak-ng.wasm` | eSpeak NG 1.49.3-dev (git `e13b602ce0bd81bb5b84f03631819fb2820fe19f`), Emscripten — ongewijzigd uit npm **text2wav 0.0.14** | GPL-3.0, zie `COPYING` |
| `espeak-ng.js` | de Emscripten-lijm uit text2wav 0.0.14, **aangepast** voor de browser (onderaan: data uit `Module.stemBestanden` / `Module.stemExtra` in het geheugen-bestandssysteem i.p.v. NODEFS) | GPL-3.0 |
| `nl-data.bin` | alleen de Nederlandse eSpeak NG-data uit text2wav 0.0.14, in één bestand gezet met `maak-nl-data.py` | GPL-3.0 |
| `fabriek.py` | de Stem-fabriek (GitHub Action `.github/workflows/stem.yml`): haalt de Piper-stemmen, maakt `proef/` | van HO-ME |
| `proef/` | voorbeelden van alle Nederlandse/Vlaamse Piper-stemmen + Piper's eigen fonemen/ids (toetsmateriaal) | — |

## Broncode

- eSpeak NG: https://github.com/espeak-ng/espeak-ng (commit `e13b602ce0bd81bb5b84f03631819fb2820fe19f`)
- de Emscripten-build van eSpeak NG (text2wav): https://github.com/abbr/text2wav.node.js — npm `text2wav` 0.0.14
- Piper: https://github.com/OHF-Voice/piper1-gpl — stemmen: https://huggingface.co/rhasspy/piper-voices
- ONNX Runtime Web: https://github.com/microsoft/onnxruntime — npm `onnxruntime-web` 1.31.1

De enige wijziging aan andermans code is de lijm in `espeak-ng.js` (zie het commentaar bovenin en onderaan dat bestand).
