# POI — plekken voor de HO-ME Live Tracker

Deze map bevat de POI-bestanden die de app downloadt (📥 Lijsten → landen aantikken → Download): per land één bestand met
⛽ benzine, 🍽 restaurant, 🛒 supermarkt, ⚡ laden, 🍔 snack, ☕ café, 🥐 bakker, 🛏 hotel, 🏧 pin, 🚻 wc,
📷 uitzicht/bezienswaardigheid, kroeg en foodcourt.

| Bestand | Wat |
|---|---|
| `index.json` | per land: bestandsnaam, naam, datum van de gegevens, grootte (download en uitgepakt), aantal plekken, de vakken |
| `NL.tsv.gz`, `DE.tsv.gz`, `AT.tsv.gz`, … | de plekken (tekst met tabs, gzip) — ±40 landen: heel Europa behalve Rusland, Wit-Rusland, Oekraïne, Moldavië, Georgië en Turkije |
| `fabriek.py` | het script dat ze maakt |
| `opslaan.sh` | opslaan + de oude POI-versies uit de geschiedenis halen |

## Hoe ze gemaakt worden

De **POI-fabriek** (`.github/workflows/poi.yml`) draait vanzelf de 3e van elke maand, of met de hand:
tab **Actions** → **POI-fabriek** → **Run workflow** (±40 minuten). Hij:

1. haalt per land het OpenStreetMap-extract bij [Geofabrik](https://download.geofabrik.de/europe.html) — één keer per
   land per run, met MD5-controle (als Geofabrik die heeft; anders controleert osmium het bestand);
2. houdt met `osmium` alleen de POI-soorten over;
3. zet per plek het midden (net als Overpass `out center`) en verdeelt alles over vakken van 0,5°;
4. schrijft per land alle vakken die het land raakt — compleet, dus een grensvak met Duitsland bevat ook de Duitse
   plekken (en Monaco is een eigen land, dus het vak van Nice is compleet). Vakken met **land** van een land dat hier niet bij zit
   (bv. Oekraïne) worden weggelaten: die haalt de app zelf als je daar bent. Alleen land telt (Natural Earth,
   publiek domein) — de grenzen van Geofabrik lopen ook over zee, en anders viel bv. Rostock weg om Deens water;
5. slaat de bestanden hier op én haalt de oude versies van de POI-bestanden uit de geschiedenis van de repo (`opslaan.sh`):
   alleen de nieuwste blijft, dus de repo groeit niet mee. Dat gebeurt alleen als niemand tussendoor iets op `main` heeft
   gezet (git `--force-with-lease`); anders slaat hij gewoon op en ruimt hij de volgende keer op. De site bouwt daarna
   vanzelf opnieuw.

Alleen opruimen (zonder nieuwe lijsten te maken): **Actions** → **POI-fabriek** → **Run workflow** → vink
**Alleen opruimen** aan.

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
#vakken	101_6 101_7 …                      (alle vakken in dit bestand, ook lege)
b	n123	52.09071	5.12140	fuel		…   (laag b/r/x, id, lat, lon, velden; gesorteerd per vak)
#einde	95123                              (aantal regels — ontbreekt deze regel, dan is het bestand niet compleet)
```
