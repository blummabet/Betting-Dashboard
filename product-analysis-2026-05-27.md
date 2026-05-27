# CocoBet — Schonungslose Produkt-Analyse
*Datum: 27. Mai 2026 | Perspektive: 10+ Jahre Betting Product Development, B2C & B2B*

---

## 1. Produkt-Gesamtbewertung

**Das ist ein ambitioniertes Hobby-Projekt das an der Schwelle zum ernsthaften Produkt steht — aber noch nicht dort ist.**

Die technische Tiefe ist beeindruckend. Ein Elo-Modell + Poisson für O/U + CLV-Tracking + Polymarket-Integration + Steam Lag Detection — das ist mehr als 90% aller „Tipster-Dashboards" auf dem Markt können. Wer das alleine gebaut hat, hat echte Expertise.

Aber: Ein marktfähiges Produkt ist das noch nicht, und zwar aus einem einzigen Hauptgrund — **der primäre CTA auf der wichtigsten Seite (Event Page „Jetzt Wetten →") macht beim Klicken nichts.** Das ist kein Schönheitsfehler, das ist ein konzeptionelles Problem. Bevor dieser Button nicht auf eine Bookie-Deeplink-Seite führt oder zumindest einen Affiliate-Flow auslöst, gibt es kein Business-Modell.

**Für B2B-Verkauf an Operator:** 6/10 — Die Dateninfrastruktur ist solid. Kein Operator kauft heute ein Produkt das (a) auf GitHub.io hosted ist, (b) einen WIP-Banner hat, (c) kein Whitelabel-Konzept zeigt, (d) die Pick-Logik exposed statt abstrahiert.

**Für B2C-Community:** 4/10 — Ein Hardcore-Bettor mit Pinnacle-Erfahrung versteht das Produkt und schätzt es. Ein normaler Sportwetter verlässt die Seite nach 30 Sekunden, weil er mit Kelly Criterion, Fair Value, CLV-Drift und Consensus Devig überfordert ist und kein einziges Erklärungs-Tooltip findet.

---

## 2. Navigation & UX

**Das Navigations-Problem: 7 Tabs für eine Zielgruppe die 2 braucht.**

| Tab | Wirklichkeit |
|---|---|
| 🇪🇺 National | Funktioniert. Kern des Produkts. |
| 🌍 International | Führt auf WM-Cards — gut. Aber Sub-Nav hat WM 2026 hidden by default (`display:none`). Ein neuer User sieht „Cards" und ein „Tracking"-Tab das eine Coming-Soon-Seite ist. |
| 📡 Sharp Radar | Funktioniert. Aber: doppelt vorhanden — einmal als Top-Nav-Tab, einmal als Liga-Filter in National. Das verwirrt. |
| 📈 Polymarket Trading | Inhalt kommt aus polymarket-tab.js, braucht frische Daten. Für normale User: komplettes Kauderwelsch. |
| 🟣 Polymarket Betting | Gleiches Problem. Zwei Polymarket-Tabs mit kaum erkennbarem Unterschied für Nicht-Trader. |
| ❤️ Heart | **Das ist interne Entwickler-Dokumentation im Produktions-Nav.** 8.000 Wörter über Python-Scripts, GitHub Actions und API Rate Limits. Kein User darf das sehen. |
| 🔧 Status | Zeigt GitHub-Actions-Links und legt den öffentlichen Repo-Namen offen. Ebenfalls intern. |

**Was fehlt:**
- Onboarding / Glossar: BET/ABWÄGEN/SKIP wird nirgends erklärt
- Kelly Criterion hat keine Tooltip-Erklärung
- Keine leere State-Behandlung: Was sieht ein User wenn keine Spiele heute sind?
- „💾 Picks speichern" ist ein Action-Button mitten in der Nav — kann versehentlich gedrückt werden, kein Undo

**Was weg muss:** Heart, Status, und die doppelten Polymarket-Tabs zu einem zusammenführen.

**Würde ein normaler Sportwetter verstehen was er tun soll?** Nein. Er würde das WIP-Banner lesen, auf National klicken, vor komplexen Daten stehen, auf „Jetzt Wetten" klicken, nichts passiert, und er geht.

---

## 3. Event Pages — Launch-Readiness

| Check | Status |
|---|---|
| Back-Link funktioniert | ❌ Zeigt auf `betting-dashboard.html` (404) |
| „Jetzt Wetten →" Button | ❌ Komplett tote CTA — kein onclick, kein href |
| Sticky Bet Bar „Wetten →" | ❌ Gleiches Problem |
| Group Table Standings | ❌ Hardcoded 0-0-0 — wird ab 11. Juni permanent falsch |
| Hero Section + Elo Donut | ✅ Visuell stark |
| Environment Section (Travel/Venue) | ✅ Echter USP, kein Konkurrent hat das |
| Decision Strip | ✅ Hervorragende UX-Entscheidung |
| AI-Preview | ⚠️ Wirkt leicht generisch ohne echten Spieler-Bezug |
| Schlüsselspieler + Spieler-Wetten | ⚠️ Quasi-dupliziert, direkt aufeinanderfolgend |
| Mobile Signal-Darstellung | ❌ signal-cards-mobile HTML fehlt — Signal-Info komplett weg auf Phone |
| SEO | ❌ Null pre-rendered Content, keine OG-Tags, kein JSON-LD |

**SEO:** Vollständig unbereit. Google sieht ein leeres `<div id="app">`. Für Content-SEO irrelevant solange Client-Side Rendering.

**Mobile:** Funktioniert grundsätzlich, aber Signal-Tabelle wird auf Mobile versteckt ohne HTML-Fallback.

---

## 4. Wett-Inhalte & Markt-Tauglichkeit

**Picks-Darstellung:** Gut für Experten, unlesbar für Anfänger. Kein einziger Tooltip zu Edge, Fair Value, CLV, Kelly.

**Märkte:** 1X2, O/U 2.5, BTTS, DNB vorhanden. Fehlend: Handicap, Asian Handicap, Correct Score, First Scorer, Double Chance.

**AI-Analyse:** Haiku-Standard-Output. „Beide Teams sind gut in Form" ist nicht glaubwürdig neben konkreten xG-Zahlen und Elo-Diffs. Muss spezifischer auf die berechneten Zahlen eingehen.

**Kelly Criterion:** Wird angezeigt, nicht erklärt. Kein Hinweis auf Half-Kelly, keine Warnung bei hohen Werten (>10%).

---

## 5. WM-Spezifisch — Die 3 kritischsten Fixes bis 11. Juni

**#1 — Jetzt Wetten Button → Bookie Deeplink (24h-Fix)**
Ohne das hat die Event Page keine Daseinsberechtigung für User. Selbst ein statischer Link zu Bet365/Pinnacle mit UTM-Parametern ist besser als nichts.

**#2 — Back-Link Fix (1h-Fix)**
`betting-dashboard.html` → korrekter Dateiname. Jeder der von einem WM-Event zurücknavigiert landet auf einer 404.

**#3 — WM Tracking Tab entfernen oder befüllen (48h-Fix)**
„Coming Soon" auf einem Tab der zur WM angeklickt wird ist ein Vertrauensbruch.

---

## 6. Konkurrenz-Check

| Kriterium | CocoBet | Kickform | Betegy | SofaScore Bet | SmartBets |
|---|---|---|---|---|---|
| Elo-Modell + Fair Value | ✅ Solide | ✅ | ✅ | ✅ | ⚠️ |
| Polymarket Integration | ✅ Einmalig | ❌ | ❌ | ❌ | ❌ |
| Steam Lag Detection | ✅ Einmalig | ❌ | ❌ | ❌ | ❌ |
| Travel/Venue Context | ✅ Einmalig | ❌ | ❌ | ❌ | ❌ |
| CLV-Tracking | ✅ | ⚠️ | ✅ | ❌ | ⚠️ |
| Mobile UX | ⚠️ Bugs | ✅ | ✅ | ✅ | ✅ |
| Onboarding für Anfänger | ❌ | ✅ | ⚠️ | ✅ | ✅ |
| Bookie-Integration (Wetten-CTA) | ❌ | ✅ | ✅ | ✅ | ✅ |
| SEO / Organic Traffic | ❌ | ✅ | ⚠️ | ✅ | ✅ |
| Deployment (Production-Grade) | ❌ GitHub.io | ✅ | ✅ | ✅ | ✅ |

**Echter USP:** *„Das einzige Betting-Dashboard das Pinnacle Sharp Money in Echtzeit mit Polymarket-Preisen kreuzt und automatisch handelt."* Das gibt es sonst nirgends.

---

## 7. Top 5 Verbesserungen — Priorisiert nach Impact

**#1 — Bookie-Deeplinks auf der Event Page** *(Umsatz-kritisch)*
Jetzt Wetten → muss auf eine Bookie-URL mit Affiliate-Tracking. Pinnacle/Bet365/Betsson haben Affiliate-Programme. Implementierungszeit: 4 Stunden.

**#2 — Onboarding-Layer: 3 Begriffe erklären** *(Retention-kritisch)*
Nicht ein Tutorial. Nur drei Tooltips: Was ist BET vs ABWÄGEN? Was ist Edge in pp? Was bedeutet Kelly 3.2%? Ohne das verlierst du 80% der neuen User sofort. Implementierungszeit: 6 Stunden.

**#3 — Heart und Status aus dem User-Nav entfernen** *(Trust-kritisch)*
Diese zwei Tabs + der WIP-Banner gehören weg. Solange ein Bettor „nicht für Produktion" liest, vertraut er deinen Picks nicht. Implementierungszeit: 2 Stunden.

**#4 — Mobile Signal-Fix und Back-Link** *(UX-kritisch)*
Signal-Cards-Mobile braucht seinen HTML-Block, Back-Link muss auf den korrekten Dateinamen. Implementierungszeit: 3 Stunden.

**#5 — USP-Sektion auf der Startseite** *(Marketing-kritisch)*
Eine Hero-Section die in einem Satz erklärt was CocoBet kann und warum Polymarket + Pinnacle der entscheidende Datenvorteil ist. Kein User versteht aktuell den Unterschied zu Kickform. Implementierungszeit: 4 Stunden.

---

## Kritische Bugs gefunden (technisch)

Zusätzlich zu den UX-Problemen wurden am 27.05.2026 folgende kritische Code-Bugs gefixed:

1. **Market Label Mismatch** — `generate_wm_picks.py` schrieb deutsche Labels, `fetch_wm_poly_prices.py` erwartete englische → O/U und BTTS auto-bets feuerten nie
2. **Verdict Threshold Divergence** — Python SKIP bei score ≤ -2, JS bei score ≤ -1 → Picks divergierten
3. **Poly History nicht committed** — `wm2026-poly-history.json` fehlte im git add → History-Daten verloren
4. **Telegram env vars fehlten** — Edge-Alert-Telegrams feuerten nie aus `manage-wm-poly.yml`

---

*Analyse erstellt mit Claude (Cowork Mode) basierend auf vollständiger Code-Review und Dashboard-Durchsicht.*
