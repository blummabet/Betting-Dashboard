"""20.07.2026 (MLS-Audit) — Guard gegen still sterbenden Lern-Loop. Unterscheidet „jung/keine
Resolves" (gesund) von „Resolves da, aber Ledger/Closing leer" (tot = CLV-für-MLS-war-tot-Klasse)."""
import check_learning_loop_alive as LLA


class TestEvaluate:
    def test_jung_keine_resolves_ist_gesund(self):
        assert LLA.evaluate(resolved=0, ledger_records=0, with_closing=0) == []
        assert LLA.evaluate(resolved=3, ledger_records=0, with_closing=0) == []   # < MIN_RESOLVED

    def test_resolves_aber_leerer_ledger_ist_tot(self):
        probs = LLA.evaluate(resolved=20, ledger_records=0, with_closing=5)
        assert len(probs) == 1 and "Ledger LEER" in probs[0]

    def test_resolves_aber_kein_closing_ist_tot(self):
        probs = LLA.evaluate(resolved=20, ledger_records=20, with_closing=0)
        assert len(probs) == 1 and "Closing" in probs[0]

    def test_beides_tot_meldet_zwei(self):
        probs = LLA.evaluate(resolved=20, ledger_records=0, with_closing=0)
        assert len(probs) == 2

    def test_gesunder_loop_ist_still(self):
        assert LLA.evaluate(resolved=20, ledger_records=20, with_closing=15) == []

    def test_eintraege_aber_null_bewertet_ist_tot(self):
        # 27.07.2026 (Lucas): der stille Bruch — Ledger voll, aber 0 prozess-bewertet.
        probs = LLA.evaluate(resolved=20, ledger_records=10, with_closing=5, graded=0)
        assert len(probs) == 1 and "0 prozess-bewertet" in probs[0]

    def test_bewertete_eintraege_sind_still(self):
        assert LLA.evaluate(resolved=20, ledger_records=10, with_closing=5, graded=6) == []

    def test_fertige_spiele_ohne_xg_ist_tot(self):
        probs = LLA.evaluate(resolved=20, ledger_records=10, with_closing=5,
                             graded=4, finished=100, finished_with_xg=0)
        assert any("0 mit Match-xG" in p for p in probs)

    def test_volle_xg_coverage_still(self):
        assert LLA.evaluate(resolved=20, ledger_records=10, with_closing=5,
                            graded=6, finished=100, finished_with_xg=100) == []

    def test_schwelle_einstellbar(self):
        assert LLA.evaluate(resolved=5, ledger_records=0, with_closing=0, min_resolved=3)


class TestCollect:
    def test_collect_liest_records_und_coverage(self, tmp_path, monkeypatch):
        import json
        (tmp_path / "l.json").write_text(json.dumps({"records": [1, 2, 3]}))
        (tmp_path / "c.json").write_text(json.dumps(
            {"overall": {"n": 9, "coverage": {"resolved": 9, "withClosing": 4}}}))
        monkeypatch.setattr(LLA, "BASE", tmp_path)
        m = LLA.collect("l.json", "c.json")
        assert m == {"resolved": 9, "ledger_records": 3, "with_closing": 4}

    def test_collect_fehlende_dateien_sind_null(self, tmp_path, monkeypatch):
        monkeypatch.setattr(LLA, "BASE", tmp_path)
        m = LLA.collect("nope.json", "nada.json")
        assert m == {"resolved": 0, "ledger_records": 0, "with_closing": 0}
