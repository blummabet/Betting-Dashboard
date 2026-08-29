"""29.08.2026 (Lucas, Status-Tab):

    🟡 408/457 'bewiesene' Wallets ohne P&L-Daten
       — Confirmed-Loser-Gate ist für sie blind

Zwei Fehler steckten darin, und beide waren still.

1. DIE SCHWELLE STIMMTE NICHT. `PROVEN_MIN_TR` stand auf 3, mit dem Kommentar
   „= poly_whale_watch MIN_TR". Lucas hatte das echte Push-Gate aber am 02.08. auf 8 gehoben
   („2/3 ist kein Beweis"). Der Guard maß dadurch 457 Wallets, von denen nur 159 ueberhaupt
   je gepusht werden koennen — die Zahl war aufgeblasen.

2. DAS BUDGET GING JEDEN LAUF AN DIESELBEN. `enrich_wallet_pnl` sortierte die Kandidaten rein
   nach Historie (-n) und holte davon die ersten 60. Also bekam jeder Lauf erneut die Top-60,
   und Platz 61 aufwaerts nie einen Wert. Gemessen: 48 von 159 hatten einen P&L — und durch
   blosses Weiterlaufen haette sich daran nichts geaendert. Das ist die Sorte Fehler, die wie
   „braucht halt noch Zeit" aussieht und in Wahrheit nie fertig wird.
"""
import os
import sys
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import poly_money_broad as B


def scores(*paare):
    """(n, pnl) → scores-Dict mit Adressen w0, w1, …"""
    return {f"w{i}": ({"n": n} if pnl is None else {"n": n, "pnl": pnl})
            for i, (n, pnl) in enumerate(paare)}


def lauf(sc, budget, min_n=5):
    """enrich_wallet_pnl mit gezaehlten Abrufen; liefert die abgefragten Wallets in Reihenfolge."""
    geholt = []

    def get(url):
        for w in sc:
            if w in url:
                geholt.append(w)
                break
        # Form der echten user-pnl-Antwort: Liste kumulierter Punkte, letzter zaehlt.
        return [{"t": 1, "p": 1.0}]

    B.enrich_wallet_pnl(sc, get, [budget], min_n=min_n)
    return geholt


class TestBudgetGehtAnDieUnbekannten:
    def test_wallet_ohne_pnl_kommt_vor_wallet_mit_pnl(self):
        """Der Kern: der Grosse hat schon einen Wert, der Kleine noch nicht."""
        sc = scores((99, 123.0), (10, None))
        assert lauf(sc, budget=1) == ["w1"]

    def test_alle_unbekannten_zuerst_dann_auffrischen(self):
        sc = scores((90, 5.0), (80, None), (70, None))
        assert lauf(sc, budget=3) == ["w1", "w2", "w0"]

    def test_unter_den_unbekannten_gewinnt_die_laengere_historie(self):
        sc = scores((10, None), (50, None), (30, None))
        assert lauf(sc, budget=2) == ["w1", "w2"]

    def test_zwei_laeufe_decken_alles_ab(self):
        """Vorher deckte kein noch so langer Betrieb die Nachzuegler ab."""
        sc = scores(*[(100 - i, None) for i in range(5)])
        lauf(sc, budget=3)
        lauf(sc, budget=3)
        assert all(isinstance(v.get("pnl"), (int, float)) for v in sc.values())

    def test_alte_reihenfolge_haette_die_nachzuegler_nie_erreicht(self):
        """Gegenprobe auf den alten Zustand: rein nach -n sortiert, Budget 1, zwei Laeufe."""
        sc = scores((99, 7.0), (10, None))
        alt = sorted(sc, key=lambda w: -(sc[w].get("n") or 0))
        assert alt[0] == "w0", "Sortierung nach -n holt den, der laengst einen Wert hat"
        assert lauf(sc, budget=1) == ["w1"], "neue Sortierung holt den Nachzuegler"


class TestBudgetUndSchwelleBleibenGewahrt:
    def test_budget_wird_eingehalten(self):
        sc = scores(*[(50, None)] * 10)
        assert len(lauf(sc, budget=4)) == 4

    def test_wallets_unter_min_n_werden_nicht_geholt(self):
        sc = scores((2, None), (50, None))
        assert lauf(sc, budget=5) == ["w1"]

    def test_kaputte_eintraege_kippen_nicht_um(self):
        sc = {"w0": None, "w1": "muell", "w2": {"n": 50}}
        assert lauf(sc, budget=5) == ["w2"]

    def test_leere_scores(self):
        assert B.enrich_wallet_pnl({}, lambda u: None, [5]) == 0
        assert B.enrich_wallet_pnl(None, lambda u: None, [5]) == 0


class TestGuardMisstDasEchtePushGate:
    def test_proven_schwelle_folgt_dem_whale_gate(self):
        """Die beiden Zahlen sind ueber Jahre auseinandergelaufen — jetzt teilen sie die Quelle."""
        import poly_data_integrity as P
        import poly_whale_watch as WW
        assert P.PROVEN_MIN_TR == WW.MIN_TR, (
            f"Guard misst n>={P.PROVEN_MIN_TR}, gepusht wird ab n>={WW.MIN_TR} — "
            "der Guard beurteilt Wallets, die nie einen Push ausloesen")

    def test_env_override_bleibt_moeglich(self, monkeypatch):
        monkeypatch.setenv("POLY_PROVEN_MIN_TR", "4")
        for m in list(sys.modules):
            if m.startswith("poly_data_integrity"):
                del sys.modules[m]
        import poly_data_integrity as P2
        assert P2.PROVEN_MIN_TR == 4
        for m in list(sys.modules):
            if m.startswith("poly_data_integrity"):
                del sys.modules[m]
