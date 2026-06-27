# CocoBet Backlog (Liga + WM)

Stand 26.06.2026. Lebendige Liste aller offenen Punkte — Liga UND noch nicht umgesetzte WM-Sachen —
damit wir alles abarbeiten können. ✅ = erledigt (Referenz), ⏳ = offen, 🔒 = blockiert.

## Liga (auf WM-Stack, ~6 Wochen bis Saisonstart)

### ✅ Erledigt (Referenz)
Daten/Odds/Picks-Engine/Renderer/Tracking/CLV/Resolve/eigener Workflow · Guards + Lern-Loop
dataset-bewusst · LeaguePressureSignal · Post-Match-xG-Re-Learning · Backtest (5 Ligen + Value-Filter
+ CLV) · Backtest-als-Prior (liga_signal_priors) · LIGA_SIGNALS.md · Club-Elo (Baseline).

### ⏳ Daten / Pipeline
- ⏳ Odds-Takt nahe Spieltage hochdrehen (~2 Wochen vor Saisonstart) — sonst werden Intraday-Steam-Drops verpasst (= genau die Picks). Jetzt sinnlos (keine Bewegung).
- ⏳ ESP/GER live verifizieren — in lokaler Kopie waren Fixtures/Standings leer; prüfen ob live korrekt kommen.
- ⏳ ClubElo-Fetch im GitHub-Workflow verifizieren — Sandbox gab 403; in Actions prüfen, sonst UA/Quelle anpassen.

### ⏳ Frontend / Cards
- ✅ Matchday-Subnav „1 dann 20"-Bug behoben (Daten-Fix pick_event_for_fixture + Frontend-Cap + Guard).
- ✅ Sharp Radar: aktuelle Linien auch OHNE Bewegung (Tabelle Pinnacle/Soft, bis Moves da sind).
- ⏳ Heart-Tab Liga-Integration (Top-Conviction-Ansicht + Liga-Signale; aktuell WM-verdrahtet).
- ✅ Pick→Card-Pfad bewiesen (simulierter Drop → 2 Cards) — Cards füllen sich automatisch bei Linienbewegung.

### ⏳ Signale (laut LIGA_SIGNALS.md, modular dazubauen)
- ✅ `injury` Liga-Fetch (Fetcher dataset-bewusst; InjurySignal liest wm[injuries]).
- ✅ `apif_predictions` Liga-Fetch (Fetcher dataset-bewusst → liga_apif_predictions.json).
- ✅ `fixture_congestion` / Erschöpfung (Ruhetage aus Spielplan; registriert, context-Familie).
- ✅ Spieler-Layer Spine: `squads` (Schlüsselspieler → lineup_signal) + `player_form`-Ledger
  (aus gespielten Spielen via fetch_liga_match_stats → liga_player_form.json, skaliert lineup_signal).
- ⏳ Spieler-Layer Rest: `topscorer_momentum` (/players/topscorers) + `squad_strength` (überlappt injury/lineup).
- ⏳ `coach_change` / `transfer_shift` (Saisonstart-relevant).
- ⏳ `referee_tendency` (zusammen mit Karten-Markt).
- ⏳ News-Signal — nur falls Datenqualität + harter Engine-Hook (Scope-Disziplin).

### ⏳ Märkte
- ⏳ Player-Props + Corner-Markt + Engine-Hooks (`corner_rate`-Signal).
- 🔒 Poly Trading / Wallets Liga — blockiert, bis Polymarket Ligen listet.

### ⏳ Lern-Loop / Guards
- ⏳ Guard-Batterie Liga voll auditieren — laufen alle relevanten Guards auf `liga_status.json`? Liga-spezifische fehlend?
- ⏳ Lern-Loop end-to-end auf echten Liga-Picks testen (sobald erste resolved sind).
- ⏳ Forward-CLV-Tracking der Liga-Paper-Picks (Einstieg Soft vs Pinnacle-Closing) + Dashboard — der eigentliche Steam-Beweis.

### ⏳ Liga-Switch-Ideen
- ⏳ Halbzeit-Märkte + Signale anpassen.
- ⏳ Liga-Historie als eigenes lernbares Signal (Backtest-als-Signal: gelernter Prior je Markt/Liga).

## WM — noch nicht umgesetzt / offen
- ⏳ KO-Bracket: `best_third` + W-Referenzen auflösen (TBD bis FIFA-Tabelle / KO-Ergebnisse).
- ⏳ Trade-Post-Mortem: Closing-Capture bei Anpfiff (CLV-Abdeckungslücke).
- ⏳ Poly Pre-Match-Close: hängt am `AUTO_SELL_ENABLED`-Secret.
- ⏳ smart_money: Holders-Endpoint am 1. echten Live-Lauf justieren.
- ⏳ Poly-Handicap-Trading: `ah_trade_enabled` gated AUS bis Token-Platzierung verifiziert.
- ⏳ Pick-Kalibrierung: nach Runde 2 auswerten.
- ⏳ Freshness-Reverser: Phase 2 (reinforcing-market).
- ⏳ Safer-Line: Phase 2 (Quarter-Linien 3.0 / 3.25 / +0.25).
- ⏳ Player-Props: deaktiviert (kein Engine-Hook) → aktivieren, wenn Markt + Hook stehen.
- ⏳ Signal-Engine-Roadmap: restliche geplante Signale der 5 Tiers.
- ⏳ Post-Match-Move-These: Dense-Capture-Daten auswerten, dann entscheiden.
- ⏳ Daten-Lücken prüfen: apif (listet WC2026 evtl. nicht), weather (war stale).
