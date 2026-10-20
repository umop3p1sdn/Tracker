#!/usr/bin/env bash
# POI-fabriek: de nieuwe lijsten opslaan ÉN de oude uit de geschiedenis halen (v63.96, Sjoerd: "Waarom niet vaker
# opruimen? Oude hebben geen waarde meer toch?" + "alleen de oude weg en de laatste laten staan").
# Draait in de map van de repo (volledige geschiedenis: actions/checkout met fetch-depth 0), nadat fabriek.py de nieuwe
# POI/*.tsv.gz + POI/index.json heeft geschreven (v63.97: en de losse vakken in POI/v/).
#  1. Oude POI-bestanden uit ALLE commits halen (git filter-repo; commits die alleen POI waren vallen weg), de nieuwe
#     erbovenop als één commit, en dan "force-with-lease": dat lukt alleen als main nog precies is zoals de fabriek hem
#     ophaalde. Heeft iemand er tussendoor iets op gezet, dan weigert git — er gaat dus nooit iets verloren.
#  2. Lukt dat niet: gewoon opslaan zoals vroeger (pull --rebase, hooguit 3x push) — opruimen gebeurt dan de volgende keer.
# De app-bestanden en hun geschiedenis blijven; alleen de interne nummers (SHA's) van de commits veranderen.
set -uo pipefail
uit() { [ -n "${GITHUB_OUTPUT:-}" ] && echo "$1" >> "$GITHUB_OUTPUT"; return 0; }
TAK="${TAK:-main}"
git config user.name "POI-fabriek"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
OUD=$(git rev-parse HEAD)
git add -A POI
# OPRUIMEN=1 (met de hand, Actions -> POI-fabriek -> Run workflow -> "alleen opruimen"): niets nieuws maken, alleen de oude
# POI-versies uit de geschiedenis halen (de huidige blijven)
if git diff --cached --quiet && [ "${OPRUIMEN:-}" != 1 ]; then echo "niets veranderd"; uit "veranderd=nee"; exit 0; fi
STAND="POI: stand $(date -u +%Y-%m-%d)"
NIEUWS=1
if git diff --cached --quiet; then NIEUWS=0; STAND="POI: stand $(git log -1 --format=%cs -- POI/index.json) (opgeruimd)"; fi
NIEUW=$(mktemp -d)
cp POI/*.tsv.gz POI/index.json "$NIEUW"/
if [ -d POI/v ]; then cp -r POI/v "$NIEUW"/; fi          # v63.97: de losse vakken (POI/v/<rij>/<kolom>.tsv.gz)
git reset -q --hard "$OUD"
URL=$(git remote get-url origin)

# 1) opruimen + opslaan (alleen als main niet bewogen heeft)
# --replace-refs delete-no-add: geen verwijzingen oud→nieuw achterlaten (GEMETEN in de proef: daarmee raakte een latere
# fetch in de war — "expected 'acknowledgments', received 'packfile'")
if git filter-repo --force --quiet --replace-refs delete-no-add --invert-paths --path-glob 'POI/*.tsv.gz' --path POI/index.json --path POI/v; then
  git remote add origin "$URL" 2>/dev/null || git remote set-url origin "$URL"
  cp -r "$NIEUW"/. POI/
  git add -A POI
  git commit -q -m "$STAND"
  # push.negotiate uit: na het herschrijven kent de server onze commits niet (GEMETEN: "push negotiation failed")
  if git -c push.negotiate=false push -q --force-with-lease="$TAK:$OUD" origin "HEAD:$TAK"; then
    echo "opgeslagen en opgeruimd (alleen de nieuwste POI-bestanden in de geschiedenis)"
    uit "veranderd=ja"; uit "opgeruimd=ja"; exit 0
  fi
  echo "opruimen ging niet (main is tussendoor veranderd, of force-push mag niet)"
else
  echo "filter-repo lukte niet - gewoon opslaan"
  git remote add origin "$URL" 2>/dev/null || git remote set-url origin "$URL"
fi

# Alleen opruimen (niets nieuws): wat hier staat kan ouder zijn dan main nu (die bewoog) - dus NIET terugzetten, stoppen;
# de volgende run ruimt op.
if [ "$NIEUWS" = 0 ]; then echo "niets nieuws op te slaan - niets veranderd"; uit "veranderd=nee"; exit 0; fi

# 2) gewoon opslaan (zoals vroeger)
echo "gewoon opslaan"
gelukt=nee
for poging in 1 2 3; do
  # noop: na het herschrijven kent de server onze commits niet, onderhandelen heeft dan geen zin (in de proef ging juist
  # die onderhandeling bij de push mis); zonder onderhandelen haalt hij main gewoon in één keer
  git -c fetch.negotiationAlgorithm=noop fetch -q --no-tags origin "$TAK" && git reset -q --hard FETCH_HEAD || { sleep 20; continue; }
  # v63.97: eerst de oude POI-gegevens weg - een vak dat nu leeg is (of een land dat er niet meer bij is) mag niet blijven
  rm -rf POI/v; rm -f POI/*.tsv.gz POI/index.json
  cp -r "$NIEUW"/. POI/
  git add -A POI
  if git diff --cached --quiet; then gelukt=ja; break; fi
  git commit -q -m "$STAND"
  if git push -q origin "HEAD:$TAK"; then gelukt=ja; break; fi
  sleep 20
done
[ "$gelukt" = ja ] || { echo "opslaan mislukt"; exit 1; }
echo "opgeslagen (nog niet opgeruimd - volgende keer)"
uit "veranderd=ja"; uit "opgeruimd=nee"
