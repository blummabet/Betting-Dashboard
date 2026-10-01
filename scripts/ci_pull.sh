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

# 🔴 30.09.2026 (Lucas: „paar Fehler aus Poly bzw. Betfair Actions in den letzten 2-3 Stunden",
# zweimal „Error: The operation was canceled."). Gemessen: Betfair 808 s und 843 s statt 90-120 s
# (09:23 und 10:23 UTC), der Live-Scan um 09:40 UTC lief 760 s und wurde IM PULL-SCHRITT
# abgebrochen — bevor er ueberhaupt scannte. Alle drei Workflows gleichzeitig langsam, jedes Mal
# rund um git. Ein `git fetch`/`git push` hat von sich aus KEINE Zeitgrenze: stockt die
# Verbindung, wartet er, bis der Job-Deckel ihn abschiesst — und mit ihm alles, was danach
# gekommen waere.
# Fehlerklasse: eine Netz-Operation ohne Zeitgrenze. Git hat eine eigene Bremse: faellt die
# Uebertragung 60 s lang unter 1 kB/s, bricht sie ab (und `|| true` bzw. die Retry-Schleifen
# fangen das). Als Repo-Konfiguration gesetzt, damit sie auch fuer jedes spaetere `git push`
# im selben Checkout gilt — 42 Workflows ziehen hierueber, statt 42 Dateien einzeln.
git config http.lowSpeedLimit 1000 2>/dev/null || true
git config http.lowSpeedTime 60 2>/dev/null || true
export GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=60
BRANCH="${1:-main}"
MODUS="${2:-merge}"
ABLAGE=".ci_kollisionen"

# 🔴 01.10.2026 (Live-Scan 12:43 UTC abgebrochen): die Bremse oben greift nur, wenn die Leitung
# UNTER 1 kB/s faellt. Der Lauf zeigte beides: erst „RPC failed; curl 28 Operation too slow" beim
# fetch (Bremse hat gegriffen) — und dann holte `git pull` DENSELBEN Stand ein zweites Mal ueber
# die Leitung, troepfelte knapp darueber und lief in den 12-Minuten-Deckel des Jobs.
# Zwei Regeln gegen die Klasse „Netz-Operation ohne harte Frist":
#   1. eine harte Frist um den fetch (eigene Funktion: auf dem Mac-Runner gibt es kein `timeout`);
#   2. genau EIN Netzzugriff. Gemergt wird danach lokal aus FETCH_HEAD — `git pull` waere ein
#      zweiter fetch. Scheitert der fetch, wird nicht gemergt: der Lauf arbeitet mit dem lokalen
#      Stand weiter, der Push-Schritt am Ende holt ohnehin nach.
FRIST_S="${CI_PULL_FRIST_S:-150}"
# Die Frist beendet die GANZE Prozessgruppe: git fetch startet git-remote-https als Kind, und
# ein ueberlebendes Kind hielte die Log-Leitung offen — der Schritt haenge weiter (beim Bau
# so gemessen, mit perl-alarm allein). `set -m` gibt jedem Hintergrund-Job eine eigene Gruppe.
_mit_frist() {
  set -m
  "$@" &
  local pid=$!
  ( sleep "$FRIST_S"; kill -TERM -- "-$pid" 2>/dev/null ) >/dev/null 2>&1 &
  local wd=$!
  wait "$pid"; local rc=$?
  kill -TERM -- "-$wd" 2>/dev/null; wait "$wd" 2>/dev/null
  set +m
  return $rc
}
FETCH_OK=0
if _mit_frist git fetch origin "$BRANCH" 2>&1; then
  FETCH_OK=1
else
  echo "⚠️  git fetch ohne Erfolg (Frist ${FRIST_S}s oder Leitung) — kein Merge, weiter mit lokalem Stand."
fi

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

if [ "$FETCH_OK" = 1 ]; then
  if [ "$MODUS" = "rebase" ]; then
    git rebase --autostash FETCH_HEAD 2>&1 || { git rebase --abort 2>/dev/null; true; }
  else
    git merge FETCH_HEAD --no-edit -X ours --autostash 2>&1 || true
  fi
fi

# ── 🔴 24.09.2026: `-X ours` hat eine platzierte Order geloescht ─────────────────────────────
# Lucas: „Kamen 2 Meldungen zum selben Spiel und beide wurden gesetzt". Fuego vs EDward Gaming,
# 06:13 und 06:18 UTC, zwei Orders. In den Buechern stand danach nur eine: beide Commits trugen
# 53 Wetten, die zweite Zeile hatte die erste ERSETZT. Order 0xc1c79cbe… steht seither in keiner
# Datei des Hauses.
#
# Der Pull oben zieht mit `-X ours`. Haengen zwei Laeufe je eine Zeile an dieselbe Stelle
# derselben Datei, ist das fuer git ein Konflikt — und `-X ours` wirft die fremde Seite weg. Fuer
# ein Artefakt, das jeder Lauf neu erzeugt, ist das richtig. Fuer ein BUCH ist jede Zeile eine
# Tatsache, und zwei Tatsachen sind kein Konflikt.
#
# Deshalb werden die Buecher nach dem Merge wieder VEREINT — gegen FETCH_HEAD, also gegen genau
# den Stand, den `-X ours` eben verworfen hat. Welche Datei ein Buch ist und was eine Zeile
# eindeutig macht, steht in `buecher_union.BUECHER` und nirgends sonst.
if [ -f buecher_union.py ]; then
  python3 buecher_union.py \
    shortlist_auto_bets_placed.json shortlist_push_ledger.json shortlist_push_seen.json \
    betfair_public_ledger.json betfair_public_seen.json betfair_alerts_seen.json \
    betfair_rutsch_ledger.json betfair_rutsch_seen.json stake_burst_seen.json || true
fi

# ── 19.09.2026: der Pull selbst ist die Quelle der Konfliktmarker ────────────────────────────
# Lucas: „Heut kein einziger polymarket Push in public (kann nicht sein)." Konnte sehr wohl:
# `--autostash` oben legt die getrackten Aenderungen weg und holt sie danach zurueck. Kollidiert
# dieses Zurueckholen mit dem eingehenden Stand, schreibt git `<<<<<<< Updated upstream` IN die
# Datei und laesst sie so liegen. Der naechste Lauf staged sie, committet sie, und das Artefakt
# ist kein JSON mehr — am 19.09. traf es 15 Poly-Dateien auf einmal, poly_wallet_track.json
# darunter. Die Leser fingen die Exception ab und arbeiteten mit {} weiter: drei Stunden
# stille Funkpause ohne einen einzigen roten Lauf.
#
# Deshalb raeumt der Pull hinter sich auf, genau hier, wo der Schaden entsteht — nicht erst
# beim naechsten `git add`, wo ihn schon jemand mitgenommen haben kann.
if [ -x scripts/ci_keine_marker.sh ]; then
  bash scripts/ci_keine_marker.sh || true
fi
