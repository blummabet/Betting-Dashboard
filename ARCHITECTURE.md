# CocoBet — Architektur (Best Practice, verbindlich)

Stand 26.06.2026. Diese Datei ist die verbindliche Referenz, wie sauber gebaut wird. WM 2026 ist die
Werkbank (wird später Champions League), Liga ist der echte Start — **beide laufen auf EINEM Stack**.
Kein zweites Frontend, kein Copy-Paste, kein „drauf klatschen".

## Grundprinzip: EIN Stack, zwei Datasets
Dieselbe Engine/Signale/Loop/Guards laufen für WM und Liga. Der Unterschied ist nur das **Dataset**
(welche Dateien, welche Liga-IDs, welche Saison) — gesteuert über `COCOBET_DATASET` (`wm`|`liga`)
und `COCOBET_PROFILE` (`wm2026`|`liga_default`). `generate_liga_picks.py` ist nur ein dünner Wrapper,
der die Env setzt und `generate_wm_picks.main()` ruft.

## Single Source of Truth — die Schichten
Jede Datei importiert die geteilte Schicht, statt Logik zu wiederholen:

- **`cocobet_dataset.py`** — die EINZIGE Dataset-Auflösung. Niemand sonst liest `COCOBET_DATASET` roh.
  - `is_liga()` / `active_dataset()` / `active_profile()`
  - `file(wm, liga)` → dataset-passender Pfad (beide Namen explizit, weil das Namensschema historisch
    variiert: `liga_*`, `liga-*`, `wm_*`, `wm2026-*`)
  - `data_file()` → Haupt-Datendatei · `prefix()` → `""`/`liga_`
  - `leagues()` → Top-5-Liga-IDs (EINZIGE ID-Definition) · `season()` / `current_season()`
- **`sharp_signals/base.py`** — `Signal`/`SignalResult` + `market_side()` (Pick-Markt → home/away/
  over/under). Kein Signal definiert `market_side` neu.
- **`sharp_signals/registry.py`** — `ACTIVE_SIGNALS`, `SIGNAL_GROUPS` (Anti-Korrelations-Familien),
  dataset-bewusste Gewichte (`liga_signal_weights.json` vs `signal_weights.json`), `evaluate_signals`.
- **`cocobet_config.json`** — Profile (`wm2026`, `liga_default`): `disabled_signals`, Overrides.

## Die Säulen (alle dataset-bewusst über die Schicht)
- **Engine** `generate_wm_picks.py` — Pinnacle-Anker + Steam als Pick-Quelle; Signale modifizieren
  Conviction, nicht die Baseline. KO/Quali-Schritte für Liga gegatet.
- **Signale** `sharp_signals/*.py` — je eine `Signal`-Subklasse, in `registry` registriert, eigene
  Gewicht-Zeile, im Lern-Loop. Neues Signal = Klasse + Registry-Eintrag + Familie + Tests.
- **Lern-Loop** `build_signal_ledger.py` → `update_signal_weights.py` — append-only Ledger +
  prozess-gewichtetes Bayesian-Update; Backtest-Prior (`liga_signal_priors.json`).
- **Guard-Batterie** `wm_data_integrity.py` — `@integrity_check`-Funktionen, schreiben `*_status.json`.
  Liga-only-Guards prüfen `ctx.is_liga`. Arbeitsregel: stiller Daten-Bug → Guard, Logik-Bug → Test.

## So baust du sauber dazu (Checkliste)
1. Dataset/Pfade NUR über `cocobet_dataset` (`is_liga`, `file`, `data_file`, `leagues`, `season`).
2. Neues Signal: `Signal`-Subklasse in `sharp_signals/`, `market_side` aus `base`, in `registry`
   (ACTIVE_SIGNALS + SIGNAL_GROUPS-Familie), Default-Gewicht 1.0, Unit-Tests.
3. Neuer Markt: erst Engine-Hook + Resolve, dann Signal (Scope-Disziplin: kein Markt ohne Hook).
4. Tests für jede reine Funktion; Guard für jeden stillen Daten-Pfad. Suite muss grün bleiben.
5. Push NUR über GitHub Desktop.

## Anti-Drift (automatisch erzwungen)
`tests/test_architecture_drift.py` schlägt fehl bei: dupliziertem `market_side`, rohem
`COCOBET_DATASET`-Zugriff (außer `cocobet_dataset`/`generate_liga_picks`), und divergierenden
Liga-IDs zwischen `cocobet_dataset.leagues()` und `build_liga_data.LEAGUES_TOP5`.

## Bekannte offene Aufräum-Kandidaten
- `_apif_get`/`apif_get` ist in vielen Fetchern lokal definiert (großteils Alt-WM-Code, leicht
  abweichende Rückgabeformen). Kandidat für einen gemeinsamen `apif`-Client — niedrige Prio, da
  hohe Churn/Risiko bei kleinem Gewinn; bei nächstem Anfassen je Fetcher mitziehen.
