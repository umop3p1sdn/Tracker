# POI — plekken voor de HO-ME Live Tracker

Deze map bevat de POI-bestanden die de app downloadt (📥 Lijsten → landen → Download): per land één bestand met
⛽ benzine, 🍽 restaurant, 🛒 supermarkt, ⚡ laden, 🍔 snack, ☕ café, 🥐 bakker, 🛏 hotel, 🏧 pin, 🚻 wc,
📷 uitzicht/bezienswaardigheid, kroeg en foodcourt.

| Bestand | Wat |
|---|---|
| `index.json` | per land: bestandsnaam, datum van de gegevens, grootte, aantal plekken en vakken |
| `NL.tsv.gz`, `BE.tsv.gz`, `DE.tsv.gz`, `LU.tsv.gz`, `FR.tsv.gz` | de plekken (tekst met tabs, gzip) |
| `fabriek.py` | het script dat ze maakt |

## Hoe ze gemaakt worden

De **POI-fabriek** (`.github/workflows/poi.yml`) draait vanzelf de 3e van elke maand, of met de hand:
tab **Actions** → **POI-fabriek** → **Run workflow** (±20–30 minuten). Hij:

1. haalt per land het OpenStreetMap-extract bij [Geofabrik](https://download.geofabrik.de/europe.html) — één keer per
   land per run, met MD5-controle;
2. houdt met `osmium` alleen de POI-soorten over;
3. zet per plek het midden (net als Overpass `out center`) en verdeelt alles over vakken van 0,5°;
4. schrijft per land alle vakken die het land raakt — compleet, dus een grensvak met Duitsland bevat ook de Duitse
   plekken. Vakken die een land raken dat hier niet bij zit (bv. Oostenrijk) worden weggelaten: die haalt de app zelf
   als je daar bent;
5. slaat de bestanden hier op en laat de site opnieuw bouwen.

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
