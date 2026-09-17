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


# ── Tages-Gedaechtnis (17.09.2026) ────────────────────────────────────────────────────────────
# Lucas: „der war die Woche nicht so gut, aber in dem Monat 600K vorn — also weiss nicht, wonach
# wir genau tracken, welchen Timeframe."
#
# Gemessen, bevor daraus ein Urteil wurde: das 30er-Fenster sagt die naechsten Aufloesungen
# SCHLECHTER voraus als der kumulative Schnitt (Fehler 1,06 gegen 0,74 pp ueber 65 Wallets mit
# vollem Fenster; die beste Mischung liegt bei 10 % Fenster). Der Grund steckt in der Einheit:
# ein volles 30er-Fenster deckt im Median sechs Tage ab. „Letzte 30 Aufloesungen" ist kein
# Zeitraum — und kann „diesen Monat gegen letzten" gar nicht beantworten.
#
# Deshalb waechst ein Tages-Gedaechtnis mit, und deshalb urteilt es NICHT.

def _tage_score(**extra):
    d = {"n": 9, "clvSumPP": 0.0, "wins": 0, "usd": 0}
    d.update(extra)
    return d


def test_jeder_tag_bekommt_seine_eigene_zeile():
    s = _tage_score()
    P._wallet_zeit(s, 2.0, True, "2026-09-10")
    P._wallet_zeit(s, -1.0, False, "2026-09-10")
    P._wallet_zeit(s, 3.0, True, "2026-09-15")
    assert s["tage"] == {"2026-09-10": [2, 1.0, 1, 5.0], "2026-09-15": [1, 3.0, 1, 9.0]}


def test_unter_der_reifegrenze_wird_nichts_gesammelt():
    """Dieselbe Schranke wie beim Fenster: 2.500 Wallets mit n<8 wuerden die Datei sprengen."""
    s = _tage_score(n=3)
    P._wallet_zeit(s, 2.0, True, "2026-09-10")
    assert "tage" not in s


def test_das_gedaechtnis_endet_nach_der_aufbewahrungsfrist():
    s = _tage_score()
    for i in range(1, 70):
        P._wallet_zeit(s, 1.0, True, "2026-%02d-%02d" % (6 + i // 30, 1 + i % 28))
    assert len(s["tage"]) <= P.WALLET_TAGE_KEEP


def test_ein_zeitraum_rechnet_nur_seine_tage():
    s = _tage_score()
    for tag, clv, win in (("2026-09-01", 9.0, True), ("2026-09-15", 3.0, True),
                          ("2026-09-17", 1.0, False)):
        P._wallet_zeit(s, clv, win, tag)
    w = P.zeitraum_bilanz(s, "2026-09-17", 7)
    assert w["n"] == 2 and w["clv"] == 2.0, w
    m = P.zeitraum_bilanz(s, "2026-09-17", 30)
    assert m["n"] == 3 and m["hit"] == round(2 / 3, 4)


def test_ohne_daten_im_zeitraum_wird_nichts_behauptet():
    s = _tage_score()
    P._wallet_zeit(s, 9.0, True, "2026-07-01")
    assert P.zeitraum_bilanz(s, "2026-09-17", 7) is None
    assert P.zeitraum_bilanz({}, "2026-09-17", 7) is None
    assert P.zeitraum_bilanz(None, "2026-09-17", 7) is None
    assert P.zeitraum_bilanz(s, "kaputt", 7) is None


def test_eine_untergrenze_gibt_es_nur_mit_streuung():
    """Ein Schnitt ohne Schranke ist kein Beleg — auch hier nicht."""
    s = _tage_score()
    for i in range(3):
        P._wallet_zeit(s, 2.0, True, "2026-09-%02d" % (10 + i))
    assert P.zeitraum_bilanz(s, "2026-09-17", 30)["clvUg"] is None
    for i in range(3, 10):
        P._wallet_zeit(s, 2.0 + (i % 3), True, "2026-09-%02d" % (10 + i))
    w = P.zeitraum_bilanz(s, "2026-09-19", 30)
    assert w["clvUg"] is not None
    assert w["clvUg"] < w["clv"], "die Untergrenze muss unter dem Schnitt liegen"


def test_kaputte_zeilen_kippen_die_bilanz_nicht():
    s = _tage_score(tage={"2026-09-16": ["x", None, 1, 0], "2026-09-17": [2, 4.0, 2, 8.0]})
    w = P.zeitraum_bilanz(s, "2026-09-17", 7)
    assert w["n"] == 2 and w["clv"] == 2.0


def test_das_gedaechtnis_haengt_an_keiner_sperre():
    """Der wichtigste Test der Datei: gemessen ist das Fenster SCHLECHTER als der kumulative
    Schnitt. Wer es trotzdem als Gate anschliesst, soll hier anschlagen und die Messung
    wiederholen muessen."""
    import subprocess
    roots = subprocess.run(["grep", "-rn", "zeitraum_bilanz", "--include=*.py", "--include=*.js",
                            str(BASE)], capture_output=True, text=True).stdout.splitlines()
    fremd = [z for z in roots
             if "poly_money_broad.py" not in z and "test_wallet_gedaechtnis" not in z]
    assert not fremd, "das Tages-Gedaechtnis urteilt woanders mit: %s" % fremd
