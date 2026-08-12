# THRESHOLDS — alle Stellschrauben an einem Ort

*Stand 12.08.2026. Zentrale Übersicht aller Signal-/Geld-/Preis-/Fenster-Schwellen.*

**Wie ändern:**
- **Backend (`.py`)** — Konstante in der genannten Datei anpassen **oder** die `env`-Variable setzen (wo vorhanden; die läuft über den Runner/Workflow). Greift beim nächsten Runner-Lauf.
- **Frontend (`.js`)** — Konstante in der Datei ändern **und** `sw.js`-Version bumpen (sonst zieht der Browser die alte Fassung aus dem Cache).
- Werte mit **env** lassen sich ohne Code-Änderung im Workflow überschreiben; ohne env muss die Konstante editiert werden.

---

## Betfair — Push/Alerts (`betfair_alerts.py`)

| Konstante | Wert | Zweck |
|---|---|---|
| `HT_TOP_EUR` | 10.000 € | Halbzeit-Geld-Schwelle Top-Liga + International |
| `HT_REST_EUR` | 5.000 € | … Rest-Ligen |
| `HT_MIN_SHARE` | 0.85 | … davon min. Anteil auf EINEN Ausgang (einseitig) |
| `MIN_LEAD_ODD` | 1.30 | Geld auf Favorit < 1.30 (führt schon) = kein Push |
| `FRESH_TOP_EUR` | 30.000 € | frisches Geld Top-Liga |
| `FRESH_REST_EUR` | 20.000 € | … Rest-Ligen |
| `PUB_HT_TOP` / `PUB_HT_REST` | 50.000 / 15.000 € | Public-Channel: HT-Geld Top / Rest |
| `PUB_FRESH_TOP` / `PUB_FRESH_REST` | 100.000 / 30.000 € | Public: frisches Geld Top / Rest |
| `PUB_FRESH_MIN_SHARE` | 0.80 | Public: min. Anteil auf eine Seite (verschärft von 0.70) |
| `JUMP_REL` | 0.40 | Quote-Sprung zwischen zwei Snapshots = verdächtig (Viking-Fall) |
| `LEAD_PUSH_FACTOR` | 1.75 | „Team führt"-Geld an starken Spieltagen anheben |
| `DEDUP_FACTOR` | 1.5 | erneuter Push erst ab so viel mehr Geld |

## Betfair — Track/Consensus (Backend)

| Konstante | Datei | Wert | Zweck |
|---|---|---|---|
| `CONC_THRESHOLD` | betfair_track_record.py | 0.65 | Geld-Favorit gilt als „konzentriert" ab Marktanteil |
| `INFLOW_MIN_EUR` | betfair_track_record.py | 2.000 € | „frischer Zufluss" ab so viel € Delta |
| `RESULTS_MIN_H` | betfair_track_record.py | 3.0 h | Anpfiff so lange her → autoritatives /results abfragbar |
| `CORRECTION_WINDOW_H` | betfair_track_record.py | 30 h | so lange nach Settle darf /results eine Zeile noch korrigieren |
| `VANISH_MIN_MINUTE` / `VANISH_GRACE_MIN` | betfair_track_record.py | 85' / 25' | „verschwundenes" Spiel erst abrechnen wenn spät gesehen + lange weg |
| `PENDING_TTL_H` | betfair_track_record.py | 60 h | pending ohne Settlement nach so vielen h verwerfen |
| `MATCH_MIN` | betfair_consensus.py | 0.60 | Namens-Match-Schwelle (beide Teams müssen Token teilen) |
| `MM_RESULTS_MIN_H` | betfair_consensus.py | 3.0 h | Money-Map: Anpfiff so lange her → abrechenbar |
| `PENDING_TTL_H` | betfair_public_eval.py | 72 h | nie „finished" gesehen → nach 3 Tagen verwerfen |
| `NOTABLE_SHARE` / `NOTABLE_INFLOW_EUR` | betfair_draw_tracker.py | 0.33 / 3.000 € | Draw-Tracker: X hat viel Anteil ODER frisches Geld |

## Betfair — Radar-Frontend (`betfair-radar.js`)

| Konstante | Wert | Zweck |
|---|---|---|
| `CHIP_FLOOR` | 500 € | Einzel-Ausgänge im Kartendetail erst ab so viel |
| `HOTSPOT_MIN_EUR` | 2.000 € | „größte Einzel-Ausgänge"-Block: Krümel raus |
| `FLOW_MIN_EUR` | 2.000 € | €-Zufluss erst ab so viel zeigen |
| `NORM_AMBER` / `NORM_RED` | ×1.6 / ×2.6 | „über Norm" auffällig / stark |
| `NORM_MIN_PEERS` / `NORM_MIN_EUR` | 4 / 3.000 € | Norm nur mit genug Vergleichsmärkten + Mindestgeld |

## Übersicht-Frontend (`main-dashboard.js`)

| Konstante | Wert | Zweck |
|---|---|---|
| `MD_WHALE_MIN_USD` | 10.000 $ | Poly-Whale-Kachel: erst ab so viel zählt es als Whale |
| `_HT_FLOOR` | 1.000 € | Betfair-HT-Kachel: Mindest-Geld |
| `_HT_MIN_ODD` / `_HT_MAX_ODD` | 1.30 / 6.0 | HT-Quasi-Lock (<1.30) bzw. fast toter Ausgang (>6) raus |

---

## Poly — Erfassung (`poly_money_broad.py`)

| Konstante | Wert | env | Zweck |
|---|---|---|---|
| `MIN_VOL_USD` | 7.500 $ | `POLY_MIN_VOL_USD` | Markt erst ab so viel Volumen erfassen |
| `MIN_ODDS` | 1.35 | `POLY_MIN_ODDS` | triviale Favoriten (≤1.35) raus |
| `MAX_HOLDER_CALLS` | 90 | — | Deckel Geld-Split-Calls (Pre), nach Volumen priorisiert |
| `MAX_HOLDER_CALLS_LIVE` | 40 | `POLY_MAX_HOLDER_CALLS_LIVE` | eigener Live-Deckel (additiv) |
| `CAPTURE_WINDOW_H` | 3.0 h | — | Geld-Verteilung nur so nah am Anpfiff einfrieren (Close-Freeze) |
| `LIVE_TAIL_H` | 3.0 h | `POLY_LIVE_TAIL_H` | so lange NACH Anpfiff weiter live erfassen |
| `LIVE_KEEP_H` | 6.0 h | `POLY_LIVE_KEEP_H` | Live-Eintrag prunen, wenn X h nicht mehr gesehen |
| `UPCOMING_WINDOW_H` | 48.0 h | `POLY_UPCOMING_WINDOW_H` | Money-Map: Sport-Märkte bis so weit vor Anpfiff (nur Preis+Vol, kein Holder-Call) |
| `WHALES_PER_MARKET` | 4 | — | Top-N einzelne Wale je Markt mitschreiben |
| `SWEEP_PAGES` | 5 | — | bis 500 Events je Richtung im tag-losen Volumen-Sweep |
| `GHOST_GRACE_H` | 6 h | `POLY_KICKOFF_GRACE_H` | unaufgelöste Märkte nach so vielen h nach Anpfiff prunen |

## Poly — Live-Einstiegs-Alerts (`poly_live_watch.py`, Trades-Channel)

| Konstante | Wert | env | Zweck |
|---|---|---|---|
| `LIVE_BIG_USD` | 25.000 $ | `POLY_LIVE_BIG_USD` | groß genug für Alarm auch OHNE Track-Record |
| `SHARP_MIN_USD` | 5.000 $ | `POLY_LIVE_SHARP_MIN_USD` | auch scharfe Wallet braucht Mindest-Summe ($370 ist kein Signal) |
| `LIVE_MAX_PRICE` | 0.90 | `POLY_LIVE_MAX_PRICE` | ≥ entschieden → Settlement, kein Signal (@100 = durch) |
| `LIVE_MIN_PRICE` | 0.10 | `POLY_LIVE_MIN_PRICE` | ≤ toter Ausgang → Lay/Rausch |
| `SEEN_TTL_H` | 12 h | `POLY_LIVE_SEEN_TTL_H` | gemeldete Wallet+Markt so lange nicht erneut alarmieren |

## Poly — Sharp-Definition (`poly_money_broad.py` + `poly-wallets.js`, müssen konsistent bleiben)

| Konstante | Wert | Zweck |
|---|---|---|
| `PW_SHARP_MIN_N` | 4 | Mindest-Historie (Wetten), bevor eine Wallet als „scharf" gelten kann |
| `PW_SHARP_MIN_HIT` | 0.50 | Treffer-Floor (beide Achsen müssen stimmen) |
| `PW_SHARP_CLEAR_HIT` | 0.55 | ab hier klar über Zufall → zählt allein |
| `PW_SHARP_STRONG_CLV` | 1.0 pp | bei marginalem Treffer (0.50–0.55) nur scharf, wenn Linie deutlich geschlagen |
| `PW_SHARP_MIN_USD` | 250 $ | $2–6-Positionen sind kein Signal (Wallet-Listen) |
| `SHARP_MIN_CLV` / `SHARP_MIN_HIT` | 1.5 pp / 0.5 | Backend-Pendant in poly_money_broad.py |

## Poly — Frontend (`poly-wallets.js`)

| Konstante | Wert | Zweck |
|---|---|---|
| `PW_MONEY_MAJ` | 0.60 | „großes Geld" erst ab echter Mehrheit (50–55% = Münzwurf) |
| `PW_LIVE_WHALE_MIN_USD` | 10.000 $ | **Übersicht Top-5 Live-Whales**: Mindest-Summe (kein $475) |
| `PW_LIVE_INFLOW_MIN_USD` | 10.000 $ | **Übersicht Top-5 Live-Zufluss**: Mindest-Zufluss (kein +$472) |
| `PW_LIVE_DECIDED_PRICE` | 0.95 | Live-Markt entschieden (Fav ≥95¢) → raus aus Live-Listen |
| `PW_STALE_AFTER_KO_H` | 4 h | >4h nach rekonstruiertem Anpfiff = Spiel fertig → raus |
| `PW_NEW_MIN_USD` | 5.000 $ | „Neu"-Einstiege: Dust/Mini-Positionen raus |
| `PW_WHALE_PUB_UNTRACKED` / `PW_WHALE_PUB_TRACKED` | 100.000 / 25.000 $ | Whale-Public-Vorschau-Schwellen (untracked/tracked Wallet) |
| `PW_EDGE_HORIZON_H` | 96 h | Edge-Board zeigt Spiele bis ~4 Tage voraus |
| `PW_ADVERSE_WARN_PP` / `PW_ADVERSE_KILL_PP` | 6 / 12 pp | Play-Umkehr: ab so viel pp Rückfall vom Hoch warnen / killen |

---

## Häufig getunt (Kurz-Index)

- **Live-Whale/Zufluss zu klein?** → `PW_LIVE_WHALE_MIN_USD`, `PW_LIVE_INFLOW_MIN_USD` (poly-wallets.js) + sw.js bumpen.
- **Live-Alerts zu klein/laut?** → `SHARP_MIN_USD`, `LIVE_BIG_USD` (poly_live_watch.py / env).
- **@100¢-Leichen in Live-Listen?** → `PW_LIVE_DECIDED_PRICE` (Frontend), `LIVE_MAX_PRICE` (Alerts).
- **Betfair-Push zu laut?** → `FRESH_*`, `HT_*`, `PUB_*`, `MIN_LEAD_ODD` (betfair_alerts.py).
- **Money-Map zeigt Poly zu spät?** → `UPCOMING_WINDOW_H` (poly_money_broad.py / env).
