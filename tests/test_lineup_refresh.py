"""
test_lineup_refresh.py — Match-Day Signal-Refresh (Fix 13.06.2026)

Regression-Schutz für das Loch, das verhinderte, dass lineup_signal (T-1h) je in
die Picks/Conviction/Bayesian-Ledger kam: heutige Spiele mit vorhandenen Picks
wurden komplett eingefroren (continue), BEVOR die Aufstellungen am Spieltag kamen.

Fix: Freeze erst NACH Anpfiff. Pre-Kickoff am Spieltag werden Märkte+Quoten
eingefroren gelassen, aber Signale + Conviction neu bewertet → lineup_signal fließt
ein. Idempotent über baseVerdict.

Der Test nutzt CAN-BIH (committete Lineups haben Džeko auf der Bank + squad[BIH]
kennt ihn als Top-Scorer) und prüft den ganzen Pfad über generate_wm_picks.main().
"""
import json
import shutil
import datetime
import io
import contextlib
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


class TestMatchDayLineupRefresh(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = REPO / "wm2026-data.json"
        cls.lineups = REPO / "wm_lineups.json"
        if not cls.data.exists() or not cls.lineups.exists():
            raise unittest.SkipTest("wm2026-data.json / wm_lineups.json fehlen")
        wm = json.loads(cls.data.read_text(encoding="utf-8"))
        lu = json.loads(cls.lineups.read_text(encoding="utf-8"))
        # Vorbedingungen: CAN-BIH Lineups vorhanden + Džeko auf Bank + squad kennt ihn
        cb = lu.get("CAN-BIH") or {}
        squad_bih = (wm.get("squads") or {}).get("BIH") or {}
        subs = (cb.get("away") or {}).get("subs") or []
        if not subs or not squad_bih.get("name"):
            raise unittest.SkipTest("CAN-BIH Lineup/Squad-Vorbedingung nicht erfüllt")

    def _prep_tmp(self, tmp: Path, kickoff_dt: datetime.datetime):
        """Kopiert benötigte JSONs + cocobet_config in tmp, setzt CAN-BIH auf heute +
        gegebenen Kickoff mit einem Pick OHNE lineup_signal. Gibt patched WM_FILE."""
        for f in REPO.glob("*.json"):
            shutil.copy(f, tmp / f.name)
        cfg = REPO / "cocobet_config.json"
        if cfg.exists():
            shutil.copy(cfg, tmp / cfg.name)
        wmp = tmp / "wm2026-data.json"
        wm = json.loads(wmp.read_text(encoding="utf-8"))
        today = _utc_now().date().isoformat()
        ko = kickoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        for g in wm["groups"].values():
            for f in g["fixtures"]:
                if {f["home"], f["away"]} == {"CAN", "BIH"}:
                    f["date"] = today
                    f["kickoff"] = ko
                    f["time"] = "22:00"
        wm["picks"]["B-1-CAN-BIH"] = [{
            "market": "Über 2.5 Tore", "verdict": "BET", "odds": 2.0,
            "modelOdds": 1.8, "edgePP": 5.0, "conf": 3, "dataQuality": "high",
            "signals": [{"name": "form_trend", "score": 1.0, "confidence": 0.6,
                         "evidence": "x", "weight": 1.0, "weighted_score": 0.6,
                         "metadata": {}}],
        }]
        wmp.write_text(json.dumps(wm, ensure_ascii=False), encoding="utf-8")
        return wmp

    @staticmethod
    def _run(wmp: Path):
        import generate_wm_picks as G
        G.WM_FILE = wmp
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            G.main()
        return buf.getvalue()

    def test_pre_kickoff_rebuild_keeps_lineup_signal(self):
        """FIX 15.06.2026 (Lucas): heutige POST-Cutover-Spiele (Anpfiff > Steam-Cutover)
        werden nicht mehr eingefroren, sondern FREI mit Steam neu gebaut. Entscheidend
        bleibt: die Signal-Engine läuft auch beim Rebuild → lineup_signal (T-1h) fließt
        weiterhin in den Pick + Conviction + Bayesian-Ledger. Markt/Verdict dürfen jetzt
        aus Steam kommen (kein eingefrorener Markt mehr)."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            # +3h ⇒ heute, Anpfiff nach dem Steam-Cutover (15.06 00:00Z) ⇒ rebuild
            wmp = self._prep_tmp(tmp, _utc_now() + datetime.timedelta(hours=3))
            self._run(wmp)
            p = json.loads(wmp.read_text(encoding="utf-8"))["picks"]["B-1-CAN-BIH"][0]
            names = [s["name"] for s in p.get("signals", [])]
            # Kern-Garantie: lineup_signal überlebt den Rebuild (Lern-Loop bleibt gefüttert)
            self.assertIn("lineup_signal", names,
                          "lineup_signal fehlt nach Steam-Rebuild — Lern-Loop-Leck")

    def test_idempotent_across_runs(self):
        """Steam-Rebuild ist deterministisch: mehrfaches Laufen darf den Verdict nicht
        flattern lassen (gleicher Snapshot → gleicher Pick)."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            wmp = self._prep_tmp(tmp, _utc_now() + datetime.timedelta(hours=3))
            self._run(wmp)
            v1 = json.loads(wmp.read_text(encoding="utf-8"))["picks"]["B-1-CAN-BIH"][0]["verdict"]
            self._run(wmp)
            self._run(wmp)
            p = json.loads(wmp.read_text(encoding="utf-8"))["picks"]["B-1-CAN-BIH"][0]
            self.assertEqual(p["verdict"], v1, "Verdict flattert über mehrere Rebuild-Läufe")

    def test_post_kickoff_stays_frozen(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            wmp = self._prep_tmp(tmp, _utc_now() - datetime.timedelta(hours=1))
            # Marker setzen, der bei jedem Refresh überschrieben würde
            wm = json.loads(wmp.read_text(encoding="utf-8"))
            wm["picks"]["B-1-CAN-BIH"][0]["verdict"] = "FROZEN_MARKER"
            wmp.write_text(json.dumps(wm, ensure_ascii=False), encoding="utf-8")
            self._run(wmp)
            p = json.loads(wmp.read_text(encoding="utf-8"))["picks"]["B-1-CAN-BIH"][0]
            self.assertEqual(p["verdict"], "FROZEN_MARKER",
                             "Post-Kickoff-Pick wurde verändert — Freeze greift nicht")


if __name__ == "__main__":
    unittest.main()
