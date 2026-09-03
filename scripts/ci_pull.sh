#!/usr/bin/env bash
# scripts/ci_pull.sh — der Pull vor dem Push, der an untrackten Dateien nicht scheitert.
#
# 03.09.2026 (Lucas: „ein poly scan von vorhin ging schief"). Der Lauf um 05:09 UTC committete
# lokal, kam dann aber fuenfmal nicht durch:
#
#     error: The following untracked working tree files would be overwritten by merge:
#             wm_poly_slugs.json
#     Aborting → Merge with strategy ort failed → push rejected (non-fast-forward)
#
# Ursache und Zusammenhang: `--autostash` legt nur GETRACKTE Aenderungen weg. Eine untrackte
# Datei, die der eingehende Commit NEU mitbringt, blockiert den Merge — git will nichts
# ueberschreiben, was es nicht kennt. `wm_poly_slugs.json` schreibt fetch_wm_poly_prices.py seit
# jeher, committet wurde sie aber nie: die Registry-Staging-Zeile war die zerschredderte
# Kommando-Substitution (`git add $(python3` ueber vier Zeilen). Seit deren Reparatur am 02.09.
# landet die Datei erstmals auf origin — und auf jedem selbst-gehosteten Runner, der sie schon
# einmal erzeugt hatte, liegt sie untracked im Weg. Ein Fix legt also einen zweiten Fehler frei,
# der die ganze Zeit da war.
#
# Statt die Fehlermeldung zu parsen wird die Kollision VORHER berechnet: welche Dateien bringt
# origin/main neu mit, und welche davon liegen lokal untracked herum? Genau die werden nach
# .ci_kollisionen/ verschoben — nicht geloescht. Sie waren nicht Teil unseres Commits (sonst
# waeren sie getrackt), origins Fassung gewinnt, und der naechste Job-Lauf erzeugt sie ohnehin neu.
#
# Aufruf im Workflow:  bash scripts/ci_pull.sh [branch] [merge|rebase]
#   merge  (Standard) = --no-rebase -X ours --autostash, wie ueberall im Repo
#   rebase             = --rebase --autostash, fuer die zwei Workflows, die das bewusst so machen
set -uo pipefail
BRANCH="${1:-main}"
MODUS="${2:-merge}"
ABLAGE=".ci_kollisionen"

git fetch origin "$BRANCH" 2>&1 || true

# Dateien, die der eingehende Stand NEU hinzufuegt (A = added gegenueber unserem HEAD).
# Gegen FETCH_HEAD, nicht gegen origin/$BRANCH: die Remote-Tracking-Referenz existiert auf einem
# frisch angelegten Checkout nicht zwingend, FETCH_HEAD nach dem fetch dagegen immer.
NEU=$(git diff --name-only --diff-filter=A HEAD FETCH_HEAD 2>/dev/null || true)
VERSCHOBEN=0
if [ -n "$NEU" ]; then
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    # nur was lokal EXISTIERT und NICHT getrackt ist, ist eine echte Kollision
    [ -e "$f" ] || continue
    git ls-files --error-unmatch "$f" >/dev/null 2>&1 && continue
    mkdir -p "$ABLAGE/$(dirname "$f")"
    if mv -f "$f" "$ABLAGE/$f" 2>/dev/null; then
      echo "↪️  untrackte Kollision beiseite gelegt: $f → $ABLAGE/$f"
      VERSCHOBEN=$((VERSCHOBEN + 1))
    else
      echo "⚠️  $f liess sich nicht wegraeumen — der Merge wird daran scheitern."
    fi
  done <<< "$NEU"
fi
[ "$VERSCHOBEN" -gt 0 ] && echo "↪️  $VERSCHOBEN untrackte Datei(en) aus dem Weg geraeumt."

if [ "$MODUS" = "rebase" ]; then
  git pull --rebase --autostash origin "$BRANCH" 2>&1 || true
else
  git pull origin "$BRANCH" --no-rebase -X ours --autostash 2>&1 || true
fi
