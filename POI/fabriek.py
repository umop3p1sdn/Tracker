#!/usr/bin/env python3
"""POI-fabriek voor HO-ME Live Tracker (v63.93; v63.96: ±40 landen, namen en vakkenlijst in index.json).

Draait 1x per maand vanzelf als GitHub Action (.github/workflows/poi.yml), of met de hand (Actions -> POI-fabriek ->
Run workflow). Wat hij doet:
  1. per land het OpenStreetMap-extract van Geofabrik ophalen (download.geofabrik.de) - een keer per land per run,
     met MD5-controle; het grote bestand gaat na het filteren meteen weg;
  2. met osmium alleen de POI-soorten van de app eruit halen (de rest van de kaart gaat weg: NL 1,3 GB -> een paar MB);
  3. alles samenvoegen (dubbele plekken uit overlappende extracten = een keer), per plek het midden (zoals Overpass
     'out center': het midden van het omhullende kader) en het vak van 0,5 graad;
  4. per land een bestand POI/<LAND>.tsv.gz met ALLE vakken die het land raakt - compleet, dus een vak op de grens met
     Duitsland bevat ook de Duitse plekken. Vakken met LAND van een land dat we NIET maken (bv. Oostenrijk) laten we weg:
     die zouden niet compleet zijn; de app haalt die zelf (Overpass) als je daar bent. Alleen land telt (Natural Earth,
     publiek domein): de grenzen van Geofabrik lopen ook over zee, en dan viel bv. Rostock weg om Deens water;
  5. POI/index.json met per land de naam, de datum van de gegevens, de grootte (download en uitgepakt), het aantal plekken
     en de lijst van vakken (daarmee wist de app een land zonder de grensvakken van een ander land);
  6. v63.97: elk vak ook LOS: POI/v/<i>/<j>.tsv.gz (alle lagen, zelfde opbouw). Bij het zoeken haalt de app alleen de vakken
     die hij nodig heeft (Lokaal: 1-4 vakken, ±5-900 KB) - zonder eerst een heel land te downloaden. In index.json bij
     'vakken': welke vakken er zijn ('vol') en welke compleet maar leeg zijn ('leeg' - daar is geen bestand van).

De lagen en velden moeten gelijk zijn aan die in de app (POI_VOORRAAD, POI_REST, POI_EXTRA en hun velden).
Gegevens: (c) OpenStreetMap-bijdragers, ODbL 1.0 - zie LEESMIJ.md.

Testen zonder downloads:  python3 fabriek.py --bron MAP --landen MC=europe/monaco --buren europe/france --uit UITMAP
  (MAP bevat <naam>-latest.osm.pbf en <naam>.poly, zonder het deel voor de laatste / - bv. monaco.poly)
Alleen de losse vakken (uit de landbestanden die er al staan, geen Geofabrik):  python3 fabriek.py --knip [--uit MAP]
"""
import argparse
import gzip
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

from shapely.geometry import Polygon, box, shape
from shapely.ops import unary_union
from shapely.prepared import prep

GEOFABRIK = 'https://download.geofabrik.de/'
# v63.96 (Sjoerd: "Maak de lijst met landen maar nog groter - er staat hoeveel data het kost, dus het is een keuze om deze
# te activeren"): heel Europa behalve Rusland, Wit-Rusland, Oekraine, Moldavie, Georgie en Turkije. Code -> (pad bij
# Geofabrik, naam in de app). Op de telefoon komt alleen wat je zelf kiest.
LANDEN = {
    'NL': ('europe/netherlands', 'Nederland'), 'BE': ('europe/belgium', 'België'), 'DE': ('europe/germany', 'Duitsland'),
    'LU': ('europe/luxembourg', 'Luxemburg'), 'FR': ('europe/france', 'Frankrijk'), 'MC': ('europe/monaco', 'Monaco'),
    'AT': ('europe/austria', 'Oostenrijk'), 'CH': ('europe/switzerland', 'Zwitserland'),
    'LI': ('europe/liechtenstein', 'Liechtenstein'), 'IT': ('europe/italy', 'Italië'), 'SI': ('europe/slovenia', 'Slovenië'),
    'ES': ('europe/spain', 'Spanje'), 'AD': ('europe/andorra', 'Andorra'), 'PT': ('europe/portugal', 'Portugal'),
    'GB': ('europe/united-kingdom', 'Verenigd Koninkrijk'), 'IE': ('europe/ireland-and-northern-ireland', 'Ierland'),
    'IM': ('europe/isle-of-man', 'Isle of Man'), 'GG': ('europe/guernsey-jersey', 'Kanaaleilanden'),
    'DK': ('europe/denmark', 'Denemarken'), 'NO': ('europe/norway', 'Noorwegen'), 'SE': ('europe/sweden', 'Zweden'),
    'FI': ('europe/finland', 'Finland'), 'IS': ('europe/iceland', 'IJsland'), 'FO': ('europe/faroe-islands', 'Faeröer'),
    'EE': ('europe/estonia', 'Estland'), 'LV': ('europe/latvia', 'Letland'), 'LT': ('europe/lithuania', 'Litouwen'),
    'PL': ('europe/poland', 'Polen'), 'CZ': ('europe/czech-republic', 'Tsjechië'), 'SK': ('europe/slovakia', 'Slowakije'),
    'HU': ('europe/hungary', 'Hongarije'), 'RO': ('europe/romania', 'Roemenië'), 'BG': ('europe/bulgaria', 'Bulgarije'),
    'HR': ('europe/croatia', 'Kroatië'), 'BA': ('europe/bosnia-herzegovina', 'Bosnië en Herzegovina'),
    'RS': ('europe/serbia', 'Servië'), 'ME': ('europe/montenegro', 'Montenegro'), 'XK': ('europe/kosovo', 'Kosovo'),
    'AL': ('europe/albania', 'Albanië'), 'MK': ('europe/macedonia', 'Noord-Macedonië'), 'GR': ('europe/greece', 'Griekenland'),
    'MT': ('europe/malta', 'Malta'), 'CY': ('europe/cyprus', 'Cyprus'),
}
# Alleen voor de volledigheid van grensvakken (geen eigen bestand). Monaco is sinds v63.96 een eigen land.
HULP = {}
# Buurlanden die we niet maken: een vak met LAND van een van deze is niet compleet en gaat niet in de bestanden (de app haalt
# die zelf). Van Rusland alleen het stuk dat aan onze landen grenst (Noordwest: Noorwegen, Finland, Estland, Letland; en
# Kaliningrad: Polen, Litouwen) - heel Rusland loopt over de datumgrens heen. Marokko voor Ceuta en Melilla (in het extract
# van Spanje).
BUREN = ['russia/northwestern-fed-district', 'russia/kaliningrad', 'europe/belarus', 'europe/ukraine', 'europe/moldova',
         'europe/turkey', 'africa/morocco']
# Land (zonder zee) - Natural Earth 1:10 miljoen, publiek domein, vaste versie
LAND = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/'
LAND_BESTANDEN = ['ne_10m_land', 'ne_10m_minor_islands']
UA = 'HO-ME-POI-fabriek/1 (github.com/umop3p1sdn/Tracker; 1x per maand)'

# Precies de lagen van de app: b = basis, r = rest, x = extra's
LAGEN = {
    'b': {'amenity': ['fuel', 'restaurant'], 'shop': ['supermarket']},
    'r': {'amenity': ['charging_station', 'fast_food', 'cafe', 'bakery'], 'shop': ['bakery'], 'tourism': ['hotel']},
    'x': {'amenity': ['atm', 'toilets', 'pub', 'food_court'], 'tourism': ['viewpoint', 'attraction']},
}
LAAG_VOLGORDE = ['b', 'r', 'x']
VELDEN = ['amenity', 'shop', 'tourism', 'name', 'brand', 'opening_hours', 'cuisine',
          'charging_station:output', 'maxpower', 'socket:type2:output', 'socket:type2_combo:output',
          'socket:ccs:output', 'socket:chademo:output', 'capacity']
# Per laag dezelfde velden als de Overpass-vraag van de app (dan gedraagt de lijst zich precies hetzelfde)
LAAG_VELDEN = {
    'b': ['amenity', 'shop', 'name', 'brand', 'opening_hours', 'cuisine'],
    'r': VELDEN[:],
    'x': ['amenity', 'tourism', 'name', 'brand', 'opening_hours', 'cuisine'],
}
VAK = 0.5
FORMAAT = 1
VAKMAP = 'v'                                   # v63.97: POI/v/<i>/<j>.tsv.gz - elk vak los


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def run(*args):
    log('$', ' '.join(args))
    subprocess.run(args, check=True)


def haal(url, pad):
    """Een bestand ophalen (curl: hervat niet, probeert hooguit 3x met een minuut ertussen - nooit in een lus)."""
    run('curl', '-fsSL', '--show-error', '--retry', '3', '--retry-delay', '60', '-A', UA, '-o', pad, url)
    log('binnen', os.path.basename(pad), os.path.getsize(pad), 'bytes')


def md5_van(url, pad):
    """De MD5 van Geofabrik, of None als die er (even) niet is - GEMETEN 18-10-2026: germany-latest.osm.pbf.md5 gaf 404
    terwijl het bestand er wel was. Dan controleert osmium het bestand bij het lezen (kapot = osmium stopt = geen commit)."""
    try:
        haal(url, pad)
    except subprocess.CalledProcessError:
        log('geen MD5 bij', url, '- osmium controleert het bestand bij het lezen')
        return None
    with open(pad) as f:
        return f.read().split()[0]


def md5(pad):
    h = hashlib.md5()
    with open(pad, 'rb') as f:
        for blok in iter(lambda: f.read(1 << 20), b''):
            h.update(blok)
    return h.hexdigest()


def filter_expressies():
    per_sleutel = {}
    for laag in LAGEN.values():
        for k, v in laag.items():
            per_sleutel.setdefault(k, [])
            for w in v:
                if w not in per_sleutel[k]:
                    per_sleutel[k].append(w)
    return ['nwr/%s=%s' % (k, ','.join(v)) for k, v in per_sleutel.items()]


def lees_poly(pad):
    """Geofabrik .poly -> shapely-vorm (ringen; '!' = gat)."""
    with open(pad, encoding='utf-8') as f:
        regels = [r.strip() for r in f]
    delen, i = [], 1                      # regel 0 = naam
    while i < len(regels) and regels[i] != 'END':
        kop, i, ring = regels[i], i + 1, []
        while regels[i] != 'END':
            x, y = regels[i].split()[:2]
            ring.append((float(x), float(y)))
            i += 1
        i += 1
        delen.append((kop.startswith('!'), ring))
    buiten = [Polygon(r) for gat, r in delen if not gat and len(r) >= 3]
    gaten = [Polygon(r) for gat, r in delen if gat and len(r) >= 3]
    vorm = unary_union([p.buffer(0) for p in buiten])
    if gaten:
        vorm = vorm.difference(unary_union([p.buffer(0) for p in gaten]))
    return vorm


def vakken_van(vorm):
    minx, miny, maxx, maxy = vorm.bounds
    p = prep(vorm)
    uit = set()
    for i in range(math.floor(miny / VAK), math.floor(maxy / VAK) + 1):
        for j in range(math.floor(minx / VAK), math.floor(maxx / VAK) + 1):
            if p.intersects(box(j * VAK, i * VAK, (j + 1) * VAK, (i + 1) * VAK)):
                uit.add((i, j))
    return uit


def lees_land(paden, kader):
    """Natural Earth (GeoJSON) -> het land binnen het kader (minx, miny, maxx, maxy), als een vorm."""
    k = box(*kader)
    delen = []
    for pad in paden:
        with open(pad, encoding='utf-8') as f:
            for ft in json.load(f)['features']:
                g = shape(ft['geometry'])
                if g.intersects(k):
                    delen.append(g.intersection(k))
    return unary_union(delen)


def schoon(w):
    return str(w).replace('\t', ' ').replace('\r', ' ').replace('\n', ' ').strip()


def schrijf_tsv(doel, naam, datum, vs, rijen):
    """Eén POI-bestand (een land, of v63.97 één los vak): kop, velden, vakken, per vak de regels (rijen[vak] is al
    gesorteerd), slotregel. gzip zonder tijd en naam: dezelfde inhoud = precies dezelfde bytes. -> (regels, bytes uitgepakt)"""
    n = tekst = 0
    with open(doel, 'wb') as ruw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=ruw, compresslevel=9, mtime=0) as gz:
            def w(s):
                nonlocal tekst
                b = (s + '\n').encode('utf-8')
                tekst += len(b)
                gz.write(b)
            w('#POI\t%d\t%s\t%s' % (FORMAAT, naam, datum))
            w('#velden\t' + ' '.join(VELDEN))
            w('#vakken\t' + ' '.join('%d_%d' % v for v in vs))
            for v in vs:
                for _, _, regel in rijen.get(v, []):
                    w(regel)
                    n += 1
            w('#einde\t%d' % n)
    return n, tekst


def reeks(vakken):
    """Vakken kort voor index.json: per rij i de kolommen j, met '..' voor een reeks - bv. '97:4..12,15 98:-3..9'
    (j kan negatief zijn: west van Greenwich)."""
    per = {}
    for i, j in sorted(vakken):
        per.setdefault(i, []).append(j)
    delen = []
    for i, js in sorted(per.items()):
        stukken, a = [], js[0]
        b = a
        for j in js[1:] + [None]:
            if j is not None and j == b + 1:
                b = j
                continue
            stukken.append('%d' % a if a == b else '%d..%d' % (a, b))
            a = b = j
        delen.append('%d:%s' % (i, ','.join(stukken)))
    return ' '.join(delen)


def schrijf_vakken(uit, werk, alle, rijen, datum):
    """v63.97 (Sjoerd: "Veel mensen downloaden niet de pre info, maar zoeken gewoon dmv POI, en dan bv benzine"): elk vak dat
    in een land-bestand staat ook los, met alle lagen: POI/v/<i>/<j>.tsv.gz. De app haalt bij het zoeken alleen de vakken die
    hij nodig heeft. Een leeg vak (zee, of niets van deze soorten) krijgt geen bestand - dat staat in index.json bij 'leeg'.
    Eerst in de werkmap, dan in één keer op de plek (vakken die nu leeg zijn of weg zijn gaan zo ook weg).
    -> het stuk 'vakken' voor index.json"""
    nieuw = os.path.join(werk, VAKMAP + '-nieuw')
    shutil.rmtree(nieuw, ignore_errors=True)
    os.makedirs(nieuw)
    vol, leeg, grootte, regels = [], [], 0, 0
    for v in sorted(alle):
        if not rijen.get(v):
            leeg.append(v)
            continue
        # per rij een map (v/97/4.tsv.gz): GitHub raadt hooguit 3.000 dingen per map aan - het zijn er ±3.300
        os.makedirs(os.path.join(nieuw, str(v[0])), exist_ok=True)
        pad = os.path.join(nieuw, str(v[0]), '%d.tsv.gz' % v[1])
        n, _ = schrijf_tsv(pad, '%d_%d' % v, datum, [v], rijen)
        vol.append(v)
        grootte += os.path.getsize(pad)
        regels += n
    doel = os.path.join(uit, VAKMAP)
    shutil.rmtree(doel, ignore_errors=True)
    shutil.move(nieuw, doel)
    log('losse vakken:', len(vol), 'bestanden,', len(leeg), 'leeg,', regels, 'regels,', grootte, 'bytes')
    return {'map': VAKMAP + '/', 'datum': datum, 'bestanden': len(vol), 'bytes': grootte, 'rijen': regels,
            'vol': reeks(vol), 'leeg': reeks(leeg)}


def schrijf_index(uit, index):
    with open(os.path.join(uit, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
        f.write('\n')


def knip(a):
    """--knip (v63.97): de losse vakken maken uit de land-bestanden die er al staan - zonder Geofabrik (de eerste keer, of als
    alleen de vakken anders moeten). Een grensvak staat in twee land-bestanden met precies dezelfde regels (zelfde run): het
    eerste land telt. index.json houdt zijn landen; alleen 'vakken' is nieuw."""
    with open(os.path.join(a.uit, 'index.json'), encoding='utf-8') as f:
        index = json.load(f)
    rijen, alle, datums = {}, set(), []
    for code, info in index['landen'].items():
        eigen, n, einde = set(), 0, None
        with gzip.open(os.path.join(a.uit, info['bestand']), 'rt', encoding='utf-8', newline='\n') as f:
            for regel in f:
                regel = regel.rstrip('\n')
                if regel.startswith('#'):
                    d = regel.split('\t')
                    if d[0] == '#POI' and (d[2] != code or int(d[1]) != FORMAAT):
                        sys.exit('%s: kop klopt niet (%s)' % (code, regel))
                    if d[0] == '#POI':
                        datums.append(d[3])
                    elif d[0] == '#velden' and d[1].split(' ') != VELDEN:
                        sys.exit('%s: andere velden dan deze fabriek' % code)
                    elif d[0] == '#vakken':
                        vs = [tuple(int(x) for x in k.split('_')) for k in (d[1].split() if len(d) > 1 else [])]
                        eigen = {v for v in vs if v not in alle}
                        alle.update(vs)
                    elif d[0] == '#einde':
                        einde = int(d[1])
                    continue
                n += 1
                d = regel.split('\t', 4)
                v = (math.floor(float(d[2]) / VAK), math.floor(float(d[3]) / VAK))   # zelfde getal als de app leest
                if v in eigen:
                    rijen.setdefault(v, []).append((LAAG_VOLGORDE.index(d[0]), d[1], regel))
        if einde != n:
            sys.exit('%s: niet compleet (%d van %s regels)' % (code, n, einde))
        log(code, n, 'regels,', len(eigen), 'vakken erbij')
    for l in rijen.values():
        l.sort()
    index['vakken'] = schrijf_vakken(a.uit, a.werk, alle, rijen, max(datums))
    schrijf_index(a.uit, index)
    log('klaar')


def kader_midden(geo):
    """Midden van het omhullende kader van alle coordinaten (zoals Overpass 'out center')."""
    mnx = mny = math.inf
    mxx = mxy = -math.inf
    stapel = [geo['coordinates']]
    while stapel:
        c = stapel.pop()
        if c and isinstance(c[0], (int, float)):
            x, y = c[0], c[1]
            mnx, mxx, mny, mxy = min(mnx, x), max(mxx, x), min(mny, y), max(mxy, y)
        else:
            stapel.extend(c)
    if mnx == math.inf:
        return None
    return (mny + mxy) / 2, (mnx + mxx) / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--uit', default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument('--werk', default='/tmp/poi-werk')
    ap.add_argument('--bron', default='', help='map met <naam>-latest.osm.pbf en <naam>.poly (geen downloads)')
    ap.add_argument('--landen', default='', help='bv. NL=netherlands,BE=belgium')
    ap.add_argument('--buren', default=None, help='bv. austria,switzerland')
    ap.add_argument('--hulp', default=None, help='extracten alleen voor de grensvakken, bv. MC=monaco')
    ap.add_argument('--geofabrik', default=GEOFABRIK, help='andere downloadplek (alleen om te testen)')
    ap.add_argument('--knip', action='store_true', help='alleen de losse vakken, uit de land-bestanden in --uit (geen downloads)')
    a = ap.parse_args()
    os.makedirs(a.werk, exist_ok=True)
    if a.knip:
        return knip(a)

    namen ={c: n for c, (_, n) in LANDEN.items()}
    landen = dict(x.split('=') for x in a.landen.split(',')) if a.landen else {c: p for c, (p, _) in LANDEN.items()}
    hulp = dict(x.split('=') for x in a.hulp.split(',') if x) if a.hulp is not None else dict(HULP)
    buren = [x for x in (a.buren.split(',') if a.buren is not None else BUREN) if x]
    os.makedirs(a.werk, exist_ok=True)
    os.makedirs(a.uit, exist_ok=True)

    def bron(naam, ext):
        kort = naam.split('/')[-1]               # europe/netherlands -> netherlands (de naam van het bestand)
        if a.bron:
            return os.path.join(a.bron, kort + ext)
        pad = os.path.join(a.werk, kort + ext)
        if ext == '.poly':
            haal(a.geofabrik + naam + '.poly', pad)
            return pad
        if ext == '.geojson':
            haal(LAND + naam + '.geojson', pad)
            return pad
        # MD5 voor en na: zet Geofabrik net een nieuwe stand neer (hun dagelijkse update), dan past het bestand bij een van
        # de twee. Past hij bij geen van beide, dan stoppen we (niets opnieuw geprobeerd).
        url = a.geofabrik + naam + '-latest.osm.pbf'
        voor = md5_van(url + '.md5', pad + '.md5')
        haal(url, pad)
        if voor:
            echt = md5(pad)
            if echt != voor and echt != md5_van(url + '.md5', pad + '.md5'):
                sys.exit('MD5 klopt niet voor %s - gestopt (niets opnieuw geprobeerd)' % naam)
        return pad

    # 0: eerst de grenzen (.poly) en het land (Natural Earth) - ontbreekt er een, dan stoppen we METEEN en niet pas na ±2 uur
    # downloaden (v63.96: ±40 landen = 1 u 49 min bij Geofabrik)
    vormen = {code: lees_poly(bron(naam, '.poly')) for code, naam in landen.items()}
    buur = [prep(lees_poly(bron(n, '.poly'))) for n in buren]
    gx0, gy0, gx1, gy1 = unary_union(list(vormen.values())).bounds
    land = lees_land([bron(n, '.geojson') for n in LAND_BESTANDEN], (gx0 - 1, gy0 - 1, gx1 + 1, gy1 + 1))
    land_p = prep(land)
    log('grenzen en land binnen:', len(vormen), 'landen,', len(buur), 'buren')

    # 1 + 2: per land ophalen en filteren (de hulp-extracten ook: hun plekken maken grensvakken compleet).
    # v63.96: de gefilterde bestanden staan in <werk>/filter met hun stand en de dag van ophalen. Mislukt een run nadat alles
    # binnen is (GEMETEN 19-10: 1 u 49 min downloaden, daarna een fout), dan pakt een nieuwe run DEZELFDE dag ze daar weer op
    # (de workflow bewaart die map dan) - zo halen we niet twee keer hetzelfde bij Geofabrik.
    datum, poi = {}, []
    filtermap = os.path.join(a.werk, 'filter')
    os.makedirs(filtermap, exist_ok=True)
    vandaag = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    for code, naam in list(landen.items()) + list(hulp.items()):
        klein = os.path.join(filtermap, code + '-poi.osm.pbf')
        stand = os.path.join(filtermap, code + '.stand')
        if not a.bron and os.path.exists(klein) and os.path.exists(stand):
            d, dag = (open(stand, encoding='utf-8').read().split() + ['', ''])[:2]
            if d and dag == vandaag:
                datum[code] = d
                poi.append((code, klein))
                log(code, 'van eerder vandaag (niet opnieuw bij Geofabrik)', d)
                continue
        groot = bron(naam, '-latest.osm.pbf')
        datum[code] = subprocess.run(['osmium', 'fileinfo', '-g', 'header.option.osmosis_replication_timestamp', groot],
                                     check=True, capture_output=True, text=True).stdout.strip()
        if not datum[code]:                    # geen stand in het bestand: dan de tijd van nu (de app ziet dan toch een nieuwe stand)
            datum[code] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        run('osmium', 'tags-filter', groot, *filter_expressies(), '-o', klein, '-O')
        if not a.bron:
            os.remove(groot)                   # schijfruimte: Duitsland en Frankrijk zijn elk 4,5 GB
        with open(stand, 'w', encoding='utf-8') as f:
            f.write('%s %s\n' % (datum[code], vandaag))
        poi.append((code, klein))
        log(code, 'datum', datum[code], 'gefilterd', os.path.getsize(klein), 'bytes')

    # 3: per land naar regels. v63.96: NIET meer eerst samenvoegen - GEMETEN op GitHub (19-10, ±40 landen): extracten van
    # verschillende momenten hebben soms een andere versie van dezelfde plek; osmium merge houdt dan beide en osmium export
    # stopt met "Node ID twice in input". Nu per land exporteren; een plek uit twee extracten telt één keer (de eerste).
    rijen = {}                                 # (i, j) -> lijst (laagnr, id, regel)
    gezien = set()
    for code, klein in poi:
        geo = os.path.join(a.werk, code + '.geojsonseq')
        run('osmium', 'export', klein, '-f', 'geojsonseq', '-a', 'type,id', '-o', geo, '-O')
        with open(geo, encoding='utf-8') as f:
            for regel in f:
                regel = regel.strip().lstrip('\x1e')
                if not regel:
                    continue
                ft = json.loads(regel)
                pr = ft.get('properties') or {}
                sleutel = (pr.get('@type'), pr.get('@id'))
                if sleutel in gezien:              # een gesloten weg kan als lijn en als vlak komen
                    continue
                lagen = [l for l in LAAG_VOLGORDE if any(pr.get(k) in v for k, v in LAGEN[l].items())]
                if not lagen or not ft.get('geometry'):
                    continue
                m = kader_midden(ft['geometry'])
                if not m:
                    continue
                gezien.add(sleutel)
                lat, lon = '%.5f' % m[0], '%.5f' % m[1]
                vak = (math.floor(float(lat) / VAK), math.floor(float(lon) / VAK))   # zelfde getal als de app leest
                ident = str(pr['@type'])[0] + str(pr['@id'])
                for l in lagen:
                    velden = [schoon(pr[v]) if (v in LAAG_VELDEN[l] and pr.get(v) not in (None, '')) else '' for v in VELDEN]
                    while velden and not velden[-1]:
                        velden.pop()
                    rijen.setdefault(vak, []).append((LAAG_VOLGORDE.index(l), ident, '\t'.join([l, ident, lat, lon] + velden)))
        os.remove(geo)                     # schijfruimte
    for l in rijen.values():               # één keer sorteren (laag, id) - voor de land-bestanden én de losse vakken
        l.sort()
    log('plekken', len(gezien), 'vakken met plekken', len(rijen))

    # 4: vakken per land; een vak met LAND van een buurland (dat we niet maken) is niet compleet. Alleen land telt: de
    # grenzen van Geofabrik lopen ook over zee (Deens water tot vlak bij Rostock, het Kanaal tot bij Calais) - daar staan
    # geen plekken van dat buurland. v63.96: eerst de snelle toets (raakt het vak een buurland?), pas dan het (dure) stuk
    # land uitsnijden - met ±40 landen zijn het duizenden vakken.
    oordeel = {}                               # vak -> True = niet compleet
    def niet_compleet(v):
        if v not in oordeel:
            r = box(v[1] * VAK, v[0] * VAK, (v[1] + 1) * VAK, (v[0] + 1) * VAK)
            dichtbij = [b for b in buur if b.intersects(r)]
            oordeel[v] = bool(dichtbij) and land_p.intersects(r) and any(b.intersects(r.intersection(land)) for b in dichtbij)
        return oordeel[v]
    land_vakken = {}
    for code, vorm in vormen.items():
        land_vakken[code] = sorted(v for v in vakken_van(vorm) if not niet_compleet(v))
    log('randvakken met land van een buurland (niet compleet, weggelaten):', sum(oordeel.values()))

    index = {'formaat': FORMAAT, 'gemaakt': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
             'bron': 'OpenStreetMap via Geofabrik (download.geofabrik.de)',
             'licentie': 'ODbL 1.0 - (c) OpenStreetMap-bijdragers', 'landen': {}}
    for code in landen:
        vs = land_vakken[code]
        tijdelijk = os.path.join(a.werk, code + '.tsv.gz')
        n, tekst = schrijf_tsv(tijdelijk, code, datum[code], vs, rijen)
        doel = os.path.join(a.uit, code + '.tsv.gz')
        shutil.move(tijdelijk, doel)
        # naam (voor het lijsten-menu), tekst = uitgepakt (± wat het op de telefoon kost), lijst = de vakken (om te wissen)
        index['landen'][code] = {'bestand': code + '.tsv.gz', 'naam': namen.get(code, code), 'datum': datum[code],
                                 'bytes': os.path.getsize(doel), 'tekst': tekst, 'rijen': n, 'vakken': len(vs),
                                 'lijst': ' '.join('%d_%d' % v for v in vs)}
        log(code, n, 'regels,', len(vs), 'vakken,', os.path.getsize(doel), 'bytes')

    # 6: elk vak ook los (v63.97). Stand = de nieuwste van de extracten (de app ziet zo elke maand een nieuwe stand).
    index['vakken'] = schrijf_vakken(a.uit, a.werk, set().union(*land_vakken.values()), rijen, max(datum[c] for c in landen))
    schrijf_index(a.uit, index)
    log('klaar')


if __name__ == '__main__':
    main()
