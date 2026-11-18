# HO-ME stem (sinds v66.1)

HO-ME spreekt met een eigen stem in plaats van de iPhone-stem, zodat je muziek blijft spelen.
De stem is **eSpeak NG**, naar WebAssembly gecompileerd. HO-ME (`index.html`) laadt deze bestanden
en speelt het geluid af als gewoon app-geluid (Web Audio).

| Bestand | Wat |
|---|---|
| `espeak-ng.wasm` | eSpeak NG 1.49.3-dev (git `e13b602ce0bd81bb5b84f03631819fb2820fe19f`), gecompileerd met Emscripten — ongewijzigd uit het npm-pakket **text2wav 0.0.14** |
| `espeak-ng.js` | de Emscripten-lijm uit text2wav 0.0.14. **Aangepast** voor de browser: onderaan is de NODEFS-koppeling vervangen door code die de data uit `Module.stemBestanden` en `Module.stemExtra` in het geheugen-bestandssysteem zet |
| `nl-data.bin` | alleen de Nederlandse eSpeak NG-data (phontab, phonindex, phondata, intonations, nl_dict, lang/gmw/nl) uit text2wav 0.0.14, in één bestand gezet met `maak-nl-data.py` |
| `COPYING` | de licentie van eSpeak NG: GNU GPL versie 3 |
| `LICENSE-text2wav` | de licentie van de text2wav-wrapper (MIT) |

## Licentie en broncode

eSpeak NG is vrije software onder de **GNU General Public License versie 3** (zie `COPYING`).
De broncode staat op:

- eSpeak NG: https://github.com/espeak-ng/espeak-ng (commit `e13b602ce0bd81bb5b84f03631819fb2820fe19f`)
- de Emscripten-build (text2wav): https://github.com/abbr/text2wav.node.js — npm-pakket `text2wav` 0.0.14

De enige wijziging is de aangepaste lijm in `espeak-ng.js` (zie het commentaar bovenin en onderaan dat bestand).
