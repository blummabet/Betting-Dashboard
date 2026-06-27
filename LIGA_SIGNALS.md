# Liga-Signal-Roadmap (Single Source)

Stand 26.06.2026. Dieses Dokument ist die **eine** Übersicht: welche Signale die Liga-Engine nutzt,
welche von der WM übernommen sind, welche neu für Liga sinnvoll sind, welche API-Daten dahinterstehen,
und wo jedes Signal angezeigt wird. Liga läuft auf dem WM-Stack (`COCOBET_DATASET=liga`, Profil
`liga_default`); Signale sind **modular** (eine Klasse in `sharp_signals/`, eigener Eintrag in
`liga_signal_weights.json`, im Bayesian-Lern-Loop) → wir bauen jederzeit dazu.

## Grundprinzipien (wie bei der WM bewährt)
- **Rückgrat = Steam-Following**, nicht „Pinnacle schlagen". Der Backtest (PL 2025/26) bestätigt:
  Form/xG sagen Sieger gut vorher (≈57–60 %), verlieren aber zur **Closing-Quote** Geld (−10 %),
  weil sie Favoriten tippen, die der Markt schon einpreist. → Edge kommt aus **Timing (Steam/CLV)**
  + **Value-Filter** (nur wetten, wenn Quote zu hoch). Daten-Signale sind **Bestätigung + Conviction**,
  nicht die Wett-Quelle.
- **Alles im Lern-Loop:** jedes Signal hat ein Gewicht in `liga_signal_weights.json`, das nach jedem
  aufgelösten Pick Bayesian angepasst wird (eigene Liga-Gewichte, getrennt von WM). Das System wird
  von Spiel zu Spiel schlauer.
- **Modular:** neues Signal = Subclass + in `registry.ACTIVE_SIGNALS` + Default-Gewicht + (falls neue
  Daten) ein dataset-bewusster Fetcher. Profil-Gating über `liga_default.disabled_signals`.
- **Zwei Flächen:** Cards = Steam + Conviction; Polymarket = EV/CLV (für Liga noch keine Poly-Daten).
- **Scope-Disziplin:** kein Markt/Signal ohne Engine-Hook (sonst Lärm im Lern-Loop).

## A) Von der WM übernommen
| Signal | Liga-Status | Was es misst | Datenquelle |
|---|---|---|---|
| `lead_lag_bias`, `steam_lag`, `freshness_leg`, `public_static_bias` | ✅ live | Steam-Rückgrat: Pinnacle-Bewegung, Soft-Lag, Frische, Sharp-vs-Public | Odds (Pinnacle + Soft) |
| `form_trend` | ✅ live | Tore-Avg-Diff letzte ~5 Spiele | API-Football Ergebnisse |
| `h2h_pattern` | ✅ live | Direktduell-Bilanz | /fixtures/headtohead |
| `xg_strength` | ✅ live | xG-Stärke (For/Against-Avg) | /fixtures/statistics (echtes Klub-xG) |
| `chance_creation`, `form_rating` | ⚠️ teil-live | KeyPasses / Spieler-Rating als Team-Aggregat | /fixtures/players (aktuell aus, s. Perf) |
| `lineup_signal` | ✅ saison-bereit | Schlüsselspieler-Ausfälle in der Aufstellung | /fixtures/lineups (T-1h) |
| `injury` | ✅ live | Verletzungen/Sperren | /injuries (5 Ligen) + /sidelined pro Team |
| `apif_predictions` | ✅ live | API-Footballs eigenes Modell als 3. Cross-Check | /predictions (fid direkt) |
| `incentive`, `altitude`, `weather`, `travel_burden`, `smart_money`, `polymarket_sharp` | ❌ aus | WM/Poly-spezifisch | — |

## B) xG: warum Liga besser ist als WM
Bei der WM war xG lückenhaft — viele Teams ohne Liga-xG, Friendlies ohne Daten, drum NT-xG-Fallback
+ schuss-basierter `xGsim`-Proxy. **Im Klub-Fußball hat jedes Spiel echtes `expected_goals`**
(API-Football /fixtures/statistics, plus Understat deckt die Top 5 voll ab). Darum ist `xg_strength`
in der Liga deutlich aussagekräftiger (Backtest: 59,6 % mit echtem xG vs 57,4 % über den Fallback).
→ xG ist in der Liga ein **Kern-Signal**, nicht nur Lückenfüller.

## C) Neue Signale, die in der Liga Sinn machen (mit API-Daten)
Priorität grob von hoch nach niedrig. Jedes als eigenes modulares Signal + Fetcher.
1. **`league_pressure`** ✅ gebaut — Titel/Abstieg/Europa/Dead-Rubber aus der Tabelle. Schläfer:
   früh ~0, rampt im Endspurt. Backtest zeigt standalone schwach → nur Rückrunde gewichten / Kombi.
   Daten: /standings (haben wir).
2. **`fixture_congestion` / Erschöpfung** ✅ gebaut (26.06.) — Ruhetage aus dem Liga-Spielplan
   (`team_schedule` im Kontext): müdes Team faden, ausgeruhten Gegner boosten, leichter Unter-Hebel,
   kein Über-Boost. Schläfer bis zur ersten englischen Woche (erstes Spiel = None). Offen für später:
   Europapokal-Reise (CL/EL-Midweek) als Verstärker — bisher nur Liga-interne Ruhetage.
3. **Spieler-Layer** — tiefer als lineup_signal:
   - `player_form` ✅ (26.06.) — per-Spieler-Form aus /fixtures/players-Ledger (post-match via
     fetch_liga_match_stats → liga_player_form.json), skaliert lineup_signal-Wichtung. Squads
     (Schlüsselspieler) ✅ via fetch_wm_squads → liga-data.json["squads"].
   - `squad_strength` 🔜 / Ausfall-Wertung — überlappt stark mit injury+lineup (niedrigere Prio).
   - `topscorer_momentum` 🔜 → /players/topscorers, /players/topassists (Hauptkreateur in Form).
4. **`apif_predictions`** 🔜 — drittes Modell als Cross-Check (haben wir für WM, nur Liga-Fetch nötig).
5. **`coach_change` / Neuer-Trainer-Bounce** 🔜 — Trainerwechsel → kurzfristiger Effekt. /coachs, /transfers.
6. **`transfer_shift`** 🔜 (Saisonstart) — große Zu-/Abgänge → Qualitäts-Verschiebung. /transfers.
7. **`referee_tendency`** 🔜 (später, mit Karten/Elfer-Märkten) — Schiri-Karten/Elfer-Quote. /fixtures (referee).
8. **News-Signal** ❓ — API-Football hat einen **News**-Bereich (im Doku-Menü). Potenziell für
   Last-Minute-Infos (Verletzung/Rotation). ABER: News = NLP/Rausch-Risiko → niedrige Prio,
   nur mit hartem Engine-Hook (Scope-Disziplin). Erst Endpunkt-Datenqualität prüfen.

## D) Zusätzliche Liga-Daten, die wir holen können (API-Football v3)
Reichlich verfügbar, jeweils pro Liga/Saison/Team: **players, players/topscorers, players/topassists,
players/squads, statistics (teams), fixtures/statistics, fixtures/players, fixtures/events, lineups,
injuries, sidelined, coachs, transfers, trophies, predictions, odds, standings, headtohead** — und
laut Doku-Menü auch **News**. Klub-Daten sind durchgängiger als NT-Daten der WM (mehr Spiele/Saison,
volle xG-Abdeckung) → mehr Signal-Substanz + schnellere Lern-Konvergenz.

## E) Wo wird was angezeigt
- **Card-Box (National → Cards):** feuernde Signale als Chips + 1-Satz-Begründung („Heim 5 Siege in
  Folge", „xG zuletzt 1,9 vs 0,7"). Conviction-Score = gewichtete Summe (Anti-Korr-Familien).
- **Event-Page (`matches/wm-match-v2.html`):** volles Signal-Board + Form/Duell/xG-Vergleich.
- **Sharp Radar (Toggle Liga):** Steam-Bewegungen (Pinnacle/Soft) der Liga.
- **Status (Toggle Liga):** Health/Guards, nicht Picks.
- **Lern-Loop:** jedes Signal-Resultat → liga_signal_ledger.json → liga_signal_weights.json.

## F) Lern-Loop & Post-Match (der Schlüssel)
Nach jedem Spiel: echtes Match-xG holen → Pick als *verdient / Pech / glücklich* bewerten →
**prozess-gewichtetes** Bayesian-Update (unglücklicher Verlust bestraft das Signal milder als ein
verdienter). So lernt das System Können von Varianz zu trennen — match-zu-match. (Bei der WM
umgesetzt; für Liga wird der Prozess-Verdict gerade verdrahtet.)

## G) Roadmap-Reihenfolge (Vorschlag)
1. Post-Match-xG-Re-Learning für Liga (Prozess-Verdict) ← gerade in Arbeit.
2. `injury` + `apif_predictions` Liga-Fetch (vorhandene WM-Signale dataset-bewusst).
3. `fixture_congestion` (englische Woche/Europa) — neuer hoher-Edge-Signal.
4. Spieler-Layer (player_form-Ledger, squad_strength, topscorer_momentum) + Player-Props-Markt.
5. Corner-Markt + `corner_rate`-Signal.
6. `coach_change` / `transfer_shift` (Saisonstart-relevant).
7. Backtest-als-Signal (gelernter Prior je Markt/Liga aus der Backtest-Trefferquote).
8. News-Signal nur falls Datenqualität + Engine-Hook überzeugen.

Verwandt: project_liga_on_wm_stack (Memory), project_signal_engine_roadmap, feedback_scope_discipline,
feedback_new_features_rule.
