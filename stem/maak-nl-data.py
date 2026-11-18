# Maakt nl-data.bin: alleen de Nederlandse eSpeak NG-data, in één bestand.
# Formaat: 'HOST' (4 bytes) + lengte van de kop (uint32, little-endian) + kop (JSON) + de bestanden achter elkaar.
# Bron: de map espeak-ng-data/ uit het npm-pakket text2wav 0.0.14 (eSpeak NG 1.49.3-dev, git e13b602).
# Gebruik: python3 maak-nl-data.py pad/naar/espeak-ng-data/ nl-data.bin
import json, struct, sys
D, uit = sys.argv[1], sys.argv[2]
bestanden = ['phontab', 'phonindex', 'phondata', 'intonations', 'nl_dict', 'lang/gmw/nl']
kop, data = [], b''
for p in bestanden:
    b = open(D.rstrip('/') + '/' + p, 'rb').read()
    kop.append({'p': p, 's': len(data), 'n': len(b)})
    data += b
k = json.dumps({'v': 1, 'bron': 'espeak-ng 1.49.3-dev (text2wav 0.0.14)', 'bestanden': kop}, separators=(',', ':')).encode()
open(uit, 'wb').write(b'HOST' + struct.pack('<I', len(k)) + k + data)
