#!/usr/bin/env python3
# Stem-fabriek (HO-ME v66.x) — draait als GitHub Action (.github/workflows/stem.yml), niet in de app.
# Haalt de gratis Nederlandse en Vlaamse Piper-stemmen (rhasspy/piper-voices op Hugging Face) en:
#   proef            → per stem dezelfde voorbeeldzinnen als mp3 in stem/proef/ + stemmen.json (naam, land, kwaliteit,
#                      grootte, licentie uit de MODEL_CARD) + per stem de fonemen/ids van Piper zelf (om HO-ME's eigen
#                      fonemen-stap mee te vergelijken) + de kleine .onnx.json-instellingen; de modellen zelf in
#                      --modellen (de workflow zet die op de zijbranch stem-modellen, niet op main)
#   kies <stem>      → alleen dat ene model (.onnx + .onnx.json) in stem/piper/ — dat downloadt HO-ME straks
import json, os, subprocess, sys, urllib.request, wave, hashlib, shutil, argparse

HF = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/'
ZINNEN = [
    ('navigatie', 'Over 300 meter, op de rotonde de tweede afslag, rechtsaf.'),
    ('flitser', 'Let op, flitser over 300 meter, 50 kilometer per uur.'),
    ('bericht', 'Jan: we stoppen bij de volgende tankplaats, wie wil er koffie?'),
]
IDS_ZINNEN = ['Over 300 meter linksaf.', 'Nu rechtsaf', 'Let op, flitser over 300 meter, 50 kilometer per uur.',
              'Op de rotonde de tweede afslag, rechtsaf.', 'Verbonden', 'Volg de route']


def haal(url, pad=None):
    req = urllib.request.Request(url, headers={'User-Agent': 'HO-ME-stem-fabriek (github.com/umop3p1sdn/Tracker)'})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
    if pad:
        with open(pad, 'wb') as f:
            f.write(data)
    return data


def nl_stemmen():
    v = json.loads(haal(HF + 'voices.json'))
    return {k: x for k, x in v.items() if x.get('language', {}).get('family') == 'nl'}


def licentie(card):
    # MODEL_CARD: vrije tekst; de regels rond "License"/"Dataset" zijn genoeg om te tonen
    regels = [r.strip() for r in card.splitlines() if r.strip()]
    uit = [r for r in regels if any(w in r.lower() for w in ('license', 'licence', 'licentie', 'dataset', 'url:', 'http'))]
    return ' · '.join(uit)[:600]


def bestand(info, eind):
    for pad, meta in info['files'].items():
        if pad.endswith(eind):
            return pad, meta
    return None, None


def laad_stem(info, map_):
    onnx, meta = bestand(info, '.onnx')
    cfg, _ = bestand(info, '.onnx.json')
    lok = os.path.join(map_, os.path.basename(onnx))
    if not os.path.exists(lok):
        haal(HF + onnx, lok)
    if meta and meta.get('md5_digest'):
        md5 = hashlib.md5(open(lok, 'rb').read()).hexdigest()
        if md5 != meta['md5_digest']:
            raise SystemExit('md5 klopt niet voor ' + onnx)
    haal(HF + cfg, lok + '.json')
    card = ''
    kaart, _ = bestand(info, 'MODEL_CARD')
    if kaart:
        try:
            card = haal(HF + kaart).decode('utf-8', 'replace')
        except Exception as e:
            card = 'MODEL_CARD niet te lezen: %s' % e
    return lok, card, (meta or {}).get('size_bytes', os.path.getsize(lok))


def proef(uitmap, modellen):
    from piper import PiperVoice
    os.makedirs(uitmap, exist_ok=True)
    os.makedirs(modellen, exist_ok=True)
    lijst = []
    for key, info in sorted(nl_stemmen().items()):
        print('==', key, flush=True)
        lok, card, grootte = laad_stem(info, modellen)
        shutil.copy(lok + '.json', os.path.join(uitmap, key + '.onnx.json'))
        stem = PiperVoice.load(lok)
        mp3s = {}
        for naam, zin in ZINNEN:
            wav = os.path.join(modellen, key + '-' + naam + '.wav')
            with wave.open(wav, 'wb') as w:
                stem.synthesize_wav(zin, w)
            mp3 = key + '-' + naam + '.mp3'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', wav, '-ac', '1', '-b:a', '64k',
                            os.path.join(uitmap, mp3)], check=True)
            mp3s[naam] = mp3
        ids = []
        for zin in IDS_ZINNEN:
            try:
                fon = stem.phonemize(zin)
                ids.append({'tekst': zin, 'fonemen': fon, 'ids': [stem.phonemes_to_ids(f) for f in fon]})
            except Exception as e:
                ids.append({'tekst': zin, 'fout': str(e)})
        with open(os.path.join(uitmap, 'ids-' + key + '.json'), 'w', encoding='utf-8') as f:
            json.dump(ids, f, ensure_ascii=False)
        lijst.append({
            'key': key, 'naam': info.get('name'), 'land': info['language'].get('region'), 'taal': info['language'].get('code'),
            'kwaliteit': info.get('quality'), 'sprekers': info.get('num_speakers', 1), 'mb': round(grootte / 1e6, 1),
            'licentie': licentie(card), 'mp3': mp3s,
        })
    with open(os.path.join(uitmap, 'stemmen.json'), 'w', encoding='utf-8') as f:
        json.dump({'zinnen': dict(ZINNEN), 'stemmen': lijst}, f, ensure_ascii=False, indent=1)
    print('klaar:', len(lijst), 'stemmen')


def kies(key, uitmap):
    stemmen = nl_stemmen()
    if key not in stemmen:
        raise SystemExit('onbekende stem: %s (er zijn: %s)' % (key, ', '.join(sorted(stemmen))))
    os.makedirs(uitmap, exist_ok=True)
    for f in os.listdir(uitmap):                 # er staat er altijd maar één
        if f.endswith('.onnx') or f.endswith('.onnx.json'):
            os.remove(os.path.join(uitmap, f))
    lok, card, grootte = laad_stem(stemmen[key], uitmap)
    with open(os.path.join(uitmap, 'MODEL_CARD-' + key + '.txt'), 'w', encoding='utf-8') as f:
        f.write(card)
    print('gekozen:', key, round(grootte / 1e6, 1), 'MB')


if __name__ == '__main__':
    a = argparse.ArgumentParser()
    a.add_argument('wat', choices=['proef', 'kies'])
    a.add_argument('stem', nargs='?')
    a.add_argument('--uit', default='stem/proef')
    a.add_argument('--modellen', default='/tmp/stem-modellen')
    x = a.parse_args()
    if x.wat == 'proef':
        proef(x.uit, x.modellen)
    else:
        kies(x.stem, x.uit if x.uit != 'stem/proef' else 'stem/piper')
