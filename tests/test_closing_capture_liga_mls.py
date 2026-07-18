"""17.07.2026 — 🔴 CLV war für Liga + MLS wochenlang TOT.

BEFUND (Lucas: „check ob mit den 2 Spielen was passiert bzgl. Lernen"): Nach den ersten drei
MLS-Spielen war `mls_closing_lines.json` leer. Ursache: `fetch_liga_odds.build_odds_entry` rief
`compute_closing(existing, cur, None, now_iso)` — `hours_to_ko` war HART None. compute_closing
entscheidet daran, ob ein Closing provisional (pre-match im Fenster) oder final (nach Anpfiff)
wird; mit None fällt es durch alle Zweige und gibt None zurück → `odds_closing` wurde NIE gesetzt
→ keine closing_lines → **kein CLV**.

Belegt am Live-Stand: WM 100/104 Odds mit Closing (84 final), Liga 0/48, MLS 0/30. Die WM nutzt
einen eigenen Fetcher (fetch_wm_odds) und war nie betroffen — deshalb sah der Status gesund aus.

⚠️ Die eigentliche Lehre (Lucas: „wild, dass wir das die ganze Zeit falsch hatten trotz Audits"):
Alle bisherigen Audits prüften, ob DATEIEN richtig verdrahtet sind — keiner, ob am Ende DATEN
ankommen. Deshalb zusätzlich der Guard check_closing_capture_alive.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def F():
    os.environ["COCOBET_DATASET"] = "mls"
    import importlib
    import cocobet_dataset
    importlib.reload(cocobet_dataset)
    import fetch_liga_odds as _F
    importlib.reload(_F)
    return _F


PREISE = {"hw": 1.90, "dr": 3.40, "aw": 4.00, "bookmaker": "pinnacle"}


def _iso(dt):
    return dt.isoformat()


class TestClosingEntsteht:
    def test_vor_anpfiff_provisional(self, F):
        now = datetime.now(timezone.utc)
        e = F.build_odds_entry(PREISE, {}, _iso(now),
                               kickoff=_iso(now + timedelta(minutes=40)))
        cl = e.get("odds_closing")
        assert cl, "kein Closing erzeugt — hours_to_ko kommt nicht an"
        assert not cl.get("final"), "vor Anpfiff darf es nicht final sein"

    def test_nach_anpfiff_wird_final(self, F):
        now = datetime.now(timezone.utc)
        pre = F.build_odds_entry(PREISE, {}, _iso(now),
                                 kickoff=_iso(now + timedelta(minutes=40)))
        post = F.build_odds_entry(PREISE, pre, _iso(now),
                                  kickoff=_iso(now - timedelta(minutes=30)))
        assert (post.get("odds_closing") or {}).get("final"), \
            "nach Anpfiff muss das provisional Closing final werden (CLV-Basis)"

    def test_ohne_kickoff_kein_absturz(self, F):
        e = F.build_odds_entry(PREISE, {}, datetime.now(timezone.utc).isoformat(), kickoff=None)
        assert isinstance(e, dict)   # darf nur kein Closing setzen, aber nicht krachen

    def test_finales_closing_wird_nie_ueberschrieben(self, F):
        """Ein final eingefrorenes Closing ist die CLV-Wahrheit — In-Play darf es nie kippen."""
        now = datetime.now(timezone.utc)
        pre = F.build_odds_entry(PREISE, {}, _iso(now), kickoff=_iso(now + timedelta(minutes=40)))
        fin = F.build_odds_entry(PREISE, pre, _iso(now), kickoff=_iso(now - timedelta(minutes=30)))
        spaeter = F.build_odds_entry({**PREISE, "hw": 1.20}, fin, _iso(now),
                                     kickoff=_iso(now - timedelta(hours=2)))
        assert spaeter["odds_closing"] == fin["odds_closing"], "finales Closing wurde überschrieben"

    def test_hours_to_kickoff_rechnet_richtig(self, F):
        now = datetime(2026, 7, 17, 20, 0, tzinfo=timezone.utc)
        assert F._hours_to_kickoff("2026-07-17T22:00:00+00:00", _iso(now)) == pytest.approx(2.0)
        assert F._hours_to_kickoff("2026-07-17T19:00:00+00:00", _iso(now)) == pytest.approx(-1.0)
        assert F._hours_to_kickoff(None, _iso(now)) is None
        assert F._hours_to_kickoff("kaputt", _iso(now)) is None


class TestGuardMerktEsBeimNaechstenMal:
    """Der Guard, der gefehlt hat: prüft ob DATEN ankommen, nicht ob Pfade stimmen."""

    def _ctx(self, gespielt: int, closing: dict, tage_alt: int = 2):
        import wm_data_integrity as W
        d = (datetime.now(timezone.utc) - timedelta(days=tage_alt)).date().isoformat()
        fixtures = [{"home": f"h{i}", "away": f"a{i}", "date": d,
                     "result": {"status": "FT", "home_score": 1, "away_score": 0}}
                    for i in range(gespielt)]
        wm = {"groups": {"MLS": {"fixtures": fixtures, "teams": []}},
              "odds": {f"h{i}-a{i}": {"hw": 1.9} for i in range(gespielt)},
              "_meta": {"profile": "mls_default"}}
        ctx = W.IntegrityCtx(wm=wm, poly={}, schedule={}, venues={}, history={}, streaks={})
        return W, ctx, closing

    def test_alarm_wenn_gespielt_aber_keine_closing_lines(self, monkeypatch):
        W, ctx, _ = self._ctx(gespielt=5, closing={})
        monkeypatch.setattr(W, "_lazy", lambda *_a, **_k: {})
        r = W.check_closing_capture_alive(ctx)
        assert not r["ok"], "toter CLV wird nicht erkannt"
        assert "LEER" in r["failures"][0]

    def test_still_wenn_noch_nichts_gespielt(self, monkeypatch):
        """Liga vor Saisonstart: keine Spiele → kein Alarm (sonst Dauer-Gelb)."""
        W, ctx, _ = self._ctx(gespielt=0, closing={})
        monkeypatch.setattr(W, "_lazy", lambda *_a, **_k: {})
        assert W.check_closing_capture_alive(ctx)["ok"]

    def test_gruen_wenn_closing_da(self, monkeypatch):
        W, ctx, cl = self._ctx(gespielt=5, closing={f"h{i}-a{i}": {"final": True} for i in range(5)})
        monkeypatch.setattr(W, "_lazy", lambda *_a, **_k: cl)
        assert W.check_closing_capture_alive(ctx)["ok"]
