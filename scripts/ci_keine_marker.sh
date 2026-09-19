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

echo "🔴 Konfliktmarker in getrackten Dateien gefunden — sie werden NICHT committet:"
N=0
echo "$BETROFFEN" | while read -r f; do
  [ -n "$f" ] || continue
  ANZ=$(grep -c '^<<<<<<< ' "$f" 2>/dev/null || echo 0)
  echo "   · $f ($ANZ Konflikt(e)) → zurueck auf den letzten committeten Stand"
  git checkout HEAD -- "$f" 2>/dev/null || true
  N=$((N + 1))
done
# Kontrolle: ist wirklich nichts mehr uebrig?
REST=$(git grep -l -I -E '^(<<<<<<< |>>>>>>> )' -- '*.json' '*.py' '*.js' '*.mjs' '*.yml' 2>/dev/null || true)
if [ -n "$REST" ]; then
  echo "⚠️  Marker ueberleben das Zuruecksetzen — sie stecken im COMMIT selbst:"
  echo "$REST" | sed 's/^/   · /'
  echo "   Das muss von Hand ausgeraeumt werden (letzte gute Fassung aus der Historie holen)."
fi
exit 0
