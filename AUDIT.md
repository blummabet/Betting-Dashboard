# Code-Audit (Phase 5, 26.06.2026)

Ehrlicher Befund nach der Konsolidierung (Phase 1–4). Frage war: wie sauber ist die *Logik* selbst,
nicht nur das Wiring.

## Verdict
**Der Produktions-Kern ist sauber.** Engine (`generate_wm_picks`), Lern-Loop (`build_signal_ledger`
+ `update_signal_weights`), Guard-Batterie (`wm_data_integrity`) und `registry` haben **keine groben
Logik-Duplikate** und laufen über die Single-Source-Schicht. Es bleiben drei klar abgegrenzte Punkte
— keiner ist gefährlich, aber alle gehören zu „alles sauber".

## Befunde

### A) Verwaiste Analyse-/Backtest-Skripte (Clutter) — größter Posten
~40 von 107 .py-Dateien hängen an **keinem** Workflow und werden von **niemandem** importiert, u.a.:
`backtest_v4.py` (1492 Z.), `check_picks_logic.py` (962), `backtest_model_health.py` (603),
`code_review_test.py` (438), `deep_dive_bugs.py` (198), `bizarre_comparisons.py` (165).
- Harmlos (nicht in der Pipeline), aber sie vermüllen das Repo + tragen den Großteil der
  `score_*`/`evaluate_pick`/`aggregate`-Duplikate.
- **Empfehlung:** in `archive/` verschieben (nicht löschen — könnten manuelle Analyse-Tools sein).
  Reduziert das Repo um ~40 Dateien / mehrere tausend Zeilen Ballast.

### B) Duplizierte Utility-Helfer — UNTERSUCHT (26.06.2026): meist SCHEIN-Duplikation
Bei genauer Prüfung sind die gleichnamigen Helfer **semantisch verschieden** — ein mechanischer
Merge würde Bugs einbauen (in untestbarem Netzwerk-Code), also das Gegenteil von sauber:
- `_num` existiert in **zwei Bedeutungen**: Wert-Coercion `_num(v)` vs Dict-Getter `_num(d, *keys)`.
- `_http_get` divergiert in der **Rückgabe**: liga_backtest liefert TEXT, die Poly-Fetcher geparstes
  JSON; dazu verschiedene Timeouts/User-Agents.
- `tg_send` (10×) variiert je **Kanal/Token** (verschiedene TELEGRAM_TOKEN-Quellen, Channels).
- `apif_get`/`_apif_get` (18×) liefern unterschiedliche Formen (list / dict / (status,data)).
- Nur `_now_iso` (4×) ist 100 % identisch — aber ein One-Liner; eine geteilte Datei dafür wäre
  Kopplung ohne echten Gewinn.
- **Entscheidung:** NICHT zwangs-mergen. Best Practice = pro Datei opportunistisch angleichen, wenn
  man sie ohnehin anfasst (z.B. neuer apif-Client erst, wenn ein Fetcher umgebaut wird). Die echte
  Single-Source-Arbeit (Dataset, Signale, market_side) ist in Phase 1–4 erledigt; hier gibt es kein
  gefährliches Drift-Risiko, das einen riskanten Big-Bang rechtfertigt.

### C) Toter Großcode: `generate_picks_for_fixture`
Der alte Elo-Edge-Pick-Pfad (~1000 Zeilen in `generate_wm_picks`). Wird **in der Produktion nicht
mehr aufgerufen** (Steam ist die Pick-Quelle), aber **2 Tests** prüfen darüber noch Markt-Scoring
(`test_disabled_markets`, `test_dnb_ah_consistency`).
- Es ist genau der Pfad, der in WM-Runde 1 Phantom-Picks machte (Lucas: nie wieder nutzen).
- **Empfehlung:** entfernen — aber sauber: die 2 Tests auf den aktiven Pfad/Helfer umhängen, damit
  die Scoring-Abdeckung erhalten bleibt. Mittlere Sorgfalt nötig (große Funktion + Tests).

## Was NICHT zu tun ist
Kein Big-Bang-Löschen, kein blindes Zusammenführen. A/B/C sind Entscheidungen — A senkt Ballast,
B/C senken Duplikation/Risiko. Reihenfolge nach Wert/Risiko: **A (sicher) → C (mittel) → B (Churn).**

## Ergebnis (26.06.2026)
- ✅ **A** erledigt: 14 verwaiste Skripte → `archive/`.
- ✅ **C** erledigt: toter Elo-Pfad `generate_picks_for_fixture` (~1042 Z.) entfernt, Tests aufs echte
  Output umgehängt, `_STEAM_OU_PAIR` als Modul-Konstante erhalten.
- ✅ **B** untersucht: meist Schein-Duplikation (divergente Semantik) → bewusst NICHT zwangs-gemergt
  (s.o.). Per-Datei-Angleich bei Gelegenheit.
Suite nach allem grün.
