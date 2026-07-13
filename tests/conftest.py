"""Gemeinsame Test-Absicherung.

13.07.2026 (MLS-Audit) — TEST-VERSCHMUTZUNG ÜBER UMGEBUNGSVARIABLEN.

Der Datensatz wird über `COCOBET_DATASET` / `COCOBET_PROFILE` / `LIGA_SEASON` gesteuert. Mehrere
Tests setzen diese Variablen, um Liga-/MLS-Verhalten zu prüfen. Vergisst einer davon das Aufräumen
(oder bricht mittendrin ab), läuft der REST der Suite im falschen Datensatz weiter — und die
Fehler tauchen dann in völlig unbeteiligten Tests auf.

Real passiert, zweimal:
  · test_poly_mls_name_resolution setzte COCOBET_DATASET=mls beim Import → 6 Liga-Tests kaputt
  · nach dem Dataset-Fix der Guards fiel test_book_health_guard NUR im Gesamtlauf um
    (isoliert grün) — weil ein Vor-Test `mls` hinterlassen hatte und der Guard seither die
    aufgelöste Datei liest statt einer hartkodierten

Diese Fixture schnappschusst die Env vor JEDEM Test und stellt sie danach wieder her. Damit kann
kein Test mehr einen anderen vergiften — unabhängig davon, ob er selbst sauber aufräumt.
"""
import os

import pytest

_COCOBET_ENV = ("COCOBET_DATASET", "COCOBET_PROFILE", "LIGA_SEASON")


@pytest.fixture(autouse=True)
def _isolierte_dataset_env():
    """Env-Schnappschuss je Test — verhindert Datensatz-Lecks zwischen Tests.

    ZWEI Dinge müssen zurückgesetzt werden, nicht eines:

    1. Die Umgebungsvariablen.
    2. Das MODUL `cocobet_dataset` — es wertet den Datensatz beim Import aus und cacht ihn.

    Punkt 2 ist die Falle, in die ich beim ersten Versuch selbst getappt bin: Ein Test setzt
    COCOBET_DATASET=mls, lädt cocobet_dataset neu, und räumt die Env am Ende SELBST auf. Von außen
    sieht die Umgebung danach sauber aus — das Modul steht aber weiter auf MLS. Wer dann eine
    Datei über D.file() auflöst, bekommt mls_*.json und wundert sich, warum ein völlig
    unbeteiligter Test umfällt (13 Stück waren es).

    Deshalb: IMMER neu laden, nicht nur wenn sich die Env sichtbar geändert hat.
    """
    vorher = {k: os.environ.get(k) for k in _COCOBET_ENV}
    try:
        yield
    finally:
        for k, v in vorher.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        try:
            import importlib
            import cocobet_dataset
            importlib.reload(cocobet_dataset)
        except Exception:
            pass   # Die Test-Absicherung darf nie selbst den Lauf killen
