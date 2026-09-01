"""tests/test_wallet_gedaechtnis.py — 01.09.2026

Lucas: „die Whales Wallets ändern sich eh, sobald z.B. eine bessere erscheinen würde, oder?"

Ja — der Pool wächst automatisch. Beim Nachsehen fiel aber auf, was der Track NICHT konnte:
`{n, wins, clvSumPP, usd, pnl}` trug keinen einzigen Zeitstempel. Man konnte weder sagen, wann eine
gerankte Wallet zuletzt aktiv war, noch ob sie zuletzt schlechter liefert als über ihre Lebenszeit
(eine Wallet mit n=622 wird auf ihrer ganzen Historie beurteilt — eine schwache Phase geht im
Mittel unter).

Diese Tests halten fest, was das neue Gedächtnis leisten muss und wo es bewusst schweigt.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

import poly_money_broad as P  # noqa: E402

TAG = datetime(2026, 9, 1, 14, 30, tzinfo=timezone.utc)


def score(n=9, **extra):
    d = {"n": n, "clvSumPP": 0.0, "wins": 0, "usd": 0}
    d.update(extra)
    return d


class TestZeitstempel:
    def test_erste_aufloesung_setzt_beide_stempel(self):
        s = score()
        P._wallet_zeit(s, 1.5, True, TAG)
        assert s["firstTs"] == "2026-09-01" and s["lastTs"] == "2026-09-01"

    def test_firstTs_bleibt_stehen_lastTs_zieht_mit(self):
        s = score(firstTs="2026-08-01", lastTs="2026-08-20")
        P._wallet_zeit(s, 1.0, False, TAG)
        assert s["firstTs"] == "2026-08-01", "der Beobachtungsbeginn wird nie überschrieben"
        assert s["lastTs"] == "2026-09-01"

    def test_auch_duenne_wallets_bekommen_zeitstempel(self):
        # Die Stille-Anzeige soll für JEDE Wallet gehen, auch für die 2.573 unter n=8.
        s = score(n=3)
        P._wallet_zeit(s, 4.0, True, TAG)
        assert s["lastTs"] == "2026-09-01"


class TestFenster:
    def test_erst_ab_ranglisten_reife_wird_gesammelt(self):
        # 2.573 Wallets liegen unter n=8; ein Fenster für alle würde die Datei vervielfachen.
        s = score(n=P.WALLET_FENSTER_AB_N - 1)
        P._wallet_zeit(s, 9.9, True, TAG)
        assert "recent" not in s

    def test_ab_der_schwelle_wird_gesammelt(self):
        s = score(n=P.WALLET_FENSTER_AB_N)
        P._wallet_zeit(s, 2.5, True, TAG)
        assert s["recent"] == [["2026-09-01", 2.5, 1]]

    def test_fenster_laeuft_ueber_und_behaelt_die_JUENGSTEN(self):
        s = score(n=50)
        for i in range(P.WALLET_FENSTER + 12):
            P._wallet_zeit(s, float(i), i % 2 == 0, TAG)
        assert len(s["recent"]) == P.WALLET_FENSTER
        assert s["recent"][-1][1] == float(P.WALLET_FENSTER + 11), "die neueste bleibt"
        assert s["recent"][0][1] == 12.0, "die ältesten fallen raus"

    def test_liste_wird_NICHT_in_place_mutiert(self):
        # update_wallet_track kopiert die scores nur flach (dict(s)) — eine in-place mutierte Liste
        # wäre dieselbe wie in `prev` und würde die Vorgänger-Daten rückwirkend verändern.
        alt = [["2026-08-30", 1.0, 1]]
        s = score(n=20, recent=alt)
        P._wallet_zeit(s, 2.0, False, TAG)
        assert alt == [["2026-08-30", 1.0, 1]], "die übergebene Liste bleibt unberührt"
        assert len(s["recent"]) == 2


class TestFensterBilanz:
    def test_leeres_fenster_behauptet_nichts(self):
        assert P.fenster_bilanz(score()) is None
        assert P.fenster_bilanz(score(recent=[])) is None
        assert P.fenster_bilanz(None) is None

    def test_rechnet_clv_und_treffer_der_letzten_aufloesungen(self):
        s = score(n=30, recent=[["2026-08-30", 2.0, 1], ["2026-08-31", -1.0, 0],
                                ["2026-09-01", 5.0, 1]])
        b = P.fenster_bilanz(s)
        assert b["n"] == 3
        assert abs(b["clv"] - 2.0) < 1e-9
        assert abs(b["hit"] - 0.6667) < 1e-3
        assert b["von"] == "2026-08-30" and b["bis"] == "2026-09-01"

    def test_liefert_n_mit_damit_der_aufrufer_selbst_urteilt(self):
        # Bewusst KEIN Urteil in der Funktion: ein Fenster mit 3 Einträgen ist kein Beleg,
        # und wer es benutzt, muss das selbst entscheiden können.
        b = P.fenster_bilanz(score(n=9, recent=[["2026-09-01", 9.0, 1]]))
        assert b["n"] == 1 and b["clv"] == 9.0

    def test_kaputte_eintraege_kippen_die_bilanz_nicht(self):
        s = score(n=30, recent=[["2026-09-01", 2.0, 1], "kaputt", ["2026-09-01"], None])
        b = P.fenster_bilanz(s)
        assert b["n"] == 1 and b["clv"] == 2.0


class TestVerdrahtung:
    def test_werten_einer_position_schreibt_das_gedaechtnis_mit(self):
        """Der Test, der zählt: greift es im echten update_wallet_track?"""
        w = "0xabc"
        prev = {"open": {f"{w}|k1|A": {"wallet": w, "key": "k1", "side": "A", "league": "L",
                                       "firstPrice": 0.40, "entryPrice": 0.40,
                                       "lastPrice": 0.55, "usd": 5000,
                                       "firstTs": "2026-08-31T10:00:00+00:00"}},
                "scores": {w: {"n": 10, "clvSumPP": 5.0, "wins": 6, "usd": 40000}}}
        markets = [{"key": "k1", "resolved": True, "resolvedPrices": {"A": 1.0, "B": 0.0},
                    "prices": {"A": 0.55, "B": 0.45}}]
        out = P.update_wallet_track(prev, markets, now=TAG)
        s = out["scores"][w]
        assert s["n"] == 11, "die Auflösung ist gezählt"
        assert s["lastTs"] == "2026-09-01", "und der Zeitstempel steht"
        assert s["recent"] and s["recent"][-1][2] == 1, "Gewinn im Fenster vermerkt"
