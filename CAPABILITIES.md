# CAPABILITIES — was CocoBet/BetEdge kann

**Zweck dieser Datei:** Einstiegspunkt. Wer hier durch ist, weiß *was existiert, in welchem Zustand und wo die Lücke ist* — ohne vorher Code zu lesen. Sie liegt bewusst im Repo (nicht in einem Memory), damit sie mit dem Code versioniert wird und im Review auffällt, wenn sie veraltet.

**Pflege:** Neues Feature, deaktiviertes Feature oder geschlossene Lücke → hier eine Zeile ändern. Das ist Teil des Features, nicht Nacharbeit.

**Stand:** 31.08.2026 (Übersicht/Konjunktion nachgetragen; §1 Poly-/Wallets-Zeilen sind Stand 24.08.)

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
| `sharp` | `renderer.js` `renderSharpRadar()` | Pinnacle-Linienbewegungen, Toggles: Top-5 / MLS / International / **Poly-Radar** (Cross-Sport Poly vs Pinnacle, read-only + Konvergenz-Tracking) |
| `polytrading` | `polymarket-tab.js` `initPolyTrader()` | Auto-Trader: offene Positionen, Health, P&L |
| `polybetting` | `polymarket-tab.js` `initPolymarket()` | Manuelles Platzieren. Drei Sichten: **📇 Cards** (gestempelte `verdict`-Picks), **💜 Value** (`edge≥1pp`, inkl. Club-Scan-O/U/BTTS), **🔥 Heute** (Broad-Conviction `_pwTopPlays`, alle Sportarten), **🐋 Whales** (24.08.: offene Positionen der Top-20 aus `_pwRankRows` — DIESELBE Auswahl wie die Rangliste im Wallets-Menü —, gefiltert auf noch spielbar (im Feed, Anpfiff in der Zukunft), Konsens zuerst, Spalte „ihr Einstieg → unser Preis"; Nachspielen wird in `poly_whale_follow.py` → `poly_whale_follow_track.json` als Papier-Depot gemessen). Seit 24.08. löst **auch Heute direkt aus** — über die CLOB-Token-ID aus dem Broad-Feed (`tokens` je Markt), nicht mehr nur bei Slug-Match auf einen Card-Pick (das deckte ~7% der Plays). Sport-Sperre `PW_BLOCKED_BET_CATS` (poly-wallets.js, **eine Quelle** für Button, Public-Gate und Papier-Depot) = US-Sport/Kampfsport. **Drei Ebenen bewusst getrennt:** Scan + Papier-Depot behalten ALLES (kostet nichts, einzige Art einen Umschwung zu bemerken) · Public-Gate `_pwPublicTopPlays` filtert die gesperrten raus (öffentlicher Track-Record = Produkt) · echtes Geld gesperrt. Wiedereintritt über **CLV**, nicht ROI (`poly_shortlist_track.reentry_status`: ≥50 frische Plays, ≥25 davon mit echter Schluss-Referenz, Ø CLV ≥ 0) — meldet nur, schaltet nichts frei. Token-Orders haben **keinen Pinnacle-Anker** → `edge=null`, Basis-Einsatz, Warnung im Bestätigungs-Dialog. |
| `polywallets` | `poly-wallets.js` | **Whale Tracker**. Datensatz-Tabs: MLS / Top-5 / **🎮 E-Sport** (noAnchor, kein Pinnacle → nur Smart-Money/Whale/Kohärenz) / WM. **Vier Unter-Reiter** (19.07., „besser aufteilen" statt 9 gestapelter Sektionen): **🎯 Chancen** (Auflösungs-Lücken + interne Fehlbepreisung + [mit Anker] Scatter+Edge-Board), **💡 Smart-Money** (Konzentration Split/Halter/Whale-Konz./Fluss + Exit-Watch), **🐋 Whales** (Einstiegsqualität mit Nachkauf-Signal + Flow-Tape + Leaderboard), **⚖️ Liegt das Geld richtig?** (Brier Geld vs Preis + „🌐 Alle Poly-Ligen" nach Kategorie). Deep-Links + O/U-Leiter 1.5/2.5/3.5 im Edge-Board. |
| `uebersicht` | `main-dashboard.js` | **Lucas' Einstiegsfläche** („was kann ich blind nachspielen?"). Zwei geldgetriebene Sektionen, die **gegensätzlich gebaut** sind und das im Kopf auch sagen (`.md-mech`-Pille): **🔒 Mehrfach gedeckt = FILTER** (Konjunktion aus `killer.py` — alle Geld-Bedingungen gleichzeitig, kann leer sein, eigenes Buch, Preis eingefroren beim Treffer) vs. **🎯 Top-Wetten jetzt = RANGLISTE** (Disjunktion über Cards/Poly/Betfair-Steam/Betfair-Geld/Money-Map — EINE Quelle genügt, ist praktisch nie leer, kein eigenes Buch). Steht ein Spiel in beiden, trägt die Top-Wette einen `🔒 gedeckt`-Chip (`_klKeys()`) — **markiert nur, ändert den Rang nicht**. Dazu: Puls, KPI-Zeile, „Heute spielenswert" (Poly-Plays, seit 31.08. mit Betfair-Zelle), Money-Map, Signal-Bilanz, NOBET-Bilanz. Zeitfenster fail-closed: ohne Anpfiff wird nicht geraten (`_fxKommend`, `MD_FIX_MAX_H=72`, `KL_FENSTER_H=12`) |
| `analyse` | `signal-check.js` | Fremden Tipp gegen alle Signale prüfen; isoliert, gibt nie ein Verdict |
| `intl-studio` | `tiktok-studio.js` | Manueller TikTok-Card-Generator |
| `status` | `status-checks.js` | Ops-Health: Browser-Checks + Server-Readiness aus `{ds}_status.json` |
| `heart` | inline in `season-finish-v2.html` | Showcase/Technik-Doku, zwei Zonen (✨ Showcase / ⚙️ Technik). **31.08.2026 inhaltlich neu geschrieben** — 2.100 → 1.363 Zeilen: WM-Ballast raus, Übersicht/Freigabe, Betfair, Poly-Intelligence und Betrieb rein, oben eine Kurzfassung „Die zehn wichtigsten Dinge". ⚠️ Zählungen (Signale/Guards/Tests/Workflows) sind ein **Stand**, kein Live-Wert; Live-Kennzahlen stehen bewusst NICHT drin (eine Doku, die ROI einfriert, wird stillschweigend falsch). Bei Struktur-Änderungen `sw.js`-VERSION hochzählen. |

**Geteilte Frontend-Logik:** `pick-verdict.js` (`computeVerdict()` — **einzige Quelle** für BET/ABWÄGEN/SKIP, nie duplizieren), `pick-engine.js` (Linienwahl, DNB/DC, Poisson), `_pick_helpers.js` (JS-Spiegel von `pick_helpers.py`), `validator.js`, `share.js`, `sw.js` (PWA, network-first).

⚠️ **`verdict` und `convictionScore` sind entkoppelt.** Verdict kommt aus `computeVerdict()` (Modell/Markt/Story), Conviction aus 6 Signal-Familien. Über 248 gestempelte Picks erreicht **kein ABWÄGEN je 6** (Verteilung 0:7 1:17 2:16 3:42 4:50 5:34). Wer eine Schwelle an Conviction hängt, muss sie gegen diese Verteilung prüfen, nicht gegen `verdict_thresholds` — sonst baut man einen No-Op.

---

## 2. Signale (`sharp_signals/`)

31 Module, alle in `registry.ACTIVE_SIGNALS`. **Kein global totes Signal** — Deaktivierung passiert pro Profil über `cocobet_config.json → profiles.<p>.disabled_signals`.

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
| `move_following` | Pinnacle-Move-Größe + Zustands-Bestätigung; klein gedeckelt (25.07., backtest-validiert auf Top-5) | ❌ | ✅ | ❌ |
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

**Konjunktion (29.–31.08.2026):** `killer.py` — die Auswahl hinter „Mehrfach gedeckt". Ein Spiel kommt nur rein, wenn Betfair-Geldanteil ≥65% **UND** ≥€2.000 frischer Zufluss (Intervall-Delta) **UND** die Quote mitzieht; Stufe 1 zusätzlich Poly-Geld ≥60% + Pinnacle-Zustimmung. Schwellen aus `betfair_track_record` **gespiegelt**, nicht neu erfunden. Nur `Match Odds` (CLV-Untergrenze +3,0pp gegen +0,4pp für alle anderen Märkte). Treffer werden bis zum Anpfiff **gehalten** (`killer_state.json`) und zum **Haltepreis** abgerechnet (`killer_ledger.json` → `bilanz()` inkl. `roiLb`). Registriert in `freigabe.py` (`killer_schublade`) — seit 31.08. als **zwei Schubladen**: `Konjunktion · Top-5 + MLS` und `Konjunktion · übrige Ligen` (`killer.TOP5_LIGEN`, Betfair-Schreibweisen — NICHT mit `stats_scope.json` zusammenlegen, das entscheidet über die Card-Bilanz). Grund: über 8.000 Track-Zeilen hat Top-5 den besseren ROI-Punktschätzer (n=10, +21,8%, UG −25,1%), der Rest den einzigen CLV mit Untergrenze über null (n=70, +3,61pp, UG +2,76) — und die Konjunktion feuert in den Top-5 **dreimal häufiger** (16,1% gegen 5,9%). Nicht entscheidbar, also getrennt qualifizieren statt raten. ⚠️ Steht auf „beobachten", nicht auf Freigabe: eigenes Buch n=56, ROI +3,2%, **UG −16,8%**; Stufe 2 (48 von 56 Zeilen) trägt +0,2%.

**Push-Gate (30.08.2026):** `pick_announce_state.push_ok(p)` ist die **einzige** Definition dafür, ob ein Pick rausgeht (vorher zwei). ABWÄGEN geht nur ohne Gegensignal raus (`hat_gegensignal`). `pick_push_ledger.py` schreibt auch die **aussortierten** Zeilen mit und rechnet sie ab (Schattenbuch, Zustand beim Anpfiff eingefroren) → `freigabe.push_schubladen()` „ABWÄGEN · gepusht" vs „· aussortiert".

**Auflösung:** `resolve_wm_results` (Trade-P&L + CLV), `resolve_wm_picks` (alle Picks inkl. Schatten), `resolve_steam_clv`, `resolve_wm_bracket`, `wm_standings`.

**Lernen:** `build_signal_ledger` → `update_signal_weights` → `compute_pick_calibration` / `compute_pick_confidence` / `compute_clv_summary`. Backtest-Kette: `liga_backtest` → `{ds}_backtest_report.json` → `prime_liga_priors` → `{ds}_signal_priors.json`.

**Trading:** `auto_wm_poly_trigger` (Edge ≥4pp / Steam-Lag 3pp, MIN_VOL 10k, `ENABLED`-Flag, Wallet-Balance + Limits **datensatz-übergreifend**), `polymarket_bet` (Order via `repository_dispatch`), `manage_wm_poly_positions` (Sell-Alerts), `monitor_open_positions` (Health 0-100), `reconcile_poly_positions` (manuelle Wallet-Eingriffe → `closed_manual`), `steam_lag_monitor`, `poly_heartbeat`.

**Poly-Edge ausnutzen (19.07.2026):**
- `poly_entry.decide_entry` — **Maker statt Taker**: bei viel Zeit + breitem Spread eine ruhende Limit-Order oben aufs Gebot statt den Spread zu crossen; nah am Anpfiff / enger Spread → Taker (Fill-Sicherheit). Eingehängt in `polymarket_bet.place_market_order` (Schritt 0).
- `poly_entry.decide_maker_action` + `poly_resting.py` + `manage_poly_maker_orders.py` — **Order-Lebenszyklus** (19.07.): ruhende Maker-Orders landen im Register `{ds}_poly_resting_orders.json`; der Monitor (in `manage-{wm,mls}-poly`, self-hosted, alle 30min) prüft je Order den Fill-Status und eskaliert unerfüllte kurz vor Anpfiff → **stornieren + als Taker crossen** (`force_taker=True`). Reihenfolge streng Storno→Platzieren; scheitert das Storno, wird NICHT platziert (kein Doppel).
- `poly_markout.py` — **Trägt Making überhaupt?** (Adverse-Selection-Test, angestoßen von Lucas' Krypto-Befund Markout −4.18pp). Simuliert aus `{ds}-poly-history` Maker-Fills auf Abwärts-Ticks und misst den Forward-Markout je Horizont; Verdikt = Markout(2h) + Spread-Ersparnis (1.5pp). → `{ds}_poly_markout.json` → Verdict-Zeile im Trading-Cockpit. **Erster Befund: Fußball viel milder als Krypto** (−0.5/−0.8pp bei 2h statt −4.18pp), MLS wird bei 6h schlechter (−1.08pp) → bestätigt das frühe Taker-Escalate (1.5h). Netto knapp positiv, hängt aber an der Spread-Annahme.
- ⚠️ **`maker_enabled=false` (Default), jetzt aktivierbar.** Aktivierungs-Tor: (1) `poly_markout` zeigt **dauerhaft 🟢 „trägt"**, (2) `trade.maker_enabled=true` in `cocobet_config`, (3) Dispatch reicht `depth`+`kickoff` je Order mit.
- `poly_coherence` — **Poly gegen sich selbst**: Underround-Arb (Ja+Nein < 1.0), O/U-Leiter-Inversionen, fette Spreads. Kein Pinnacle-Anker nötig. → `{ds}_poly_coherence.json` → Wallets-Tab. Dünn-Markt-Filter (MIN_VOL 5k) gegen Scheinarbs aus veralteten Preisen.
- `poly_settlement_gap` — **Auflösungs-Lücke**: Spiel FT, Gewinner-Ausgang handelt noch < 0.97 (Oracle hinkt). → `{ds}_poly_settlement.json` → Wallets-Tab. Harter **Stale-Schutz**: nur werten, wenn der Preis-Snapshot NACH Anpfiff + Spieldauer liegt (sonst wäre jeder Vorspiel-Preis ein „garantierter Gewinn").
- Beide Detektoren laufen in `fetch-{wm-data,mls-odds-dense}` + `update-mls` direkt nach dem Poly-Fetch. **Keine Ausführung, nur Analyse** — Handeln entscheidet der Mensch / gegateter Trigger.
- `betfair_name_bridge.py` — **Namens-Bruecke Betfair <-> unsere Fixtures** (26.08.): Betwatch schreibt BETIS / ATHLETIC BILBAO, wir REAL BETIS / ATHLETIC CLUB. `compatible/pair_matches/find/index`, bewusst ENG (Enthaltensein ab 4 Zeichen, Wort-Schnitt ab 5 ohne Stadt-Stopwords, Treffer muss EINDEUTIG sein). Ein falscher Treffer haengt einem Spiel fremdes Geld an — im Zweifel nichts. EINZIGE Definition; `generate_wm_match_pages` importiert sie (die `_bf_*`-Namen sind nur noch Aliasse).
- `betfair_card_link.py` — **unsere Card neben die Geld-Seite** (26.08., Lucas): das Terminal zeigte in der Pick-Spalte immer den Betfair-Runner, nie unseren Pick -> man sah nicht, ob die Boerse mit uns oder gegen uns steht. `betfair_consensus.json` x **`liga-data.json`** (28.08. korrigiert — `picks_output.json` ist das ALTE 20-Ligen-System) -> `betfair_card_link.json` {matchId: {market, odds, sc, agree}}. `agree`: true/false nur auf der 1X2-Achse (inkl. Doppelte Chance + AH), Tore/Ecken/BTTS bekommen **null statt eines erfundenen Urteils**. Information, KEIN zweites Urteil — die Engine bleibt die einzige Demotions-Autoritaet. ⚠️ 31.08.: der Fixture-Index lief nur ueber das Team-PAAR — `event_key` ist reihenfolge-unabhaengig, also ueberschrieb das pickfreie Rueckspiel das heutige Spiel (876 von 876 Schluesseln doppelt belegt). Der exakte Pfad konnte NIE treffen, verlinkt war nur, was die Namens-Bruecke auffing: 1 von 12. Schluessel traegt jetzt den Tag -> 4 von 12. `nCandidates` steht seitdem in der Datei (vorher nur im Log) und Guard `check_card_link_alive` meldet **error**, wenn es Kandidaten gab und keinen Treffer.
- `betfair_coherence_watch.py` — **wann liegt Geld in den Tormaerkten?** (26.08.): `betfair_coherence` hat nie gefeuert, und der Grund ist der ZEITPUNKT, nicht die Schwelle — Geld fliesst zuerst in den Hauptmarkt (Real Madrid 7h vor Anpfiff: MO 80.644 EUR vs Ue/U 2.5 365 EUR), in die Tormaerkte erst zum Anpfiff. Schreibt je Lauf mit, an welcher Huerde es scheiterte und wie weit der Anpfiff weg war (Bucket 0-1h ... >24h), dedupliziert auf (Spiel, Markt, Bucket). -> `betfair_coherence_watch.json`. Read-only, entscheidet nichts; nach ein paar Tagen entscheidet die Kurve.
- `poly_money_accuracy.py` — **Liegt das Poly-Geld richtig?** (19.07.): friert die Geld-Verteilung (share/usd je Ausgang aus `{ds}_poly_smartmoney`) nah am Anpfiff ein (`{ds}_poly_money_close.json`), löst gegen den Ausgang auf. Misst Geld-Mehrheit-Trefferquote, Preis-Favorit-Baseline, und **Brier Geld vs. Preis** (ist das Geld schärfer als der Preis oder nur Rauschen?) + Uneinigkeits-Bucket. `evaluate(min_odds, byLeague)` — Mindest-Quote-Filter (triviale Favoriten raus) + Liga-Aufschlüsselung. Empirischer Test der These [[project_polymarket_not_sharp]]. → `{ds}_poly_money_accuracy.json` → Wallets-Tab-View „🎯 Liegt das Geld richtig?". Daten-hungrig.
- `poly_money_broad.py` — **BREIT über alle Poly-Ligen** (19.07.): alles was Poly anbietet mit Volumen ≥ Schwelle (~7.5k) + Quote ≥ 1.35, aufgelöst über **Polys eigene Settlement** (kein externer Feed nötig). Tags: `nba nfl mlb nhl epl soccer tennis ucl` + **E-Sport** (`esports cs2 lol dota valorant`). `fetch_markets()` ist real (Gamma je Tag + Holders-Geld-Split + Resolution, gedeckelt), läuft scharf nur am **Mac-Runner** (Poly EU-geoblockt). `evaluate` ist outcome-agnostisch (home/draw/away ODER Teamnamen). → `poly_money_broad.json` (global) → Wallets-Geld-View „🌐 Alle Poly-Ligen", **nach Kategorie geordnet** (Fußball/US-Sport/E-Sport/Tennis) mit Subtotalen + „schärfste/dümmste Liga"-Highlight.
- `poly_cross_sport.py` — **Cross-Sport-Radar** (19.07., Sharp-Radar-Tab „Poly-Radar"): Poly vs de-viggte **Pinnacle** (nicht weiche Bücher!) über mehrere Sportarten (NBA/NFL/MLB/NHL, konfigurierbar), nur standardisierte Moneyline-Märkte (Outrights sind Regel-/Marge-Falle). Unabhängig vom Fußball-Trading. Kern: **Konvergenz-Tracking** (`poly_cross_sport_history.json`) — eine Lücke ist erst echt, wenn sie sich über die Tage schließt (Poly läuft zur Pinnacle); bleibt sie stehen = Artefakt. Reiner Kern testbar; Fetch/Matching läuft scharf nur am **Mac-Runner** (Poly EU-geoblockt), in `manage-mls-poly`. Read-only.

**Content:** `compute_streaks` / `compute_player_streaks` (strikt Content, nie in Picks/Trading), `generate_daily_tiktok` (Playwright → 4 PNGs → Telegram), `wm_story_engine` + `wm_story_angles/*`, `generate_wm_ai_preview` (Haiku) bzw. `generate_wm_rule_preview` (ohne API-Key), `generate_track_record_card`, `signal_check` (isoliert, neutrale Gewichte). Telegram: `telegram_wm` (Morning + Recap, zweisprachig), `telegram_trades` (eigener Channel), `telegram_streaks`, `telegram_streak_watch`, `notify_new_picks`.

**Guards:** `wm_data_integrity` (~40 Checks, sichtbar als 🛡️-Panel), `pre_match_readiness`, `safe_write.preserve_nonempty`, `check_not_wiped` (harter Exit 1), `odds_plausibility` (Overround 1.00-1.30, **eine Quelle**), `validate_wm_picks`, `detect_pick_changes`, `detect_wm_sharp_moves`, `state_files_registry` (zentrale git-add-Listen).

---

## 4. Workflows

Alle `ubuntu-latest` **außer** den self-hosted Trading-Workflows (Mac).

**Hauptläufe:** `fetch-wm-data` (`0 4,8,12,16,20`), `update-liga` (`7 6` pre / **`37 7` pre-Nachzügler** / `7 18` post), `update-mls` (`11 19` pre / `11 7` post), `update-dashboard` (Legacy-Stack). ⚠️ Die Minuten sind **nicht** kosmetisch: auf `:00` starten repo-weit bis zu 11 Jobs gleichzeitig, und GitHub droppt genau dort. Der **Nachzügler** (31.08.) fängt einen verschluckten `7 6`-Lauf auf — sicher nur, weil `liga_telegram_sent.json` seit 27.08. committet wird und `morning_card:<datum>` den Doppelpost verhindert. ⚠️ `update-liga`/`update-mls` unterscheiden PRE/POST über `github.event.schedule == '<cron>'`: **jeder** neue Cron muss in JEDE passende `if:`-Bedingung, sonst läuft der Job grün durch und tut nichts (Tests: `test_cron_schedule_hygiene.py`).

**Odds/Closing:** `fetch-pinnacle-odds` (`0 2,6,10,14,18,22`), `fetch-liga-odds-dense` (`17 */2`), `fetch-mls-odds-dense` (`23 */2`, inkl. Pick-Gen), `capture-closing{,-liga,-mls}` (je `*/15` in den Anpfiff-Bändern).

**Ergebnisse/Lineups:** `fetch-results` (4×/Tag → resolve-Kette + CLV), `wm-lineup-watcher` (`*/15 9-23`, T-1h Hot-Cron).

**Trading (self-hosted Mac):** `manage-wm-poly`, `manage-mls-poly`, `poly-bets` (`repository_dispatch` vom Dashboard-Button), `close-poly-position`, `kill-switch` (manuell). ⚠️ **Kein EU-VPS-Runner** — Poly blockt EU-VPS trotz DE-Standort; der Mac ist der einzige Poly-Runner.

⚠️ **Auf dem Mac gilt: kurze Jobs, kein Halten** (31.08.2026, gemessen über die Commit-Historie 26.–31.08.). `poly-live-scan` startete stündlich und hielt den Runner ~70 Min für einen internen 15-Min-Loop — gedacht war ein zweiter Mac-Runner. Ist-Abdeckung: **8–29%** der Soll-Läufe, Lücken von 3–12 Stunden, sechs Tage lang unbemerkt. Auf **derselben** Maschine erreichten Betfair-Radar (`*/10`) und Global-Scan (`:15/:45`) ~100% mit Lücken von 15–31 Min. Der Runner war nie das Problem: ein Job, der den Runner exklusiv über eine Stunde will, kommt gegen die kurzen nicht an, und `cancel-in-progress` räumt den wartenden Lauf beim nächsten Trigger ab, bevor er startet — aus Warten wird Aushungern. Seitdem: kurzer Einzeldurchlauf `4,19,34,49` (versetzt zu beiden Nachbarn, weg von `:00`), `cancel-in-progress: false`, Timeout 12 Min. Guard `check_live_scan_laeuft` schlägt an, wenn `health/poly-live-scan.json` älter als 90 Min ist — bewusst die **Gesundheits**datei, nicht die Live-Daten: die stehen auch still, wenn kein Spiel läuft.

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

**Global (datensatz-übergreifend, Poly-Broad-Scan):** `poly_money_broad_close/live.json` (seit 24.08. inkl. `tokens` = CLOB-Token je Ausgang → Direkt-Order aus „Heute"; nur offene Märkte tragen das Feld), `poly_resolutions.json` (Sieger je Slug — die einzige Auflösungsquelle für Märkte ohne Fixture), `poly_shortlist_track.json` (**Papier-Depot** der Heute-Plays, $10 fix, unverfälschte Baseline), `poly_direct_bets.json` (`poly_direct_bets.py` → die **echt** aus „Heute" gesetzten Wetten, über den Slug abgerechnet: P&L + CLV ohne Fixture; offene Bets verfallen nie, Guard `direct_bets_settling`).

**Konjunktion (global, seit 29.08.):** `killer.json` (was die Sektion zeigt + `bilanz` inkl. `roiLb`), `killer_state.json` (Latch: Treffer bis zum Anpfiff), `killer_ledger.json` (eigenes Buch zum Haltepreis). Dazu `pick_push_ledger`-Zustand für das ABWÄGEN-Schattenbuch. Alle vier stehen in den Commit-Listen von `betfair.yml`.

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
10. **MLS-Event-Pages komplett leer** (19.07.): MLS rendert im Frontend unter `_mode='liga'`, also baute der Renderer die Event-Page-Slugs mit Prefix `liga-…`. Die JSONs schreibt `generate_wm_match_pages` aber mit dem **Datensatz**-Prefix `mls-…` → 404 → leere Seite. Wieder die `is_liga()`-gilt-auch-für-MLS-Familie, nur im Frontend. → `_mpPrefix(fx)` leitet den Prefix pro Fixture aus der Gruppe ab (`groupKey==='MLS'` → `mls-`), Test `mls-event-page-slug.test.mjs`. Die generierten Seiten decken nur das aktuelle Fenster (≈ letzte/nächste 2 Wochen) ab — ferne/vergangene Spieltage haben bewusst keine, genau wie Liga.
11. **Poly-Fläche „fertig", liefert aber NIE Daten** (20.07.): Audit fand zwei verdrahtete Poly-Features, die seit Bau 0 Commits hatten. **Cross-Sport-Radar**: `fetch_poly_rows()` war ein Stub `return []` (`TODO(Runner)` nie umgesetzt) → Radar konnte sich nie füllen, zeigte aber „füllt sich am Runner". **E-Sport-Tab**: stieg bei 0 Events STILL aus (keine Datei, kein Grund). Exakt die CLV-tot-Klasse: verdrahtet, Frontend liest, hinten kommt nie was an, kein Guard sah hin. → (a) `fetch_poly_rows` echt gebaut (Gamma, `event_key` reihenfolge-unabhängig), (b) E-Sport schreibt `esports_poly_status.json` mit `rawEventsByTag`/`reason` statt still, (c) **Guard `check_poly_surfaces_alive`** in der Integritäts-Batterie: rot, wenn eine Fläche STEHT (nie/>30h keine Ausgabe) — leer-aber-frisch bleibt grün. Regel geschärft: **ein „fertiges" Feature muss beweisen, dass hinten Daten ankommen — Verdrahtung ≠ Ankunft.**
12. **Fehlende Information ist keine Erlaubnis** (25.08.): Code-Audit über den ganzen Stack, **16 Befunde, keiner davon knallt** — alle sehen im Log wie Normalbetrieb aus. Eine Bauform: eine Sicherung, die bei kaputten Eingangsdaten den harmlosesten Wert zurückgibt (`except: pass`, `.get(x, default)`, `mkt_k="hw"`), sodass der Aufrufer „nichts gefunden" nicht von „fehlgeschlagen" unterscheiden kann — und dann über Geld entscheidet. → (a) alle Geld-Schreiber atomar (`safe_write.write_json_atomic`, temp→fsync→replace), (b) vier Loader merken sich Lesefehler (`_LOAD_FAILED`/`_LAZY_FAILED`/`_UNREADABLE`/`_stUnloadable`) und melden „❔ unbekannt" statt grün, (c) `polymarket_bet` bricht bei kaputter Wett-Datei ab (ohne sie greift KEIN Cap), (d) E-Sport-`clustersAll`/`matches` echt gebaut + Guard `check_wallet_clusters`, (e) `byLeague` beim **Konsumenten** repariert, nicht beim Producer — der kennt die Liga gar nicht, und so wird die alte Historie rückwirkend nutzbar. Offen: vier **tote Signale** (unerreichbare Schwellen) — das ist eine Entscheidung, keine Reparatur. Bericht: [[project_audit_stille_fehler_25_08]].

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
