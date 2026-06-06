# CocoBet Changelog

## 2026-06-06 — Großes Architektur-Refactor (Single Source of Truth)

**Ziel:** Bulletproof-Architektur vor WM-Start mit echtem Geld auf Polymarket.
Liga-fähig (ein Config-Switch für komplette Saison), erweiterbar, professionell.

**Outcome:** 24 Files migriert, 5 obsolete Workflows gelöscht, 165 automatisierte Tests grün.

---

### Phase A — Foundations (Single Source of Truth)

| File | Zweck |
|------|-------|
| `pick_constants.py` + `pick_constants.json` | DIRECTION_MAP (29 Markets) + INCOMPATIBLE-Pairs |
| `pick_helpers.py` | `is_legitimate_pick`, `hero_sort_key`, `find_picks_conflicting_with_hero` |
| `cocobet_config.json` + `cocobet_config.py` | **ALLE** Magic Numbers, Profile-aware (wm2026 vs liga_default) |
| `state_files_registry.json` + `state_files_registry.py` | Welcher Workflow welche State-Files committet |

### Phase B — Python Migration (11 Files)

Alle Magic Numbers raus, durch `_cfg("section", "key", default)` ersetzt. Default-Wert == ehemaliger Hardcode → 100% backwards-compatible.

- Picks: `generate_wm_picks.py`, `resolve_wm_picks.py`, `validate_wm_picks.py`, `compute_pick_confidence.py`, `detect_pick_changes.py`
- Trade: `auto_wm_poly_trigger.py`, `manage_wm_poly_positions.py`, `polymarket_bet.py`
- Sender: `fetch_wm_poly_prices.py`, `detect_wm_sharp_moves.py`, `telegram_wm.py`
- Sonstige: `monitor_open_positions.py`, `steam_lag_monitor.py`, `generate_daily_tiktok.py`

**Safety-Pattern:** `AUTO_SELL_ENABLED`, `CHAIN_ID=137` (Polygon) und Private-Keys bleiben bewusst Hardcode. Config-Tippfehler kann nie Geld bewegen.

### Phase C — JavaScript Migration

`_pick_helpers.js` (NEU, UMD-Modul für Browser + Node) ersetzt 80+ duplizierte Zeilen in:
- `wm2026-renderer.js`
- `matches/wm-match.html` (Event-Pages)
- `polymarket-tab.js`

Anti-Drift-Test: `tests/test_js_pick_helpers.py` prüft per Source-Parsing, dass JS-Map exakt zu `pick_constants.json` passt. Plus Node-Funktional-Tests für Hero-Sort, isLegitimate, Konflikt-Detection.

### Phase D — Workflows + Registry

5 Workflows umgestellt von hardcoded `git add` Listen auf Registry-Lookup:
- `fetch-wm-data.yml` (25 Zeilen → 1 Zeile)
- `manage-wm-poly.yml`, `track-record-card.yml`, `daily-wm-story.yml`, `daily-tiktok.yml`

**Bug nebenbei gefixt:** Registry hatte `daily_story_state.json` (Phantom-File) statt `tiktok_sent.json` (echtes Dedup-File) → Daily-TikTok-Dedup hätte zwischen Runs verlieren können.

**Aufgeräumt:** 5 obsolete Workflows gelöscht (`fix-wm-squads`, `test-odds-api`, `test-poly-prices`, `test-trades-channel`, `telegram-send`) → 22 → 17 Workflows.

---

### Was nun anders ist vs vorher

| Vorher | Jetzt |
|--------|-------|
| DIRECTION_MAP in 4 Files dupliziert (Python + 3 JS) | EINE Quelle: `pick_constants.json` |
| Magic Numbers verstreut über 7+ Files | Alle in `cocobet_config.json` |
| trackingExcluded-Check 4× inline kopiert | `is_legitimate_pick()` Helper |
| Hero-Sort in 2 Files dupliziert | `hero_sort_key()` Helper |
| Liga-Saison hätte Code-Edit gebraucht | EIN Config-Wert wechseln |
| Drift zwischen Python und JS möglich | Tests verbieten Drift |
| Hardcode-Bugs schwer zu finden | Code-Reviews zeigen sofort wer was ändert |

### Liga-Switch (nach WM)

In `cocobet_config.json`:
```json
"profiles": { "active": "liga_default" }
```

**Automatisch übernommen:** Edge-Schwellen, Stake-Caps, Sell-Thresholds, Pre-Match-Close-Hours, Telegram-Alert-Levels, Sharp-Move-Sensibilität, TikTok-Dedup-Fenster.

**Bewusst nicht im Config:** Safety-Master-Switches (`AUTO_SELL_ENABLED`, `AUTO_TRIGGER_ENABLED`), Network-ID (`CHAIN_ID=137`), Secrets (Private-Keys, Tokens).

### Test-Architektur

```
tests/
├── test_pick_constants.py        # Schema + JSON mirror
├── test_pick_helpers.py           # is_legitimate, Hero-Sort, Konflikte
├── test_cocobet_config.py         # Profile-Switch, ENV-Override, Fallback
├── test_state_files_registry.py   # Schema + Content
├── test_generate_wm_picks.py      # Regression-Snapshot
├── test_resolve_wm_picks.py
├── test_validate_wm_picks.py
├── test_stat_tools.py
├── test_auto_wm_poly_trigger.py   # WM-Werte == Pre-Refactor + Liga-Differs
├── test_manage_wm_poly_positions.py
├── test_fetch_wm_poly_prices.py
├── test_detect_wm_sharp_moves.py
├── test_polymarket_bet.py         # Konsistenz mit auto_trigger
├── test_remaining_python_files.py
├── test_js_pick_helpers.py        # Anti-Drift JS↔Python
└── snapshots/picks_pre_refactor.json
```

**165 Tests, 1 skip** (skip = wm2026-data.json fehlt im Sandbox, läuft im Workflow grün).

### Pre-Refactor → Post-Refactor: Verhalten unverändert

Jeder Test prüft, dass die WM2026-Werte exakt mit den ehemals hardcoded Werten übereinstimmen. Liga-Tests prüfen, dass das Liga-Profil andere Werte liefert. Regression-Snapshot fängt jede Code-Änderung am Picks-Output.

**Ergebnis:** Pipeline funktioniert für die WM identisch zu vorher. Nach der WM ein Config-Switch und sie funktioniert für Ligen.
