# BetEdge Betting Dashboard

Live: [blummabet.github.io/Betting-Dashboard/season-finish.html](https://blummabet.github.io/Betting-Dashboard/season-finish.html)

---

## Architektur

- `season-finish.html` — Haupt-Dashboard (alle JS, HTML, CSS in einer Datei)
- `update_dashboard.py` — Bot: holt Daten, ersetzt nur den `const LEAGUES = {...}` Block
- `picks_history.json` — alle Picks (resolved + pending)
- `prematch-data.json` — Quoten, xG, Form-Daten
- `fetch_results.py` — holt Ergebnisse und resolved Picks
- `resolve_picks.py` — markiert Picks als won/lost

Der Bot `update_dashboard.py` überschreibt **nur** den LEAGUES-Datenblock via regex — alle JS-Logik, Buttons und UI-Code bleiben bei jedem Bot-Run erhalten.

---

## Modell-Dokumentation

### Edge-Berechnung (`getBettingPicks`)

```
ip  = (1 / odds) * 1.03    // implied prob, bereinigt um ~3% Buchmaker-Marge
edge = mp - ip
value = edge >= 0.13 → 🔥 hot | edge >= 0.07 → 💰 value | sonst null
```

Der Faktor `1.03` korrigiert die Buchmaker-Marge (Vig). Ohne ihn erscheint jede Edge ~3% höher als real → zu viele Picks als „value" markiert.

### Form-Modifier (`_formMod`)

Drei Pfade je nach Team-Status:

| Pfad | Bedingung | Effekt |
|---|---|---|
| `isRed` | Abstiegszone | stark (±0.5–2.0), inverse Logik (schlechte Form → mehr Kampfgeist) |
| `isStake` | Titelrennen / CL / Europa | moderat (±0.3–1.2) |
| default | kein Stake | schwach (±0.3–0.5) |

Gewicht im Score: `× 0.35` pro Team.

### Liga-spezifische Over/Under Caps (`_lgCap`)

```javascript
const _lgCap = {
  ENG: 0.05, GER: 0.05,   // torreich
  AUT: 0.04, TUR: 0.03,
  SCO: 0.03, NED: 0.03,
  POR: 0.01, ESP: 0,
  ITA: -0.04, FRA: -0.04  // defensiv
}[leagueKey] || 0;
```

Anwendung: Basis-Wahrscheinlichkeit für O2.5, U2.5, O3.5 wird um `_lgCap` verschoben (proportional skaliert je nach expGoals-Bracket). Harte Grenzen: 0.05–0.92.

### Bookmaker-Marge De-Vig (1X2)

Für 1X2-Quoten wird die Marge via Normalisierung rausgerechnet:
```
_bkrTot = 1/hw + 1/dr + 1/aw
_bkrPH  = (1/hw) / _bkrTot   // faire Heimsieg-Wahrscheinlichkeit
```
Diese de-viggte Prob wird als Basis für alle Heimsieg/Auswärtssieg-Picks verwendet.

### Pressure System

- `mustWin` = Team braucht einen Sieg (pressureRatio > 0.65)
- `_pressureBoost` ∈ [0, 1] = kombinierter Druck-Faktor
- Beeinflusst: Score, Over/Under mp, BTTS mp, Auswärtssieg-Wahrscheinlichkeit

### Motivations-Penalty

| Status | Effekt |
|---|---|
| `none` (mathematisch gesichert) | Score -2.0 / -1.0 (beide/einer) |
| `low` (nahezu gesichert) | Score -0.6 / -0.3 |

Label-Unterscheidung: `red`-Teams → "Abstieg quasi sicher", andere `low`-Teams → "nahezu gesichert".

---

## Bekannte Eigenheiten

- CDN-Cache GitHub Pages: ~10 min TTL nach Push
- `.git/HEAD.lock` / `.git/index.lock`: Wenn der Sandbox-Git hängt → `rm .git/*.lock` im Terminal
- `_mergeLocalPicks()`: dedupliciert via `dateIso|home|away` + `home|away` um localStorage-Duplikate zu vermeiden
- `renderResultsStats()` respektiert den aktiven Day-Filter (`_activeDaysFilter`)

---

## Changelog

| Datum | Was |
|---|---|
| Apr 2026 | Margin Fix: `ip = (1/odds) * 1.03` für realistische Edge-Berechnung |
| Apr 2026 | FormMod für alle Stake-Teams (gold/blue/orange/purple), nicht nur red |
| Apr 2026 | Liga-spezifische O/U Caps: ENG/GER +0.05, ITA/FRA -0.04 |
| Apr 2026 | Infografik-Text vollständig auf Englisch übersetzt (`_igT()`) |
| Apr 2026 | Results Stats Bar respektiert Day-Filter (7d/30d/all) |
| Apr 2026 | Motivations-Label fix: Wolves-Typ (Abstieg quasi sicher) vs. nahezu gesichert |
| Apr 2026 | 📋/🖼️ Buttons sichtbar (width:auto Fix) |
| Apr 2026 | localStorage Dedup Fix (home\|away zusätzlich zu dateIso\|home\|away) |
