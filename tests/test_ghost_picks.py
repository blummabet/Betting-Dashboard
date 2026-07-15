"""14.07.2026 — Picks, die aus PLATZHALTER-Quoten geboren wurden.

BEFUND (Lucas: „check nochmal alles was mit MLS zu tun hat"): Beide existierenden MLS-Picks waren
Geister. Ihre Karten-Texte behaupteten Moves, die es nie gab:
    „📉 Pinnacle 1.17→2.27 · Sharp-Money-Drop +25.0pp"
Die echte (geheilte) Eröffnung war 2.30 — 1.17 war ein API-Platzhalter (Overround 270 %).
Erzeugt am 09.07., also VOR dem Plausibilitäts-Guard in steam_engine. Neue Geister können nicht
mehr geboren werden — aber `_carry_nobet` schleppt NOBET-Picks „über Rebuilds bis Anpfiff" mit.

⚠️ DIE LEHRE AUS DEM ERSTEN VERSUCH: Ich wollte zuerst über die MOVE-GRÖSSE filtern (>20pp).
Das hätte DREI legitime Picks vernichtet — WM „Über 3.5" (23pp), Liga (48pp und 44pp). Deren
Eröffnungen sind nachweislich echt (Overround 1.07); Linien reifen über Wochen tatsächlich von
5.64 auf 1.50. **Ein großer Move ist kein Beweis für einen Geist.**

Das Kriterium ist die QUELLE, nicht die Größe:
  (a) 1X2: gespeicherte Eröffnung passt nicht zur geheilten odds_open  → Geist
  (b) irgendeine Quote < 1.05 (Plausibilitätsgrenze)                    → Geist
(a) gilt NUR für 1X2: bei Tor-Märkten/AH kann die Linie abgeleitet sein, dort ist die Zuordnung
Markt→Quote nicht eindeutig (vier WM-O/U-Picks wären sonst zu Unrecht entsorgt worden).
"""
import json
from pathlib import Path

import pytest

from generate_wm_picks import _is_ghost_pick

REPO = Path(__file__).resolve().parent.parent


def _snap(hw=2.70, dr=3.50, aw=2.30, **rest):
    return {"odds_open": {"hw": hw, "dr": dr, "aw": aw, **rest}}


class TestGeisterErkennung:
    def test_der_echte_mls_geist_eroeffnung_passt_nicht(self):
        """MLS-17-1607-1603: Pick behauptet Eröffnung 1.17, echt war 2.30."""
        pick = {"market": "Auswärtssieg", "steamOpen": 1.17, "steamCur": 2.27,
                "steamMovePP": 25.0, "verdict": "NOBET", "result": None}
        assert _is_ghost_pick(pick, _snap(aw=2.30)) is True

    def test_der_zweite_mls_geist_quote_unter_der_grenze(self):
        """MLS-17-9569-1608: steamCur 1.04 — so kurz notiert kein echter Markt."""
        pick = {"market": "AH Heim −1.5", "steamOpen": 1.36, "steamCur": 1.04,
                "steamMovePP": 26.2, "verdict": "NOBET", "result": None}
        assert _is_ghost_pick(pick, _snap(hw=1.36)) is True


class TestKeineFehlalarme:
    """Die drei Picks, die mein erster (falscher) 20pp-Filter vernichtet hätte."""

    def test_grosser_move_mit_echter_eroeffnung_bleibt(self):
        # Liga ITA: 5.64 → 1.50 = 48.9pp. Eröffnung 5.64 stimmt mit odds_open überein → echt.
        pick = {"market": "Auswärtssieg", "steamOpen": 5.64, "steamCur": 1.50,
                "steamMovePP": 48.9, "verdict": "NOBET", "result": None}
        assert _is_ghost_pick(pick, _snap(hw=1.52, dr=4.31, aw=5.64)) is False

    def test_torpick_mit_abgeleiteter_linie_bleibt(self):
        """WM „Über 2.5": steamOpen 4.0, odds_open.o25 = 2.11 — die Linie ist abgeleitet, die
        Zuordnung Markt→Quote also NICHT eindeutig. Darf kein Geist sein."""
        pick = {"market": "Über 2.5 Tore", "steamOpen": 4.0, "steamCur": 3.45,
                "steamMovePP": 3.2, "verdict": "NOBET", "result": None}
        assert _is_ghost_pick(pick, _snap(o25=2.11)) is False

    def test_aufgeloester_pick_bleibt_immer(self):
        """Was gelaufen ist, bleibt in der Bilanz — auch wenn es ein Geist war."""
        pick = {"market": "Auswärtssieg", "steamOpen": 1.17, "steamCur": 2.27,
                "result": "LOSS"}
        assert _is_ghost_pick(pick, _snap(aw=2.30)) is False

    def test_ohne_odds_snapshot_kein_raten(self):
        pick = {"market": "Auswärtssieg", "steamOpen": 1.17, "steamCur": 2.27, "result": None}
        assert _is_ghost_pick(pick, None) is False
        assert _is_ghost_pick(pick, {}) is False


class TestEchteDaten:
    """Gegen die echten Datensätze — der Filter darf NUR die MLS-Geister treffen."""

    @pytest.mark.parametrize("datei,erwartete_geister", [
        ("mls-data.json", 2),      # die beiden bekannten
        ("wm2026-data.json", 0),
        ("liga-data.json", 0),
    ])
    def test_nur_die_echten_geister(self, datei, erwartete_geister):
        p = REPO / datei
        if not p.exists():
            pytest.skip(f"{datei} nicht vorhanden")
        wm = json.loads(p.read_text("utf-8"))
        odds = wm.get("odds") or {}
        n = 0
        for key, plist in (wm.get("picks") or {}).items():
            fx = "-".join(key.split("-")[-2:])
            for pk in (plist if isinstance(plist, list) else [plist]):
                if isinstance(pk, dict) and _is_ghost_pick(pk, odds.get(fx) or {}):
                    n += 1
        assert n == erwartete_geister, f"{datei}: {n} Geister statt {erwartete_geister}"


class TestCarryEntferntSie:
    def test_carry_nobet_schleppt_geister_nicht_mit(self):
        """_carry_nobet hält NOBET-Picks „über Rebuilds bis Anpfiff" — Geister müssen dabei
        aussortiert werden, sonst überleben sie bis zum Anpfiff auf den Cards."""
        from generate_wm_picks import _carry_nobet
        geist = {"market": "Auswärtssieg", "steamOpen": 1.17, "steamCur": 2.27,
                 "verdict": "NOBET", "result": None}
        echt = {"market": "Heimsieg", "steamOpen": 2.70, "steamCur": 2.40,
                "verdict": "NOBET", "result": None}
        out = _carry_nobet([geist, echt], [], _snap(), "2026-07-14T00:00:00Z")
        markets = {p.get("market") for p in out}
        assert "Auswärtssieg" not in markets, "Geist überlebt den Rebuild"
        assert "Heimsieg" in markets, "echter NOBET darf NICHT verschwinden"
