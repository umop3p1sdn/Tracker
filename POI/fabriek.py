#!/usr/bin/env python3
"""POI-fabriek voor HO-ME Live Tracker (v63.93).

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
  5. POI/index.json met per land de datum van de gegevens, de grootte en het aantal plekken.

De lagen en velden moeten gelijk zijn aan die in de app (POI_VOORRAAD, POI_REST, POI_EXTRA en hun velden).
Gegevens: (c) OpenStreetMap-bijdragers, ODbL 1.0 - zie LEESMIJ.md.

Testen zonder downloads:  python3 fabriek.py --bron MAP --landen MC=monaco --buren france --uit UITMAP
  (MAP bevat <naam>-latest.osm.pbf en <naam>.poly)
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

GEOFABRIK = 'https://download.geofabrik.de/europe/'
LANDEN = {'NL': 'netherlands', 'BE': 'belgium', 'DE': 'germany', 'LU': 'luxembourg', 'FR': 'france'}
# Alleen voor de volledigheid van grensvakken (geen eigen bestand): Monaco ligt in het vak van Nice
HULP = {'MC': 'monaco'}
# Buurlanden die we niet maken: een vak met land van een van deze is niet compleet en gaat niet in de bestanden
BUREN = ['denmark', 'poland', 'czech-republic', 'austria', 'switzerland', 'liechtenstein', 'italy',
         'spain', 'andorra', 'united-kingdom', 'guernsey-jersey']
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
    a = ap.parse_args()

    landen = dict(x.split('=') for x in a.landen.split(',')) if a.landen else dict(LANDEN)
    hulp = dict(x.split('=') for x in a.hulp.split(',') if x) if a.hulp is not None else dict(HULP)
    buren = [x for x in (a.buren.split(',') if a.buren is not None else BUREN) if x]
    os.makedirs(a.werk, exist_ok=True)
    os.makedirs(a.uit, exist_ok=True)

    def bron(naam, ext):
        if a.bron:
            return os.path.join(a.bron, naam + ext)
        pad = os.path.join(a.werk, naam + ext)
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

    # 1 + 2: per land ophalen en filteren (de hulp-extracten ook: hun plekken maken grensvakken compleet)
    datum, poi = {}, []
    for code, naam in list(landen.items()) + list(hulp.items()):
        groot = bron(naam, '-latest.osm.pbf')
        datum[code] = subprocess.run(['osmium', 'fileinfo', '-g', 'header.option.osmosis_replication_timestamp', groot],
                                     check=True, capture_output=True, text=True).stdout.strip()
        if not datum[code]:                    # geen stand in het bestand: dan de tijd van nu (de app ziet dan toch een nieuwe stand)
            datum[code] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        klein = os.path.join(a.werk, code + '-poi.osm.pbf')
        run('osmium', 'tags-filter', groot, *filter_expressies(), '-o', klein, '-O')
        if not a.bron:
            os.remove(groot)                   # schijfruimte: Duitsland en Frankrijk zijn elk 4,5 GB
        poi.append(klein)
        log(code, 'datum', datum[code], 'gefilterd', os.path.getsize(klein), 'bytes')

    # 3: samenvoegen en naar regels
    alle = os.path.join(a.werk, 'alle.osm.pbf')
    run('osmium', 'merge', *poi, '-o', alle, '-O')
    geo = os.path.join(a.werk, 'alle.geojsonseq')
    run('osmium', 'export', alle, '-f', 'geojsonseq', '-a', 'type,id', '-o', geo, '-O')

    rijen = {}                                 # (i, j) -> lijst (laagnr, id, regel)
    gezien = set()
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
    log('plekken', len(gezien), 'vakken met plekken', len(rijen))

    # 4: vakken per land; een vak met LAND van een buurland (dat we niet maken) is niet compleet. Alleen land telt: de
    # grenzen van Geofabrik lopen ook over zee (Deens water tot vlak bij Rostock, het Kanaal tot bij Calais) - daar staan
    # geen plekken van dat buurland.
    vormen = {code: lees_poly(bron(naam, '.poly')) for code, naam in landen.items()}
    buur = [prep(lees_poly(bron(n, '.poly'))) for n in buren]
    gx0, gy0, gx1, gy1 = unary_union(list(vormen.values())).bounds
    land = lees_land([bron(n, '.geojson') for n in LAND_BESTANDEN], (gx0 - 1, gy0 - 1, gx1 + 1, gy1 + 1))
    land_p = prep(land)
    oordeel = {}                               # vak -> True = niet compleet
    def niet_compleet(v):
        if v not in oordeel:
            r = box(v[1] * VAK, v[0] * VAK, (v[1] + 1) * VAK, (v[0] + 1) * VAK)
            oordeel[v] = land_p.intersects(r) and any(b.intersects(r.intersection(land)) for b in buur)
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
        n = 0
        tijdelijk = os.path.join(a.werk, code + '.tsv.gz')
        with open(tijdelijk, 'wb') as ruw:
            with gzip.GzipFile(filename='', mode='wb', fileobj=ruw, compresslevel=9, mtime=0) as gz:
                def w(s):
                    gz.write((s + '\n').encode('utf-8'))
                w('#POI\t%d\t%s\t%s' % (FORMAAT, code, datum[code]))
                w('#velden\t' + ' '.join(VELDEN))
                w('#vakken\t' + ' '.join('%d_%d' % v for v in vs))
                for v in vs:
                    for _, _, regel in sorted(rijen.get(v, [])):
                        w(regel)
                        n += 1
                w('#einde\t%d' % n)
        doel = os.path.join(a.uit, code + '.tsv.gz')
        shutil.move(tijdelijk, doel)
        index['landen'][code] = {'bestand': code + '.tsv.gz', 'datum': datum[code], 'bytes': os.path.getsize(doel),
                                 'rijen': n, 'vakken': len(vs)}
        log(code, n, 'regels,', len(vs), 'vakken,', os.path.getsize(doel), 'bytes')

    with open(os.path.join(a.uit, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
        f.write('\n')
    log('klaar')


if __name__ == '__main__':
    main()
