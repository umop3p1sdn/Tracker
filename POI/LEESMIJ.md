# POI — plekken voor de HO-ME Live Tracker

Deze map bevat de POI-bestanden van de app: ⛽ benzine, 🍽 restaurant, 🛒 supermarkt, ⚡ laden, 🍔 snack, ☕ café,
🥐 bakker, 🛏 hotel, 🏧 pin, 🚻 wc, 📷 uitzicht/bezienswaardigheid, kroeg en foodcourt — en sinds v64.8 (laag `d`, het
tabblad **Service** in de app) 🅿️ parkeren, ⛺ camping/camperplaats, 🏦 bank, 🏥 ziekenhuis, 👮 politie, 💊 apotheek,
🔧 garage (werkplaats, motorzaak/-werkplaats, banden) en 🚉 treinstation/halte — op twee manieren:

- **zoeken** (v63.97): zoek je iets (bv. ⛽ Benzine), dan haalt de app alleen de vakken van 0,5° die hij nodig heeft uit
  `v/` (Lokaal: 1–4 vakken, meestal een paar honderd KB) en bewaart ze op je telefoon — zonder eerst iets te downloaden;
- **offline** (📥 Lijsten → landen aantikken → Download): per land één bestand, alles vooraf op je telefoon (voor onderweg
  zonder bereik).

| Bestand | Wat |
|---|---|
| `index.json` | de lagen (`lagen`, v64.8); per land: bestandsnaam, naam, datum van de gegevens, grootte (download en uitgepakt), aantal plekken, de vakken; bij `vakken`: welke losse vakken er zijn (zie onder) |
| `NL.tsv.gz`, `DE.tsv.gz`, `AT.tsv.gz`, … | de plekken per land (tekst met tabs, gzip) — ±40 landen: heel Europa behalve Rusland, Wit-Rusland, Oekraïne, Moldavië, Georgië en Turkije |
| `v/<rij>/<kolom>.tsv.gz` | dezelfde plekken per vak van 0,5° (bv. `v/104/11.tsv.gz` = Ede, `v/97/4.tsv.gz` = Parijs); per rij een map, omdat GitHub hooguit 3.000 dingen per map aanraadt |
| `fabriek.py` | het script dat ze maakt |
| `opslaan.sh` | opslaan + de oude POI-versies uit de geschiedenis halen |

## Hoe ze gemaakt worden

De **POI-fabriek** (`.github/workflows/poi.yml`) draait vanzelf de 3e van elke maand, of met de hand:
tab **Actions** → **POI-fabriek** → **Run workflow** (±2,5 uur, vooral het downloaden bij Geofabrik). v64.8: zijn de
lijsten op de 3e nog geen 14 dagen oud (net met de hand gemaakt), dan slaat de geplande run die maand over — met de hand
starten gaat altijd. Hij:

1. haalt per land het OpenStreetMap-extract bij [Geofabrik](https://download.geofabrik.de/europe.html) — één keer per
   land per run, met MD5-controle (als Geofabrik die heeft; anders controleert osmium het bestand);
2. houdt met `osmium` alleen de POI-soorten over. Laag `d` neemt daarvan alleen (zie `dienst_past` in `fabriek.py`): niets
   privé; **parkeren** alleen openbaar (geen klanten, vergunning, bewoners …), geen vakken langs de straat, en dan een
   parkeergarage, P+R, een naam of minstens 50 plekken (in NL staan 236.120 parkeerplekken in OSM, meest kleine privé-
   terreinen — die blijven weg); **motorparkeren** alles wat openbaar is; **stations** alleen voor de trein (geen metro,
   sneltram, tram, kabelspoor);
3. zet per plek het midden (net als Overpass `out center`) en verdeelt alles over vakken van 0,5°;
4. schrijft per land alle vakken die het land raakt — compleet, dus een grensvak met Duitsland bevat ook de Duitse
   plekken (en Monaco is een eigen land, dus het vak van Nice is compleet). Vakken met **land** van een land dat hier niet bij zit
   (bv. Oekraïne) worden weggelaten: die haalt de app zelf als je daar bent. Alleen land telt (Natural Earth,
   publiek domein) — de grenzen van Geofabrik lopen ook over zee, en anders viel bv. Rostock weg om Deens water;
5. zet elk vak ook los in `v/` (v63.97) — een leeg vak (zee, of niets van deze soorten) krijgt geen bestand;
6. slaat de bestanden hier op én haalt de oude versies van de POI-bestanden uit de geschiedenis van de repo (`opslaan.sh`):
   alleen de nieuwste blijft, dus de repo groeit niet mee. Dat gebeurt alleen als niemand tussendoor iets op `main` heeft
   gezet (git `--force-with-lease`); anders slaat hij gewoon op en ruimt hij de volgende keer op. De site bouwt daarna
   vanzelf opnieuw.

Alleen opruimen (zonder nieuwe lijsten te maken): **Actions** → **POI-fabriek** → **Run workflow** → vink
**Alleen opruimen** aan.

Alleen de losse vakken opnieuw maken uit de landbestanden die hier al staan (niets bij Geofabrik, ±5 minuten): vink
**Alleen vakken** aan. (v64.8: dat kan ook met landbestanden van vóór laag `d` — de vakken krijgen dan alleen de lagen
die élk land heeft, `b r x`.)

Mislukt een run nadat de extracten binnen zijn, dan bewaart hij de gefilterde stukken (cache); een nieuwe run op dezelfde
dag haalt dan niets opnieuw bij Geofabrik. De grenzen (`.poly`) haalt hij als eerste: ontbreekt er een, dan stopt hij
meteen in plaats van na ±2 uur downloaden.

**Let op** — opruimen herschrijft de geschiedenis: de inhoud van alle app-commits blijft precies gelijk, maar hun nummers
(SHA) veranderen. Uploaden via de website van GitHub gaat gewoon. Wie de repo lokaal heeft (git): na een run eerst
`git fetch` en `git reset --hard origin/main` (een push vanaf een oude kopie wordt geweigerd — er gaat niets kapot).

## Licentie en bron

De gegevens komen van **OpenStreetMap** en vallen onder de
[Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/):
**© OpenStreetMap-bijdragers** — <https://www.openstreetmap.org/copyright>.
Deze bestanden zijn een afgeleide database en vallen daarom ook onder de ODbL: je mag ze gebruiken en delen, met
vermelding van de bron.

## Opbouw van een `.tsv.gz`

```
#POI	1	NL	2026-10-18T20:21:03Z        (formaat, land, stand van de OSM-gegevens)
#velden	amenity shop tourism name …        (namen van de kolommen na lat/lon)
#lagen	b r x d                            (v64.8: de lagen die dit bestand compleet heeft; ontbreekt de regel: b r x)
#vakken	101_6 101_7 …                      (alle vakken in dit bestand, ook lege)
b	n123	52.09071	5.12140	fuel		…   (laag b/r/x/d, id, lat, lon, velden; gesorteerd per vak)
#einde	95123                              (aantal regels — ontbreekt deze regel, dan is het bestand niet compleet)
```

Een los vak heeft dezelfde opbouw, met het vak waar het land stond: `#POI	1	104_11	<stand>` en `#vakken	104_11`.
In `index.json` staat bij `lagen` welke lagen de bestanden hebben (v64.8; ontbreekt het: b r x), en bij `vakken` de stand, en welke vakken er zijn: `vol` (met een bestand) en `leeg` (compleet, maar
zonder plekken — daar is geen bestand van). Kort geschreven per rij: `104:6..12,15` = rij 104, kolommen 6 t/m 12 en 15
(een kolom kan negatief zijn: west van Greenwich). Vak `rij_kolom` = de zuidwesthoek op (rij × 0,5°, kolom × 0,5°).

**Volgorde bij een nieuwe laag** (v64.8): een app van vóór v64.8 weigert een regel met een laag die hij niet kent. Daarom
eerst de app bijwerken (die leest `#lagen`, slaat een onbekende laag over en haalt wat een oud bestand niet heeft live), en
pas daarna de fabriek laten draaien.
