/* HO-ME natuurlijke stem (v66.2) — Web Worker, apart van de kaart (geen haperingen tijdens het rekenen).
 * Piper-stem (VITS, ONNX) via onnxruntime-web (WebAssembly, 1 thread); de fonemen maakt eSpeak NG (dezelfde WebAssembly
 * als de robotstem, nu met --ipa), precies zoals Piper dat zelf doet (piper/phonemize_espeak.py + phoneme_ids.py, 1.3.0).
 * Bestanden staan naast dit script (map stem/); de service worker bewaart ze na één download (cache-first).
 *
 * Van de app:  { soort: 'laad', stemmen: [{ code, model }], actief }      → alles downloaden; de actieve stem laden
 *              { soort: 'kies', code }                                   → andere stem actief (laadt hem uit de cache)
 *              { soort: 'zeg', id, tekst, tempo }                        → spreek uit met de actieve stem
 * Naar de app: { soort: 'voortgang', binnen, totaal } · { soort: 'binnen', code } (gedownload)
 *              { soort: 'klaar', code, sr } (geladen, kan spreken) · { soort: 'pcm', id, pcm, sr, ms } · { soort: 'fout', id, tekst }
 */
'use strict';
importScripts('ort.wasm.min.js', 'espeak-ng.js');
const BASIS = new URL('./', self.location.href).href;
ort.env.wasm.numThreads = 1;          // geen SharedArrayBuffer op GitHub Pages — één thread
ort.env.wasm.wasmPaths = BASIS;
ort.env.logLevel = 'error';

let espeakMod = null, espeakData = null;     // eSpeak (fonemen)
const modelBuf = {};                         // code → ArrayBuffer (gedownload)
const cfgs = {};                             // code → .onnx.json
let actief = null, sessie = null, sessieCode = null, laadKlaar = null, rij = Promise.resolve();
// spreken wacht alleen tot de GEKOZEN stem geladen is — niet tot ook de andere stem binnen is
let sessieKlaar = null, sessieKlaarOk = null;
const nieuweSessie = () => { sessieKlaar = new Promise(r => { sessieKlaarOk = r; }); };
nieuweSessie();
const slaap = (ms) => new Promise(r => setTimeout(r, ms));
// de service worker bewaart een download pas als hij helemaal binnen is: even wachten voordat we zelf iets doen
async function wachtOpCache(url, ms) { for (let t = 0; t < ms; t += 250) { if (await inCache(url)) return true; await slaap(250); } return inCache(url); }

const post = (m, t) => self.postMessage(m, t || []);

async function haal(url, opBytes) {
  const r = await fetch(BASIS + url);
  if (!r.ok) throw new Error(url + ' HTTP ' + r.status);
  if (!r.body || !opBytes) return r.arrayBuffer();
  const lezer = r.body.getReader(); const delen = []; let n = 0;
  for (;;) { const { done, value } = await lezer.read(); if (done) break; delen.push(value); n += value.length; opBytes(value.length); }
  const uit = new Uint8Array(n); let p = 0; for (const d of delen) { uit.set(d, p); p += d.length; }
  return uit.buffer;
}
function pakUit(buf) {   // 'HOST' + kop-lengte + JSON-kop + bestanden (nl-data.bin, zie maak-nl-data.py)
  const dv = new DataView(buf); const kl = dv.getUint32(4, true);
  const kop = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 8, kl))); const m = {};
  kop.bestanden.forEach(b => { m[b.p] = new Uint8Array(buf, 8 + kl + b.s, b.n); });
  return m;
}
// tekst (één bijzin) → IPA met eSpeak NG: een verse instantie per bijzin (milliseconden)
function ipa(tekst, stemNaam) {
  return new Promise((ok, fout) => {
    const uit = []; let M = null;
    M = {
      arguments: ['-v', stemNaam || 'nl', '-q', '--ipa', '-b', '1', '-f', '/t.txt'],
      stemBestanden: espeakData, stemExtra: { '/t.txt': tekst },
      print: (t) => uit.push(t), printErr: () => {},
      instantiateWasm: (imports, ontvang) => { WebAssembly.instantiate(espeakMod, imports).then(i => ontvang(i, espeakMod), fout); return {}; },
      postRun: [() => ok(uit.join(' ').replace(/\s+/g, ' ').trim())],
      onAbort: (w) => fout(new Error('eSpeak: ' + w)),
    };
    try { EspeakNg(M); } catch (e) { fout(e); }
  });
}
// tekst → zinnen → fonemen (codepunten), zoals Piper: bijzin + leesteken (+ spatie na , : ;), NFD, per zin
async function fonemen(tekst, stemNaam) {
  const t = String(tekst).replace(/\s+/g, ' ').trim();
  const zinnen = []; let zin = [];
  // bijzinnen: knip na een leesteken dat door een spatie of het einde gevolgd wordt (zo blijft "1,5" één getal)
  const delen = []; const re = /[,.;:!?]+(?=\s|$)/g; let m, start = 0;
  while ((m = re.exec(t))) { delen.push({ kern: t.slice(start, m.index).trim(), term: m[0].charAt(0) }); start = m.index + m[0].length; }
  if (t.slice(start).trim()) delen.push({ kern: t.slice(start).trim(), term: '' });
  for (const { kern, term } of delen) {
    if (kern) {
      let f = (await ipa(kern, stemNaam)).replace(/\([^)]+\)/g, '');
      f += term;
      if (term === ',' || term === ':' || term === ';') f += ' ';
      zin.push(...Array.from(f.normalize('NFD')));
    }
    if (term === '.' || term === '?' || term === '!') { if (zin.length) zinnen.push(zin); zin = []; }
  }
  if (zin.length) zinnen.push(zin);
  return zinnen;
}
function naarIds(fon, kaart) {
  const ids = [...kaart['^'], ...kaart['_']];
  for (const f of fon) { const v = kaart[f]; if (!v) continue; ids.push(...v, ...kaart['_']); }
  ids.push(...kaart['$']);
  return ids;
}
async function laadSessie(code) {
  if (sessieCode === code && sessie) return;
  if (!modelBuf[code]) throw new Error('stem ' + code + ' nog niet binnen');
  const s = await ort.InferenceSession.create(modelBuf[code], { executionProviders: ['wasm'], graphOptimizationLevel: 'all' });
  delete modelBuf[code];                      // de sessie heeft zijn eigen kopie — 63 MB minder geheugen
  if (sessie) { try { await sessie.release(); } catch (e) {} }
  sessie = s; sessieCode = code;
  if (sessieKlaarOk) sessieKlaarOk();
  post({ soort: 'klaar', code, sr: cfgs[code].audio.sample_rate });
}
// staat het al in de cache (van de service worker)? Dan niet opnieuw downloaden
async function inCache(url) { try { return !!(self.caches && await caches.match(BASIS + url)); } catch (e) { return false; } }
async function bewaar(url, buf) {   // vangnet als de service worker het niet bewaarde (bv. nog niet actief)
  try { if (self.caches && !(await wachtOpCache(url, 5000))) await (await caches.open('home-stem')).put(BASIS + url, new Response(buf.slice(0))); } catch (e) {}
}
async function haalWeg(url, opBytes) {   // alleen downloaden (in de cache), niet in het geheugen houden
  const r = await fetch(BASIS + url);
  if (!r.ok) throw new Error(url + ' HTTP ' + r.status);
  if (r.body) { const lezer = r.body.getReader(); for (;;) { const { done, value } = await lezer.read(); if (done) break; opBytes(value.length); } }
  else await r.arrayBuffer();
  try { if (self.caches && !(await wachtOpCache(url, 5000))) await (await caches.open('home-stem')).add(BASIS + url); } catch (e) {}
}
async function laad(m) {
  const stemmen = m.stemmen; actief = m.actief || stemmen[0].code;
  const volg = stemmen.filter(x => x.code === actief).concat(stemmen.filter(x => x.code !== actief));   // eerst de gekozen stem
  // wat moet er nog gedownload worden? (de rest komt uit de cache van de service worker)
  const groot = [{ url: 'ort-wasm-simd-threaded.wasm', bytes: 14848852 }].concat(volg.map(x => ({ url: x.model, bytes: x.bytes || 0 })));
  const nodig = []; for (const g of groot) if (!(await inCache(g.url))) nodig.push(g);
  const totaal = nodig.reduce((t, g) => t + g.bytes, 0);
  const moet = new Set(nodig.map(g => g.url));   // alleen wat écht gedownload wordt telt mee in de voortgang
  let binnen = 0, laatst = 0;
  const tel = (n) => { binnen += n; if (binnen - laatst > 1.5e6) { laatst = binnen; post({ soort: 'voortgang', binnen, totaal }); } };
  if (totaal) post({ soort: 'voortgang', binnen: 0, totaal });
  const [mod, dat] = await Promise.all([haal('espeak-ng.wasm').then(b => WebAssembly.compile(b)), haal('nl-data.bin')]);
  espeakMod = mod; espeakData = pakUit(dat);
  // onnxruntime zelf (wasm ±15 MB): zelf ophalen = voortgang + in de cache; de lijm (.mjs) haalt ort zelf naast dit script
  const ow = await haal('ort-wasm-simd-threaded.wasm', moet.has('ort-wasm-simd-threaded.wasm') ? tel : null);
  bewaar('ort-wasm-simd-threaded.wasm', ow);   // op de achtergrond — niet wachten
  ort.env.wasm.wasmBinary = ow;
  for (const x of volg) {
    cfgs[x.code] = JSON.parse(new TextDecoder().decode(await haal(x.model + '.json')));
    if (x.code === actief) {
      modelBuf[x.code] = await haal(x.model, moet.has(x.model) ? tel : null);
      bewaar(x.model, modelBuf[x.code]);         // op de achtergrond — niet wachten
      post({ soort: 'binnen', code: x.code });
      await laadSessie(actief);
    } else {
      if (!(await inCache(x.model))) await haalWeg(x.model, tel);   // de andere stem: alleen downloaden, klaar voor de knop
      post({ soort: 'binnen', code: x.code });
    }
  }
  if (totaal) post({ soort: 'voortgang', binnen: totaal, totaal });
}
async function zeg(m) {
  const t0 = performance.now();
  await sessieKlaar;
  if (!sessie) throw new Error('nog geen stem geladen');
  const cfg = cfgs[sessieCode];
  const zinnen = await fonemen(m.tekst, (cfg.espeak && cfg.espeak.voice) || 'nl');
  const inf = cfg.inference || {}; const tempo = m.tempo || 1;
  const delen = [];
  for (const fon of zinnen) {
    const ids = naarIds(fon, cfg.phoneme_id_map);
    if (ids.length < 4) continue;
    const feeds = {
      input: new ort.Tensor('int64', BigInt64Array.from(ids.map(BigInt)), [1, ids.length]),
      input_lengths: new ort.Tensor('int64', BigInt64Array.from([BigInt(ids.length)]), [1]),
      scales: new ort.Tensor('float32', Float32Array.from([inf.noise_scale ?? 0.667, (inf.length_scale ?? 1) / tempo, inf.noise_w ?? 0.8]), [3]),
    };
    if ((cfg.num_speakers || 1) > 1) feeds.sid = new ort.Tensor('int64', BigInt64Array.from([0n]), [1]);
    const uit = await sessie.run(feeds);
    delen.push(uit[sessie.outputNames[0]].data);
  }
  const n = delen.reduce((s, d) => s + d.length, 0);
  const pcm = new Float32Array(n); let p = 0; for (const d of delen) { pcm.set(d, p); p += d.length; }
  post({ soort: 'pcm', id: m.id, pcm, sr: cfg.audio.sample_rate, ms: Math.round(performance.now() - t0) }, [pcm.buffer]);
}
self.onmessage = (e) => {
  const m = e.data || {};
  if (m.soort === 'laad') {
    laadKlaar = laad(m).catch(err => { post({ soort: 'fout', tekst: String((err && err.message) || err) }); });
  } else if (m.soort === 'kies') {
    actief = m.code;
    nieuweSessie();   // spreken wacht op de nieuwe stem
    laadKlaar = (async () => {
      await laadKlaar;
      if (sessieCode !== m.code) {
        const x = (m.stemmen || []).find(y => y.code === m.code);
        if (!x) throw new Error('onbekende stem ' + m.code);
        if (!cfgs[m.code]) cfgs[m.code] = JSON.parse(new TextDecoder().decode(await haal(x.model + '.json')));
        modelBuf[m.code] = await haal(x.model);   // uit de cache (al gedownload)
        await laadSessie(m.code);
      } else { if (sessieKlaarOk) sessieKlaarOk(); post({ soort: 'klaar', code: m.code, sr: cfgs[m.code].audio.sample_rate }); }
    })().catch(err => { post({ soort: 'fout', tekst: String((err && err.message) || err) }); });
  } else if (m.soort === 'zeg') {   // één tegelijk: een sessie rekent niet twee zinnen tegelijk
    rij = rij.then(() => zeg(m)).catch(err => post({ soort: 'fout', id: m.id, tekst: String((err && err.message) || err) }));
  } else if (m.soort === 'fonemen') {   // alleen voor de test: dezelfde stap als Piper
    fonemen(m.tekst, m.stem || 'nl').then(z => post({ soort: 'fonemen', id: m.id, zinnen: z, ids: cfgs[sessieCode] ? z.map(f => naarIds(f, cfgs[sessieCode].phoneme_id_map)) : null }))
      .catch(err => post({ soort: 'fout', id: m.id, tekst: String((err && err.message) || err) }));
  }
};
