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
| `uebersicht` | `main-dashboard.js` | **Lucas' Einstiegsfläche** („was kann ich blind nachspielen?"). Seit **01.09.2026** eine einzige Sektion **🎯 „Was kann ich spielen?"** (`_mdSpielbar`) mit **drei nummerierten Ebenen von streng nach breit** — vorher drei gleich gebaute Sektionen untereinander, was redundant wirkte, obwohl die gemessene Überschneidung **null** war (Register 0 Spiele, Konjunktion 1, Rangliste 3, Schnitt 0). Die drei unterscheiden sich in **drei Achsen gleichzeitig** — Einheit (Schubladen vs. Spiele), Zeit (Wochen vs. 12h), Logik (Urteil vs. UND vs. ODER) —, und genau das stand nirgends. Jede Ebene trägt dieselbe Kopfform (Nummer · Frage · `.md-mech`-Bauart-Pille · eigener Stand): **① „Darf ich überhaupt blind spielen?" = REGISTER** (`_mdFreigabe()` aus `freigabe.json`) — beurteilt **Schubladen**, zeigt kein einziges Spiel; je Zeile n/Ziel, ROI **mit** einseitiger 95%-Untergrenze, CLV und die Engine-Version, auf die gefiltert wurde (ältere Plays nur als „alt" daneben); fehlt die Datei, steht dort **❔ unbekannt**, nie „nichts freigegeben". · **② „Wo fällt gerade alles zusammen?" = FILTER** (Konjunktion aus `killer.py` — alle Geld-Bedingungen gleichzeitig, kann leer sein, eigenes Buch, Preis eingefroren beim Treffer). ⚠️ Ihr Badge spricht seit 01.09. **nur noch über das eigene Buch**; das Freigabe-Urteil gehört Ebene ① und wird nicht wiederholt (das war die einzige echte Doppelung). · **③ „Was ist gerade das Stärkste?" = RANGLISTE** (Disjunktion über Cards/Poly/Betfair-Steam/Betfair-Geld/Money-Map — EINE Quelle genügt, praktisch nie leer, kein eigenes Buch, **trägt bewusst keine Signalfarbe und keinen Stand**). Steht ein Spiel in ② und ③, trägt die Top-Wette einen `🔒 gedeckt`-Chip (`_klKeys()`) — **markiert nur, ändert den Rang nicht**. ⚠️ **Desktop-Layout (01.09.2026):** die **Ebenen** bleiben untereinander — nebeneinander liest sich als gleichrangig, und genau das war der Redundanz-Eindruck. Die **Spiele** innerhalb einer Ebene sind untereinander gleichrangig und stehen ab **1040px zweispaltig** (`.md-kl-paar` / `.md-jz-paar`); darunter passt das Deckungs-Profil (7 feste Blöcke) nicht in eine halbe Spalte. Dazu eine **Lesebreite**: `.md-kl-bz` ist auf 820px gedeckelt und `.md-kl-bl` wuchs vorher mit `flex:1` über die ganze Breite — dadurch landeten ROI/CLV am äußersten Rand und das Auge musste 1200px wandern, um Label und Zahl zu verbinden. Tests: `uebersicht-freigabe` (Ebenen-Reihenfolge + Bauart-Pillen), `uebersicht-killer` (② spricht kein Freigabe-Urteil), `uebersicht-abgrenzung`. Dazu: Puls, KPI-Zeile, „Heute spielenswert" (Poly-Plays, seit 31.08. mit Betfair-Zelle), Money-Map, Signal-Bilanz, NOBET-Bilanz. Zeitfenster fail-closed: ohne Anpfiff wird nicht geraten (`_fxKommend`, `MD_FIX_MAX_H=72`, `KL_FENSTER_H=12`) |
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

**🥇 Whale-Rangliste: die Sortierung trug null Information (02.09.2026):** Lucas: *„hast du Ideen, wie wir bessere Whales rausfinden?"* Audit ergab: sortiert wurde nach `scores[w].pnl` — und das ist die **Polymarket-weite** Lebenszeit-Bilanz aus `/pnl` (Wahlen, Krypto, alles), **nicht** unsere getrackten Sportwetten. Gemessen über die echten Daten:

| | |
|---|---|
| Median Ø-CLV der angezeigten Top-20 | **0,59 pp** |
| Median Ø-CLV aller 86 Qualifizierten | **0,60 pp** |
| Korrelation P&L ~ Ø CLV | 0,06 |
| Korrelation P&L ~ Ø Einsatzgröße | 0,04 |

⭐ **Die Liste pickte den REICHSTEN der Qualifizierten, nicht den schärfsten** — eine Zufallsauswahl aus denselben 86 hätte dieselbe mittlere Kante gehabt. (Der Schärfe-Floor arbeitet dagegen: 390 Kandidaten → 112 → 86.)

**Gegenbefund:** CLV **persistiert**. Disjunkte Fenster (`recent` gegen den Rest, je ≥5 Auflösungen, n=21): **r = 0,78**; obere Hälfte +0,64pp → +0,18pp, untere −0,50pp → −1,22pp. Die erste klare Persistenz im Projekt — n ist dünn, `recent` läuft erst seit 01.09.

**Umgestellt** auf die einseitige 95%-**CLV-Untergrenze** als Rang-Kriterium (`_pwClvUg`), P&L bleibt als Kontext-Spalte. `clvSqSum` wird seit 02.09. mitgeschrieben, damit die Streuung und damit eine echte Untergrenze rechenbar ist; solange sie fehlt, wird **geschrumpft** (`avgClv·n/(n+25)`) und im Tooltip ausdrücklich **nicht** Untergrenze genannt. ⚠️ Die Lehre vom 31.07. (n=9 mit Traum-CLV auf #1) bleibt — sie hing am **kleinen n**, nicht an der P&L: solange nur geschrumpft wird, gilt das strengere Gate `PW_RANK_MIN_N=12` statt 8. Wirkung auf die echten Daten: **Median-CLV der Top-20 von 0,59 auf 1,35 pp**, Median-n sogar leicht höher (51,5 statt 43,5), 13 von 20 Wallets ausgetauscht.

**Zwei neue Zuschnitte** (beide opt-in, beide ohne Urteil über das Ausgeblendete): **Sportart** (`bySport` je Wallet — ein globaler Score mischt LoL, Tennis, MLB und Fußball; Chips nur für Sportarten mit ≥3 Wallets Historie) und **Aktivität** (≤21 Tage; Wallets ohne Zeitstempel bleiben drin — unbekannt ist kein Urteil).

**Vorlauf als neue Achse:** offene Positionen merken sich `sport` und `htkFirst` (Stunden bis Anpfiff beim **ersten** Sehen, wird bewusst **nicht** aufgefrischt — sonst sähe jede Position am Ende wie ein Last-Minute-Einstieg aus). Beim Auflösen landet der CLV zusätzlich in `vorlauf.frueh` (≥6h) bzw. `.spaet`. Bewertet wird noch nichts — erst messen, ob es trennt (im Killer-Buch war Vorlauf der stärkste Trenner).

**🔴 Sport-Klassifizierer gab bei jedem unbekannten Tag „Fußball" zurück:** `_tag_category` endete auf `.get(tag, "Fußball")`. Gemessen im Close-Freeze: sechs **`lec-*`**-Märkte (League of Legends EMEA, $63.563 im größten) standen als `sport: Fußball` — und damit in den Fußball-Flächen und im Sperr-Abgleich. Rugby, Handball, Volleyball, Darts hätte es genauso getroffen. Jetzt: bekannter Sport-Tag → Kategorie, Fußball-Tag/entdeckte Liga → Fußball, **alles andere → None**.

**Sport-Inventar (Lucas: „check ob Sportarten bespielt werden, die wir nicht drin haben"):** aus unseren Dateien ist das **nicht** beantwortbar — `open` entsteht aus unserem Scan und ist per Konstruktion vollständig. `sport_inventar()` wertet stattdessen die `/positions`-Antworten aus, die wir für den Ø-Einstieg **ohnehin schon holen** (kein zusätzlicher Call), und listet Markt-Universen außerhalb unseres Scans nach USD → `poly_money_broad.json` → `whaleAusserhalb`. Heutiger Stand des Scans: Fußball 738 · E-Sport 307 · Tennis 290 · US-Sport 183 · Kampfsport 23 · Cricket 4. Offene Positionen **bewiesener** Wallets: SOCCER 71 ($210K) · TENNIS 35 ($250K) · MLB 27 (**$384K**) · ESPORTS 16 ($128K) · CRICKET 3. ⚠️ Das meiste Whale-Geld liegt damit in **MLB — einer für Wetten gesperrten Kategorie** (`PW_BLOCKED_BET_CATS`).

**🔴→✅ Und die zweite Schicht: eine Anzeige-Schwelle entschied, OB wir fragen (02.09.2026):** Lucas, zum neuen Punktestand: *„Wieso gibt es kein Pini? Das Spiel ist zu 100% bei Pinnacle."* Er hatte recht — Sassuolo–Frosinone ist **Coppa Italia**, seit jeher in der Ankerkarte. Die Lücke lag zwei Schichten tiefer: `betfair_consensus.games` entsteht nur aus `live_pool`, und der ist mit **`qualifies_radar()` auf ≥15.000 €** im größten FT-Markt gefiltert — dieselbe Schwelle wie die Radar-**Liste**. Gemessen: Sassuolo–Frosinone **10.289 €**, Mito–Kashima 12.115 €, Hiroshima–Nagoya 5.309 €. Alle drei fielen raus, also fragte **niemand** Pinnacle für sie, und der Punktestand meldete korrekt ❔.

⭐ **Merksatz: eine Schwelle, die entscheidet WAS ANGEZEIGT wird, darf nicht entscheiden, OB WIR FRAGEN.** Neu `betfair_anker.json` (`ANKER_FILE`): Zweitmeinungen (`moneySide/poly/pinn/pinnMove`) für **jedes noch nicht beendete Spiel mit Match-Odds-Markt**, ohne Volumenschwelle. Kostet **keinen einzigen zusätzlichen API-Call** — die Events sind längst geholt, es ist nur Zuordnen. `games` bleibt unverändert die Radar-Liste. `killer.baue(anker=…)` mischt: Radar-Zeilen behalten Vorrang (vollständiger: Totals, Soft-Bücher), der Anker füllt nur Lücken; ein kaputter Eintrag kostet nur sich selbst.

⚠️ **Und meine Erfolgsmeldung von 05:12 war gegen den falschen Nenner gemessen.** `ankerQuote: 1.0` hieß „100% der Spiele **im Konsens**" — und im Konsens standen nachts drei. Von den drei Spielen im Punktestand hatte **null** einen Anker. Jetzt zählt `ankerQuote` gegen **alle offenen Spiele** (`ankerN` daneben). ⭐ *Eine Quote ohne ihren Nenner ist eine Behauptung.*

**Poly-Relevanzschwelle (Lucas: „Sassuolo hat knapp 3K auf Poly, ab wann wird es relevant?"):** zwei Stufen — **$7.500 Marktvolumen** (`poly.money_broad_min_vol` in `cocobet_config.json`) entscheidet, ob der Markt überhaupt **erfasst** wird; darunter gibt es keine Zeile, keine Anteile, keine Wale (deshalb ❔ und nicht 0/3). Erst danach greift **`POLY_MIN_ANTEIL=60`** für die zwei Grundpunkte. Offen: ob 7.500 richtig liegt — in einem dünnen Markt erzeugt ein einzelnes 2K-Ticket schnell 70% Anteil.

**🔴→✅ Pinnacle-Anker lag auf 2% der morgigen Spiele — Ligen werden jetzt entdeckt statt gepflegt (01.09.2026):** Lucas: *„ich akzeptier keine andere Meinung, da wir extra die OddsAPI mit fünf Millionen API-Calls zur Verfügung haben."* Er hatte recht — die Beschränkung war **nie die Quota**, sondern `LEAGUE_ODDS_KEY`: eine handgepflegte Liste mit **30 Ligen gegen 229 Ligastrings** im Betfair-Feed. Gemessen: von **57 Betfair-Spielen am 02.09. hatte genau EINES** einen Pinnacle-Anker (2%); über den ganzen Ledger kommt Pinnacle in **23 von 212 Ligen** an (9% der Zeilen) — dort aber fast lückenlos (La Liga 13/13, PL 10/10, Serie A 10/10). Kein Fetch-Problem, ein Zuschnitt-Problem.

Neu: `fetch_sports()` holt einmal je Lauf `/sports` (**kostet kein Kontingent**), `aktive_fussball_keys()` filtert auf `group=="Soccer"` + `active` + kein `has_outrights`, und der Lauf holt **alle** aktiven Fußball-Wettbewerbe (Deckel `BF_MAX_ODDS_KEYS=90` — er schützt die **Laufzeit** des 12-Minuten-Mac-Runners, nicht die Quota). Fällt `/sports` aus, greift der letzte Abzug aus `odds_sports.json`, statt die halbe Abdeckung zu verlieren. Die Handliste bleibt als **schnelle, sichere Zuordnung mit Vorrang**; findet sie nichts, folgt ein zweiter Anlauf im **globalen Pool**.

⚠️ **Der globale Pool braucht eine Anpfiff-Schranke, sonst wird er zur Verwechslungsmaschine.** `match_event` vergleicht nur Teamnamen — über ~70 Wettbewerbe trifft dasselbe Klubpaar auch in Pokal, Liga und Reserve. Neu `match_event(..., max_h=ANPFIFF_FENSTER_H=2.0)`: liegen die Anpfiffzeiten weiter auseinander, zählt der Namenstreffer nicht, und **fehlt eine der beiden Zeiten, zählt er ebenfalls nicht** — ein Treffer, den wir nicht prüfen können, ist keiner. Ein falsch zugeordneter Anker wäre schlimmer als gar keiner, weil er wie ein Beleg aussieht. Totals bleiben auf die kuratierten Keys begrenzt (die O/U-Leiter wird nur im Poly-Terminal verbraucht; jeder Call kostet Laufzeit).

**Nebenbefund, eigener Bug:** MLS hatte **105 Ledger-Zeilen und null Pinnacle-Anker**. Der Eintrag stand seit jeher in der Karte — als `"Major League Soccer"`, während der Betfair-Feed die Liga **`"US MLS"`** nennt. Wieder „eingebaut, feuert aber nie", diesmal an einer Schreibweise. Beide Schreibweisen stehen jetzt drin. Wächter **`check_pinn_anker`** (77.) meldet jeden Kartencheintrag, der keinen Ligastring im Feed trifft — als **`warn`**, weil er „falsch geschrieben" nicht von „außer Saison" unterscheiden kann (aktuell: `CONMEBOL Copa Libertadores`, außer Saison). `betfair_consensus.json` trägt jetzt `oddsKeysFetched` und `ankerQuote`, damit die echte Abdeckung messbar ist statt aus der Handliste geschätzt.

**🏛️ Bücher-Punktestand — Ebene 2 der Übersicht (01.09.2026):** Lucas: *„ich will die Bücher alle im Vergleich mit den Kriterien, wie viel erfüllt wird, mit einer Punkteanzeige … das Maximum ist zehn von zehn"* — und *„ich sitze nicht zehn Stunden am Dashboard"*: die Übersicht ist der Sekundenblick, Radar- und Poly-Terminal bleiben die Detailarbeit. `killer.buecher_punkte()` (rein/testbar) ersetzt den harten UND-Filter durch einen Score 0–10:

| Buch | Grundpunkt | Zusatzpunkt (Tiefe) |
|---|---|---|
| 💷 Betfair | **2** — Geldanteil ≥65% | **1** — Zufluss ≥€2K **und** Quote zieht mit |
| 💜 Polymarket | **2** — Poly-Geld ≥60% auf derselben Seite | **1** — **bewiesenes** Wallet drauf (n≥8 **und** Ø-CLV>0, aus `poly_wallet_track`) |
| 📐 Pinnacle | **2** — dieselbe Seite als Favorit | **1** — Move ≥ `PINN_MIN_MOVE_PP` in unsere Richtung |
| ⏱ Dauer | — | **1** — steht schon ≥3h vor Anpfiff |

**Die Gewichtung ist gemessen, nicht geraten:** Buch = 2, Tiefe = 1, weil Bücher addieren trug (+11,5%) und Signale stapeln nicht (−1,1%). 6 Punkte gibt es nur, wenn **alle drei** Bücher zustimmen; Betfair allein kommt nie über 3. Der Dauer-Punkt kommt aus dem eigenen Buch (<1h vor Anpfiff −4,1% · ≥6h +48,9%, UG +7,6%). ⚠️ **Ein nicht erhobenes Buch senkt den NENNER, es kostet keine Punkte** — „5/7", nicht „5/10"; ein Nein zählt dagegen in den Nenner. Genau diese Verwechslung hat die Poly-Bedingung monatelang tot gehalten.

Ebene 2 ersetzt damit das alte Deckungs-Profil, das **Betfair mit 3 und Pinnacle mit 2 Plätzen** zählte — „6/7 voll gedeckt" las sich wie sechs Zeugen und waren zweieinhalb. Sortiert wird nach Punkten, bei Gleichstand nach Anteil am Möglichen, dann nach Vorlauf. Die Pille heißt jetzt **Punktestand** statt *Filter*; „Heute spielenswert" (Ebene 3, `_pwTopPlays`) bleibt unangetastet — die deckt E-Sport und alles, was Betfair nicht führt.

**Mitschreiben, nicht filtern:** `killer.baue()` bewertet **jedes** Fußballspiel in `pending` mit gültiger Quote (`alleBewertet`), nicht nur die Tor-Passierer. `punkte_fortschreiben()` friert den letzten Stand vor Anpfiff ein (`punkte_state.json`), rechnet aus `betfair_track_results` ab (`punkte_ledger.json`, `PUNKTE_KEEP=4000`) und `punkte_bilanz()` liefert ROI **je Punktzahl** — der **Gradient** ist die Aussage: steigt der ROI mit den Punkten, oder ist die 8 nur seltener? Spät abgerechnete Spiele bleiben bis 60h offen, statt still aus dem Gradienten zu fallen. Zweite Vorregistrierung **`buecher_score_hoch`** (≥7 von **10 möglichen**, Ziel n=40) misst das vorwärts. Wächter **`check_buecher_punkte`** (76.) schlägt an, wenn ≥10 Spiele bewertet sind und bei **keinem** ein zweites Buch erhoben war — dann ist es ein Betfair-Score mit Zeremonie. ⚠️ **Beim Bau war genau das der Zustand: von 43 bewerteten Spielen hatte EINES mehr als Betfair+Dauer** (die Konsens-Datei deckt 28 von 43 Spielen, davon 7 mit allen drei Büchern). Poly-Vorfenster und Pinnacle-Abdeckung sind der Engpass, nicht die Punktelogik.

Datenweg dafür: `betfair_consensus.match_poly()` reicht jetzt `key`, `whales` (**auf unsere Seite gefiltert**) und `whaleUsd` durch — `whales: None` (nicht erhoben) und `[]` (erhoben, keiner dafür) sind bewusst verschieden.

⚠️ **Eigener Werkzeug-Fehler an diesem Abend:** eine Patch-Ersetzung per Index-Bereich (`s[:dek] + neu + s[alt_end:]`) hat den frisch gebauten Wächter `check_betfair_ledger` mitgelöscht, weil er zwischen den beiden Ankern lag. Dieselbe Fehlerklasse wie ein Testfenster fester Breite — nur im Werkzeug statt im Test. Wiederhergestellt; die Warnung steht jetzt im Block.

**🔒 Vorangemeldete Kandidaten (01.09.2026):** `vorregistrierung.py` + `freigabe.vorregistrierte_schubladen()` → 6. Strom im Register (Ebene 1), Datei `vorregistrierung.json` (**muss committet werden**, steht in `betfair.yml`). Erster Zuschnitt: **`poly_bf_bestaetigt`** — die Teilmenge der Poly-Rangliste, bei der zusätzlich Betfair dieselbe Seite bestätigt (`signals` enthält `bf`), Ziel **n=60**. Anlass war die erste ROI-Untergrenze über null in diesem Projekt: **n=75, ROI +18,1%, UG +1,1%** (ohne Betfair: n=425, −5,1%, UG −12,2%; 83% der 500 Plays sind rein Poly-intern entschieden). ⚠️ **Und genau deshalb belegt sie nichts: 57 der 75 sind dieselben Plays, aus denen die Hypothese am 31.08. gezogen wurde.** Aus 500 Plays lassen sich Dutzende Teilmengen schneiden; die beste liegt per Konstruktion oben.

Drei Sperren machen daraus einen echten Vorwärtstest, jede gegen eine bekannte Selbsttäuschung: **(1) vorwärts messen** — Plays vor der Anmeldung gehen nie ins Urteil, laufen aber als `rueckblick`/`nDavor` sichtbar mit (Muster wie `nAlt` bei den Engine-Versionen); ein Play ohne lesbaren Zeitstempel zählt **nicht** als neu. **(2) Zuschnitt einfrieren** — die Definition liegt als `signatur` in der Anmeldung; ändert sie jemand, meldet die Schublade `ruht`/`ungueltig` statt still etwas anderes zu messen. **(3) Ziel-n vorher nennen** — `zielN` steht bei der Anmeldung fest, sonst hört man auf zu messen, sobald die Zahl gefällt. Eine bestehende Anmeldung wird **nie** überschrieben. Wächter **`check_vorregistrierung`** (75.): schlägt an bei Signaturbruch und wenn nach >21 Tagen kein einziger Play dazukam (= Datei wird nicht committet, jeder Lauf meldet neu an → das Fenster bleibt ewig leer und sieht dabei gesund aus).

**🔴🔄 Korrigiert am selben Abend — mehr BÜCHER hilft, mehr Bedingungen aus EINEM Buch nicht (01.09.2026):** Erste Fassung dieses Eintrags behauptete, zusätzliche UND-Bedingungen machten die Konjunktion messbar schlechter. **Das war ein Messfehler von mir, und Lucas hat ihn erkannt** (*„das ist doch Blödsinn, oder? … das sind trotzdem drei Bücher, die einem Match folgen"*). Gemessen hatte ich `conc AND inflow AND dir` — **drei Bedingungen aus EINEM Buch (Betfair)**. Seine These war eine ganz andere: **drei verschiedene Bücher** (Betfair · Polymarket · Pinnacle), die unabhängig voneinander auf dasselbe Spiel reagieren. Meine Tabelle widerlegte seine These nicht — sie testete sie nie.

Richtig gemessen an 500 abgerechneten Poly-Plays, und das Ergebnis stützt ihn:

| A) mehr Signale aus DEMSELBEN Buch | n | ROI | UG | | B) mehr BÜCHER | n | ROI | UG |
|---|---|---|---|---|---|---|---|---|
| 1 Poly-Signal | 172 | −1,3% | −15,4% | | 0 fremde Quellen | 415 | −4,3% | −11,5% |
| 2 Poly-Signale | 317 | −1,1% | −8,1% | | **1 fremde Quelle** | **85** | **+11,5%** | −4,6% |
| 3 Poly-Signale | 11 | −18,8% | −58,2% | | davon nur `bf` | 75 | **+18,1%** | **+1,1%** |

**Signale stapeln bringt nichts; Bücher addieren schon.** Deshalb war die alte Betfair-Tabelle auch kein Widerspruch: `conc/inflow/dir` sind fast unabhängig (P(Zufluss\|Anteil)=25,4% gg. Basis 21,4%), aber sie sind **dieselbe Stimme dreimal gefragt**.

⚠️ **Und Lucas' zweiter Punkt — die Zeit — war ebenfalls richtig und wurde nie gemessen.** *„schon pre und dann am Spieltag kommen immer mehr dazu"*. Am eigenen Killer-Buch (n=80) nachgerechnet:

| gelatcht | n | ROI | UG |
|---|---|---|---|
| < 1h vor Anpfiff | 51 | −4,1% | −25,2% |
| ≥ Median (0,7h) | 40 | +18,7% | −4,3% |
| **≥ 6h vor Anpfiff** | **8** | **+48,9%** | **+7,6%** |

Wie lange die Konjunktion **durchhält**, trennt besser als jede zusätzliche Bedingung. (n=8 im obersten Eimer — Hypothese, kein Beleg, und wieder rückwärts geschnitten.)

⭐ **Merksätze:** (1) **Bevor man eine These widerlegt, prüft man, ob die Messung sie überhaupt betrifft.** Ich hatte within-source-Stapelung gemessen und cross-source-Konsens widerlegt — zwei verschiedene Dinge. (2) **Zählt Quellen, nicht Bedingungen.** Von Lucas' acht Bedingungen sind nur ~3,5 eigene Bücher: „Poly Top-Wallet" und „Poly Odd-Richtung" sind dasselbe Buch wie „Poly Money"; das Streak-Signal ist unser eigenes Modell und damit die vierte, wirklich fremde Stimme. (3) **Eine Idee, die n zerstört, baut man als SCORE, nicht als Filter** — Stufe 1 (5 Bedingungen) hat in fünf Wochen 10 Zeilen erzeugt; bei n=10 ist nichts belegbar. Mitschreiben, nicht filtern.

⚠️ **Zweites Größenbudget entdeckt (01.09.2026):** `tests/test_pages_artifact_size.py` steht bei **170,16 MB gegen 170 MB Budget** — bereits rot vor allen heutigen Änderungen (Datenwachstum). Das kompakte Ledger-Format entlastet es beim nächsten Lauf um **2,30 MB** (3,14 → 0,84 MB) und kostet bei 40.000 Zeilen später netto +1,06 MB gegen heute. Der Deckel bleibt also tragbar, aber der Kopfraum ist dünn; größte Posten in der Wurzel: `betfair_history.json` 7,2 MB · `betfair_coherence_watch.json` 5,9 MB · `betfair_track_record.json` 5,2 MB. **Das Budget wurde NICHT angehoben** — eine Grenze zu verschieben, bis die Zahl passt, ist genau der Fehler, gegen den die Vorregistrierung oben gebaut ist.

**Konjunktion (29.–31.08.2026):** `killer.py` — die Auswahl hinter „Mehrfach gedeckt". Ein Spiel kommt nur rein, wenn Betfair-Geldanteil ≥65% **UND** ≥€2.000 frischer Zufluss (Intervall-Delta) **UND** die Quote mitzieht; Stufe 1 zusätzlich Poly-Geld ≥60% + Pinnacle-Zustimmung. Schwellen aus `betfair_track_record` **gespiegelt**, nicht neu erfunden. Nur `Match Odds` (CLV-Untergrenze +3,0pp gegen +0,4pp für alle anderen Märkte). Treffer werden bis zum Anpfiff **gehalten** (`killer_state.json`) und zum **Haltepreis** abgerechnet (`killer_ledger.json` → `bilanz()` inkl. `roiLb`). Registriert in `freigabe.py` (`killer_schublade`) — seit 31.08. als **zwei Schubladen**: `Konjunktion · Top-5 + MLS` und `Konjunktion · übrige Ligen` (`killer.TOP5_LIGEN`, Betfair-Schreibweisen — NICHT mit `stats_scope.json` zusammenlegen, das entscheidet über die Card-Bilanz). Grund: über 8.000 Track-Zeilen hat Top-5 den besseren ROI-Punktschätzer (n=10, +21,8%, UG −25,1%), der Rest den einzigen CLV mit Untergrenze über null (n=70, +3,61pp, UG +2,76) — und die Konjunktion feuert in den Top-5 **dreimal häufiger** (16,1% gegen 5,9%). Nicht entscheidbar, also getrennt qualifizieren statt raten. ⚠️ Steht auf „beobachten", nicht auf Freigabe: eigenes Buch n=56, ROI +3,2%, **UG −16,8%**; Stufe 2 (48 von 56 Zeilen) trägt +0,2%.

**🔴 Betfair-Ledger hatte sechs Tage Gedächtnis (01.09.2026):** Lucas: *„kann es sein dass da schon ewig 8000 steht … bild mir ein sollte mehr sein."* Ja — `RESULTS_KEEP = 8000` deckelte `betfair_track_results.json`, und bei ~1.300 Abrechnungen/Tag hielt der Ledger damit **exakt sechs Tage** (gemessen 26.08.–01.09.). Die Kachel „Signale 8000" las sich wie eine Gesamthistorie und war ein rollendes Fenster. Folge war nicht kosmetisch: **kein Liga×Markt-Bucket kam je über n≈24** (Median 5) — während das **Lern-Board ab n=15 Card-Signale umdreht** (`sharp_signals/betfair_money.MIN_TR_N`). Von 1.418 Kombinationen erreichten 60 die Schwelle, aus 12 von 212 Ligen; davon zeigte der Display-Cap 24. **Das** war die Antwort auf Lucas' zweite Frage („oben nur paar Ligen, unten alle — hat das einen Grund?"): der Grund war die Wirkungsschwelle, die Größe des Ausschnitts war die Amnesie.

Deckel jetzt **40.000** (~6 Wochen, `BF_RESULTS_KEEP`). Möglich nur durch **`betfair_track_store.py`** — Spaltenform mit internierten Wörterbüchern (Liga/Markt/Team/Land/via/fav/dir stehen einmal im Kopf, die Zeile trägt den Index; `settledAt` als Sekunden-Offset): **392 → 105 B/Zeile**, 40.000 Zeilen = 4,2 MB statt 15,7 MB. Das zählt, weil die Datei **alle 10 Minuten committet** wird und `.git` bereits bei ~1 GB steht. *Reines Feld-Weglassen war der erste Plan und wurde verworfen: gemessen nur 17% Ersparnis, und `home/away` trägt `byTeamMarket`, `ft/ht` trägt sowohl das Korrekturfenster als auch `betfair_public_eval._track_index()`.* **Verlustkontrolle:** unbekannte Felder landen in einer `rest`-Spalte statt verloren zu gehen; ein Wert, der nicht in seine Spalte passt (`conc=1` statt `True`), wandert ebenfalls dorthin statt als etwas anderes zurückzukommen. Genau zwei dokumentierte Verluste: Mikrosekunden in `settledAt`, und ein ausdrückliches `None` kommt als fehlender Schlüssel zurück (kein Leser prüft Schlüsselpräsenz — am 01.09. geprüft). `aggregate()` liefert vorher/nachher **byte-identische** Buckets. Leser umgestellt: `betfair_track_record`, `killer` (2×), `betfair_public_eval`, `betfair_data_integrity`; `freigabe` reicht durch. Altformat wird weiter gelesen, es gibt keine Migration — **aber Rückrollen wischt den Ledger** (alter Code sieht ein Dict, nicht `list` → `[]`), Warnung steht im Modulkopf. Wächter **`check_betfair_ledger`** (74.) meldet immer die **Fensterdauer** mit und schlägt an, wenn der Ledger am Deckel klebt und trotzdem < 3 Tage abdeckt; unlesbar → `warn`, nie grün. Im Radar trägt die Signal-Kachel jetzt die Dauer („5.9 Tage · 26.08.–01.09."), die Überschrift sagt „rollendes Fenster" statt „über alle", und das Lern-Board beziffert seinen Ausschnitt („3 von 100 Kombinationen") sowie verschluckte Zeilen des Display-Caps.

⚠️ **Offen und wichtiger als der Deckel:** ob das Lern-Board überhaupt trägt. Fenster halbiert (Schnitt 29.08. 17:18), Verdikt aus Hälfte A in Hälfte B gemessen: `boost` +2,7% (n453) / `neutral` +0,1% (n171) / **`fade` +6,8% (n556)** — bei n≥5 je Hälfte dasselbe Bild (+1,9 / −5,0 / **+7,8**). Die als „verliert hier → Card fadet" markierten Kombinationen laufen **out-of-sample besser** als die verstärkten. Bei ±7pp nicht beweisend, aber bei beiden Schwellen dieselbe verkehrte Richtung — Mean Reversion statt Persistenz, dasselbe Muster wie beim Poly-Kalibrator. Sechs Wochen Fenster machen das erstmals ernsthaft messbar; bis dahin dreht `betfair_money.py` weiterhin Signale auf n=15 um.

**🔎 Vor-Fenster lief, lieferte aber nichts — Diagnose eingebaut (01.09.2026, abends):** Lucas: *„haben wir da Lösung schon wieso poly fehlt"*. Stand: der `"vor"`-Zweig ist deployed (identisch mit HEAD), die Klassifizierung greift — **22 frische Vor-Märkte** im echten 3–8h-Fenster mit realem Volumen ($18K–$300K) — aber **kein einziger trug Geld-Anteile**. Von aussen waren drei völlig verschiedene Defekte ununterscheidbar: kein Kandidat kam an · der Holders-Endpoint lieferte nichts · das Ergebnis verpuffte beim Zurückschreiben. Deshalb zählt der Lauf jetzt selbst mit (`rep["vorStats"]` in `poly_money_broad.json`: `kandidaten/calls/mitAnteilen/ohneGeldSplit/budgetLeer/nachgelegt`) und druckt eine Vor-Fenster-Zeile. **Die Zahl gehört in die Datei, nicht ins Log** — ein Log, das niemand liest, hat die tote Poly-Bedingung monatelang gedeckt.

Gleichzeitig beseitigt: der dritte Kandidat war ein **stiller No-Op**. `if _u is not None: _u["shares"] = shares` warf das Ergebnis eines bereits **bezahlten** Holder-Calls weg, wenn der Gratis-Eintrag fehlte — ohne Spur in irgendeiner Datei. Der Zweig ist jetzt die reine Funktion **`vor_zeile(alt, …) → (zeile, nachgelegt)`**: fehlt `alt`, wird die Zeile angelegt statt verworfen, und `nachgelegt` meldet dem Wächter, dass der Ingest-Pfad nichts geliefert hat (ein Halb-Defekt, der sonst grün meldet, weil der Notnagel greift).

⚠️ **Der Wächter selbst hatte einen Messfehler.** `check_poly_vorfenster` zählte Einträge mit `3 < hoursToKickoff <= 8` aus `poly_money_upcoming.json` und meldete **63** — aber `hoursToKickoff` ist ein **Snapshot vom Erfassungszeitpunkt** und wird nie fortgeschrieben; ein zwei Stunden alter Eintrag mit gespeicherten 3,2h steht real 1,2h vor Anpfiff. Echt im Fenster waren **22**. `prune_upcoming` rechnet genau deshalb `real_htk` — der Wächter tat es nicht. Dieselbe Klasse wie eine gedeckelte Zahl ohne ihren Deckel: **ein gespeicherter Zeitabstand ohne sein Alter lügt.** Der Wächter liest jetzt `vorStats` statt zu schätzen, **benennt den schuldigen Zweig** (Geld-Split vs. Budget) und ist ohne `vorStats` **`warn`/unbekannt, nie grün**.

**Poly-Vorfenster (01.09.2026):** neue Erfassungs-Klasse `"vor"` in `poly_money_broad._capture_class` für **3h < htk ≤ `VOR_WINDOW_H`=8h**, mit **eigenem Budget** `MAX_HOLDER_CALLS_VOR=22` und eigenem Ziel: die Anteile werden in `poly_money_upcoming.json` geschrieben (genau die Quelle, auf die `pick_poly` außerhalb des Freeze zurückfällt), **nicht** in `markets`. ⭐ **Bewusst NICHT durch Aufbohren von `PMA.CAPTURE_WINDOW_H`:** das Holder-Budget (90) wird nach **Volumen** vergeben — ein weiteres Fenster ließe ferne Märkte um dieselben Calls konkurrieren, nahe würden verdrängt und der Close-Freeze dünner. Der ist aber die **Auswertungs-Basis** (`poly_money_accuracy`), und „Geldverteilung kurz vor Anpfiff" würde rückwirkend etwas anderes bedeuten. ⭐ **Fußball-Vorrang im Vor-Budget** (`_vor_ist_fussball`, im Zweifel großzügig): gemessen sind von 58 Märkten im Fenster nur **20 Fußball** — nach reinem Volumen gingen **13 von 25 Calls an Tennis**, also an Märkte, die `killer.py` nie benutzt (es sieht ausschließlich Betfair-Fußball-Match-Odds). Mit Vorrang deckt ein **kleineres** Budget **alle** relevanten ab. Kosten: bis zu 22 zusätzliche Holder-Calls/Lauf ≈ **+17%** API-Last, ohne dass der Close-Freeze etwas verlieren kann. Guard `check_poly_vorfenster` (73. Guard): schlägt an, wenn ≥5 Märkte im Fenster stehen und **keiner** Anteile trägt („eingebaut ≠ feuert"); leeres Fenster ist kein Fehler, unlesbare Datei = ❔. Tests: `TestVorFensterBudget`, `TestVorFussballVorrang`, `TestVorFensterGuard` (14).

**🔴 Poly-Bedingung im Killer war strukturell tot (01.09.2026):** `killer.zeile()` prüfte `(poly.get("sharePct") or 0) >= POLY_MIN_ANTEIL` — das `or 0` macht aus einem **unbekannten** Anteil eine **0**, also ein Nein. Unbekannt ist er systematisch: die Holder-Anteile stehen nur in `poly_money_broad_close.json`, und dieser Freeze reicht nur bis **~2,8h vor Anpfiff** (Median 0,3h). Weiter draußen fällt `pick_poly` auf `poly_money_upcoming.json` zurück — und die Datei hat **überhaupt kein `shares`-Feld** (0 von 120 Einträgen), nur Preis und Volumen. Folge: bei **22%** der gelatchten Zeilen konnte Poly gar nicht zustimmen, angezeigt identisch zu „Poly ist dagegen". Jetzt **drei Zustände** in `polyStatus` (`ja` / `nein` / `unbekannt`); Stufe 1 verlangt weiterhin ein echtes `ja` (fehlende Information ist keine Erlaubnis), aber das Deckungs-Profil zeigt **❔** statt eines leeren Platzes und zählt ihn **nicht ins Mögliche** (3/6 statt 3/7). Eine `killer.json` ohne `polyStatus` gilt ebenfalls als unbekannt. ⚠️ Der Tooltip behauptete „kein Poly-Markt" — meist gibt es den Markt sehr wohl. Tests: `test_killer.py::TestPolyDreiZustaende` (6), `uebersicht-killer` (+3). **Offen:** Holder-Anteile auch für Märkte >3h vor Anpfiff erheben würde die Bedingung erst wirklich lebendig machen — kostet API-Quota, noch nicht entschieden.

**„Großes Geld" + „Bewegung"-Audit (02.09.2026, Lucas: „ob das vernünftig implementiert oder man da mehr rausholen kann"):** der 01.09.-Check oben behandelte die Symptome — dies ist die Ursache darunter. Nachgemessen über 1.912 Märkte aus `poly_money_broad_close.json` zerfällt der Geld-Split in zwei Hälften, und **keine davon war eine Aussage über die Masse**:

- 🔴 **Zwei-Wege-Märkte (Tennis, E-Sport, MLB, Over/Under), n=1.262: der Geld-Anteil IST der Preis.** |Geld% − Preis| Median **0,0 pp**, **1262 von 1262 unter 1 pp**. Das ist Struktur, kein Zufall: bei komplementären Tokens hält jede Ja-Aktie eine Nein-Aktie als Gegenstück, also ist `Wert_A/Wert_B` zwangsläufig `p/(1−p)`, und `_market_money` rechnet `shares × aktueller Preis`. „Geld auf X 68% (69¢)" war **eine Zahl, zweimal gesagt**. Dass ESPORTS/TENNIS/UFC/NFL im Rückblick alle auf ⚪ „gleichauf" standen, war keine Messung, sondern eine Tautologie.
- 🔴 **Drei-Wege-Fußball (1X2), n=650: Splits, die kein Preis hergibt.** Belegfall `lal-osa-get` — Osasuna 44,5¢ mit $745.597, Draw 33,5¢ mit $13.100, Getafe 22,5¢ mit $13.006. Ursache: `/holders` liefert **seitenweise**, der Abruf holte genau **eine Seite à 200 Halter je Ausgang** — und schrieb nicht mit, ob das alle waren. Eine abgeschnittene Liste auf der Gegenseite las sich damit als „dort liegt kein Geld“. Genau daher kamen die Trefferquoten von 22–42 % im Fußball, die als „die Masse liegt daneben → faden“ gelesen wurden. **Sie sagen nichts über die Masse, nur über die abgeschnittene Liste** — die Handlungsempfehlung war aktiv schädlich.

⚠️ **Korrektur am selben Tag, bevor daraus eine Kennzahl wurde.** Mein erster Anlauf maß die Güte als `sum(shares)/totalUsd` und nannte das „Abdeckung“ (Median 36 %). `totalUsd` ist aber das gehandelte **Volumen** (`volumeNum`, kumulierter Umsatz), **nicht die offene Position** — die beiden stehen in keinem festen Verhältnis, und ein Markt mit viel Hin und Her hätte allein deswegen „schlecht erfasst“ ausgesehen. Die Zahl hätte plausibel gewirkt und nichts gemessen: genau die Sorte Kennzahl, die dieses Projekt sonst überall verbietet. Gemessen wird jetzt, was der Abruf **wirklich weiß** — ob seine Halter-Liste zu Ende war.

Fix in zwei Teilen. (1) `_alle_holder()` **blättert** jetzt durch `/holders` (`offset`, bis 5 Seiten à 200) und meldet `trunc`, wenn es nicht durchkam — drei Abbruchgründe, und nur einer ist harmlos: kurze Seite = fertig; nur schon bekannte Wallets = die API ignoriert `offset`; Seiten-Deckel erreicht = es gibt mehr. Ein leerer oder gescheiterter Abruf ist **nicht** „null Halter“, sondern abgeschnitten. (2) `split_guete(shares, totalUsd, trunc)` (eine Quelle in `poly_money_accuracy`, re-exportiert in `poly_money_broad`) stempelt jedem Markt `splitGuete: {art, trunc}` mit `art ∈ leer|preis_echo|belastbar|abgeschnitten|unbekannt`. **„unbekannt“ ist bewusst nicht „belastbar“** — Alt-Bestand aus der Zeit vor `trunc` urteilt nicht mit. Die Oberfläche behauptet eine Seite nur noch bei `belastbar`, zeigt sonst „= Preis" bzw. „Split nicht belastbar (X% erfasst)". `evaluate` wertet **nur** `belastbar` und trägt die Aufschlüsselung als `guete` mit. Im Alt-Bestand ist das **null von 1.915** (1.262 `preis_echo`, 650 `unbekannt`, 3 `leer`) — die Rückblick-Fläche sagt deshalb „noch kein Urteil“, bis der nächste Mac-Runner-Scan die Märkte mit `trunc` stempelt. Das ist der ehrliche Stand: vorher stand dort ein rotes „faden“ auf derselben Datenlage. Dazu Mindest-Stichproben (`URTEIL_MIN_N = 30` global, `URTEIL_MIN_N_LIGA = 20`), darunter steht „noch kein Urteil" statt „gleichauf"; und der Liga-Chip fiel bei unbekanntem Verdikt still auf ⚪ neutral zurück — **eine Aussage, wo keine ist** — jetzt „? kein Urteil". ⚠️ Zwei Konventionen füttern `evaluate`: `capture()` friert normalisierte Anteile ein (Summe 1), `poly_money_broad` Dollar — nur dort gibt es eine Lücke; `split_guete` trennt sie an der Summe.

**`SOCCER` war mit 318 von 819 Zeilen (39 %) der größte Eimer der Liga-Tabelle — und trug keinen Liganamen.** Die Slugs kennen die Liga (`lal-`, `elc-`, `ucl-`), und sie muss nicht geraten werden: dieselben Präfixe stehen anderswo im Datensatz **mit** gesetztem Label. `liga_lernen()` lernt die Zuordnung aus den eigenen Daten (min. 3 Belege + klare Mehrheit), `liga_label()` wendet sie an; was das nicht erfüllt, bleibt getrennt aber unbenannt (`SOCCER:MEX`) — getrennt und ehrlich statt zusammengeworfen. 62 % der SOCCER-Märkte lösen sich so auf. Nebenbei: MLB bekam 🏀, weil das Icon an der **Kategorie** hing; `_pwSportIcon` hat jetzt eine Liga-Ebene (⚾/🏈/🏒), `_pwCatOf` bleibt die Kategorie-Funktion für Abschnitts-Überschriften.

**📈 Bewegung — drei Messfehler, alle gemessen:** (1) `base = arr[0]` maß gegen den **ältesten** Snapshot: Fensterlänge über 563 Märkte Median 2,5 h, **Spanne 0,1 h bis 29,2 h** — und dann wurde nach absolutem Move sortiert, ein 26-pp-Drift über 29 h also über einen 3-pp-Ruck über 1 h. Die Tabelle sortierte faktisch nach „wie lange steht der Markt in der History". (2) Die Signal-Spalte las **einen einzigen Tick** (letzter gegen vorletzten Snapshot, Schwelle 0,3 pp bei 0,5¢-Raster): **65 % von 1.884 Schritten waren exakt 0,00 pp** → „flach", der Rest bekam „Steam"/„dreht" aus einem 0,5–2-pp-Tick. Daher stand bei +26,0 pp „flach" und bei +37,0 pp „dreht". (3) Die Anpfiff-Spalte zeigte `latest.htk` **zum Snapshot**, deshalb „<1h" bei laufenden Spielen. Fix: `_pwFensterPunkte` (festes 6h-Fenster, **kein** Rückfall auf `arr[0]`), Sortierung nach **pp/h**, Richtung aus der Steigung über den jüngeren Teil (`_pwTrendSchwanz`, min. 4 Punkte im Fenster — bei genau drei ist der Schwanz die ganze Reihe und die Gerade wird vom ersten Schritt dominiert), darunter „— zu kurz" statt geraten; `htk` altert mit; laufende Spiele tragen „Spielstand drin" (die oberste Zeile war Burnley–Boro 3¢→51¢ „▲ Steam" — das waren drei Tore). **Dieselbe Rechnung steckte in `_pwMoveFor`, das die BET/FADE-Conviction der Shortlist speist**, und in `_pwFlips`; beide nutzen jetzt dasselbe Fenster.

**🐋 Whale-Rangliste — eigener Fehler, am selben Tag korrigiert:** `_pwClvUg` rechnete die Varianz aus `clvSqSum` gegen das **globale** `n`. `n` zählt alle Auflösungen seit jeher, `clvSqSum` erst die seit dem 02.09. — die Rohvarianz wird negativ, und `Math.max(0, …)` machte daraus „null Streuung", also **maximale Sicherheit**. Gemessen: **72 von 127** Wallets im UG-Modus. Die mit den **wenigsten** Daten wären nach oben gerankt worden — die Umkehrung dessen, wozu eine Untergrenze da ist. Jetzt ein in sich geschlossenes Fenster (`clvFenN`/`clvFenSum`/`clvSqSum`, min. 5), sonst wird geschrumpft; eine nennenswert negative Rohvarianz heißt „Fenster kaputt" und führt zum Schrumpfen, nicht zu einer Scheinsicherheit.

### 📐 Anzeige-Regeln (03.09.2026, Lucas: „damit wir alle Probleme mit der Zeit und bei jedem neuen Checkup reduzieren")

Der Checkup vom 03.09. brachte acht Befunde, und es waren nicht acht Fehler — es war **einer, achtmal**: eine Zahl ohne ihre Basis, oder eine Behauptung, die breiter war als ihr Beleg.

| Was dastand | Was es war |
|---|---|
| „🎯 Cards **n30** · 78 % Treffer 21–6" | Quote auf 27 (3 VOIDs), n war das Fenster |
| „Mix bf+money+sharp 3/30 · ROI +135 % **(UG +74 %)**" | Mittelwert mit Etikett — drei ähnliche Ergebnisse haben keine Streuung |
| „**7 Konsens** · BF × Poly × Pinn" | 2 Zeilen ohne Poly-Geld, eine davon $74 |
| „Ø CLV **−2,62 pp** · schlägt Close 13,3 %" | 7 von 30 Werten waren Platzhalter-Nullen (belegt: −3,41 / 17,4 %) |
| „Beste Stufe Conv 7 · +2,5 % · **n149**" | drei Engine-Versionen, aktuell davon 4 |
| „**älteste Quelle** Serien vor 64 Min" | 8 von 13 Feeds geprüft, Poly-LIVE gar nicht |
| „→ Real Sociedad · **jetzt €148K**" | Volumen des ganzen Marktes, nicht der Auswahl |
| „🥅 Torjäger · 46 % dafür · **75 % gegen**" | drei von vier Fällen |

Daraus fünf Regeln, an denen sich jede neue Fläche messen lassen muss:

1. **Jede Quote nennt ihren Nenner** — nicht im Tooltip, im Text. Weichen mehrere Basen in derselben Kachel voneinander ab (Fenster / gewertet / mit CLV), stehen alle drei da.
2. **Eine Untergrenze gibt es erst ab `UG_MIN_N = 30`.** Darunter steht der Punktschätzer allein und „nicht belegt". Eine kleine Stichprobe ohne Spreizung ist keine Gewissheit — sie sieht nur so aus (`untergrenze([1.35]*3) → +1.35`).
3. **Eine Aussage über mehrere Quellen zählt die, die wirklich beitragen** — nicht die Verdikte. `nSources`/`polyGeld` stehen in der Zeile; wer sie ignoriert, behauptet drei Bücher, wo zwei sind.
4. **Jeder Betrag nennt seinen Bezug** (Auswahl oder Markt), jede Zeitangabe ihre Bedeutung (Anpfiff / Dauer der Übereinstimmung / Beginn der Haltung).
5. **Ein Wert ist nur so aktuell wie seine Datei.** Hinkt die Quelle hinter einem frischeren Feed auf derselben Seite her, trägt der Wert seinen Stand mit — sonst liest sich ein alter Preis wie der von jetzt.

Mechanisch gesichert, wo es geht: `uebersicht-frische-und-basis.test.mjs` (14) liest die Ladezeile `_md.data = {…}` als Wahrheit darüber, welche Feeds es gibt, und schlägt an, sobald einer nicht in die Frische-Rechnung eingeht — **die Regel wächst also mit, ohne dass jemand daran denken muss.** Dazu `test_freigabe.py` (Schwelle == Gate-Schwelle), `test_puls_leiste_und_clv.py` (Engine-Filter, Bucket-Regeln gegen `poly_shortlist_track.aggregate`, `clvResolved`), `test_poly_preis_abweichung.py`.

**Die zwei offenen Punkte aus dem Checkup (03.09.2026, Lucas: „na dann schau dir die 2 an"):**

- 🔴 **Die Puls-Leiste maß nach anderen Regeln als das Register direkt darunter.** `agg.byConv` aggregiert den **ganzen** Bestand: 500 abgerechnete Plays über mehrere Engine-Versionen (`ev`: 70× `2026-09-01`, 76× `2026-08-29b`, 8× `2026-08-29`, **346 ohne Stempel**). Die Kopfzeile warb mit „Beste Stufe Conv 7 · +2.5 % ROI · **n149**", während Ebene 1 für dieselbe Stufe `4/30` zeigt und sagt: *„Plays älterer Versionen zählen nicht für eine Freigabe"*. Dazu nimmt `_best_bucket` das **Maximum über ~10 Buckets** und zeigte einen Punktschätzer — ein Maximum über viele Buckets ist selbst eine Auswahl. `_strip` rechnet jetzt auf `_aktuelle_zeilen()` (dieselbe Regel wie `freigabe.aktuelle_engine`) und `_best_bucket` bekommt die **Renditen je Play** statt fertiger Aggregate, damit `freigabe.untergrenze` greifen kann. Ergebnis auf den echten Daten: statt „Conv 7 · +2.5 % · n149" steht dort **„Conv 6 · +0.5 % · n30 · nicht belegt (UG −24.1 %)"**, statt „bf · +17.0 % · n93" **„sharp · +15.0 % · n41 · nicht belegt (UG −3.0 %)"** — was zu „nichts freigegeben" eine Ebene tiefer passt. Ein Test hält die Bucket-Regeln gegen `poly_shortlist_track.aggregate`, damit die beiden Flächen nicht auseinanderdriften.
- 🔴 **Die Platzhalter-Nullen im CLV.** `clvPP` steht auf **jedem** Pick — angelegt mit `0.0`, gefüllt erst mit einer Closing-Linie. Gemessen an den Pick-Dateien: **122 von 264** Liga-Picks tragen `clvPP == 0`, und davon hat **kein einziger** `clvResolved` (MLS 18/1, WM 52/0). `compute_clv_summary` kennt die Unterscheidung seit jeher (*„kein Closing erfasst → zählt nur in die Abdeckung"*), `build_signal_ledger` reichte das Flag nur nie durch — und der Puls zählte die Nullen deshalb voll: sie zogen den Ø CLV Richtung null (**die Zahl sah besser aus als sie ist**) und saßen im Nenner von „schlägt Close", wo sie per Konstruktion nie zählen können. Gemessen im Fenster: **Ø −2,62 pp / 13,3 %** angezeigt gegen **Ø −3,41 pp / 17,4 %** belegt — beide Zahlen falsch, je eine pro Richtung. Der Ledger trägt das Flag jetzt, der Puls verlangt es (fehlt es, gilt die Zeile als unbelegt: nicht wissen ist keine Erlaubnis). Alle drei Ledger einmal neu gebaut, damit die Fläche nicht bis zum nächsten Lauf leer steht.

Nebenbei bestätigt: der `n`/`nGraded`-Unterschied aus Fix 2 sind **VOID**-Picks (WM-Ledger: `{'LOSS': 75, 'WIN': 96, 'VOID': 5}`) — weder WIN noch LOSS, also zu Recht nicht in der Trefferquote.

**Was fehlte bei Betis–Real Madrid von Poly? Das Geld (03.09.2026, Lucas).** Die Money-Map-Zeile trug `poly: {sharePct: 48, usd: 74, src: "scan"}`. `src: "scan"` heißt: sie kam aus `pinnacle_poly_scan.json`, das nur ein Preis-Tripel und ein `vol` liefert — `shares` ist dort per Konstruktion **leer**. Letzter Snapshot: `poly: [0.45, 0.195, 0.475], vol: 74.0`. **Vierundsiebzig Dollar.** Der Geld-Scan hatte den Markt nicht, weil er zwei Bedingungen verfehlt: Anpfiff in ~36 h (Fenster `CAPTURE_WINDOW_H = 3`) und $74 Volumen (Schwelle `min_vol = 7.500`). Beides normal so früh — der Markt füllt sich noch.

Der eigentliche Befund kam beim Nachsehen: der Poly-**Preis** sagte **47,5¢** für Real Madrid, Pinnacle **69 %**, Betfair **92 %** Geldanteil bei Quote 1,41 (≈ 71 %). Gut zwanzig Punkte daneben — kein Widerspruch aus Überzeugung, sondern ein Eröffnungskurs, den niemand angefasst hat. Und die „Zustimmung" bestand darin, dass 47,5¢ (Real) knapp über 45¢ (Betis) lag: **zweieinhalb Cent Abstand bei $74 Umsatz.** Rauschen, das zufällig in dieselbe Richtung zeigt.

Zwei Änderungen: (1) `poly_preis_abweichung(pl, pinn)` misst, wie weit ein reiner Scan-Preis vom Anker liegt (Betis: **21,4 pp**, Schwelle `POLY_PREIS_MAX_ABW_PP = 15`), die Zeile trägt `polyPreisAbwPP`/`polyPreisWeit`, und die Karte schreibt statt „Preis (dünn)" dann „Preis liegt 21pp neben dem Anker". Der Preis **verschwindet nicht** — er ist eine Information, nur eben keine Zustimmung. Für eine Poly-Seite aus echtem Geld ist die Frage gegenstandslos (`sharePct` misst dort Geld, nicht einen Preis) und die Felder stehen gar nicht erst da. (2) Die Übersichts-Kachel schrieb „7 Konsens · **BF × Poly × Pinn**" — eine Drei-Bücher-Behauptung für alle sieben Zeilen, obwohl zwei davon `polyGeld: false` und `nSources: 2` tragen. Sie zählt jetzt die echten Drei-Bücher-Zeilen und benennt den Rest: „5 Konsens · 5× alle drei · 2 ohne Poly-Geld". Tests: `test_poly_preis_abweichung.py` (9) mit den echten Zahlen der Zeile, plus zwei Frontend-Wächter.

**Übersicht-Checkup (03.09.2026, Lucas: „kleinen Checkup der Übersicht auf inhalt, logik, fehler"):** drei Fehler behoben, zwei Logikbrüche dokumentiert und offen gelassen.

- 🔴 **Die Kopfzeile verschwieg die trägsten Feeds.** Oben stand „älteste Quelle Serien vor 64 Min", während dieselbe Seite unten „letzte Erfassung vor 2 h" meldete. `_mdQuellenAlter()` prüfte **8 von 13** geladenen Datensätzen (`mlsStreaks`, `bfDir`, `bfTrack`, `killer`, `freigabe` fehlten), und der Polymarket-LIVE-Feed hat gar kein Feld in `_md.data` — er kommt über `_pwCache.broadLiveNow`. Der Kommentar in `_head()` verspricht ausdrücklich das Gegenteil („die Seite ist nur so frisch wie ihr trägster Feed"). Jetzt zählen alle 13 plus `_pwLiveStaleMin()` — also genau die Zahl, die die Kachel unten selbst anzeigt. Weil der Poly-Cache **lazy** lädt, zieht `_mdRefreshAsof()` den Kopf nach, sobald er da ist; ohne das bliebe er auf dem Stand von vor dem Laden stehen, also wieder zu optimistisch. Ein Test liest die Ladezeile `_md.data = {…}` als Wahrheit darüber, was es gibt, und schlägt an, sobald ein Datensatz dazukommt, der nicht in die Frische-Rechnung eingeht.
- 🔴 **„n30" über einer Quote, die auf 27 rechnet.** `n` ist die Fenstergröße (alle abgerechneten Picks), `winPct = wins/(wins+losses)`. Picks, deren `result` weder WIN noch LOSS ist, fallen aus der Quote und blieben im angezeigten n (`n:30, nGraded:29, wins:21, losses:8`). Jetzt trägt jede Zahl ihre eigene Basis: „n30 · 27 gew." und „Ø CLV · n27" — und nur dann, wenn sie sich unterscheiden.
- 🔴 **Untergrenzen auf n=3, die keine sind.** `untergrenze([1.35, 1.35, 1.35])` gab **+1.35** zurück — den Mittelwert mit einem Etikett. In der Übersicht stand daraufhin „Mix bf+money+sharp 3/30 · ROI +135% **(UG +74%)**": 74 % Rendite „belegt" aus drei Plays. Drei ähnliche Ergebnisse haben eine Streuung nahe null, und ohne Streuung fällt die Schranke auf den Punktschätzer zusammen — **dieselbe Krankheit wie die geklemmte Varianz in der Whale-Rangliste am 02.09.** Die Grenze steht jetzt bei `UG_MIN_N = MIN_N = 30`, also dort, wo die Approximation laut eigenem Anspruch trägt und wo das Gate sie ohnehin erst abfragt. **17 Schubladen** zeigen ihren ROI weiter, aber „UG —". Am Gate ändert sich nichts (0 freigegeben vorher wie nachher); was sich ändert, ist die CLV-Seite — ein `clvLb` aus 10 CLV-Werten neben 40 Renditen gibt es nicht mehr, und ohne `clvLb` bleibt die Schublade „geprueft". Auch das ist gewollt: die CLV-Bedingung existiert genau deshalb, weil sie Glück von Kante trennt.

⚠️ **Bewusst offen gelassen, weil sie eine Entscheidung enthalten:** (a) der Puls wirft für „Beste Stufe Conv 7 · +2.5% ROI n149" aktuelle und alte Engine-Plays zusammen und lässt die Untergrenze weg — während Ebene 1 direkt darunter `4/30` zeigt und ausdrücklich sagt, dass alte Plays nicht zählen; (b) die Money-Map-Kachel zählt `verdict === 'konsens'`, obwohl zwei der sieben Zeilen unten „beide knapp — schwaches Signal" tragen und eine davon nur „2 / 3 · Poly nur Preis" — und ein Zwei-Wege-Poly-Split **ist** per Konstruktion der Preis (Befund vom 02.09.), also keine dritte Stimme. Dazu ein ungeprüfter Verdacht: von 30 CLV-Werten im Puls sind **10 exakt `0.0`** — das sieht nach „kein Schlusskurs erfasst" aus (Signatur vom 28.07.), zählt aber voll in Ø CLV und in den Nenner von „schlägt Close".

**Der Fix legte einen zweiten Fehler frei (03.09.2026, Lucas: „ein poly scan von vorhin ging schief"):** der Poly-Global-Scan um 05:09 UTC committete lokal und kam dann **fünfmal** nicht durch —

```
error: The following untracked working tree files would be overwritten by merge:
        wm_poly_slugs.json
Aborting → Merge with strategy ort failed → push rejected (non-fast-forward)
```

`--autostash` legt nur **getrackte** Änderungen weg. Eine **untrackte** Datei, die der eingehende Commit NEU mitbringt, blockiert den Merge — git überschreibt nichts, was es nicht kennt. Und warum ausgerechnet jetzt: `wm_poly_slugs.json` schreibt `fetch_wm_poly_prices.py` seit jeher, committet wurde sie **nie**, weil die Registry-Staging-Zeile die zerschredderte Kommando-Substitution war. Seit deren Reparatur landet sie erstmals auf origin (`3618d5daf`, 03.09. 07:09) — und auf jedem selbst-gehosteten Runner, der sie schon einmal erzeugt hatte, liegt sie untracked im Weg. **Ein Fix hat einen zweiten Fehler freigelegt, der die ganze Zeit da war.** Blast-Radius geprüft: von 54 Registry-Dateien war genau diese eine betroffen, `wm_poly_resting_orders.json` ist die letzte verbleibende Kandidatin.

`scripts/ci_pull.sh` ersetzt in **allen 43** Pull-Stellen den rohen `git pull`. Statt die Fehlermeldung zu parsen wird die Kollision **vorher** berechnet: welche Dateien bringt der eingehende Stand neu mit (`git diff --diff-filter=A HEAD FETCH_HEAD` — gegen FETCH_HEAD, weil `origin/main` auf einem frischen Checkout nicht zwingend existiert), und welche davon liegen lokal untracked herum? Genau die wandern nach `.ci_kollisionen/` (gitignored) — **verschoben, nicht gelöscht**: sie waren nicht Teil unseres Commits, origins Fassung gewinnt, der nächste Lauf erzeugt sie ohnehin neu. Zwei Workflows rebasen bewusst statt zu mergen (`pinnacle-poly-scan`, `liga-backtest`) — dafür nimmt das Skript einen zweiten Parameter, die Merge-Strategie bleibt unangetastet. Tests (`test_ci_pull.py`, 10) bauen zwei echte Klone eines Bare-Repos und prüfen beide Hälften: dass der alte Pull an der Kollision **scheitert** (ohne diesen Beweis sagt der Rest nichts), dass das Skript sie auflöst — und dass es **nichts anfasst**, was ihm nicht gehört: untrackte Dateien ohne Kollision bleiben liegen, getrackte lokale Änderungen gewinnen weiter per `-X ours`. Dazu ein Wächter, dass kein Workflow wieder direkt `git pull` ruft.

**Archiv-Wachstum + 83 stille `git add`-Fehler (02.09.2026, Lucas: „Haben diese Tik Tok … auch da ein Speicher Problem / Und die Event Seiten, kann man die vergangenen … löschen?"):**

- 🔴 **TikTok-Karten: ja, und ohne jede Bremse.** 145 MB im Arbeitsbaum, alles in git, **nirgends eine Aufräum-Logik**, Zuwachs ~2,2 MB/Tag. `daily-tiktok` (83 MB) war seit dem **20.07. tot** — sechs Wochen keine neue Datei. Niemand liest alte Karten: der Dedup in `generate_daily_tiktok` prüft nur Dateien von HEUTE (`OUTPUT_DIR.glob(f"{today_iso}_*.png")`).
- ⚪ **Event-Seiten: nein, das ist der falsche Hebel.** Die 120 HTML-Seiten sind zusammen **2,9 MB** — sie zu löschen bringt nichts und kostet genau den SEO-Bestand. (Meine frühere Angabe „125 Seiten à ~550 KB = 69 MB" war der Ordner-Durchschnitt, nicht die Seiten.) Teuer war `matches/data`: **1.373 JSONs, 65 MB**, davon **832 ohne Event-Seite und ohne Index-Eintrag**.

`scripts/archiv_aufraeumen.py` als Regel statt Handarbeit: **alle Karten außer denen von heute** (Lucas: „brauch ich ja danach nicht mehr … sind eh auf telegram gepusht und dort gespeichert"); eine `matches/data/<slug>.json` nur, wenn **alle drei** zutreffen — keine `matches/<slug>.html`, kein `matches/*index*.json` nennt den Slug, und das Datum liegt über 7 Tage zurück. Die Datums-Bedingung ist die Sicherung gegen einen Generator-Aussetzer (leerer Index ⇏ frische Daten weg); ein unlesbarer Index löst **eine Exception aus statt zu löschen**, ein Dateiname ohne Datum bleibt. ⚠️ Die Karten von **heute** bleiben liegen, und zwar nicht aus Vorsicht, sondern weil sie gebraucht werden: `generate_daily_tiktok.py` prüft `_today_done and _existing_pngs` — der primäre Cron läuft 04:00 UTC, der Backup-Cron 05:30. Wären die PNGs schon weg, fände der Backup-Lauf keine, der **Doppel-Sende-Schutz griffe nicht** und der öffentliche Channel bekäme dieselben Karten zweimal. Zweiter Grund: scheitert der Telegram-Versand, ist die Karte noch da. Ein Test hält beides zusammen — ändert jemand den Guard, fällt der Test statt des Channels. Einmal gelaufen: **1.459 Dateien, ~174 MB frei** (Artefakt 169,3 → **121,9 MB**, Arbeitsbaum 198 → **164 MB**; `mls_daily-tiktok` und `liga_daily-tiktok` stehen jetzt bei 0 Dateien, `daily-tiktok` bei 8 undatierten Vorlagen, die die Regel korrekt in Ruhe lässt). Läuft täglich in `daily-tiktok.yml` mit `git add -A` je Ordner, damit die Löschungen auch committet werden. ⚠️ **`.git` (1,3 GB) schrumpft dadurch nicht** — die Historie behält jede je committete Datei; dagegen hülfe nur ein History-Rewrite, und der ist eine eigene Entscheidung.

- 🔴 **83 `git add`-Zeilen in 18 Workflows staged seit jeher nichts.** Gefunden beim Nachsehen: `git add mls_daily-tiktok2>/dev/null || true` — **ohne Leerzeichen**. Die Shell liest den Pfad als `mls_daily-tiktok2`, den es nicht gibt; `|| true` schluckt den Fehler, danach ist nichts gestaged, `git diff --staged --quiet` meldet „keine Änderung" und der Job endet **grün**. Dieselbe Signatur wie der sechsstündige Betfair-Ausfall vom 01.09. Betroffen u.a. `mls_track_record_state.json`, `liga_closing_lines.json`, `wm2026-odds-history.json`, `mls-odds-history.json`.
- 🔴 **Fünf Workflows hatten eine zerschredderte Kommando-Substitution.** `git add $(python3` / `git add state_files_registry.py` / `git add --bash-list` / `git add <job>)` — gemeint war **eine** Zeile `git add $(python3 state_files_registry.py --bash-list <job>)`. Ein früherer „eine Datei pro `git add`"-Umbau hat sie an den Leerzeichen zerlegt; seitdem lief ein offenes `$(` über vier Zeilen und `python3` startete ohne Argumente. Betroffen: `daily-tiktok`, `daily-wm-story`, `fetch-wm-data`, `manage-wm-poly`, `track-record-card` — genau die Jobs, deren Ausgaben immer wieder „alt" aussahen. Ersetzt durch eine Schleife, die die Registry einmal auswertet und dann Datei für Datei staged.

Tests: `test_workflow_git_add.py` wächst um drei Wächter (Pfad klebt am Umleitungs-Operator · unbalancierte Klammern in einer `git add`-Zeile · die Registry wird weiterhin, aber einzeln gestaged), `test_archiv_aufraeumen.py` (15) nagelt fest, dass die Regel keine Event-Seite und nichts aus einem Index anfasst — inklusive Gegenprobe am echten Bestand.

**Pages-Artefakt bei 99,6 % des Budgets:** gemessen 169,3 von 170 MB. Ein Test, der bei 99,6 % grün ist, warnt nicht mehr, er beruhigt. Ein erster Anlauf zählte die acht größten unbenutzten JSONs **namentlich** auf — also genau die Bauart, die am 28.08. still veraltet ist und den Deploy gekippt hat. Jetzt eine **Regel** statt einer Liste: `scripts/pages_ballast.py` entfernt jedes Wurzel-JSON, das keine ausgelieferte HTML/JS/CSS-Datei erwähnt (66 Dateien, 21,1 MB). Dynamisch gebaute Namen (`ds + '_poly_prices.json'`) überleben, weil auch Namens-Endstücke ab einem Unterstrich gesucht werden. Der Test fährt **dieselbe** Regel (kein Nachbau) und prüft gegen, dass nichts Gelöschtes referenziert ist — und dass im Workflow **keine** Namensliste zurückkehrt. Budget **160 MB**, real 148,3. ⚠️ Mehr ist ohne Entscheidung nicht drin: die 148 MB sind je etwa zur Hälfte `matches/` (125 Event-Seiten, ~550 KB pro Stück) und **referenzierte** Wurzel-JSONs. Letztere braucht die Seite nur als **Rückfall** — geholt wird primaer von `raw.githubusercontent.com/main`. Wer den Rückfall aufgibt, spart auf einen Schlag ~79 MB; das ist eine Produktentscheidung (Verhalten bei raw-Ausfall), keine Aufräumarbeit.

Guard `check_split_vollstaendig` (`poly_data_integrity`, 14 Guards): schlägt an, wenn frisch eingefrorene Märkte kein `splitGuete` tragen (Producer schreibt es nicht mehr) oder der Anteil abgeschnittener Mehrweg-Splits über 30 % steigt (das Blättern kommt nicht durch — Quota, API-Wechsel, ignoriertes `offset`). Tests: `test_geld_split_guete.py` (28, inkl. Blättern), `poly-split-und-bewegung.test.mjs` (25); migriert (alter Vertrag, dokumentiert): `test_poly_money_accuracy.py`, `test_poly_money_broad.py`, `test_whale_ranking.py`, `poly-money-accuracy.test.mjs`, `poly-stale-kickoff.test.mjs`, `poly-wallet-kickoff-gate.test.mjs`.

**„Großes Geld"-Check (01.09.2026):** zwei Befunde. 🔴 **Die Kachel „🏆 Masse weiß am meisten" stand GRÜN auf MLB, während dieselbe Ansicht MLB darunter als „🔴 Preis besser" führte.** Ursache: der Vorfilter `Math.abs(edge)>=0.01` sortiert nach **Betrag**, nicht nach **Vorzeichen** — sind alle übrigen Ligen negativ (aktuell 12 von 12, beste MLB −0,027), wird `s[0]` als Sieger gekrönt, obwohl er der am wenigsten schlechte Verlierer ist. Jetzt: Sieger-Kachel nur bei `edge>0`, Verlierer-Kachel nur bei `edge<0`; sonst ein goldener Hinweis **„keine Liga — in keiner ist das Geld schärfer als der Preis"** samt „am nächsten dran". Die Kachel nennt jetzt **beide** Maße (Trefferquote UND Brier-Vorsprung) — ausgewählt wurde nach dem Vorsprung, angezeigt war nur die Trefferquote. · 🔴 **Die Tabelle „zum Folgen" listet 30 Märkte, während für KEINE Liga „🟢 Geld schärfer" gilt** (17 Ligen: 12× preis_besser, 5× gleichauf, 0× geld_schaerfer). Das Urteil stand nur im Rückblick weiter unten; jetzt trägt **jede Zeile** einen Chip `🟢 folgen / ⚪ neutral / 🔴 faden`, und eine Liga ohne Historie bekommt **„?"**, nicht Schweigen. Tests: `poly-geld-check.test.mjs` (4).

**Poly-Terminal-Check (01.09.2026):** vier Befunde behoben. ⭐ **Die Spalte hieß „CLV-Bucket" und zeigte den `roi`** — bei Konv 7 (n=175) stehen ROI **+1,3%** und CLV **−0,2pp**, sie widersprechen sich im Vorzeichen, die Überschrift log also genau dort, wo es zählt; `clvAvg` lag in `agg.byConv` die ganze Zeit vor und wurde nie gelesen. Heißt jetzt **„Stufen-Bilanz"** und zeigt **ROI und CLV getrennt benannt**. · Der **Public-ROI** stand als nackter Punktschätzer da (die letzte Stelle im Terminal ohne Untergrenze): `_pwSegUg()` rechnet sie aus `settled`, `_pwUgFarbe()` färbt **grün erst bei UG>0**, gold bei positivem ROI ohne Beleg, grau bei unbekannt. +2,3% (n=180) hat UG **−7%** → gold. · „1 handelbare Plays" → Einzahl. · ⭐ Der Wallet-Satz war **Singular, obwohl `_pwSharpInfoForKey` die Wallets EINER Seite summiert** (`b.n += raw.n`; `count` lag vor und wurde nie gezeigt) — „(128/213, 60%)" las sich wie eine Wallet, waren aber zwei. Jetzt Plural + „N Wallets, zusammen …". Und ein Beleggrad von **99,8%** hieß „noch nicht belegt", obwohl eine der beiden bewiesen war (Wilson-UG 0,532) und die zweite um 0,0005 verfehlte → ab **95%** „faktisch belegt". Tests: `poly-terminal-check.test.mjs` (7).

**Gedächtnis je Wallet (01.09.2026):** `poly_money_broad._wallet_zeit` schreibt beim Werten einer Position `firstTs`/`lastTs` und ein gleitendes Fenster `recent` (letzte `WALLET_FENSTER=30` Auflösungen als `[Datum, CLV-pp, 1/0]`) in `poly_wallet_track.json`; `fenster_bilanz()` rechnet daraus Ø-CLV und Trefferquote **ohne zu urteilen** (liefert `n` mit). Gesammelt wird erst ab `WALLET_FENSTER_AB_N=8` — 2.573 der 2.956 Wallets liegen unter n=8 und würden die Datei sonst vervielfachen; Zeitstempel bekommen aber **alle**. ⭐ **Grund:** der Track trug keinen einzigen Zeitstempel — man konnte weder sagen, wann eine gerankte Wallet zuletzt aktiv war (15 der Top-20 hatten keine offene Position), noch dass eine Wallet mit n=622 auf ihrer **ganzen Lebenszeit** beurteilt wird und eine schwache Phase im Mittel untergeht. Frontend (`poly-wallets.js`): Spalte **„zuletzt"** in **beiden** Ranglisten — `heute`/`gestern`/`Xd`, grün ≤3d, gold ≤14d, sonst grau; ab 5 Fenster-Einträgen ein ▲/▼, das die letzten Auflösungen gegen den Lebenszeit-CLV hält. ⚠️ Ohne Zeitstempel steht dort **„—", nie „frisch"**. Das Fenster ist heute leer und füllt sich erst mit neuen Auflösungen (Vergangenheit ist nicht nachtragbar) — es wird vorerst nur **mitgeschrieben, nicht bewertet**. Tests: `test_wallet_gedaechtnis.py` (12), `poly-wallet-stille.test.mjs` (5).

**Conviction-Kalibrierung beobachtet nur noch (01.09.2026):** `PW_CALIB_AKTIV = false` in `poly-wallets.js`. `_pwCalibConv` rechnet weiter und liefert `hinweis`/`wuerde`, verändert aber **kein `conv`** und vergibt **keinen `calib+`/`calib-`-Tag** (der würde über die Signal-Eimer ins Papier-Depot und ins Public-Gate zurückwirken). ⭐ **Grund — gemessen, nicht vermutet:** Walk-Forward über `poly_shortlist_track` (jeder Play lernt nur aus seiner eigenen Vergangenheit) ergab an **sechs von sechs** Startpunkten, dass die **abgestuften** Plays die hochgestuften schlagen. Ursache: die Rangfolge der Signal-Mixe hält, die **Größe** nicht (`bf+money` +52,2% → +9,2%), und die Formel `(roi−base)×15×conf` bemisst sich am rohen Punktschätzer — `conf=n/(n+25)` dämpft nach Stichprobengröße, nicht nach Rauschanteil (bei n=60 nur auf 0,7). Die Untergrenze als Richter hilft **nicht** (stuft dann 318 von 328 ab); 0/5 in beiden Varianten. Angefasst wurden vorher **32%** aller Plays. ⚠️ **Vor jedem Wiedereinschalten `python3 scripts/calib_walkforward.py` laufen lassen** — „die Eimer sehen plausibel aus" ist kein Beleg, „hoch schlägt runter über mehrere Startpunkte" ist einer; ein einzelner 50/50-Schnitt war am 01.09. bereits irreführend positiv. Tests: `poly-calib-beobachtet.test.mjs` (6), `poly-terminal-calibration` (Rangfolge wandert von `conv` nach `wuerde`).

**Money Map wird messbar (01.09.2026):** `betfair_consensus.money_map_row` reicht jetzt `moneyOdd` durch, `update_mm_ledger` hält **zwei** Preise fest — `moneyOddFirst` (beim ersten Auftauchen, nur der war nehmbar → ROI, wird nie überschrieben; ein Seitenwechsel verwirft ihn) und `moneyOddLast` (zuletzt gesehen → CLV). `mm_summary` liefert je Verdikt/Stärke/global zusätzlich `roi`, `roiLb`, `nRoi`, `clv`, `clvLb`, `nClv`. ⭐ **Grund:** die Fläche schrieb seit August `moneyWin` mit, aber **nie eine Quote** — ihre 81,3% Trefferquote bei „stark" (n=524) sagen nichts über Geld, weil das Geld auf Favoriten liegt. Ohne Preis war sie nicht widerlegbar. ⚠️ `nRoi` wird **getrennt** von `n` gezählt: Alt-Zeilen ohne Quote zählen in die Trefferquote, nicht in die Rendite — sonst sähe ein ROI aus 4 Zeilen aus wie einer aus 900. Frontend (`money-map.js`): eigene Spalte „Rendite" mit Untergrenze und `n`, grün erst wenn UG>0; Intro sagt „**trifft ist nicht zahlt**". Tests: `test_moneymap_rendite.py` (11).

**Trades-Push der Konjunktion + Freigabe (01.09.2026):** `killer_push.py` schickt **nur Stufe 1** in den Trades-Channel (`TELEGRAM_TRADES_CHAT_ID`), `freigabe_push.py` meldet **Freigabe-Wechsel** — beide in `betfair.yml` im ~15-Min-Takt. Zuschnitt **gemessen**, nicht geschätzt: das Konjunktions-Buch nimmt **20–58 Zeilen/Tag** auf (Stufe 1 davon ~5, Bilanz 8–2; Stufe 2 trägt nur +0,2% bei n=67), und der Median-Abstand **Latch → Anpfiff liegt bei 48 Minuten** — deshalb das enge Fenster `KILLER_PUSH_MIN_MIN=10` / `KILLER_PUSH_MAX_H=12` (darunter ist die Nachricht gelesen, wenn das Spiel läuft; darüber gilt der genannte Preis nicht mehr). ⭐ **Eigenes Buch:** `killer_push_ledger.json` rechnet zum **`pushPreis`** ab — dem Preis, der in der NACHRICHT stand —, nicht zum `haltePreis` der Fläche; `killer_ledger.json` misst die Sektion, dieses hier den Channel, und beide driften auseinander (Latch ≠ Versand). Ein fehlgeschlagener Send vermerkt **weder** `seen` **noch** eine Ledger-Zeile. Jede Nachricht trägt den Stand mit („ROI +4% (Untergrenze −13%) → NICHT belegt. Beobachtung, keine Freigabe") — der Channel darf nie mehr versprechen als das Register. `freigabe_push.py` meldet **Rücknahmen gleichberechtigt** (⛔), meldet **keine** Zwischenstufen, und ein **Erstlauf sendet nichts** (sonst fluteten 38 Schubladen den Channel); eine unlesbare `freigabe.json` lässt den Zustand unangetastet. Guard `check_killer_push_buch` (72. Guard): meckert, wenn gepushte Zeilen >48h nach Anpfiff noch „offen" sind (Abrechnung findet sie nicht) oder `pushPreis` fehlt; fehlende Datei = ❔, nie grün. ⚠️ **Ebene ③ „Top-Wetten jetzt" wird bewusst NICHT gepusht** — praktisch nie leer und die einzige Fläche **ohne eigenes Buch**. Tests: `test_killer_push.py` (25), `test_freigabe_push.py` (12).

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

### 🎰 Stake Radar (03.09.2026, Lucas: „ich würde gerne nur im Dashboard einen Bereich mit den Spielen sehen … dann rein und wir sammeln das")

Vierte Quelle, und die einzige, die **einen einzelnen Einsatz mit Betrag** nennt: Stake zeigt große
Wetten öffentlich (Event, User, Zeit, Quote, Einsatz). Betfair gibt Matched-Volumen, Poly gibt
Preis-als-Geldanteil, Pinnacle gibt den Anker — keine davon nennt eine einzelne Wette.

Das ist der eigentliche Grund, das zu bauen, und er steht in unserer eigenen Messung vom 01.09.
auf 500 Plays: **Bücher addieren (+11,5 %), Signale innerhalb eines Buchs stapeln nicht (−1,1 %)**.
Stake bringt eine neue Achse (Einsatz*fluss*), nicht ein weiteres Preissignal — Stakes Quoten
kommen aus einem eingekauften Feed und sind preisseitig gar nicht unabhängig.

**Status: Sammlung, kein Signal.** Für Stake-Einsatzfluss ist im Projekt weder eine Trefferquote
noch ein CLV gemessen. Die Anregung dazu kam mit einer fertigen Bewertungstabelle („4–5 Wetten in
1 Minute 🟢 Strong"), die keine Trefferquote, keinen CLV und kein n nennt — genau die Klasse
Behauptung, die der Checkup vom selben Tag achtmal aus der Übersicht geräumt hat. Sie kommt
deshalb weder in den Sammler noch in den Tab; beide Testdateien prüfen ihre **Abwesenheit**.

Drei Dinge, die die Fläche nicht darf, jeweils mit Test:

| Verbot | Warum |
|---|---|
| unbekannten Einsatz als 0 führen | Wetten laufen in BTC/ETH ohne USD-Kurs im Feed. Unbekannt ≠ klein → `einsatzUsd: null` + sichtbarer Zähler „ohne $-Wert" (*fehlende Information ist keine Erlaubnis*) |
| einen Feed-Fehler als leere Liste zeigen | Stake sitzt hinter Cloudflare. Ein 403 sähe sonst aus wie „heute keine großen Wetten" → `status: fehler/schema_unbekannt` + Grund auf der Fläche |
| Wetten ohne ID mitzählen | ohne ID keine Deduplizierung, und doppelt gezähltes Geld ist schlimmer als eine fehlende Wette → `ohneIdVerworfen` |

**Bekannte Schwäche der Quelle, und sie steht auf der Fläche:** Stake hat eine „Wetten
verbergen"-Einstellung. Wer sie nutzt, taucht nicht auf — die Liste ist **eine Auswahl, keine
Grundgesamtheit**, und die Auswahl geht systematisch in die falsche Richtung (wer verbirgt, hat
meist einen Grund). Deshalb: erst gegen den **Pinnacle-Schlusskurs** messen (CLV, aussagekräftig
ab n≈200, ohne auf Ergebnisse zu warten), dann über ein Vorwärtsbuch reden.

**Woher die Abfrage kommt.** Endpunkt `https://stake.com/_api/graphql`, Feld
`highrollerSportBets`, ohne Anmeldung. Die Abfrage ist am 03.09. aus der Netzwerkanfrage
**mitgelesen**, die Stakes eigene Highroller-Seite stellt — nicht geraten. Introspection ist
dort abgeschaltet (HTTP 400, Apollo) und die „Did you mean"-Vorschläge sind es auch; für den
Tag, an dem Stake umbaut, liegt darunter ein Lernweg, der die Selektion aus den
Validierungsfehlern des Servers rekonstruiert (graphql-js meldet alle Verstöße eines Dokuments
gemeinsam, eine Ebene kostet also eine Anfrage). Reihenfolge: `stake_query.json` → verifizierte
Abfrage → lernen.

**Vier Fallen, alle am echten Feed gefunden, keine davon hätte geknallt:**

| Falle | Was passiert wäre |
|---|---|
| **HTTP 400 ist eine Antwort.** GraphQL beantwortet Validierungsfehler mit 400 *und* gültigem `errors`-Body — genau der ist die Auskunft. `_post` warf ihn wegen des Statuscodes weg | Sonde meldete „Endpunkt antwortet nicht", obwohl der Server präzise geantwortet hatte |
| **Zeitstempel sind RFC-1123** (`Thu, 03 Sep 2026 19:12:06 GMT`), nicht ISO. `fromisoformat` scheitert daran | Eine vollständig gefüllte Sammlung wäre im Dashboard als „keine großen Wetten im Fenster" erschienen — der stillste Fehler des ganzen Features |
| **`limit=51` liefert kommentarlos 0 Einträge** (50 ist der Deckel), ohne Fehler oder Warnung | Ein zu hoch gesetzter Wert hätte den Feed abgewürgt und ausgesehen wie ein ruhiger Tag. Jetzt hart gedeckelt, Env kann ihn nicht überschreiben |
| **Typbewusstsein im Lernweg.** Erkenntnisse wurden global nach Feldnamen angewandt; `amount` gibt es auf `SportBet` und nicht auf `User`, also strich „Cannot query field amount on type User" auch das gültige `amount` an der Wurzel | Der Kandidatenbaum lief Runde für Runde leer. Gefunden hat es ein nachgebauter Apollo-Server im Test, nicht der echte Endpunkt — dort hätte es „findet nichts" geheißen |

**Was der Feed hergibt** — pro Wette: `iid` (die Nummer vom Wettschein), Betrag + Währung,
Gesamtquote, Zeit, und je Bein Quote, **Markt** („Winner"), **Auswahl** („Taylor Fritz"),
Fixture-ID, Anpfiff, Turnier und Sportart. Also mehr als die Website selbst anzeigt.

**Was er nicht hergibt, und das ändert den Plan:** `user` ist bei **jeder** Wette `null` —
Stake anonymisiert die Highroller-Liste vollständig. Ein Track-Record je Konto, wie ihn die
Poly-Wallets tragen, ist hier **unmöglich**. Es bleibt aggregierter Fluss, nie „dieser Spieler
hat schon wieder recht behalten". Das Feld wird trotzdem mitgeführt und die Fläche sagt es
laut, damit niemand später darauf plant.

**Kombis zählen nicht.** Ein 2.000-$-Vierer hängt an vier Spielen und gehört keinem davon.
Kombiwetten bleiben sichtbar (ausgegraut, mit Beinzahl), aber weder ihr Geld noch ihre Seite
geht in die Spielsumme. Gruppiert wird über die Fixture-ID, nicht über den Namen — dasselbe
Paar kann in Liga und Pokal stehen.

---

### 🔴 Live-Plays: die Zahlen müssen aus dem laufenden Spiel kommen (03.09.2026)

Lucas im Trades-Channel: *„8/10 · BET · Hapoel Tel Aviv vs Beitar 🔴 LIVE → Hapoel @48¢ · großes
Geld (74%) → $22K · Steam läuft rein (+6.0pp)"* — gepusht um 19:28, da stand es **3:0 in der 92.
Minute**. Und: *„die 48 Cent gab es ewig zuvor, aber da kam nie ne Push."*

Drei Fehler auf einmal, nachgesehen an den echten Dateien:

| | Was dastand | Was es war |
|---|---|---|
| 1 | „🔴 LIVE → @48¢ · 74% · $22K" | **Vorspiel-Zahlen.** `_pwTopPlays` bewertet `m` aus `broadLive` — dem **Close**-Satz. Für dieses Spiel: `capturedAt 17:27:50`, `hoursToKickoff 0.09`, also fünf Minuten *vor* Anpfiff. `broadLiveNow` wurde nur gefragt, **ob** das Spiel noch läuft, nie **wie es steht**. Die Geldquote beweist es: 3507,9 / 4756,0 = **74%** im Close-Satz, 3692,6 / 5975,5 = **62%** im Live-Satz |
| 2 | Der Live-Satz hätte auch nicht getragen | Er führte `prices {Hapoel 0.5, Draw 0.5, Beitar 0.5}` — drei sich ausschließende Ausgänge, Summe **1,5**. Das ist kein Preis, sondern ein **leeres Orderbuch**, dessen Mittelwert auf 0,5 zurückfällt. Betroffen: **21 von 62 Live-Märkten (34%)** gegenüber 4 von 2002 im Close-Satz (0,2%). Geprüft hat das nie jemand |
| 3 | Kein Halt nach Anpfiff | `PW_STALE_AFTER_KO_H_FOOTBALL = 2.5h` beantwortet *„ist dieser Markt noch echt?"*, nicht *„kann man das noch spielen?"*. In der 92. Minute liegt man mit 1,6h komfortabel darunter |

Punkt 1 und 2 sind Fehler, Punkt 3 ist ein **fehlendes Urteil**. Alle drei sind zu; jeder für sich
hätte diesen Push verhindert.

- **`_pwLiveMerge(close, now)`** — läuft ein Spiel, werden Preis, Geld und Volumen aus dem
  Live-Satz genommen; Stammdaten (Liga, Sport, Anpfiff-Stempel) bleiben aus dem Close-Satz, weil
  der Live-Scan sie nicht immer mitführt. Jeder Play trägt seither `preisQuelle`.
- **`_pwPreisBrauchbar(prices)`** — ≥2 Preise, nicht alle exakt 0,500, Summe innerhalb von 10pp
  um 1. **Beide** Regeln sind nötig: bei zwei Ausgängen summiert sich 0,5/0,5 sauber auf 1,0 und
  käme durch die Summenprüfung glatt durch — und genau das waren die meisten der 21 Fälle.
- **`_pwLiveZuSpaet(m)`** — Fußball 75 Minuten, sonst 2h. Das ist ausdrücklich ein **Urteil, keine
  Messung**: ein Siegermarkt ist nach der regulären Zeit in der Sache entschieden. Die 2,5h daneben
  bleiben, was sie sind — die Frage nach der Echtheit des Marktes, nicht nach der Spielbarkeit.
- Die Push-Zeile nennt jetzt die **Spielminute** („🔴 LIVE · 93. Min") und warnt, wenn ein
  Live-Play seinen Preis doch aus dem Vorspiel-Satz zieht.

Warum es *vorher nie* gepusht wurde, obwohl es die 48¢ „ewig zuvor" gab: `fresh_plays` schickt
einen Play, wenn seine Conviction **steigt**. Sie stieg erst, als das Spiel praktisch vorbei war —
Geldanteil und Steam härten in einem laufenden Markt genau dann aus, wenn der Ausgang feststeht.
Das ist die allgemeine Lehre aus dem Fall und der Grund, live strenger zu gaten als vor Anpfiff:
**die Flusssignale werden am stärksten, wenn sie am wenigsten wert sind.**

---

### 🎰 Stake als vierte Quelle — messbar gemacht (03.09.2026)

Lucas: *„bitte alles umsetzen … anhand der Daten dort kriegen wir genug kleine Ligen, wo Leute
mit guten Infos setzen. Und bei den Mainstream-Ligen kriegen wir für unsere anderen Features
ein weiteres Signal."*

**Der Fund, der alles ändert: die Abrechnung kostet nichts.** `bet(iid:)` liefert zu jeder
gesammelten Wette `status`, `payout` und je Bein `won`/`lost` — geprüft am echten Endpunkt:

```
sport:648199979  settled   payout 0        Beine ["won","lost"]   (2er-Kombi)
sport:648200455  confirmed payout 0        Beine ["pending"]      ← laeuft noch
sport:648200459  settled   payout 2373.5   Beine ["won"]
```

Damit braucht der Stake-Fluss **keine Ergebnis-Pipeline und kein Namens-Matching**: die Wahrheit
kommt aus derselben Quelle wie die Wette. Bei Betfair und Poly müssen wir Ergebnisse selbst
beschaffen und Namen brücken. Bis zu 25 Wetten je Anfrage über GraphQL-Aliase — 300 Wetten
kosten zwölf Anfragen, nicht 300.

`"confirmed"` heißt **angenommen, nicht abgerechnet** und wäre fast durchgerutscht. Die Liste in
`stake_settle.py` führt deshalb das OFFENE auf, nicht das Fertige: ein morgen neu auftauchender
Zwischenzustand gilt als offen und wird weiter nachgefragt, statt stillschweigend als
abgerechnet zu zählen.

**Was gezählt wird — und was nicht.** Messeinheit ist das **Bein** (ein Bein = eine Meinung zu
einem Spiel), nicht die Wette. Trefferquote über alle Beine, Kombi-Beine eingeschlossen; **Geld
und ROI nur über Einzelwetten**, denn bei einer Kombi hängt der Einsatz an mehreren Spielen und
ist keinem davon zurechenbar. Annulliert (`void`/`cancelled`/`push`) ist weder Treffer noch
Fehlschlag und fällt aus der Quote, statt sie nach unten zu ziehen. Wetten, die nach fünf Tagen
noch offen sind, bleiben als `unaufloesbar` sichtbar — eine Wette, die verschwindet, fälscht
jede Quote nach oben.

**Zwei Bücher, nicht eins.** Im ersten echten Ledger waren **77 von 93 Wetten live gesetzt**, nur
16 vor Anpfiff. Das sind verschiedene Dinge: vor Anpfiff ist CLV gegen den Pinnacle-Schlusskurs
möglich, live gibt es keinen Schlusskurs — dort zählt nur die Abrechnung, und die Spielminute,
denn ein Einsatz in der 85. auf den Führenden ist kein Signal (siehe Hapoel-Fall eine Sektion
weiter oben). `phase` und `spielminute` sind seither erstklassige Felder; alte Zeilen werden in
der Auswertung aus `ts` und `anpfiff` nachgerechnet statt als „unbekannt" zu verschwinden.

**„Auffällig" ist relativ, nicht absolut.** Eine feste Schwelle findet keine kleinen Ligen, sie
findet nur große Zahlen — und die stehen fast immer bei La Liga und im US Open. Die Norm je Liga
wird deshalb aus den eigenen Daten gelernt (Median und 90 %-Punkt, ab 15 Wetten), und auffällig
heißt „das x-fache dessen, was hier sonst durchgeht". Aus den ersten 93 Wetten:

| Liga | n | Median | 90 %-Punkt | größter |
|---|---|---|---|---|
| US Open Men Singles | 21 | $2.000 | $10.000 | $17.862 |
| La Liga | 17 | $2.900 | $6.000 | $33.750 |

Ligen unter 15 Wetten bekommen **keine Norm und keinen Faktor** — nicht 1.0, nicht 0. Über sie
ist nichts bekannt, und das ist etwas anderes als ein gemessenes Nein. Für genau sie greift ein
ausdrücklich **schwächeres** zweites Kriterium (kleine Liga + Einsatz über dem globalen
90 %-Punkt), und die beiden Gründe werden auf der Fläche nie vermischt. Der erste Treffer daraus:
**$39.999 auf ein US-Open-Doppel** — die einzige Wette dieser Liga im Ledger.

**Vorwärts angemeldet.** Fünf Schubladen stehen in `stake_vorregistrierung.json`, geschrieben
bevor die Zahlen da waren: `vor_anpfiff_alle` (Ziel n=200), `vor_anpfiff_gross`, `ueber_liga_norm`,
`kleine_liga`, `live_frueh`. Ein Anmeldedatum wandert nicht, ein später angemeldeter Trigger
startet bei n=0.

**Der Sampling-Deckel bleibt das Risiko.** 50 Einträge je Abruf deckten 12 Minuten ab; der
Sammler lief alle 15. Er hängt jetzt an `betfair.yml` (*/10) und **misst seine Lücken**: ist der
älteste Eintrag eines Abrufs jünger als der jüngste des letzten, steht das als `luecke`/`lueckeMin`
im Ledger. Bei Vollprogramm am Wochenende wird auch */10 nicht reichen — dann sagt es das Ledger,
statt dass „an dem Abend war wenig los" unbemerkt „wir haben nicht hingeschaut" bedeutet.

**Terminal** unter „⋯ Mehr → 🎰 Stake Radar": Spiele · Auffällig · Bilanz · Norm. Jede Quote
nennt ihr n und ihre Wilson-Untergrenze; unter n=30 steht „kein Urteil" statt einer Zahl.

**US-Sport gesperrt** (Lucas: *„Ganze US-Sport brauch ich aktuell mal nicht. Ähnlich Poly"*) —
NBA, MLB, NHL, NFL, dazu NCAA/WNBA über dieselbe Kategorie. Gesperrt heißt **ausgeblendet, nicht
ungesammelt**: das ist die schon getroffene Entscheidung aus dem Poly-Fall vom 24.08.
(*„was wenn sie besser werden?"*) — das Mitschreiben ist gratis und die einzige Art, je zu
merken, dass eine Sportart dreht. Deshalb sammelt und **rechnet** der Sammler weiter alles ab,
die Auswertung führt sie in `gesperrteSchubladen`, und der Bilanz-Reiter zeigt sie unter
„ausgeblendet — mitgeschrieben, nicht mitgezählt".

Die Liste steht **einmal** (`GESPERRT` in `stake_highroller_fetch.py`) und reist über
`stake_highroller.json` zum Tab — dieselbe Konstruktion wie `PW_BLOCKED_BET_CATS` im Poly-Tab.
Der Spiele-Reiter zählt sichtbar mit, wie viele Wetten er weglässt; ein stiller Filter wäre
genau die Klasse Fehler, die Abschnitt 7 auflistet. **MLS bleibt Fußball** — sie wird getradet
und darf nicht mit untergehen; ohne Sport-Slug fiel sie erst auf „Sonstige", gefunden vom Test,
nicht im Betrieb.

---

### 📊 Die Liga-Norm muss aus der ZEIT kommen, nicht aus dem Fenster (03.09.2026)

Lucas: *„das heißt wir lernen jetzt auch schon mit, was normale Einsätze für eine Liga sind und
was dann höher ist, je mehr Daten wir sammeln?"* — die Frage hat einen Defekt aufgedeckt, den
niemand gemeldet hätte.

Die Norm wurde bei jedem Lauf frisch aus `stake_bet_ledger.json` gerechnet. Das Ledger ist auf
20.000 Wetten gedeckelt, und gemessen laufen **4,3 Wetten pro Minute** ein — der Deckel reicht
also **rund 3,2 Tage** zurück. Die Norm sah damit immer nur ein rollendes Drei-Tage-Fenster, und
eine Liga, die einmal pro Woche spielt, erreicht darin **nie** die 15 Wetten für eine Norm.
Ausgerechnet die kleinen Ligen — die, um die es überhaupt geht — wären dauerhaft ohne Basis
geblieben und immer auf das schwächere Ersatzkriterium durchgefallen.

Das ist **derselbe Fehler wie im Betfair-Badge am 24.08.**, wo die Basis aus dem Moment statt aus
der Zeit kam und Fulham–Chelsea mit „×80,6 Norm" dastand, obwohl es gegen echte EPL-Spiele bei
×0,6 lag. Die Lehre steht dort im Dateikopf: *„Das Badge war nicht ungenau, es war invertiert."*

`stake_league_norm.py` führt jetzt denselben Bautyp wie `betfair_league_norm_state.json`: einen
wachsenden Stichprobenstand je Liga, dedupliziert über die Wett-ID, je Liga bis 600 Proben und
120 Tage. Kombis und gesperrte Sportarten kommen gar nicht erst hinein. `stake_analyse.py` liest
den Stand nur noch — die Rechnung aus dem Ledger bleibt als Rückfall, mit demselben MIN_N, damit
nichts leiser durchrutscht.

**Antwort auf die Frage, präzise:** ja, und ab jetzt wirklich — die Norm wächst weiter, solange
der Job läuft, statt alle drei Tage zu vergessen.

### 🎰 Stake-Terminal, zweiter Ausbau

| | Warum |
|---|---|
| **×N Norm** auf der Spielkarte | Der **größte einzelne** Einsatz gegen den Median der Liga — nicht die Summe. Zehn Wetten à $2.000 sind ein normaler Abend, **eine** über $30.000 ist das Ereignis |
| **⚔️ umkämpft** | Liegen ≥ 30 % des Geldes auf einer zweiten Seite, ist der Markt uneinig — das ist kein einheitlicher Fluss. Der Poly-Tab unterdrückt solche Fälle seit dem 12.08. im öffentlichen Kanal; hier werden sie wenigstens markiert |
| **Anpfiff / Spielminute** je Karte | „🔴 63. Min" statt eines nackten LIVE — die Lehre aus dem Hapoel-Push, diesmal vorbeugend |
| **„noch spielbar"** als Schalter | Nur was nicht angepfiffen ist oder höchstens 30 Minuten läuft; die weggelassenen werden gezählt |
| **Sortierung × Norm** | Nach Auffälligkeit statt nach Größe — der eigentliche Blick |
| **Lücke in der Kopfzeile** | Stakes 50er-Deckel kann Zeit verschlucken. Das gehört auf die Fläche, nicht nur ins JSON |
| **Karten aufklappbar** | Über sechs Wetten hinaus, ohne Neuladen |

---

### 🎨 Stake grafisch — vier Bilder, jedes mit einer Aufgabe (03.09.2026)

Lucas: *„das Terminal würd ich gern noch so pimpen, dass es grafisch vielleicht mit Graphen
optisch einfach cooler aussieht."* Vier Bilder, und **jedes hat genau eine Serie, also eine
Farbe** — wo nur eine Größe dargestellt wird, ist ein zweiter Farbton kein Informationsgewinn,
sondern ein verbrannter Kanal. Ein Farbverlauf nach Balkenlänge wäre die Länge doppelt kodiert.

| Bild | Aufgabe | Form |
|---|---|---|
| **Geld je Stunde** (Spiele-Reiter) | Verlauf über Zeit | Säulen, 4px runde Datenkante, eckiger Fuß, 2px Lücke |
| **Norm-Streifen** (Auffällig-Reiter) | ein Wert an einer Grenze | Meter mit Median-Marke, log-Skala (Einsätze streuen über Größenordnungen — steht im Tooltip) |
| **Median je Liga** (Norm-Reiter) | Größenvergleich | liegende Balken, heller Teil = 90 %-Punkt |
| **Zeitachse** (aufgeklappte Karte) | wann kam das Geld | Punkte, **Fläche** ~ Einsatz (Radius über die Wurzel, sonst sieht doppelt wie vierfach aus), Anpfiff markiert |

Beschriftet wird sparsam — eine Zahl an jedem Punkt liest niemand; die Tooltips (`<title>` im
SVG, also auch für Screenreader) tragen den Rest.

### 🎰 Drei Stake-Kacheln in der Übersicht

**größtes Geld** · **über der Norm** · **noch spielbar**. Die dritte war Lucas' offene Frage,
und sie ist die wichtigste: die ersten beiden zeigen fast immer Spiele, die schon laufen oder
durch sind — 77 von 93 Wetten im ersten Ledger waren live gesetzt. Eine Übersicht, in der drei
Kacheln dasselbe abgelaufene Spiel zeigen, ist hübsch und nutzlos. Nur die dritte beantwortet
*„und worauf könnte ich jetzt noch schauen?"*.

**Drei Fehler, alle vom Ausprobieren gefunden, keiner vom Nachdenken:**

1. **US-Sport in der Kachel.** „Chicago Cubs – Milwaukee Brewers" stand da, obwohl MLB gesperrt
   ist: Zeilen von vor dem Kategorie-Stempel haben kein `kat`, und der Filter las
   `w.kat || ''`. Behoben mit demselben Rückfall wie im Terminal.
2. **„NCAA, Regular" rutschte durch.** Das Rückfall-Muster suchte `" ncaa "` mit Leerzeichen —
   das Komma ließ es ins Leere laufen, und `american-football` fehlte ganz. Jetzt Wortgrenzen
   (`\b`), und `american[- ]?football` fängt auch „American Football League" mit Leerzeichen.
   Ein Test vergleicht die Muster in Terminal und Übersicht **gegeneinander** statt sie
   nachzubauen — ein Test, der die Regel noch einmal formuliert, prüft nur sich selbst.
3. **Erfüllt ist nicht gemessen.** Der Frische-Guard vom Vormittag hat sofort verlangt, dass die
   neuen Datensätze in `_mdQuellenAlter` stehen — das war richtig und hat gegriffen. Er prüft
   aber nur, ob eine Quelle in der Liste *steht*, nicht ob `_ageMin` sie *lesen* kann. Die
   Stake-Dateien stempeln mit `asof`, das der Leser nicht kannte: Liste erfüllt, Alter immer
   `null`. `asof` ist jetzt drin, und ein zweiter Test prüft, dass jeder benutzte Stempelname
   auch wirklich ein Alter ergibt.

---

### 🎯 Quotenschwelle — messen statt setzen (03.09.2026)

Lucas: *„glaub Odds-Schwelle sollten wir auch bauen … weil @1,03 und 1,2 ist schon relativ low.
Wollen wir die 1,35 wieder als Minimum?"* Anlass war ein Spiel, das mit **$271 K** ganz oben in
der Liste stand: $264 K auf Sakkari **@1,20**.

**Was die Daten sagen** (445 Wetten, US-Sport raus):

| Quotenband | Wetten | Einsatz Σ | möglicher Gewinn Σ |
|---|---|---|---|
| bis 1,20 | 120 | $234.061 | **$27.852** |
| 1,20–1,35 | 26 | $34.863 | $71.200 |
| 1,35–1,60 | 73 | $79.290 | $170.309 |
| 1,60–2,00 | 114 | $208.847 | $353.317 |
| 2,00–3,50 | 83 | $122.854 | $374.002 |
| ab 3,50 | 50 | $40.238 | $245.030 |

**Unter 1,35 liegen 32 % der Wetten und 35 % des Einsatzes — aber nur 3 % des möglichen
Gewinns.** Eine Liste nach Einsatz sortiert also systematisch Favoritenschieber nach oben.

Aber die Umkehrung taugt auch nicht: nach möglichem Gewinn sortiert steht **$3.260 @ 298,98**
an der Spitze — ein Lottoschein. **Keine der beiden Zahlen ersetzt die andere**, deshalb fahren
beide mit (`einsatzUsd` und `gewinnUsd`), und beide sind sortierbar.

**Warum die 1,35 trotzdem nicht als Wahrheit eingebaut ist.** Sie ist im Projekt schon der Boden
(`pick-engine.js`, *Cheap ML filter*) — aber **dort** geht es um unsere eigenen Wetten, wo bei
1,20 die Marge den Wert frisst. **Hier** geht es um die Meinung eines anderen, und ob die bei
1,20 schlechter informiert ist, ist **nicht gemessen**. Also:

- Terminal: Regler `alle · 1,20 · 1,35 · 1,60 · 2,00`, Start bei 1,35, mit sichtbarem Zähler
  („n unter Quote 1,35") — er blendet aus, er urteilt nicht.
- Übersicht: derselbe Boden für die Anzeige. Auf einer Übersicht ist das Rauschen, das die
  echten Kandidaten verdeckt — Sakkari verschwand daraufhin aus der Geld-Kachel.
- Auswertung: **sechs Quotenbänder als eigene Schubladen** plus `quote_ab_135` /
  `quote_unter_135` **vorregistriert**, Ziel n=200 bzw. 150. In ein paar Wochen sagt die
  Abrechnung, wo der Boden hingehört — oder ob es gar keinen braucht.
- Ohne Quote wird **nicht** gefiltert: unbekannt ist nicht dasselbe wie niedrig.

**Nebenbefund aus dem Test.** In der Schublade hießen zwei verschiedene Grundgesamtheiten fast
gleich: `einsatzUsd` zählte nur *abgerechnete* Wetten (für den ROI), `gewinnUsd` *alle*. Der
Test hat es gefunden, bevor irgendwo eine Rendite auf der falschen Basis stand. Jetzt heißen sie
`einsatzUsd`/`gewinnUsd` (alle Einzelwetten) gegen `abgerechnetUsd`/`abgerechnetN`/`roi` (nur
die abgerechneten), und der Bilanz-Reiter schreibt die abgerechnete Zahl neben den ROI.

---

### ⚠️ Eine Trefferquote ohne die Quoten ist keine Zahl (04.09.2026)

Nach 8,7 Stunden Sammeln lagen **1.309 Wetten und 1.026 abgerechnete Beine** vor — die erste
echte Messung. Und sie hat vor allem einen Fehler in **meinem eigenen Urteilskriterium**
aufgedeckt.

`stake_analyse.py` setzte `belegt`, wenn die **Wilson-Untergrenze der Trefferquote über 50 %**
lag. Das ist aus der Poly-Wallet-Logik übernommen, wo Märkte nahe am Münzwurf liegen. Bei
Wetten mit unterschiedlichen Quoten sagt es **gar nichts**:

| Schublade | n | Treffer | Ø-Quote | **Rendite je Bein** | UG (95 %) |
|---|---|---|---|---|---|
| gesamt | 950 | 63,9 % | 1,72 | **−6,8 %** | −11,5 % |
| vor Anpfiff | 139 | 70,5 % | 1,58 | **−4,2 %** | −14,2 % |
| live | 811 | 62,8 % | 1,74 | **−7,2 %** | −12,4 % |
| Einsatz ≥ $10k | 85 | 67,1 % | 1,51 | **−9,6 %** | −22,3 % |
| über 5× Liga-Norm | 72 | — | — | **−4,1 %** | −18,5 % |
| Quote < 1,35 | 273 | 93,0 % | 1,09 | **+0,8 %** | −2,1 % |

**Jede Schublade, die nach dem alten Kriterium „BELEGT" hieß, verlor Geld.** Wer bei Quote 1,20
setzt, braucht 83 % zum Nullpunkt — 70 % Treffer sind dort ein Desaster, nicht ein Erfolg.

Das Urteil hängt seither an der **Rendite-Untergrenze** (`freigabe.untergrenze`, dieselbe
Rechnung wie im Freigabe-Register), nie an der Trefferquote. Die Quote bleibt sichtbar, weil man
sie lesen will — sie entscheidet nur nichts mehr, und sie steht jetzt immer neben der
**Durchschnittsquote**, ohne die sie nicht interpretierbar ist. Der Bilanz-Reiter sagt das auch
laut: *„Eine Trefferquote über 50 % ist hier kein gutes Zeichen."*

**Der Zwischenstand selbst, ehrlich gelesen:** −6,8 % über alles ist ungefähr die Marge des
Buchmachers. Das ist genau das Ergebnis, das man erwartet, wenn im aggregierten Fluss **keine
Information** steckt — die Kunden verlieren den Hold. Keine einzige Teilmenge trägt bisher, auch
nicht die interessanten (über Liga-Norm −4,1 %, kleine Liga −2,1 %, Fußball +4,5 % bei
UG −12,0 %). Alles im Rauschen.

**Was das noch nicht heißt.** 8,7 Stunden, dominiert von US-Open-Tennis (618 von 1.091) und zu
83 % Live. Genau die Teilmengen, um die es geht — kleine Ligen tagsüber, Fußball vor Anpfiff —
haben n=10 bis n=178. Das ist der Grund, warum die Vorregistrierung Ziel-n von 150 bis 200 je
Schublade nennt. Bis dahin ist die richtige Aussage: *noch nichts gefunden*, nicht *nichts da*.

---

### 🐋 Die Public-Pushs — zwei Dinge, die gleich hießen (04.09.2026)

Lucas: *„in diesem Track-Record haben wir ja die Public-Kandidaten … aktuell schicken wir aber
schon Polymarket-Push in den Public-Channel, aber ich weiss nicht wie gut das abschneidet."*

Die Frage ließ sich beantworten, aber erst nachdem klar war, dass sie **zwei verschiedene Dinge**
meint, die bis heute beide „Public" hießen:

| | was es ist | sendet? |
|---|---|---|
| **◆ Public-Kandidaten** (Track-Record) | Shortlist-Plays, die das harte Gate bestehen *würden* | **nein** — reine Vorschau |
| **🐋 Public-Pushs** (`poly_whale_watch.py`) | Whale-Positionen einer Top-10-Wallet | **ja** — das geht raus |

Die 156 abgerechneten Plays mit 70,5 % und +5,1 % ROI im Track-Record beschreiben also eine
**Vorschau, die nie jemand bekommen hat**. Über die echten Pushs sagen sie nichts.

**Das echte Buch** (`poly_public_eval.py` → `poly_public_record.json`, seit 02.09.) steht bei
**n=3 vorwärts**: drei CS2-Märkte einer einzigen Wallet, alle getroffen, +$17,51 auf $30 = ROI
+58,4 %. Dazu 34 rückwirkend rekonstruierte Einträge, von denen **23 nie aufgelöst** wurden und
bei den **11 übrigen der Einstiegspreis fehlt**.

Zwei Korrekturen, beide dieselbe Lehre wie eine Etage höher:

1. **Die Trefferquote urteilte.** Das Buch gab `hit`/`hitUg` aus und daneben einen ROI ohne jede
   Schranke. Der Retro-Block zeigte damit „91 % Treffer (UG 68 %)" — bei elf Zeilen ohne
   Einstiegspreis. Zehn Treffer zu unbekannten Quoten können +40 % oder −40 % sein. Seither
   entscheidet `roiUg` (`freigabe.untergrenze`), und `geldurteil` sagt beim Namen, ob über Geld
   überhaupt geredet werden kann.
2. **Die CLV-Untergrenze war ein Mittelwert mit Etikett.** Sie lief über eine eigene Inline-Formel
   ab n>1 — genau die Krankheit, die `freigabe.untergrenze` am 03.09. behandelt hat. Im
   gespeicherten Record stand `clvUg: -0,65` aus **drei** Werten. Jetzt dieselbe n≥30-Grenze wie
   überall; der Wert ist folgerichtig verschwunden.

**Die ehrliche Antwort auf die Frage:** noch nicht messbar. +58,4 % aus drei Plays ist ein
Punktschätzer. Bei der gemessenen Push-Rate — **37 Pushs in 30 Tagen, gut einer pro Tag** — ist
n=30 in rund vier Wochen erreicht. Vorher gibt es keine Untergrenze, und ohne die kein Urteil.
Der Block steht ab jetzt sichtbar auf dem Track-Record-Reiter, direkt unter den Kandidaten,
damit die Verwechslung nicht wiederkommt.

---

### 💭 „$41K auf Over" — der Push, den niemand nachprüfen konnte (04.09.2026)

Lucas' eigene Zwei-Wochen-Bilanz aus dem Channel: **12 Win, 2 Lost, E-Sport alles Win, 2 Premier
League Lost.** Das Ledger zählt seit 21.08. genau **14 abgerechnete Pushs** — dieselbe Zahl, also
sieht er dasselbe wie das Buch. Aber es zählt **13:1**, nicht 12:2.

Die eine Abweichung ist Leeds–Brentford am 30.08. Der Push lautete:

> 💰 **$41K** auf **Over**

Endstand 1:1. **Over was?** Der Markt war `epl-lee-bre-2026-08-30-more-markets`, ein Totals-Markt
ohne erfasste Linie: bei 1:1 gewinnt Over 1,5 und verliert Over 2,5. Lucas hat ihn als Verlust
gebucht, unsere Auflösung als Treffer — und **keiner von beiden konnte es wissen**. In
`poly_money_broad_close.json` tragen **alle 2.000 Märkte** weder `title` noch `question`; die
Marktfrage wird nie mitgeschrieben. Von 230 `-more-markets`-Einträgen sind **213 Over/Under**.

Ein Tipp, dem der Leser nicht folgen und den er nicht nachprüfen kann, gehört nicht in den
öffentlichen Kanal — und ein Ergebnis, das wir selbst nicht eindeutig zuordnen können, verschmutzt
das Buch. Seither sperrt `_pub_seite_benennbar` generische Ausgänge (Over/Under/Yes/No/Draw) für
Public. Im Trades-Kanal bleiben sie, dort steht der Markt-Link daneben.

**Die Bilanz selbst, ehrlich gelesen.** Der Break-even-Preis ist exakt die Trefferquote: 12 von 14
= 85,7 %, also war es Gewinn, sofern der Ø-Einstieg darunter lag. Das ist er zwangsläufig — seit
22.08. deckelt `PUB_MIN_ODDS = 1,30` jeden Push bei **76,9 ¢**. Selbst am Deckel:

| Trefferbilanz | Ø-Preis 63,8 ¢ (die 3 bekannten) | 70 ¢ | 76,9 ¢ (Deckel) |
|---|---|---|---|
| **12:2** (Lucas — und nach der Korrektur auch das Buch) | +34,3 % | +22,4 % | **+11,5 %** |

Also ja, es hat verdient. Was es **nicht** ist: ein Beleg. Die Trefferquote-Untergrenze steht bei
12/14 auf 64,7 %, eine Rendite-Untergrenze gibt es erst ab n=30, und vor allem stammen die
vierzehn Pushs aus **genau zwei Wallets** — 9 der 10 E-Sport-Treffer von `0x29b5…`, alle vier
übrigen von `0x076d…`. Zwei Wochen messen hier zwei Wallets, nicht ein Verfahren.

---

### 🔴 Wir haben einen Gewinn erfunden (04.09.2026)

Lucas hat nachgeschlagen: *„es war Over 2,5 — weiss ich, weil ich mir den Preis angesehen hab."*

Der Push `💰 $41K auf Over` auf Leeds–Brentford stand als **Treffer** in unserem Buch. Endstand
1:1 sind zwei Tore, der Markt war Over 2,5 — die Wette war **verloren**. Seine 12:2 stimmen,
unsere 13:1 nicht.

**Wie das passieren konnte.** Ein `-more-markets`-Slug ist auf Polymarket kein Markt, sondern ein
**Bündel**: Over/Under auf mehreren Linien, BTTS, Ecken. `poly_resolutions.json` hält je Slug
genau einen Sieger — `{key: "…-more-markets", winner: "Over"}` — und kann die Linien nicht
auseinanderhalten. Bei 1:1 gewinnt Over 1,5 und verliert Over 2,5, und beide heißen „Over". Die
Abrechnung verglich `side == winner`, fand „Over" == „Over" und buchte einen Gewinn.

**Wie weit das reicht.** Im Bestand liegen **3.103 Bündel-Auflösungen, davon 3.029 mit
Over/Under** (1.518 Under, 1.511 Over). Betroffen ist jede Abrechnung, die gegen Slug-Sieger
läuft — und die teuerste ist nicht das Public-Buch, sondern `poly_wallet_track.json`: aus
`wins/n` je Wallet entsteht die Trefferquote, und die entscheidet über `PUB_MIN_TR` /
`PUB_MIN_HITRATE`, **wer überhaupt gepusht werden darf**. Ein erfundener Treffer macht dort eine
Wallet „scharf", die es nicht ist — und die pusht dann weiter. 234 solcher Positionen lagen offen.

**Die Regel** steht jetzt in `poly_slug_urteil.py` und gilt in allen fünf Abrechnungen
(`poly_money_broad`, `poly_shortlist_track`, `poly_direct_bets`, `poly_whale_follow`,
`poly_public_eval`): wo der Sieger-Name die Linie nicht trägt, wird **nicht abgerechnet** — weder
als Treffer noch als Fehlschlag. Der Eintrag bleibt offen und läuft in `unaufloesbar`. Gesperrt
wird, was mehrdeutig ist, nicht was einen bestimmten Slug hat: `…-more-markets → "England"`
bleibt abrechenbar, und „Draw" ist im Moneyline-Markt ein echter Ausgang.

**Zwei Entscheidungen, die begründet sein wollen:**

- *Nachträglich zurücknehmen.* „Einmal abgerechnet bleibt abgerechnet" gilt für ein Ergebnis auf
  tragfähiger Basis. Dieses war nie ableitbar, also wird es zurückgenommen — mechanisch, für
  jeden solchen Eintrag, mit `zurueckgenommen: {war: "win", grund: …}` im Ledger.
- *Den bekannten Verlust behalten.* Ihn nur zu streichen wäre bequemer und **schönt**: ohne ihn
  stünde das Buch bei 12:1 statt 12:2. Er steht deshalb in `poly_public_korrekturen.json` mit
  Herkunft und Begründung. Damit daraus keine Hintertür wird, greift eine Korrektur **nur**, wo
  die Maschine `unaufloesbar` sagt — ein maschinelles Ergebnis kann sie nie überschreiben —, sie
  braucht `quelle` und `warum`, und der Report zählt sie getrennt (`korrigiert`).

**Und dann die Anschlussfrage** (*„aber kriegt man jetzt over Märkte richtig?"*) — berechtigt, denn
bis hierhin war nur das Lügen abgestellt, nicht das Auflösen repariert.

Die eigentliche Ursache saß eine Ebene tiefer: `_outcomes` wählt aus einem Event den Markt mit dem
**meisten Volumen**, und `over/under` fällt in `_MAP_PROP_RE` — bei einem reinen Totals-Bündel ist
die Vorauswahl also leer und es entscheidet allein das Volumen. Volumen verschiebt sich zwischen
Anpfiff und Abrechnung, **also konnte die Auflösung einen anderen Markt lesen als die Erfassung.**
Welchen, stand nirgends: `poly_money_broad_close.json` trug bei allen 2.000 Märkten weder `title`
noch `question`, obwohl Gamma beides mitliefert und `_is_map_prop` die Frage sogar schon liest.

Seit heute wird beides mitgeschrieben:

- **`cond`** (conditionId) nagelt den Markt fest. Der Backfill löst nach der *gespeicherten*
  conditionId auf statt nach „was heute das meiste Volumen hat" — damit lesen Erfassung und
  Abrechnung denselben Markt, und `aufloesbar(..., cond=…)` gibt Bündel wieder frei.
- **`frage`** nennt die Linie. Der Push zeigt jetzt `💰 $41K auf Over 2.5 goals` statt `auf Over`,
  und `_pub_seite_benennbar` lässt generische Ausgänge wieder durch — **sobald** die Frage da ist.
  Fehlt sie, bleibt der Push gesperrt.

Alteinträge ohne conditionId werden **nicht** rückwirkend freigegeben: dort ist der Markt nicht
rekonstruierbar, und „wird schon gepasst haben" wäre derselbe Fehler noch einmal. Sie bleiben
`unaufloesbar`. Ab jetzt aufgenommene Over-Märkte rechnen korrekt ab.

---

### 🃏 WM-Gruppenlogik auf Liga-Tabellen (04.09.2026)

Lucas' Cards-Check förderte drei Defekte zutage, die alle dieselbe Form haben: **die Begründung
sagte etwas anderes als die Daten.**

**1. „Beide ausgeschieden" am 3. Spieltag.** Auf den Liga-Cards stand als Pick-Begründung:

> ❌ **Beide ausgeschieden** — Friendly-Charakter, beide ohne Druck. *(Ipswich–Liverpool, PL ST 3)*
> **Real Betis braucht zwingend Sieg + Schützenhilfe**, Real Madrid bereits sicher. *(La Liga ST 4)*
> 🔥 **Aufstiegs-Druck** *(PSG–Monaco, Ligue 1 ST 3)*

Die Ursache ist eine WM-Gruppenregel auf einer Liga-Tabelle:

```js
const hSafe = hPos <= 2, hOut = hPos > 3;
```

In einer Vierergruppe heißt das „durch" und „raus". In `standings['ESP']` stehen aber **20 Teams**
(ENG 20, GER 18) — dort ist ab Platz 4 jeder „ausgeschieden" und auf Platz 1–2 jeder „bereits
sicher". Praktisch jede Liga-Card ab ST 3 trug damit einen frei erfundenen Tabellen-Kontext, an
**drei** Stellen (Kopfzeilen-Kategorie, Begründungstext, Szenario-Satz). Das ist nicht kosmetisch:
bei Ipswich–Liverpool stützte „beide ohne Druck" einen Über-2.5-Pick. `_istGruppentabelle` (≤ 4
Zeilen) schaltet die Gruppenlogik jetzt scharf; wo es keine Gruppe gibt, wird kein Ersatz-Kontext
erzählt, sondern gar keiner.

**2. Der H2H-Satz stimmte nie zu — er stimmte immer zu.** Auf der Venezia-Card:

> ⚔️ Aus den letzten 4 Duellen: im Schnitt **1.2 Tore** (Linie 2.5) · in **25 %** fielen über 2.5
> Tore → **spricht für Über 2.5.**   — daneben der Wert **−3,5pp**

Die Zahlen waren richtig, der Satz sagte das Gegenteil. `side_str` kam aus der *Pick*-Richtung,
nicht aus dem Vorzeichen des Scores, also war der Schluss-Satz unabhängig vom Ergebnis immer
zustimmend (gleiche Krankheit im BTTS-Zweig: „passt zu"). Wer nur die Begründung liest — und
dafür ist sie da — bekam ein Argument **für** den Pick, wo das Signal dagegen sprach.

**3. Serien aus der falschen Hälfte.** Auf Werder Bremen (Heim) v RB Leipzig (Auswärts):

> RB Leipzig · 🔥 Ungeschlagen **HEIM** 6× · Werder Bremen · 🚩 Über 9,5 Ecken **AUSWÄRTS** 5×

Beide Zeilen beschrieben die jeweils andere Hälfte — in `liga_streaks.json` hat Werder
ausschließlich Auswärts-Serien, Leipzig fast nur Heim-Serien. Die Präferenz war richtig gedacht,
schloss den falschen Fall aber nie aus: `score = 2 / 1 / 0`, und die 0 gewann gegen den Startwert
−1. Das betraf nicht nur die Box „Serien in diesem Spiel", sondern auch
`streak_momentum._pick_team_streak` — also das **Signal, das in die Pick-Bewertung eingeht**.

**4. Das Kachel-Gitter log nicht, aber es lud zum Fehlschluss ein.** Auf der Elche-Card standen
sechs Kacheln (−6,8 · +2,1 · −1,0 · +1,3 · +1,1 · +1,6) und **gar kein Netto**. Drei Dinge liefen
zusammen:

- Das Netto war **versteckt**, weil `|+0,17| < 0,5` als „nicht nennenswert" galt. Damit fehlte der
  einzige Anker, und die Kacheln wirkten wie das ganze Ergebnis.
- Die Kacheln **summieren nicht** auf das Netto und sollen es auch nicht: `combined_score_pp` ist
  ein nach Konfidenz und Gewicht **gemittelter** Wert, die Kacheln zeigen rohe Scores. Sichtbar
  ergibt Elche −0,44, das Netto +0,17. Beides richtig — nebeneinander ohne Erklärung sieht es nach
  Rechenfehler aus.
- `slice(0, 6)` schnitt in **Registry-Reihenfolge** ab, ohne Hinweis. Auf Elche fiel
  `move_following +1,2` heraus — nicht weil es klein war, sondern weil es hinten stand.

Seither: Netto immer sichtbar (auch nahe null, mit eigenem ruhigen Ton), als „Ø gew." benannt statt
als Summe (der Titel nennt die Kachel-Summe zum Vergleich), Sortierung nach Betrag statt nach
Registry, und Abgeschnittenes steht als „+N weitere" mit Namen und Werten im Titel.

---

### 🔥 Serien: Länge war der falsche Maßstab (04.09.2026)

Lucas: *„sind die Serien wirklich optimal dargestellt, oder kann man da was verbessern, um sie
schlauer und wichtiger zu machen?"* — Gemessen über 733 aktive Serien: drei Sachen, und die
erste erklärt fast alles.

**1. Länge ist über Märkte hinweg nicht vergleichbar.** Die Liga-Grundraten liegen weit
auseinander:

| Markt | Liga-Grundrate | 5er-Serie rein zufällig |
|---|---|---|
| Team trifft | 81 % | 35 % |
| Über 2,5 | 61 % | 8 % |
| Ungeschlagen | 69 % | 16 % |
| Sieg-Serie | 47 % | 2,3 % |
| Zu null | 28 % | 0,17 % |

Das Board sortierte nach **Länge**. Folge: **17 der Top-25 waren „Team trifft"** — der
häufigste Markt im Angebot —, während Inters 15er-Ungeschlagen-Serie *unter* sechs „Team trifft
15×"-Einträgen stand und Barcelonas 8er-Siegesserie gar nicht vorkam. Jede Serie trägt jetzt
ihre **Zufallswahrscheinlichkeit** (`zufallPct` = p^Länge gegen die Liga-Grundrate des Marktes),
und danach wird sortiert. Die neue Spitze: Parma 9× Unter 2,5 (1 zu 4.613), Colorado 5× Zu null
(1 zu 3.702) — beide vorher unsichtbar.

**2. Die grüne Plakette urteilte über sich selbst.** Füllt eine Serie das 15-Spiele-Formfenster,
war die „Eigentendenz" die Serie selbst — 100 %. Der Kommentar über `_pre_streak_rate` warnt seit
dem 08.08. wörtlich vor der *„tautologischen 100 %"*, und der Fallback tat es trotzdem:

> **457 von 733** Serien ohne unabhängige Basis · **345** davon als „intakt" ausgewiesen ·
> **alle 25** der Top-25 nach Länge urteilten über sich selbst.

*„Bournemouth Team trifft 15× — Eigen 100 % + Gegner 87 % → 95 % → Serie intakt"*: die 100 % sind
kein Beleg, sie **sind** die Serie. Jetzt tritt an die Stelle die Liga-Grundrate des Marktes
(`basis: "liga"`) — eine unabhängige Zahl —, und der Balken heißt dort auch „Liga" statt „Eigen".
`basis: "pure"` gibt es nicht mehr.

**Das wirkte bis ins Signal.** `streak_momentum` las dieselbe Rate als Stärke: **307 von 466**
Serien, die das Signal-Gate passierten, taten das mit einer tautologischen 100 %-Rate — allein
141-mal „Team trifft". Die Liga-Rate darf aber nicht durch dasselbe Gate (`min_rate_pct = 55` ist
für eine *Team*-Rate gedacht; auf eine Liga-Norm angewandt fielen Zu null 28 %, Unter 2,5 39 % und
Sieg-Serie 47 % komplett heraus — die aussagekräftigsten Märkte). Deshalb zwei Wege: mit
Team-Vorgeschichte wie bisher, ohne sie speist sich die Stärke aus der **Seltenheit** des Laufs
und ist auf 0,6 gedeckelt — „ungewöhnlich für den Markt" ist schwächeres Wissen als „typisch für
dieses Team".

**3. Gleich lange Sieg- und Ungeschlagen-Serien sind dieselben Spiele.** Bei **8 von 14** Teams
mit Siegesserie war die Ungeschlagen-Serie exakt gleich lang (Bayern 7/7, Freiburg 7/7, Arsenal
3/3, Barcelona 5/5 …) — zwei Einträge, eine Nachricht. Juventus trug fünf Serien über drei Spiele.
`impliziertVon` markiert das jetzt (auch Zu null → „beide treffen — Nein"); längere
Ungeschlagen-Serien bleiben eigenständig, weil die Remis-Spiele echte Zusatzinfo sind.

**Was ausdrücklich NICHT passiert ist:** die Seltenheit ist kein Signal und keine Wettempfehlung.
Eine seltene Serie ist nur die, über die zu reden lohnt — die Gambler's-Fallacy-Warnung im Kopf
von `compute_streaks.py` gilt unverändert.

---

### 🪞 Warum die Übersicht immer wieder Fehler hat (04.09.2026)

Lucas: *„Bin gespannt, wann wir die Übersicht mal fehlerfrei haben."* — Die drei Funde des Tages
waren nicht drei Zufälle, sondern dreimal dieselbe Bauart, und **zwei davon waren Korrekturen,
die am selben Tag woanders schon gemacht waren**:

| Fund | woanders korrigiert | in der Übersicht |
|---|---|---|
| Serien nach Länge statt Seltenheit | morgens, `compute_streaks.py` + Serien-Tab | eigene `allStreaks()` — nicht mitgekommen |
| „Poly Public" = Vorschau, sendet nicht | morgens, Track-Record | eigene Kachel — hieß weiter so |
| `basis === 'pure'` | Wert existiert nicht mehr | toter Zweig, wählte still das falsche Label |

**Die Ursache ist strukturell, nicht schlampig.** Die Übersicht fasst elf Engines zusammen und
**baut deren Logik nach, statt sie zu lesen**: eigene Serien-Sortierung, eigene
Betfair-Schwellen (`MD_BFTR_*`), eigene Sportart-Zuordnung, eigene Kachel-Texte. Jede Korrektur
anderswo muss von Hand gespiegelt werden. `main-dashboard.js` trägt inzwischen **73 Kommentare,
die einen früheren Fehler dokumentieren** — die Datei wird ständig repariert und produziert
trotzdem weiter dieselbe Fehlerklasse.

Dazu kommt die zweite Bauart: **fest getippte Sätze, die eine Zahl behaupten.** „keine Schublade
hat ihre Untergrenze über null", „Grundrate X %", „Poly Public" — zum Schreibzeitpunkt richtig,
danach still veraltet.

**Was dagegen gebaut wurde** (`tests/frontend/vertrag-produzent-uebersicht.test.mjs`): kein
Frontend darf auf einen Feldwert prüfen, den sein Produzent nicht (mehr) erzeugen kann. Das hätte
`basis === 'pure'` sofort gefangen — gegengeprüft: baut man den toten Zweig ein, schlägt der Test
mit *„main-dashboard.js prüft auf basis === 'pure', aber compute_streaks.py kann nur
prior/liga/unbelegt schreiben — toter Zweig"* an. Dazu Tests, die Übersicht und Serien-Tab an
dasselbe Sortierkriterium binden und die alten Behauptungs-Sätze verbieten.

Vorbild ist der bestehende Test *„die Schwellen stehen an drei Stellen — und überall gleich"*
(`uebersicht-bftrack.test.mjs`) — der hat heute funktioniert: er hat angeschlagen, als die
Betfair-Schwellen auf die Untergrenze umgestellt wurden. Genau diese Idee gehört auf jedes
Duplikat ausgeweitet.

**Ehrlich zur Ausgangsfrage:** „fehlerfrei" wird die Übersicht nicht, solange sie elf Engines
zusammenfasst — jede Engine-Änderung kann dort einen Satz falsch machen. Was schließbar ist, ist
die *Klasse*: dass eine Korrektur woanders hier nicht ankommt. Der richtige Weg ist weniger
Nachbau (die Übersicht sollte lesen, was der Produzent entschieden hat) und für jedes verbleibende
Duplikat ein Test, der bei Divergenz anschlägt.

---

### 🧭 Übersicht-Check: drei Sätze, die etwas anderes sagten als die Zahlen (04.09.2026)

**1. Die Serien-Kachel sortierte weiter nach Länge.** Der Serien-Umbau vom selben Tag
(`zufallPct` statt Länge) lief an der Übersicht vorbei — sie hat ihre eigene Sortierung. Das
Ergebnis stand fünfmal untereinander:

> 🇺🇸 Chicago Fire · Team trifft · **15×** · Grundrate 82 % · 🇺🇸 Inter Miami · Team trifft ·
> **15×** · Grundrate 82 % · 🏴 Bournemouth · Team trifft · **15×** · Grundrate 81 % …

Die Kachel schrieb die Grundrate selbst dazu **und rankte trotzdem danach, dass sie hoch ist.**
Jetzt sortiert sie nach Seltenheit wie der Serien-Tab, blendet logisch eingeschlossene Serien aus
und sagt beim Label, woher die Rate kommt („Liga-Schnitt 82 %" vs. „vorher 40 %") — vorher hieß
beides „Grundrate".

**2. Ebene 1 nannte den falschen Blocker.** Der Text lautete pauschal *„keine Schublade hat ihre
Untergrenze über null"*. An dem Tag stimmte das nicht:

| Schublade | n | ROI | ROI-UG | CLV-UG |
|---|---|---|---|---|
| **Liga · ABWÄGEN** | 46 | +24,4 % | **+3,7 %** | −2,16 |

Die Rendite-Untergrenze lag sehr wohl über null — gescheitert ist die Schublade an der
**CLV-Bedingung**. Wer nur den Satz liest, hält die Renditen für chancenlos, obwohl eine Hürde
genommen war und eine andere blockierte. Der Grund wird jetzt aus den Zahlen bestimmt.

Dabei fiel ein zweites auf: **7 der 18 reifen Schubladen tragen gar keinen CLV-Wert** — darunter
Over/Under 2.5 (n=1668) und Match Odds (n=1654). „CLV-UG ≥ 0" ist mit einem fehlenden Wert nie
erfüllbar; die sind **strukturell nicht freigebbar**, egal wie gut ihr ROI wird. Das steht jetzt
dabei, statt als „noch nicht so weit" durchzugehen.

**3. „🎮 Poly Public n155 · 70 % · +5,0 %" war die Vorschau, die nichts sendet.** Genau die
Verwechslung, die Lucas am Morgen im Track-Record gemeldet hatte — hier stand sie noch, und zwar
ganz oben im Puls, wo sie sich wie die Bilanz des öffentlichen Kanals liest. Die Kachel las
`agg.public` aus dem Shortlist-Track; `poly-wallets.js` sagt an derselben Stelle selbst *„NUR
Vorschau (sendet nicht)"*. Das echte Push-Buch stand bei **n=3**. Die Kachel heißt jetzt
„Poly-Kandidaten · Vorschau, sendet nicht" und trägt die Zahl der wirklich gesendeten Pushs als
eigenes Feld daneben; `sendet: False` ist im Producer hart verdrahtet.

---

### 🧭 Das Lern-Gedächtnis war 18 Tage lang (04.09.2026)

Lucas: *„der Bereich wo quasi gelernt wird steht immer noch mit 500 Plays — ist das eh kein hard
cap sondern lernt weiter auch wenn 500 erreicht?"*

Es lernt weiter, aber nur aus den letzten `SETTLED_KEEP` Plays (`settled[-KEEP:]`). Und 500 war
ein engeres Fenster, als die Zahl aussehen lässt: bei gemessenen **27 abgerechneten Plays pro
Tag** waren das genau **18,4 Tage** (16.08. – 04.09.).

Für die häufigen Signal-Mixe ist das folgenlos — `money+sharp` (197), `money+steam` (91),
`bf+money` (78) und `sharp` (65) sättigen das Vertrauensgewicht `n/(n+25)` ohnehin. Das Problem
sind die **seltenen**:

| Mix | n | Rate | 16 Roh-Plays bräuchten | Fenster |
|---|---|---|---|---|
| `bf+money+sharp` | 12 | 0,65/Tag | **25 Tage** | 18 |
| `sharp+steam` | 11 | 0,60/Tag | **27 Tage** | 18 |
| `steam` | 13 | 0,71/Tag | **23 Tage** | 18 |

Sie sammeln langsamer, als das Fenster sie verdrängt — ein **Gleichgewicht knapp unter der
Schwelle**, dauerhaft. Ausgerechnet `bf+money+sharp` stand dabei mit **+77,1 % ROI** als beste
Zeile auf dem Lern-Board und hätte nie bestätigt werden können.

**Das ist dieselbe Bauform wie der Register-Fund vom 01.09.** Dort stand es schon im Code:
*„die stärkste Schublade (Conviction 9, n=12, ROI +16 %) … konnte n=30 nie erreichen und
schrumpfte stattdessen aus dem rollierenden Fenster heraus."* Das Register bekam damals den Fix,
das Lern-Board nicht.

`SETTLED_KEEP = 2000` (≈ 75 Tage), über `SHORTLIST_SETTLED_KEEP` überschreibbar. Datei ~266 KB →
~1 MB, gegen 122 MB Artefakt vernachlässigbar. **Kein Risiko für die Freigabe:**
`freigabe.poly_schubladen` urteilt ohnehin nur auf der aktuellen Engine und führt Alt-Plays
getrennt als Kontext; der Kalibrierer gewichtet sie halb (`PW_CALIB_LEGACY_W`). Beides hängt an
der Engine-Version, nicht am Alter — mehr Historie verwässert also nichts, sie macht die
seltenen Mixe nur erreichbar.

Ein Test hält die Regel fest: das Gedächtnis muss länger sein als die langsamste Kombination
braucht, sonst steht sie für immer bei n<8.

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
