#!/usr/bin/env bash
# scripts/ci_keine_marker.sh — kein Commit mit Git-Konfliktmarkern im Artefakt.
#
# 🔴 19.09.2026 (Lucas: „Heut kein einziger polymarket Push in public (kann nicht sein)").
# Konnte sehr wohl sein. Der Lauf „🐋 Poly Global-Scan 19.09.2026 18:05 UTC" (9b1e5f47a3) hatte
# FUENFZEHN Poly-Artefakte mit Konfliktmarkern committet:
#
#       "htkFirst": 2.57
#      },
#     <<<<<<< Updated upstream
#       "0x2a69...|epl-eve-ips-2026-09-19-exact-score|...": {
#
#     poly_wallet_track.json        13 Konflikte      poly_money_upcoming.json     621
#     poly_money_broad_close.json   30                poly_money_broad_live.json   178
#
# „Updated upstream / Stashed changes" ist die Sprache von `git stash pop` — also vom
# `--autostash` in scripts/ci_pull.sh, das im Push-Retry laeuft. Kollidiert der Autostash-Pop
# mit dem eingehenden Stand, schreibt git die Marker IN die Datei und laesst sie dort liegen.
# Der naechste Lauf staged sie mit `git add` und schickt sie weg.
#
# Die Datei ist danach kein JSON mehr. Und die Leser fangen die Exception ab und arbeiten mit
# dem Default weiter — poly_whale_watch lief drei Stunden auf {} Wallets, fand null Kandidaten
# und schwieg. Kein Absturz, kein roter Lauf. Genau die Fehlerklasse „fehlende Information
# rendert als harmloser Default", an der lautesten moeglichen Stelle.
#
# Der Griff hier ist absichtlich stumpf: eine Datei mit Markern ist NIE richtig, egal welche
# Seite gewinnen sollte. Sie wird auf den letzten committeten Stand zurueckgesetzt — die
# Pipeline erzeugt ihren Inhalt im naechsten Lauf ohnehin neu. Lieber vier Minuten Daten
# verlieren als drei Stunden still nichts senden.
#
# Aufruf:  bash scripts/ci_keine_marker.sh        (vor `git add` / nach `ci_pull.sh`)
# Beendet sich NIE mit Fehler — ein Waechter darf den Lauf nicht kippen, den er schuetzt.
set -uo pipefail

BETROFFEN=$(git grep -l -I -E '^(<<<<<<< |>>>>>>> )' -- '*.json' '*.py' '*.js' '*.mjs' '*.yml' 2>/dev/null || true)
# git grep sieht nur getrackte Dateien — genau richtig: untrackte werden nicht committet.

if [ -z "$BETROFFEN" ]; then
  exit 0
fi

# Die letzte Fassung OHNE Marker holen. Meist ist das HEAD — aber wenn der Schaden schon
# committet wurde (am 19.09. war er das, zweimal hintereinander), steckt er auch in HEAD, und
# ein `git checkout HEAD -- f` holt ihn nur zurueck. Dann wird die Historie zurueckgelaufen,
# bis eine saubere Fassung kommt. Ein Waechter, der den Schaden nur benennt, ist keiner.
# ⚠️ KEINE PIPE in die Pruefung. Der erste Entwurf hatte
#       if ! git show "$sha:$f" | grep -q '^<<<<<<< '
#   und meldete fuer ZWOELF kaputte Dateien "geheilt aus HEAD", waehrend die Marker unveraendert
#   drinstanden: `grep -q` steigt beim ersten Treffer aus, `git show` stirbt an SIGPIPE, und mit
#   `set -o pipefail` (oben) ist der Status der Pipe dann git's 141 statt grep's 0 — die Bedingung
#   drehte sich also GENAU dann um, wenn Marker da waren. Deshalb erst in eine Datei schreiben,
#   dann die Datei pruefen.
heile() {
  f="$1"
  for sha in HEAD $(git log --format=%H -40 -- "$f"); do
    git show "$sha:$f" > "$f.ci_heil" 2>/dev/null || { rm -f "$f.ci_heil"; continue; }
    if grep -q '^<<<<<<< ' "$f.ci_heil"; then
      rm -f "$f.ci_heil"; continue
    fi
    mv -f "$f.ci_heil" "$f"
    echo "$sha"
    return 0
  done
  rm -f "$f.ci_heil"
  return 1
}

echo "🔴 Konfliktmarker in getrackten Dateien gefunden — sie werden NICHT committet:"
echo "$BETROFFEN" | while read -r f; do
  [ -n "$f" ] || continue
  ANZ=$(grep -c '^<<<<<<< ' "$f" 2>/dev/null || echo 0)
  if SHA=$(heile "$f"); then
    echo "   · $f ($ANZ Konflikt(e)) → geheilt aus ${SHA:0:10}"
  else
    echo "   ⚠️  $f ($ANZ Konflikt(e)) → KEINE saubere Fassung in 40 Commits, bleibt kaputt"
  fi
done

REST=$(git grep -l -I -E '^(<<<<<<< |>>>>>>> )' -- '*.json' '*.py' '*.js' '*.mjs' '*.yml' 2>/dev/null || true)
if [ -n "$REST" ]; then
  echo "⚠️  nicht heilbar, von Hand ansehen:"
  echo "$REST" | sed 's/^/   · /'
fi
exit 0
