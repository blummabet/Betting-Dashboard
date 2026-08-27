"""27.08.2026 — „Real Madrid war noch nicht ausgewertet" (Lucas)

`resolve_picks.py` griff im Pending-Filter hart auf `e["dateIso"]` zu. ZWEI Poly-Direktwetten
(Frankreich–Irak vom 19.06., ein Tennis-Play vom 25.08.) hatten den Schlüssel gar nicht →
KeyError → das Skript starb, BEVOR es irgendetwas auflöste. Der Workflow-Schritt steht auf
`continue-on-error: true`, also lief der Job grün weiter und committete die anderen Dateien.

Ergebnis: seit dem 31.05. wurde KEIN Pick mehr aufgelöst. 315 Einträge, zwei Monate, kein
einziges rotes Licht. Ein einzelner kaputter Datensatz darf den ganzen Lauf nicht kippen.
"""
import datetime

import resolve_picks as R


class TestEntryDate:
    def test_iso_wird_gelesen(self):
        assert R.entry_date({"dateIso": "2026-08-26"}) == datetime.date(2026, 8, 26)

    def test_fehlender_schluessel_wirft_nicht(self):
        """DAS war der Absturz."""
        assert R.entry_date({"date": "19.06.2026"}) == datetime.date(2026, 6, 19)

    def test_deutsches_datum_als_rueckfall(self):
        assert R.entry_date({"dateIso": None, "date": "25.08.2026"}) == datetime.date(2026, 8, 25)

    def test_unbrauchbar_gibt_none(self):
        for bad in ({}, {"dateIso": "kaputt"}, {"date": "irgendwas"}, {"dateIso": ""}, None, "x", 5):
            assert R.entry_date(bad) is None, repr(bad)

    def test_zeitanteil_stoert_nicht(self):
        assert R.entry_date({"dateIso": "2026-08-26T19:00:00Z"}) == datetime.date(2026, 8, 26)


class TestKeinAbsturzAufEinerZeile:
    """Die zwei echten Zeilen, die zwei Monate gekostet haben."""

    ECHT = [
        {"id": "poly-19.06.2026-Frankreich-Irak-AH_Heim_-4.5", "date": "19.06.2026",
         "home": "Frankreich", "away": "Irak", "league": "WM2026", "polyBets": [{}]},
        {"id": "poly-25.08.2026-Henrique_Rocha-Michael_Mmoh", "date": "25.08.2026",
         "home": "Henrique Rocha", "away": "Michael Mmoh", "league": "TENNIS", "polyBets": [{}]},
    ]

    def test_beide_sind_datierbar_statt_toedlich(self):
        for e in self.ECHT:
            assert R.entry_date(e) is not None

    def test_zeile_ohne_picks_ist_kein_fehler(self):
        """Poly-Direktwetten stehen mit `polyBets` statt `picks` in derselben Datei."""
        for e in self.ECHT:
            assert (e.get("picks") or []) == []

    def test_quelltext_greift_nirgends_mehr_hart_auf_picks_zu(self):
        """Regressions-Anker: ein harter Zugriff wäre der nächste Absturz an derselben Stelle.

        Über den AST, nicht über Textsuche — sonst schlägt der Test auf dem Kommentar an, der
        den Bug beschreibt, und man baut ihn schweigend wieder ein, um den Test grün zu kriegen.
        """
        import ast
        baum = ast.parse(open(R.__file__, encoding="utf-8").read())
        hart = [n for n in ast.walk(baum)
                if isinstance(n, ast.Subscript)
                and isinstance(n.slice, ast.Constant)
                and n.slice.value in ("picks", "dateIso")]
        assert not hart, ["Zeile %d" % n.lineno for n in hart]


class TestGuard:
    """Guard-auf-jeden-Bug: dass der Resolver still stirbt, muss sichtbar werden."""

    def test_grosser_rueckstand_wird_rot(self):
        import wm_data_integrity as W
        heute = datetime.date(2026, 8, 27)
        hist = [{"dateIso": "2026-08-01", "resolved": False} for _ in range(30)]
        offen, aeltester = W._picks_history_open(hist, heute)
        assert offen == 30 and aeltester == datetime.date(2026, 8, 1)
        assert offen > W.RESOLVE_MAX_OPEN

    def test_frisch_gespielt_zaehlt_nicht(self):
        """Ein Spiel von gestern ist noch kein Rückstand — sonst ist der Guard nur Lärm."""
        import wm_data_integrity as W
        hist = [{"dateIso": "2026-08-26", "resolved": False}]
        assert W._picks_history_open(hist, datetime.date(2026, 8, 27))[0] == 0

    def test_aufgeloeste_zaehlen_nicht(self):
        import wm_data_integrity as W
        hist = [{"dateIso": "2026-06-01", "resolved": True} for _ in range(50)]
        assert W._picks_history_open(hist, datetime.date(2026, 8, 27))[0] == 0

    def test_muell_wirft_nicht(self):
        import wm_data_integrity as W
        assert W._picks_history_open([None, "x", 5, {}, {"dateIso": "kaputt"}],
                                     datetime.date(2026, 8, 27)) == (0, None)

    def test_guard_ist_registriert(self):
        import wm_data_integrity as W
        assert any(f.__name__ == "check_picks_resolved" for f in W.INTEGRITY_CHECKS)
