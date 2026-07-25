# MLS Signal-Audit & Ideen — 25.07.2026

**Frage von Lucas:** Welche Signale können wir für die MLS noch einbauen bzw. schärfen, um bessere Card-Qualität zu liefern — und nutzen wir Odds- und Data-API wirklich aus?

**Datenbasis dieses Audits:** `mls-data.json` (34 Odds-Einträge, 30 Teams, 17 aktive Picks), `mls_backtest_report.json`, `mls_signal_weights.json`, `cocobet_config.json` (mls_default-Profil), `registry.py`, die Poly-State-Files. Alles Stand 25.07. gestaged, nicht verändert.

---

## 0. Der eine Befund, der alles rahmt

Die MLS-Card ist **nicht durch Signal-Genauigkeit** gedeckelt, sondern durch **Conviction-Familien-Abdeckung.**

Über die 17 aktiven Picks (`convictionFamilies`) leuchten **nur** `sharp_money` und `model_stack`. **Nie** `context`, **nie** `market`, **nie** `unique`.

Mit `family_caps = {sharp_money:3, model_stack:3, context:3, market:1}` liegt das erreichbare Maximum praktisch bei **~6**. Beobachtete Conviction-Verteilung der 17 Picks: `2:6 · 3:5 · 4:2 · 5:3 · 6:1`. Maximum = 6. `steam_bet_threshold` für MLS = **8** → **kein Pick erreicht je BET.** `mls_clv_summary`: `BET: 0, ABWÄGEN: 12`, betRate 0 %.

**Konsequenz für die Roadmap:** Der Hebel liegt nicht bei „ein 15. Genauigkeits-Signal", sondern bei **den zwei toten Familien.** Jede Maßnahme unten ist danach sortiert, ob sie eine leere Familie zum Leuchten bringt.

Der Handover-Fix von heute (`league_pressure` + `mls_travel` in die Kontext-Familie) ist genau der richtige erste Schritt — er hebt 3 Heim-Picks in Richtung 7, sobald er gepusht ist. Dieses Dokument baut darauf auf.

---

## 1. Signale, die AN sind, aber für MLS strukturell NICHTS liefern

Das ist der billigste und größte Hebel: kein neues Modell, nur Daten/Schwellen reparieren. Alle vier fallen in die bekannte „verdrahtet ≠ liefert Daten"-Bug-Klasse (CAPABILITIES §7.11).

### 1a. `smart_money` — Poly-Topf für MLS zu dünn; Gate NICHT naiv senken  🟡 kleiner Hebel (Korrektur 25.07.)
- Woher die Daten: Polymarket `/holders` (`fetch_wm_poly_smartmoney.py` → `mls_poly_smartmoney.json`). Gemessen wird das **offene Interesse der Top-Halter** je Ausgang (USD-Split + Wallet-Konzentration), NICHT das Handelsvolumen.
- Config-Gate: `smart_money.min_volume_usd = 100000` (identisch in allen 3 Profilen) prüft `totalUsd` = Halter-OI.
- Reale MLS-Halter-OI (19 Spiele mit Daten): **Median $1.309, Max $90k → 0 von 19** erreichen $100k. Selbst bei $10k nur **4 von 19**. Halter je Ausgang: Median **15**, oft nur 7.
- → `smart_money` feuert in **0 von 17** Picks.
- **⚠️ Lucas' Einwand ist korrekt — Poly-MLS ist schlicht zu dünn.** Und das Gate einfach auf $5–10k zu senken wäre nicht nur schwach, sondern **falsch herum**: `topHolderShare` (= die „Smartness") ist bei dünnen Märkten ein **Artefakt der Dünne**. Beispiel `25484-1597` Heim: `topHolderShare=1.0` bei **7 Haltern und $145** — kein Wal, nur ein Mini-Markt. Naives Senken flaggt die dünnsten, lautesten Märkte als die smartesten.
- **Falls überhaupt:** MLS-eigene Schwelle **+ Halter-Anzahl-Floor** (z. B. ≥40 Halter UND ≥$10–15k OI im mls_default-Block), damit nur die 3–4 Spiele mit echter Tiefe (`1614-9568`: $78k/122 Halter) durchkommen. Universal via Config. Aber: **kleiner Hebel, nicht Prio 1** — die stärkeren MLS-Gewinne hängen nicht an Poly-Tiefe (§1b, §2a).

### 1b. `chance_creation` + `form_rating` — zwei model_stack-Signale dunkel  ✅ GEFIXT 25.07.
- `xgStats` für **alle 30 Teams**: `keyPassesForAvg = null`, `ratingAvg = null`.
- `chance_creation` braucht keyPasses → feuert 1× (mit −1), effektiv tot. `form_rating` braucht ratingAvg → feuert **0×**.
- **Root-Cause bestätigt (nicht die Quelle, unsere Config):** `aggregate_team_stats` (`fetch_wm_nt_xg.py`) holt keyPasses+Rating aus dem `/fixtures/players`-Endpoint, aber nur wenn `nt_xg.fetch_player_stats: true`. Im `mls_default`-Profil stand **`false`** (WM=true), gesetzt um API-Quota zu sparen → der Players-Call wurde für MLS nie gemacht (Code Z. 350/377). Die API HAT die Daten, wir haben sie abgeschaltet.
- **Änderung 25.07.:** `mls_default.nt_xg.fetch_player_stats` → `true` (liga bleibt bewusst aus, eigene Quota-Entscheidung). Regression-Test in `tests/test_cocobet_config.py` (`TestPlayerStatsPerProfile`) prüft den aufgelösten `fetch_wm_nt_xg.CFG` je Profil. Greift schon beim nächsten `update-mls` (Staleness-Skip lässt `keyPassesForAvg=null`-Einträge durch). Doppelter Nutzen: belebt beide Signale UND bringt sie erstmals in den Lern-Loop (heute sammeln sie 0 Beobachtungen).
- Kosten: ~30 Teams × 6 Fixtures extra `/fixtures/players`-Calls je Refresh (2×/Tag, minus Staleness) — Quota beobachten.

### 1c. Poly-Card-Signale (`steam_lag`, `polymarket_sharp`) — reichster MLS-Datenschatz, 0 Beitrag  🟠
- Polymarket ist **offizieller MLS-Partner**, Preise liegen für **alle 34** Spiele vor.
- Trotzdem: `steam_lag` und `polymarket_sharp` tragen zu **0 von 17** Picks' Conviction bei.
- Zu klären: Kommen die Poly-Preise überhaupt in die **Conviction** (Cards) oder nur ins **Trading**? Falls nur Trading, verschenken wir das MLS-nativste Signal auf der Card-Fläche. `steam_lag` misst Divergenz Pinnacle↔Poly — aber 19/34 Spiele haben *kein* Pinnacle (siehe §3), also kann es dort per Definition nicht feuern.

### 1d. `lineup_signal` — die `unique`-Familie ist für MLS blind  🟠
- CAPABILITIES §6: **MLS-Lineup-Watcher fehlt** (kein Hot-Cron). `lineup_signal` bekommt für MLS nie die T-1h-Aufstellung.
- `lineup_signal` ist das **einzige** Signal in der `unique`-Familie (voller Gewicht, kein Anti-Korr-Discount). Ohne Hot-Cron bleibt `unique` dauerhaft leer.
- **Fix:** MLS-Lineup-Watcher analog `wm-lineup-watcher` (`*/15` im Anpfiff-Band). Bringt die dritte tote Familie zum Leuchten und liefert die späteste realtime-Wahrheit.

---

## 2. Signale, die feuern, aber richtungsblind / falsch kalibriert sind (schärfen)

### 2a. `mls_travel` — starke Richtungs-Asymmetrie, ungenutzt  🔴 hohe Prio
- Backtest per Markt:
  - `mls_travel | Auswärtssieg`: **0.704** (n=321) ← sehr stark
  - `mls_travel | Heimsieg`: **0.452** (n=321)
  - `mls_travel | Unter 2.5`: 0.42 (n=176)
- Das ist **genau das Muster** des `league_pressure`-Richtungs-Bugs, den du heute gefixt hast: aggregiert wirkt das Signal mittelmäßig (0.544), aber die Richtung trägt die ganze Information. Reisebürde trifft das **Auswärtsteam** → sie sollte primär Auswärtssieg *dämpfen* / Heimsieg *stützen*, nicht symmetrisch als „Composite" auf beide Seiten.
- **Aktion:** Richtungslogik in `mls_travel.py` prüfen — feuert der Malus gerichtet auf das reisende Team, oder als symmetrischer xG-Shift? Verdient einen eigenen API-Backtest (wie league_pressure), bevor das Gewicht steigt. Der Hitrate-Split sagt: hier liegt echter, gerichteter Edge.

### 2b. Venue-Split-Form voll ausnutzen  🟠
- `form` trägt bereits `venueSeq` (H/A-Sequenz) und getrennte `avgScored/avgConceded` pro Heim/Auswärts (die Evidence-Zeile zeigt „Heim trifft 1.7, Auswärts 1.4"). Gut.
- MLS hat wegen Reise/Zeitzonen einen **extremen** Heimvorteil. Frage: Wie stark gewichtet `form_trend` die venue-*spezifische* Form gegenüber der aggregierten? Ein Team mit 2.1 daheim / 0.9 auswärts ist für ein Heimspiel etwas anderes als sein Mittelwert 1.5. In kompakten EU-Ligen Rauschen — in der MLS Signal.

### 2c. `fixture_congestion` — allein Null, aber MLS-Kombis brutal  🟡
- Backtest: **0.502** (n=287) = reines Rauschen, als Solo-Signal.
- Aber MLS koppelt Midweek + Transkontinental-Reise wie keine EU-Liga. Die Rest-Tage *allein* sagen nichts; **Rest-Tage × Reisedistanz** (mls_travel-Daten liegen vor) könnte der eigentliche Erschöpfungs-Trigger sein. → Eher `mls_travel` um eine Kongestion-Interaktion erweitern als `fixture_congestion` isoliert zu retten.

---

## 3. Nutzen wir die Odds-API aus? — Nein, mehrere Lücken

Aus der Feld-Analyse der 34 Odds-Einträge:

| Beobachtung | Zahl | Bewertung |
|---|---|---|
| Einträge mit Poly-Preis | 34/34 | ✅ voll |
| Einträge mit **Pinnacle 1X2** | **15/34** | 🔴 19 Spiele nur Poly, kein Sharp-Anker |
| **BTTS**-Odds (b_yes/b_no) | **0** | 🔴 Markt im Profil offen, aber nie Odds → toter Markt |
| O/U-Linien | fast nur **2.5** (3.5 auf 5 Spielen, kein 1.5) | 🟠 O/U-Picks kollabieren auf eine Linie |
| Corner-/Card-Markt | 0 in Odds | 🟠 Form-Daten da, Markt nicht |

- **19/34 ohne Pinnacle:** wahrscheinlich Timing (Pinnacle listet MLS erst ~2–3 Tage vor Anpfiff), aber zu bestätigen — falls Coverage-Lücke, hat die halbe Slate keinen Sharp-Anker und kann keine Card kriegen.
- **BTTS:** `form` trägt `bttsSeq`, `bttsRate`, `scoredRate`, `cleanSheetRate`, H2H trägt `bttsRate` — reiche Daten, aber **null BTTS-Odds** → das Signal-Material verpufft mangels Markt. `fetch_liga_odds` für MLS um BTTS + mehr O/U-Linien erweitern ist der direkteste „mehr Card-Fläche"-Hebel.

**Data-API-Lücken (Zusammenfassung §1):** keyPasses/Rating null (2 Signale dunkel), Lineup nie geholt (unique-Familie blind), Poly-Whale/Holder dünn und hinter WM-Schwelle.

---

## 4. Neue Signal-Ideen aus VORHANDENEN, ungenutzten MLS-Daten (kein neuer API-Call)

Nur Ideen, die deiner Scope-Disziplin genügen (Markt + Engine + Signal + Conviction) — bzw. wo der fehlende Markt der eigentliche Blocker ist:

1. **Heim/Auswärts-Tabellen-Split als Kontext-Modifikator.** `standings` liefert nur Aggregat. MLS-Teams sind oft „Festung daheim, harmlos auswärts". Ein Home/Away-Punkteschnitt-Signal (aus resolved results ableitbar) füllt die **context**-Familie mit MLS-nativer Information. Hoher strategischer Wert, weil es die tote Familie trifft.

2. **Card/Booking-Signal — vorbereitet, aber Markt fehlt.** `cornersForm` trägt bereits `cardLine`, `cardOverSeq`, `cardOverRate` (n=15). Vollständig ungenutzt. Aber Scope-Disziplin: erst wenn Karten-Odds für MLS geholt werden, sonst Signal ohne Markt. → Auf den Backlog, gekoppelt an §3 Odds-Erweiterung.

3. **Poly-Konvergenz als MLS-Card-Signal.** `poly_coherence` (Underround/Inversionen) und `poly_settlement_gap` laufen bereits, aber read-only im Wallets-Tab. Für Spiele *ohne* Pinnacle (19/34) ist Poly-gegen-sich-selbst der **einzige** verfügbare Markt-Anker. Prüfen, ob ein gedämpftes Konvergenz-Signal die sharp_money-Familie für die Pinnacle-losen Spiele füllen kann.

---

## 5. Priorisierung (Wirkung × Aufwand)

**Korrigiert nach dem Poly-Tiefe-Check (25.07.):** `smart_money` von Prio 1 heruntergestuft — Poly-MLS ist zu dünn, um es zu einem Haupthebel zu machen (§1a). Die stärksten Hebel hängen NICHT an Poly-Tiefe.

| # | Maßnahme | Familie belebt | Aufwand | Wirkung |
|---|---|---|---|---|
| ~~1~~ | ✅ **ERLEDIGT 25.07.:** keyPasses/Rating-Fetch für MLS aktiviert (`fetch_player_stats: true`) | **model_stack↑** | — | 🔴 hebt Conviction-Cap, Poly-unabhängig |
| 2 | `mls_travel` Richtungslogik + API-Backtest | context (Qualität) | M | 🔴 gerichteter Edge (0.704!), Poly-unabhängig |
| 3 | MLS-Lineup-Watcher (Hot-Cron) | **unique↑** | M | 🟠 dritte tote Familie |
| 4 | Heim/Auswärts-Standings-Split-Signal | **context↑** | M | 🟠 MLS-nativ, Poly-unabhängig |
| 5 | Odds-Breite: BTTS + O/U-Linien holen | neue Card-Fläche | M | 🟠 mehr Picks |
| 6 | `smart_money` NUR mit Halter-Floor (≥40 Halter + ≥$10–15k) | sharp_money↑ | S | 🟡 klein, betrifft 3–4 Spiele |
| 7 | Poly-Card-Signal für Pinnacle-lose Spiele | sharp_money↑ | M–L | 🟡 deckt halbe Slate, aber dünn |

**Reihenfolge-Logik:** 1+2 verdichten zwei Familien und heben den Conviction-Deckel — der Weg von „nie BET" zu „gelegentlich BET" — und beide sind unabhängig vom dünnen Poly-Markt. Danach die restlichen toten Familien (3, 4) und Fläche (5). Poly-basiertes (6, 7) bleibt hinten, weil die MLS-Poly-Tiefe es strukturell klein hält.

---

## 5b. Lern-Loop-Status (verifiziert 25.07.)
- **Loop lebt und hat gelernt.** Die Runde 22./23.7. (5 aufgelöste Card-Picks) ist vollständig im `mls_signal_ledger.json` (kein Resolve→Ledger-Gap), Gewichte am 25.7. 09:06 aktualisiert. Die scheinbar offenen MD17-Picks sind heute/morgen (Anpfiff 25.7. 23:30Z ff.) — korrekt pending.
- **Aber ausgehungert.** 5 Records gesamt, je Signal 1–4 Beobachtungen gegen Prior-Stärke **n=25** → echte Daten = ~5–14 % des Posteriors. Gewichte sitzen praktisch noch auf den Backtest-Priors. 4 von 5 Picks Verluste, Conviction nur 2–4 (hängt am Familien-Cap: nie BET → nur dünne Steam-Picks im Tracking).
- **Zwei Kanäle:** Priors lernen aus allen 238 gespielten 2026-Spielen (+540 aus 2025), aber **nur Trefferquote, keine historischen Quoten** (`odds:0` im Backtest → kein ROI/CLV). Live-Loop lernt nur aus echten Card-Picks (n=5, ~+5/Runde).
- **Verbindung zu §1b:** Solange `fetch_player_stats` aus war, konnten `chance_creation`/`form_rating` nie Beobachtungen sammeln → nie Gewicht verdienen. Der 25.07.-Fix bringt sie erstmals in den Lernstrom.

## 6. Was ich NICHT empfehle
- Kein 15. Genauigkeits-Signal in `model_stack`/`form`, solange zwei Familien leer sind — der Anti-Korr-Discount (0.4) frisst es sowieso, und es hebt den Cap nicht.
- Keine Schwellensenkung von `steam_bet_threshold` 8 als Abkürzung zu „mehr BET" — das ist der No-Op-/Kalibrierungs-Fehler aus CAPABILITIES §1 (Conviction gegen die echte Verteilung prüfen, nicht die Schwelle ans Ziel biegen). Der Cap gehört *gehoben* (Familien beleben), nicht *umgangen*.
- `fixture_congestion` nicht als Solo-Signal reanimieren (0.502 = Null) — nur als Interaktion mit Reise.
