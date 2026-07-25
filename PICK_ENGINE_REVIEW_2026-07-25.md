# Pick-Engine & Card-Review — 25.07.2026

**Auftrag (Lucas):** Card-Generierung (Top-5 + MLS), Signale, ungenutztes Potenzial, und vor allem — ist die Pick-Engine wirklich richtig gebaut?

**Methode:** 3 parallele Review-Agenten über den Kern (`steam_engine.py`, `generate_wm_picks.py`, `conviction_score.py`, `pick-engine.js`, `pick-verdict.js`, `wm2026-renderer.js`, Signale, Fetcher), danach habe ich **jeden schweren Fund selbst am echten Repo gegengeprüft**. Nur Verifiziertes steht hier als Fakt; Unsicheres ist markiert.

---

## Gesamturteil

**Die Engine ist im Kern solide.** Verifiziert sauber: das Poisson-/Asian-Fair-Modell (`pick-engine.js`, inkl. korrekter Viertel-Ball-Behandlung), die de-viggte 1X2/DC-Ableitung, `computeVerdict`-Schwellen, die Anti-Korrelations-Familien, und — wichtig — die `generate_liga/mls_picks`-Wrapper setzen Dataset+Profil korrekt **vor** dem Import (keine `is_liga()`-Falle dort). Kein katastrophaler Bug.

Die echten Themen sind drei: **(1)** ein systematischer, kleiner De-Vig-Fehler in der Edge-Rechnung, der dem eigenen Docstring widerspricht; **(2)** ganze Märkte sind „an", werden aber strukturell nie mit Daten gefüttert (BTTS, Ecken, Karten, O/U-Leiter); **(3)** viel gesammelte Data fließt nie in die Picks (Heim/Auswärts-Split, Sequenz-Raten, Schuss-Qualität).

---

## A. Korrektheit (verifiziert)

### A1 — 🟠 Markt-De-Vig `× 1.03` ist unbegründet; bricht das eigene „AH-Edge ~0"-Versprechen
`generate_wm_picks.py:514` und `:882`:
```python
market_prob = (1.0 / market_odds) * 1.03      # Zeile 514
edge_pp = round(((1/model_odds)*MODEL_MARGIN - (1/odds)*1.03) * 100)   # Zeile 882
```
Der Break-Even am tatsächlich gespielten Preis ist **exakt `1/odds`** — da wird nichts de-viggt (du zahlst genau diese Quote). Das `× 1.03` zieht jeder Edge zusätzlich ~`0.03/odds` (≈ 1,5–3pp) ab. Für **AH** gibt `_steam_model_odds` bewusst `None` → `model_odds = odds` → `edge = (1/odds)·(0.96 − 1.03) ≈ −3,5pp konstant`. Der Docstring (`:845`) sagt aber „AH → … Edge ~0, ehrlich" — das stimmt **nur ohne** das `1.03`.

- **Was es NICHT betrifft:** Die Card-BET-Entscheidung. Die hängt an `STEAM_BET_THRESHOLD` auf der **Conviction** (`:103/:2208`), nicht am Edge. Card-Verdicts sind also unberührt (und negativer Preis-Edge ist bei Cards ohnehin gewollt — du zahlst den Sharp-Preis).
- **Was es betrifft:** `effectiveEdgePP_trade` (`:2125`, speist den Auto-Trader) und jeder angezeigte Edge. Alle Steam-Edges erscheinen ~3% zu schlecht, AH trägt einen deterministischen −3,5pp-Sockel. In einem System, das auf ehrlichem Edge/CLV besteht, ist das die wichtigste Engine-Baustelle.
- **Fix:** `market_prob = 1/odds` (das `1.03` streichen). Dann ist AH-Edge exakt 0 wie versprochen, und der Rest bleibt korrekt negativ-by-design (Vig).
- Konfidenz: **hoch** (deterministisch aus den Konstanten, am Code verifiziert).

### A2 — 🟠 BTTS-Markt aktiv, aber Quoten werden strukturell nie geholt
`fetch_liga_odds.py:540` fragt nur `&markets=h2h,totals,spreads`. BTTS steht im Code (`_extract_btts`), ist aber nie im Batch (Kommentar: „BTTS später per-Event, Phase 2"). Folge in `mls-data.json`: `bttsY/bttsN` = 0/34. MLS hat BTTS **nicht** in `disabled_markets` → der Markt gilt als aktiv, liefert aber nie etwas. Toter Folge-Code: der BTTS-Zweig in `xg_strength.py` und `_eval_ou_btts` in `public_static_bias.py` können nie feuern. Konfidenz: **hoch**.

### A3 — 🟡 O/U-Leiter kollabiert faktisch auf 2.5
`totals` liefert nur die Hauptlinie, `alternate_totals` wird nicht angefragt. In `mls-data.json`: `o25` 15/34, `o35` nur 5/34, `o15` 0/34, `public_o35` 0/34. Die 1.5-/3.5-Pfade in `steam_engine`, `lead_lag_bias`, `public_static_bias`, `xg_strength` laufen fast immer ins Leere. Konfidenz: **hoch** (Daten + markets-String verifiziert).

### A4 — 🟡 Zwei „tote" Config-Knöpfe
- `family_caps.sharp_money` wird nie angewandt: `conviction_score.py:501-504` setzt die sharp_money-Familie über eine feste Strength-Leiter auf max 3; `caps["sharp_money"]` wird nirgends gelesen (nur model_stack/context/market nutzen `caps`). Default (3) = Leiter-Max, deshalb heute wirkungslos, aber ein Profil-Override verpufft.
- Steam-Kern-Trigger `TRIGGER_PP = 3.0` ist hartkodiert: `build_steam_picks` wird in `generate_wm_picks.py:1218` **ohne** `trigger_pp` gerufen → Default. Liga (mehr Rauschen) vs. WM lässt sich die zentrale „ab wann ist es Steam"-Schwelle nicht tunen.
- Konfidenz: **hoch** (verifiziert). Severity niedrig, aber es sind echte eingefrorene Stellhebel.

### A5 — 🟡 `convictionScore` (angezeigt) ≠ Conviction im BET-Gate
`generate_wm_picks.py:2189` speichert `convictionScore = round(_conv_raw + _cal_nudge − _early_pen)`, das BET-Gate (`:2217`) prüft aber `(conv["score"] − _early_pen)` **ohne** `_cal_nudge`. Bei `_conv_raw=5, nudge=+0.5` zeigt die Card „6/10", das Gate sieht 5 → kein BET. Kosmetisch/verwirrend, kein Geldverlust, aber Anzeige und Entscheidung driften. Konfidenz: **mittel** (Code gelesen, kein Live-Repro).

### A6 — ⚪ Design-Fragen (nicht als Bug bestätigt)
- `lead_lag_bias`: „bestätigt" (4.0) wird höher gescort als „früh/EARLY" (2.5). Gegen die reine Stale-Preis-/CLV-These wäre der frühe, noch nicht bestätigte Move der wertvollere. Verteidigbar als Richtungs-Confidence — **deine Design-Intention bitte bestätigen.**
- `market_side()` behandelt „Doppelte Chance — 1X/X2" als reinen Heim-/Auswärts-Bonus (DC-12 bekommt keine Seite). Leichte direktionale Ungenauigkeit.

---

## B. Ungenutztes Potenzial (verifiziert — niemand liest diese Daten für Picks)

### B1 — 🟢 Heim/Auswärts-Split + Sequenz-Raten (größter Hebel)
`form.venueSeq`, `o25Seq`, `bttsSeq`, `scoredSeq`, `csSeq`, `scoredRate`, `cleanSheetRate`, per-Team `over25Rate`/`bttsRate` — 30/30 befüllt, aber **kein Signal/keine Engine** liest sie (nur die Streaks-Content-Pipeline). Das Tor-Modell poolt heute nur `avgScored` (`:320-321`). `venueSeq` gäbe echten Heim-Form-vs-Auswärts-Split — gerade in der reise-lastigen MLS wertvoll —, `o25Seq`/`bttsSeq` dichte, aktuelle O/U-/BTTS-Raten statt der dünnen h2h-Rate (n≈10). Konfidenz: **hoch** (grep: keine Pick-Leser).

### B2 — 🟢 Ecken- & Karten-Markt: Modell/Daten da, Quoten nie geholt
`expected_corners()` (`generate_wm_picks.py:703`) existiert, wird aber **nirgends aufgerufen** (verifiziert). Ecken-Quoten werden nie geholt (`markets=h2h,totals,spreads`). `cornersForm.cardLine/cardOverSeq/cardOverRate/cardVenueSeq` (30/30) werden von keinem Pick-Code gelesen. Eine ganze Marktfamilie liegt brach, obwohl Modell (Ecken) und Kartendaten schon da sind. Konfidenz: **hoch**.

### B3 — 🟢 Schuss-Qualität als lebender Ersatz fürs tote `chance_creation`
`sotForAvg`, `shotsInsideForAvg`, `blocksForAvg`, `xgSimForAvg` sind 30/30 befüllt und werden explizit in den Signal-Context gereicht — aber die Konsumenten (`chance_creation`, `form_rating`) sind für MLS tot (keyPasses/rating null, wird separat gefixt via `fetch_player_stats`). Ein Signal direkt auf `sotForAvg`/`shotsInsideForAvg` wäre der sofort lebende MLS-Angriffs-Edge, unabhängig vom Player-Endpoint. Konfidenz: **hoch**.

### B4 — 🟡 19/34 Spiele nur mit Polymarket bepreist → keine Book-Picks
Nur 15/34 Einträge haben Pinnacle `hw/dr/aw`; 19 haben nur `poly_*`. Für die läuft `steam_engine` + alle Book-Signale leer. Poly-implied als Pricing-Fallback/Anker (mind. Analyse) würde > die Hälfte der Partien überhaupt erst bepreisen. (Timing-Frage: Pinnacle listet MLS evtl. erst spät — trotzdem prüfen.) Konfidenz: **mittel**.

---

## C. Was die Agenten FALSCH hatten (Transparenz)

Wichtig, damit du dem Rest vertraust — ich habe diese aussortiert:
- **„Guard-Tests fehlen"** (`test_no_unguarded_1x2_devig.py`, `test_js_pick_helpers.py`): **existieren beide** im echten `tests/`. Die Agenten sahen nur die gestagete Teilmenge. Alle darauf gestützten „ungeschützt"-Schlüsse sind hinfällig.
- **„Betfair-Preise ungenutzt"**: falsch — `sharp_signals/multi_book_steam.py` liest `bf_hw/dr/aw` (zweiter Sharp-Anker). Der *Volumen*-Punkt von neulich bleibt separat gültig.
- **Frontend-Hero-Divergenzen / eigenständige Demotion (`asymData`)**: der Agent war selbst unsicher (die auslösenden `dataQuality`-Werte erzeugt kein gestagetes Python) und der behauptete fehlende Drift-Test existiert. **Nicht bestätigt** — ich würde das erst gegen `test_js_pick_helpers.py` prüfen, bevor irgendwer etwas anfasst.

---

## D. Priorisierung

| # | Thema | Typ | Aufwand | Wirkung |
|---|---|---|---|---|
| 1 | **B1** Heim/Auswärts-Split + Sequenz-Raten ins Modell/Signale | Potenzial | M | 🟢 größter Datenhebel, alles schon da |
| 2 | **A1** `× 1.03` streichen (Edge = `1/odds`); AH-Edge wird ehrlich 0 | Korrektheit | S | 🟠 ehrlicher Trade-Edge + Doku-Konsistenz |
| 3 | **A2/A3** BTTS + O/U-Leiter (1.5/3.5) via Per-Event/`alternate_totals` holen | Korrektheit/Fläche | M | 🟡 aktivierte Märkte endlich befüllen |
| 4 | **B2** Ecken/Karten-Quoten holen (Modell/Daten liegen) | Potenzial | M | 🟢 neue Marktfamilie |
| 5 | **B3** Schuss-Qualitäts-Signal (MLS-Ersatz für totes chance_creation) | Potenzial | M | 🟢 sofortiger Angriffs-Edge |
| 6 | **A4** `family_caps.sharp_money` + `TRIGGER_PP` profil-konfigurierbar | Korrektheit | S | 🟡 eingefrorene Stellhebel |
| — | **A5** Anzeige-vs-Gate-Conviction angleichen; **A6** lead_lag-Richtung bestätigen | Klärung | S | ⚪ |

**Rote Linie:** Kein Fund rechtfertigt Panik — die Engine tut im Kern das Richtige. Aber „aktivierte Märkte ohne Daten" (A2/B2) und „gesammelte Daten ohne Nutzung" (B1/B3) sind genau deine wiederkehrende Frage „nutzen wir alles aus?" — und die Antwort ist hier ehrlich: noch nicht.
