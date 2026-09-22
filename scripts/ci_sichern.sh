#!/usr/bin/env bash
# scripts/ci_sichern.sh — den Beleg einer Wirkung SOFORT dauerhaft machen.
#
# 🔴 19.09.2026 (Lucas: „Push kam 2x. Wurde auch 2x auf Poly gesetzt." — Vila Nova FC vs
# América FC, 18.09. 23:39 UTC).
#
# In allen Buechern stand der Play genau EINMAL: eine Zeile im Push-Buch, eine im Dedup-Stand,
# eine Wette mit einer Order-ID. Zwei Nachrichten und zwei Orders gab es trotzdem.
#
# Der Grund ist keine Zeile Code, sondern eine Reihenfolge. Push und Auto-Play wirken sofort und
# ausserhalb dieses Repos: die Nachricht ist raus, die Order liegt an der Boerse. Der BELEG dafuer
# — der Dedup-Stand — wurde bis heute erst im Commit-Schritt ganz am Ende des Laufs dauerhaft,
# rund zehn Schritte spaeter. Alles, was dazwischen den Lauf beendet (das 25-Minuten-Timeout, ein
# Abbruch, ein gescheiterter Push), laesst die Wirkung stehen und loescht die Erinnerung. Der
# naechste Lauf liest den alten Stand und macht beides noch einmal.
#
# Die Regel dahinter gilt ueberall, wo ein Schritt nach draussen wirkt: **wer handelt, schreibt
# sofort.** Ein Gedaechtnis, das erst am Ende des Laufs dauerhaft wird, ist fuer jeden Lauf, der
# das Ende nicht erreicht, gar keines.
#
# Aufruf:  bash scripts/ci_sichern.sh "<Grund fuer die Commit-Nachricht>" datei1.json datei2.json …
# Faellt NIE hart aus: der aufrufende Lauf soll weiterlaufen, der End-Commit versucht es erneut.
set -uo pipefail
GRUND="${1:-Zwischenstand}"
shift || true

git config --local user.email "action@github.com"
git config --local user.name  "GitHub Action"

ETWAS=0
for f in "$@"; do
  [ -f "$f" ] && git add "$f" && ETWAS=1
done
[ "$ETWAS" -eq 0 ] && { echo "ℹ️  keine der Dateien existiert — nichts zu sichern."; exit 0; }

if git diff --staged --quiet; then
  echo "ℹ️  nichts Neues — kein Zwischen-Commit noetig."
  exit 0
fi

git commit -m "🔐 $GRUND $(date -u +'%d.%m.%Y %H:%M') UTC" || { echo "⚠️  commit fehlgeschlagen"; exit 0; }

# 🔴 21.09.2026 (Lucas: „das kam als Fehler" — `GITHUB_TOKEN: unbound variable`, Zeile 42).
# Hier stand `${GITHUB_TOKEN}` blank unter `set -u`. Auf dem self-hosted Mac steht die Variable
# in der Runner-Umgebung, also lief es dort seit Wochen; der erste Lauf auf `ubuntu-latest` —
# der Verlauf-Nachtrag — brach genau hier ab. Der Commit war da, der Push nie, und weil der
# Runner danach verschwindet, war die ganze Arbeit weg.
#
# Zwei Dinge daran waren falsch. Das Skript verlangte eine Variable, die es nirgends deklariert
# und die nur auf EINEM Runner-Typ zufaellig existiert. Und es brauchte sie gar nicht:
# `actions/checkout` legt den Token als `http.extraheader` in die lokale Git-Config, der Push
# geht auch ohne. Die Umschreibung ist nur ein Ersatzweg fuer den Fall, dass er fehlt.
# Fehlerklasse: eine Abhaengigkeit, die nirgends steht und deshalb nur dort auffaellt, wo sie
# fehlt — also spaet.
if [ -n "${GITHUB_TOKEN:-}" ] && [ -n "${GITHUB_REPOSITORY:-}" ]; then
  git remote set-url origin "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" 2>/dev/null || true
  git config --local credential.helper "" 2>/dev/null || true
fi
for versuch in 1 2 3; do
  bash scripts/ci_pull.sh main || true
  if git push 2>&1; then echo "✅ Beleg gesichert (Versuch $versuch)"; exit 0; fi
  echo "⚠️  Push $versuch fehlgeschlagen — retry…"
  sleep $((versuch * 3))
done
echo "⚠️  Beleg nicht gepusht — der Lauf laeuft weiter, der End-Commit versucht es erneut."
exit 0
