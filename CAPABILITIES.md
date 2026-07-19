# CAPABILITIES — was CocoBet/BetEdge kann

**Zweck dieser Datei:** Einstiegspunkt. Wer hier durch ist, weiß *was existiert, in welchem Zustand und wo die Lücke ist* — ohne vorher Code zu lesen. Sie liegt bewusst im Repo (nicht in einem Memory), damit sie mit dem Code versioniert wird und im Review auffällt, wenn sie veraltet.

**Pflege:** Neues Feature, deaktiviertes Feature oder geschlossene Lücke → hier eine Zeile ändern. Das ist Teil des Features, nicht Nacharbeit.

**Stand:** 19.07.2026

---

## Grundprinzip

**Eine Engine, drei Datensätze.** `COCOBET_DATASET` (`wm|liga|mls`) + `COCOBET_PROFILE` (`wm2026|liga_default|mls_default`) steuern per Env, welche Dateien gelesen/geschrieben und welche Signale/Märkte aktiv sind.

- Auflösung zentral in `cocobet_dataset.py` (`D.file(wm_name, liga_name)`, `D.data_file()`, `D.prefix()`).
- ⚠️ **`is_liga()` ist auch für MLS `True`.** Das ist die Ursache der ganzen Bug-Klasse „läuft unter mls, arbeitet auf Liga-Dateien" (MLS-Vollaudit 13.07.: 14 Funde).
- Schwellen in `cocobet_config.json`, Loader `cocobet_config.py` (merged über die **Union** der Keys — vorher fiel `conviction_score` still raus und Liga wettete mit WM-Schwelle 6 statt 8).

**Die Wett-Philosophie in drei Sätzen:** Pinnacle de-viggt ist der Anker, wir versuchen nicht ihn zu schlagen. Ein Odds-Move ist ein **Trigger**, keine Wahrheit — wir wissen, dass Geld kommt, nicht von wem oder warum, also challengen wir den Move mit eigenen Daten. CLV ist der Nordstern für reines Steam-Following; wo orthogonale Signale *gegen* den Move schießen, gilt er nicht 1:1.

**Zwei Flächen, nicht verwechseln:** Cards (Wett-Empfehlung nach Drop-Bestätigung, negativer Preis-Edge by design) vs. Polymarket (Trade nach EV/CLV). Und innerhalb Poly: **Trading** = Auto-Trader, **Betting** = manuelle Card-Picks.

---

## 1. Frontend-Flächen

SPA `season-finish-v2.html`, Weiche `showView()` in `ui.js` (`panelMap`). `season-finish.html` ist Legacy.

| View | Datei | Zweck |
|---|---|---|
| `national-cards` | `wm2026-renderer.js` (`_mode='liga'`) | Klub-Picks-Cards; liest `liga-data.json`, merged `mls-data.json` als weitere „Liga" |
| `national-tracking` | `wm2026-tracking.js` | P&L / Hit-Rate / CLV der Klub-Picks |
| `intl-cards` | `wm2026-renderer.js` (`_mode='wm'`) | WM-Cards inkl. Sibling-JSONs (Poly, Travel, Confidence, Pick-Changes) |
| `intl-tracking` | `wm2026-tracking.js` | WM-Pick-Tracking, Single Source `wm2026-data.json` |
| `*-streaks` | `renderer.js` `initStreaks()` | Serien/Streaks, quotenfrei — reines Content-Produkt |
| `sharp` | `renderer.js` `renderSharpRadar()` | Pinnacle-Linienbewegungen, eigener Toggle je Datensatz |
| `polytrading` | `polymarket-tab.js` `initPolyTrader()` | Auto-Trader: offene Positionen, Health, P&L |
| `polybetting` | `polymarket-tab.js` `initPolymarket()` | Manuelles Platzieren aus Card-Picks |
| `polywallets` | `poly-wallets.js` | **Whale Tracker**: Edge=Signal, Whales=Veto + Auflösungs-Lücken + Poly-interne Fehlbepreisung + Whale-Einstiegsqualität (aus Ledger). Einstieg = MLS (WM ans Ende). |
| `analyse` | `signal-check.js` | Fremden Tipp gegen alle Signale prüfen; isoliert, gibt nie ein Verdict |
| `intl-studio` | `tiktok-studio.js` | Manueller TikTok-Card-Generator |
| `status` | `status-checks.js` | Ops-Health: Browser-Checks + Server-Readiness aus `{ds}_status.json` |
| `heart` | inline | Showcase/Technik-Doku |

**Geteilte Frontend-Logik:** `pick-verdict.js` (`computeVerdict()` — **einzige Quelle** für BET/ABWÄGEN/SKIP, nie duplizieren), `pick-engine.js` (Linienwahl, DNB/DC, Poisson), `_pick_helpers.js` (JS-Spiegel von `pick_helpers.py`), `validator.js`, `share.js`, `sw.js` (PWA, network-first).

⚠️ **`verdict` und `convictionScore` sind entkoppelt.** Verdict kommt aus `computeVerdict()` (Modell/Markt/Story), Conviction aus 6 Signal-Familien. Über 248 gestempelte Picks erreicht **kein ABWÄGEN je 6** (Verteilung 0:7 1:17 2:16 3:42 4:50 5:34). Wer eine Schwelle an Conviction hängt, muss sie gegen diese Verteilung prüfen, nicht gegen `verdict_thresholds` — sonst baut man einen No-Op.

---

## 2. Signale (`sharp_signals/`)

30 Module, alle in `registry.ACTIVE_SIGNALS`. **Kein global totes Signal** — Deaktivierung passiert pro Profil über `cocobet_config.json → profiles.<p>.disabled_signals`.

| Signal | Misst | WM | Liga | MLS |
|---|---|:--:|:--:|:--:|
| `lead_lag_bias` | Pinnacle bewegt zuerst, Softbooks hinken nach | ✅ | ✅ | ✅ |
| `public_static_bias` | Softbook-Konsens vs. Pinnacle: wo überbettet das Public | ✅ | ✅ | ✅ |
| `reverse_line_move` | Linie bewegt gegen die Public-Seite | ✅ | ✅ | ✅ |
| `opener_move` | Opening→früh = schärfstes Sharp-Fenster | ✅ | ✅ | ✅ |
| `multi_book_steam` | Pinnacle + Betfair korroborieren gegen Public | ✅ | ✅ | ✅ |
| `freshness_signal` | Ist der Move noch frisch? confirm/drift/reverse | ✅ | ✅ | ✅ |
| `steam_lag` | Pinnacle-Move ≥X pp, Poly noch nicht nachgezogen | ✅ | ❌ | ✅ |
| `polymarket_sharp` | Poly als 2. Anker, Bestätigung Richtung Pinnacle | ✅ | ❌ | ✅ |
| `smart_money` | Poly-Geld-Split + Wallet-Konzentration vs. Pinnacle-Fair | ✅ | ❌ | ✅ |
| `injury_signal` | Ausfälle positionsgewichtet (GK/CB/CM/FW) | ✅ | ✅ | ✅ |
| `lineup_signal` | T-1h-Aufstellung als Grundwahrheit der Ausfälle | ✅ | ✅ | ✅ |
| `form_trend` | Form letzte 5 + Mean-Reversion bei xG-Gap | ✅ | ✅ | ✅ |
| `form_rating` | Minutengewichtetes Rating + kassiertes xGsim | ✅ | ✅ | ✅ |
| `chance_creation` | Schlüsselpässe + Schüsse im 16er (orthogonal zu xG) | ✅ | ✅ | ✅ |
| `xg_strength` | xG-Diff als Team-Stärke | ✅ | ✅ | ✅ |
| `h2h_pattern` | Persistente H2H-Dominanz (min. 5 Spiele) | ✅ | ✅ | ✅ |
| `apif_predictions` | Externes API-Football-Modell als Cross-Check | ✅ | ✅ | ✅ |
| `streak_momentum` | Serien als Signal, mit Markt-Persistenz-Multiplikator | ✅ | ✅ | ✅ |
| `topscorer_momentum` | Konzentrierte Angriffsbedrohung | ✅ | ✅ | ✅ |
| `coach_change` | Neue-Trainer-Bounce, zerfällt über ~75 Tage | ✅ | ✅ | ✅ |
| `transfer_shift` | Schlüsselspieler-Abgang → dauerhaft geschwächt | ✅ | ✅ | ✅ |
| `fixture_congestion` | Ruhetage/englische Woche → müde Beine | ✅ | ✅ | ✅ |
| `league_pressure` | Titel/Europa/Abstieg bzw. MLS-Playoff je Conference | ✅ (no-op) | ✅ | ✅ |
| `game_state_openness` | Asymmetrische Verzweiflung → Über/BTTS | ✅ | ✅ | ✅ |
| `mls_travel` | MLS Distanz/Zeitzonen/Höhe/Kunstrasen-Composite | ✅ | ✅ | ✅ |
| `travel_burden` | Langstrecke + wenig Pause + Höhenwechsel → xG-Abzug | ✅ | ❌ | ❌ |
| `altitude_signal` | Stadionhöhe (Mexico City 2240 m ≈ −12-15 % VO2max) | ✅ | ❌ | ❌ |
| `weather_signal` | Hitze-Penalty für Teams aus kühlen Klimazonen | ✅ | ❌ | ❌ |
| `pressure_index` | Turnier-Druck / Muss-Sieg-Psychologie | ✅ | ❌ | ❌ |
| `incentive_signal` | Quali-Mathematik, Dead-Rubber, Bracket-Asymmetrie | ✅ | ❌ | ❌ |

**Warum die Liga-Gates** (`registry.py`): `incentive` würde Liga-Tabellenplatz als Gruppen-Quali fehldeuten; `altitude`/`weather`/`travel` sind in kompakten EU-Ligen Rauschen; `smart_money`/`polymarket_sharp`/`steam_lag` brauchen Poly-Liquidität, die es für EU-Ligen nicht gibt. None-Fallback reichte nicht → hart aus.

**Anti-Korrelation:** `SIGNAL_GROUPS` bündelt zu `sharp_money / form / public / context / incentive / unique`. Pro Familie zählt nur das stärkste Signal voll, der Rest mit `CORRELATION_DISCOUNT = 0.4`.

**Lernen:** Gewichte je Datensatz getrennt (`signal_weights.json`, `liga_*`, `mls_*`), Bayesian-Update aus `{ds}_signal_ledger.json`, Priors aus Backtest (`PRIOR_STRENGTH=25`).

---

## 3. Pipelines

**Pick-Erzeugung:** `generate_wm_picks.py` ist der Motor; `generate_liga_picks.py` / `generate_mls_picks.py` sind dünne Wrapper, die Dataset+Profil **vor dem Import** setzen. `steam_engine.py` = das eigentliche Modell (Move-Following, kein Fair-Value; ein bettbarer Pick je Spiel; AH-Leiter lebt in `_AH_LADDER`/`_best_ah`, **nicht** in `MARKET_CFG`). `conviction_score.py` (0-10), `pick_staking.py` (Viertel-Kelly), `pick_constants.py`/`pick_helpers.py` (+ JSON-Mirror für JS).

**Fetcher WM:** `fetch_wm_odds` (Pinnacle 1X2 + Opening-Carry + Closing), `fetch_wm_multibook_odds` (Softbook-Median), `fetch_wm_form`, `fetch_wm_nt_xg`, `fetch_wm_corners`, `fetch_wm_injuries`, `fetch_wm_lineups`, `fetch_wm_player_stats`, `fetch_wm_squads`, `fetch_wm_apifootball_predictions`, `fetch_wm_venues`, `fetch_wm_weather`, `fetch_wm_match_results`, `fetch_wm_poly_prices` (Gamma), `fetch_wm_poly_smartmoney` (`/holders`), `fetch_wm_poly_balance`, `capture_dense_odds` (isoliert, nur Analyse).

**Fetcher Liga/MLS:** `build_liga_data` (→ exakt WM-Struktur), `fetch_liga_odds` (eigener dünner Fetcher, inzwischen auf WM-Niveau: AH-Leiter + public-O/U alle Linien + Closing-Capture), `fetch_liga_elo` (Elo ist **nur** Baseline, nie Pick-Quelle), `fetch_liga_xg`, `fetch_liga_match_stats` (Post-Match-xG → Prozess-Verdict), `fetch_liga_topscorers`, `fetch_liga_team_changes`.

**Auflösung:** `resolve_wm_results` (Trade-P&L + CLV), `resolve_wm_picks` (alle Picks inkl. Schatten), `resolve_steam_clv`, `resolve_wm_bracket`, `wm_standings`.

**Lernen:** `build_signal_ledger` → `update_signal_weights` → `compute_pick_calibration` / `compute_pick_confidence` / `compute_clv_summary`. Backtest-Kette: `liga_backtest` → `{ds}_backtest_report.json` → `prime_liga_priors` → `{ds}_signal_priors.json`.

**Trading:** `auto_wm_poly_trigger` (Edge ≥4pp / Steam-Lag 3pp, MIN_VOL 10k, `ENABLED`-Flag, Wallet-Balance + Limits **datensatz-übergreifend**), `polymarket_bet` (Order via `repository_dispatch`), `manage_wm_poly_positions` (Sell-Alerts), `monitor_open_positions` (Health 0-100), `reconcile_poly_positions` (manuelle Wallet-Eingriffe → `closed_manual`), `steam_lag_monitor`, `poly_heartbeat`.

**Poly-Edge ausnutzen (19.07.2026):**
- `poly_entry.decide_entry` — **Maker statt Taker**: bei viel Zeit + breitem Spread eine ruhende Limit-Order oben aufs Gebot statt den Spread zu crossen; nah am Anpfiff / enger Spread → Taker (Fill-Sicherheit). Eingehängt in `polymarket_bet.place_market_order` (Schritt 0).
- `poly_entry.decide_maker_action` + `poly_resting.py` + `manage_poly_maker_orders.py` — **Order-Lebenszyklus** (19.07.): ruhende Maker-Orders landen im Register `{ds}_poly_resting_orders.json`; der Monitor (in `manage-{wm,mls}-poly`, self-hosted, alle 30min) prüft je Order den Fill-Status und eskaliert unerfüllte kurz vor Anpfiff → **stornieren + als Taker crossen** (`force_taker=True`). Reihenfolge streng Storno→Platzieren; scheitert das Storno, wird NICHT platziert (kein Doppel). ⚠️ **Default `maker_enabled=false`** — jetzt aber aktivierbar. Aktivierungs-Checkliste: (1) `trade.maker_enabled=true` in `cocobet_config`, (2) Dispatch reicht `depth`+`kickoff` je Order mit (sonst fällt decide_entry mangels Tiefe auf Taker zurück).
- `poly_coherence` — **Poly gegen sich selbst**: Underround-Arb (Ja+Nein < 1.0), O/U-Leiter-Inversionen, fette Spreads. Kein Pinnacle-Anker nötig. → `{ds}_poly_coherence.json` → Wallets-Tab. Dünn-Markt-Filter (MIN_VOL 5k) gegen Scheinarbs aus veralteten Preisen.
- `poly_settlement_gap` — **Auflösungs-Lücke**: Spiel FT, Gewinner-Ausgang handelt noch < 0.97 (Oracle hinkt). → `{ds}_poly_settlement.json` → Wallets-Tab. Harter **Stale-Schutz**: nur werten, wenn der Preis-Snapshot NACH Anpfiff + Spieldauer liegt (sonst wäre jeder Vorspiel-Preis ein „garantierter Gewinn").
- Beide Detektoren laufen in `fetch-{wm-data,mls-odds-dense}` + `update-mls` direkt nach dem Poly-Fetch. **Keine Ausführung, nur Analyse** — Handeln entscheidet der Mensch / gegateter Trigger.

**Content:** `compute_streaks` / `compute_player_streaks` (strikt Content, nie in Picks/Trading), `generate_daily_tiktok` (Playwright → 4 PNGs → Telegram), `wm_story_engine` + `wm_story_angles/*`, `generate_wm_ai_preview` (Haiku) bzw. `generate_wm_rule_preview` (ohne API-Key), `generate_track_record_card`, `signal_check` (isoliert, neutrale Gewichte). Telegram: `telegram_wm` (Morning + Recap, zweisprachig), `telegram_trades` (eigener Channel), `telegram_streaks`, `telegram_streak_watch`, `notify_new_picks`.

**Guards:** `wm_data_integrity` (~40 Checks, sichtbar als 🛡️-Panel), `pre_match_readiness`, `safe_write.preserve_nonempty`, `check_not_wiped` (harter Exit 1), `odds_plausibility` (Overround 1.00-1.30, **eine Quelle**), `validate_wm_picks`, `detect_pick_changes`, `detect_wm_sharp_moves`, `state_files_registry` (zentrale git-add-Listen).

---

## 4. Workflows

Alle `ubuntu-latest` **außer** den self-hosted Trading-Workflows (Mac).

**Hauptläufe:** `fetch-wm-data` (`0 4,8,12,16,20`), `update-liga` (`0 6` pre / `0 18` post), `update-mls` (`0 19` pre / `0 7` post), `update-dashboard` (Legacy-Stack).

**Odds/Closing:** `fetch-pinnacle-odds` (`0 2,6,10,14,18,22`), `fetch-{liga,mls}-odds-dense` (je `0 */2`, inkl. Pick-Gen), `capture-closing{,-liga,-mls}` (je `*/15` in den Anpfiff-Bändern).

**Ergebnisse/Lineups:** `fetch-results` (4×/Tag → resolve-Kette + CLV), `wm-lineup-watcher` (`*/15 9-23`, T-1h Hot-Cron).

**Trading (self-hosted Mac):** `manage-wm-poly`, `manage-mls-poly`, `poly-bets` (`repository_dispatch` vom Dashboard-Button), `close-poly-position`, `kill-switch` (manuell). ⚠️ **Kein EU-VPS-Runner** — Poly blockt EU-VPS trotz DE-Standort; der Mac ist der einzige Poly-Runner.

**Content:** `daily-tiktok` (`30 4` + Backup `30 5`), `daily-wm-story`, `track-record-card{,-mls}`, `telegram-wm-recap`, `telegram-streaks` (montags).

**Sonstiges:** `ci-tests`/`tests`, `deploy-pages` (push + `*/15`, weil Bot-Commits den Deploy nicht triggern), `{liga,mls}-backtest` (manuell).

---

## 5. Daten-Artefakte

Präfix-Muster: WM = `wm_`/`wm2026-`/kein Präfix, Liga = `liga_`/`liga-`, MLS = `mls_`/`mls-`. Aufgelöst über `D.file()`.

| Muster | Schreiber → Leser |
|---|---|
| `{ds}-data.json` | **Kern.** Fetcher → Renderer/Tracking/Picks. Enthält groups, odds, picks, form, h2h, xgStats, standings, squads |
| `{ds}-odds-history.json` | Odds-Fetcher → Sharp Radar, CLV, `opener_move`/`reverse_line_move` |
| `{ds}_closing_lines.json` | Closing-Capture → CLV |
| `{ds}_signal_weights.json` | `update_signal_weights` → `registry.load_signal_weights()` |
| `{ds}_signal_ledger.json` | `build_signal_ledger` → Weights + Kalibrierung |
| `{ds}_signal_priors.json` | `prime_liga_priors` → `update_signal_weights` |
| `{ds}_clv_summary.json` | `compute_clv_summary` → Status/Tracking |
| `{ds}_status.json` | `pre_match_readiness` → `status-checks.js` |
| `{ds}_poly_{prices,smartmoney,wallets,balance}.json` | Poly-Fetcher → Trading-Tabs, `smart_money`/`polymarket_sharp` |
| `{ds}_streaks.json`, `{ds}_player_streaks.json` | Content-Pipeline → Streaks-Panel, Telegram |

**Nur WM:** `wm_lineups`, `wm_weather`, `wm_venues`/`wm_venue_schedule`, `wm_travel_burden`, `wm_nt_xg`, `wm_bracket`, `wm_results` (Trade-P&L, **nicht** Card-Picks), `wm_auto_bets_placed`, `wm_kill_switch`, `wm_dense_odds_log` (isoliert).

**Commit-Kontrolle:** `state_files_registry.json` definiert die git-add-Listen je Kategorie; Workflows holen sie per `python state_files_registry.py --bash-list <kategorie>` statt eigener driftender Listen.

---

## 6. Bewusst aus / unvollständig

**Deaktiviert mit Begründung:**
- **Player-Picks** (wm2026-Profil): weder die Signale noch das Conviction-Gate adressieren Spieler-Märkte — eigene Heuristik ohne Engine-Hook. Re-enable erst mit Player-Engine-Signal.
- **Corner-Märkte** (wm2026): kein Signal hat NT-Corner-Daten → reine Poisson ohne Signal-Filter. **Für Liga aktiv** (Vereins-Historie vorhanden).
- **Skellam / BTTS-Corner-105**: Backtest −9.57 % ROI, signifikant.
- **Auto-Trading**: `ENABLED`-Flag + `wm_kill_switch.json` + `kill-switch.yml`.

**Gemessen und verworfen:**
- **Poly↔Pinnacle Lead-Lag: kein Vorlauf in eine der beiden Richtungen** (18.07., `analyze_poly_pinnacle_lag.py`). Kreuzkorrelation über 25 WM-Matches, Peak sitzt bei Lag 0 (r=+0.21), alle anderen Lags ~0 — stabil über Raster 15/30/60/120min. Heißt: Polymarket taugt **nicht** als Frühwarnung vor unserem Steam-Trigger, und Pinnacle gibt uns keinen ausbeutbaren Zeitvorsprung gegenüber Poly. Deshalb gibt es kein Poly-Lead-Signal. ⚠️ Das widerspricht `steam_lag` nicht: das misst *Divergenz* (Pinnacle bewegt sich, Poly ist noch nicht nachgezogen), nicht *Vorlauf*.

**Offene Lücken:**
- **Wallet-Track-Record (CLV/ROI je Wallet)** — der Ledger sammelt seit 18.07.; die Auswertung je Wallet folgt, sobald genug Auflösungen da sind. Dann `smart_money` auf bewiesene statt große Wallets umstellen.
- **Liga-Steam-Log fehlt** — `steam_lag_log.json` ist WM-only, deshalb kein Liga-Check in `wm_data_integrity`.
- **MLS-Lineup-Watcher fehlt** — kein Hot-Cron, `lineup_signal` bekommt für MLS nie Daten.
- **`pre_match_readiness` ist WM-only.**
- **`monitor_open_positions`**: Verletzungen + Form-Veränderung sind Phase 2.
- **MLS Reise/Höhe/Wetter**: Profil-Gates noch gesetzt, obwohl `mls_travel` existiert.
- **`liga_backtest`**: nur PL, eine Saison, ohne Quoten/ROI. Steam nicht backtestbar (historische Linienbewegung existiert nicht) → nur vorwärts paper-tradebar.
- **CLV für BTTS/DC/AH/Corners bleibt `None`** — nicht im Poly-History-Snapshot.
- **AH-P&L vor 19.06.2026 ist Phantom-kontaminiert** (Entry am Mid, Sells am Cache-Mid). Unter ~15 entschiedenen Bets je Linie ist die Aussage wertlos.
- **`cocobet_dataset.current_season()`** bricht für MLS ab Feb 2027.
- **`mls_poly_balance.json`** wird am Mac geschrieben, erreicht das Repo aber nie (Ursache offen, kein Blocker — Balance wird datensatz-übergreifend gelesen).

---

## 7. Bug-Klassen, die uns Geld gekostet haben

Jede hat einen Guard. Wer eine ähnliche Änderung baut, prüft hier zuerst.

1. **Platzhalter-Quoten** (13.07.): API lieferte Opening `1.04/1.01/1.04` = 291 % Overround → Fake-Mover, **80,8pp „STEAM"-Alerts an Telegram**, verseuchte CLV. Der erste Guard prüfte `odds_open` (geheilt = grün), während die Verbraucher die **History** lesen. → `odds_plausibility.py` als einzige Quelle + `check_history_snaps_plausible`.
2. **Daten-Wipe** (12.07.): abgelaufener API-Zugang → `mls-data.json` mit 0 Teams + 292 verwaisten Picks überschrieben; Workflows liefen mit `|| true`. → `safe_write.preserve_nonempty`, `check_not_wiped` (Exit 1). Audit fand dieselbe Klasse in 11 weiteren Skripten.
3. **CLV war für Liga+MLS wochenlang tot** (17.07.): `hours_to_ko=None` hart verdrahtet → `odds_closing` nie gesetzt. **Mehrere Audits fanden es nicht, weil alle prüften ob DATEIEN verdrahtet sind, keiner ob DATEN ankommen.** → Regel: ein leeres Artefakt braucht eine *belegte* Erklärung, keine plausible. Guard `check_closing_capture_alive` fragt die **persistente** Datei ab, nicht `ctx.odds` (dort werden gespielte Spiele gepruned).
4. **Lern-Loop war tot** (12.06.): `update_signal_weights` las `wm_results.json` (kein `signals[]`) → 0 Beobachtungen, alle Gewichte ewig 1.0. → `build_signal_ledger` als Quelle.
5. **`standings` war leer** (17.06.): `incentive_signal` komplett tot, `pressure_index` halb. Kein Skript schrieb die Tabelle. → `wm_standings.py`.
6. **Logik-Drift durch Duplikat** (15.06.): Travel-Logik lag in `generate_wm_picks` **und** `travel_burden` — einer gefixt, einer nicht. → `travel_common.py`.
7. **`is_liga()` gilt auch für MLS** (13.07.): 14 Funde, u.a. 5 Geld-Guards prüften WM-Wetten, Match-Pages überschrieben `liga-index`, Config-Merge verwarf `conviction_score` → **Liga wettete mit WM-Schwelle**.
8. **Test-Verschmutzung** (13.07.): `COCOBET_DATASET` auf Modul-Ebene gesetzt → 13 fremde Tests rot. → `tests/conftest.py` isoliert Env + reloadet `cocobet_dataset` (Env-Reset allein reicht nicht, das Modul cached beim Import).
9. **Stiller Telegram-Send**: leeres Secret → `.get(key, default)` gibt `""` zurück (Default greift nur bei *fehlendem* Key). → `(get() or default)`. **Gesetzt-aber-leer ≠ fehlend.**

---

## 8. Harte Arbeitsregeln

- **Push nur über GitHub Desktop**, nie CLI.
- **Pipeline-Output nie lokal regenerieren** — erzeugt Merge-Konflikte. Nur Code pushen; nötiger Lauf → `git checkout --` reverten.
- **Gepostete Picks sind immutabel** (≤ morgen veröffentlicht) — Guards müssen sie ausnehmen.
- **Kein fixture-spezifischer Code.** Jeder Fix universal.
- **Stiller Daten-/Geld-Bug → Guard. Logik-Bug → Test.**
- **Neue Features nach Standard:** Config + JSON-Pools + Templates + Liga-Profile + Tests + CI.
- **Leeres eigenes File = unser Fetcher-Bug**, nicht die Quelle.
- **Engine ist die einzige Demotions-Autorität** — alle Flächen zeigen 1:1 dieselben Picks.
- **Scope-Disziplin:** nur Märkte mit Engine + Signal + Conviction.
