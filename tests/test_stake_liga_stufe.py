"""tests/test_stake_liga_stufe.py — 07.09.2026

Lucas: „ne 50k Wette auf Arsenal sagt 0 / Eine 50k Wette auf ein 2-3. Liga Team / Ist
zumindest jemand der mehr dran glaubt mmn."

Was hier schiefgehen kann, ist nicht die Rechnung, sondern die ZUORDNUNG:

 · Eine Liga, die nicht in der Tabelle steht, darf nicht wie eine oberste Spielklasse
   aussehen. Fehlende Information ist keine Erlaubnis — dieselbe Klasse, die im Repo schon
   mehrfach zugeschlagen hat.
 · Der Slug ist nicht sportartenrein: `bundesliga` gibt es im Feed als Fussball UND als
   Handball, `premier-league-srl` als Fussball und Cricket. Eine Handball-Wette darf keine
   Fussball-Spielklasse bekommen.
 · Der Referenzeinsatz muss sagen, WOHER er kommt. „3x der Norm" heisst etwas anderes, wenn
   die Norm aus 600 Wetten derselben Liga stammt, als wenn sie der Median der ganzen Ebene ist.
 · Ebene 1 und Ebene 2/3 laufen gegenlaeufig (gemessen 07.09.: -2,1 % -> -13,9 % gegen
   +7,5 % -> +46,7 %). Wer beide in eine Schublade wirft, mittelt genau den Unterschied weg —
   die Dilutions-Klasse aus CAPABILITIES §7. Deshalb ein Test, der die Trennung festhaelt.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import stake_liga_stufe as LS


def w(slug="championship", usd=10000.0, sport="soccer", liga=None, quote=2.0, pnl=None,
      event="A - B", kombi=False):
    d = {"ligaSlug": slug, "sport": sport, "liga": liga if liga is not None else slug,
         "einsatzUsd": usd, "quote": quote, "kombi": kombi, "event": event,
         "eventId": event, "markt": "Match Result", "auswahl": "A", "id": event + slug}
    if pnl is not None:
        d["abrechnung"] = {"pnlUsd": pnl, "beine": [{"status": "won" if pnl > 0 else "lost"}]}
    return d


# ── Zuordnung ────────────────────────────────────────────────────────────────
def test_ebenen_sitzen_richtig():
    assert LS.stufe("premier-league") == "1"
    assert LS.stufe("championship") == "2"        # zweite Klasse, obwohl grosser Markt
    assert LS.stufe("league-two") == "3"
    assert LS.randliga("championship") and LS.randliga("league-two")
    assert not LS.randliga("premier-league")


def test_unbekannte_liga_ist_none_und_nicht_ebene_1():
    """Der eigentliche Fehlerfall: eine neue Liga taucht auf und zaehlt still als Spitzenliga."""
    assert LS.stufe("liga-die-es-noch-nicht-gibt") is None
    assert LS.randliga("liga-die-es-noch-nicht-gibt") is False


def test_slug_ist_nicht_sportartenrein():
    """`bundesliga` ist im Feed Fussball UND Handball — die Handball-Zeile bekommt nichts."""
    assert LS.stufe("bundesliga", "soccer") == "1"
    assert LS.stufe("bundesliga", "handball") is None
    assert LS.stufe("premier-league-srl", "cricket") is None


def test_wettbewerbe_bekommen_eine_marke_statt_einer_zahl():
    assert LS.stufe("uefa-champions-league") == "kontinental"
    assert LS.stufe("fa-cup") == "pokal"
    assert LS.stufe("u20-womens-world-cup") == "jugend"
    assert LS.stufe("laliga-srl") == "srl"
    assert LS.stufe("women-bundesliga") == "frauen"
    # und keines davon zaehlt als Randliga, auch wenn es klein ist
    assert not LS.randliga("fa-cup")


def test_srl_faellt_nicht_als_echte_liga_durch():
    """Simulated Reality League sind simulierte Spiele. Sie duerfen nicht als Ebene 1 gelten,
    nur weil der Slug wie die echte Liga anfaengt."""
    for s in ("premier-league-srl", "laliga-srl", "serie-a-srl", "bundesliga-srl", "ligue-1-srl"):
        assert LS.stufe(s) == "srl", s


# ── Referenz ─────────────────────────────────────────────────────────────────
def test_referenz_nennt_ihre_basis():
    # Genug Zeilen je Ebene, damit BEIDE Ebenen einen Median haben — die Ebene-Norm
    # entsteht je Ebene, nicht global (der globale Median waere Tennis).
    wetten = ([w("championship", 2000.0) for _ in range(20)]
              + [w("league-two", 2000.0) for _ in range(20)])
    ebmed = LS.ebene_median(wetten)
    norm = {"Championship": {"basis": "gelernt", "median": 1000.0}}
    # eigene Liga-Norm vorhanden -> Basis "liga"
    f, basis = LS.faktor(w("championship", 5000.0, liga="Championship"), norm, ebmed)
    assert basis == "liga" and f == 5.0
    # keine Liga-Norm -> Median der EBENE, und das steht auch dran
    f2, basis2 = LS.faktor(w("league-two", 4000.0, liga="League Two"), {}, ebmed)
    assert basis2 == "ebene" and f2 == 2.0


def test_ohne_jede_basis_gibt_es_keinen_faktor():
    """Kein Rueckfall auf einen globalen Median: der wird von Tennis und E-Sport getragen."""
    f, basis = LS.faktor(w("league-two", 4000.0), {}, {})
    assert f is None and basis == "unbekannt"


def test_ebene_median_ignoriert_kombis_und_fremde_sportarten():
    wetten = ([w("championship", 2000.0) for _ in range(20)]
              + [w("championship", 999999.0, kombi=True)]
              + [w("bundesliga", 999999.0, sport="handball")])
    assert LS.ebene_median(wetten)["2"] == 2000.0


def test_ebene_median_erst_ab_min_n():
    assert LS.ebene_median([w("championship", 2000.0) for _ in range(LS.EBENE_MIN_N - 1)]) == {}


# ── Auswahl und Kreuztabelle ─────────────────────────────────────────────────
def test_kandidaten_nur_ebene_2_und_tiefer():
    basis = ([w("championship", 2000.0, liga="Championship") for _ in range(20)]
             + [w("league-two", 2000.0, liga="League Two") for _ in range(20)]
             + [w("premier-league", 2000.0, liga="Premier League") for _ in range(20)])
    wetten = basis + [w("premier-league", 500000.0, liga="Premier League", event="gross oben"),
                      w("league-two", 20000.0, liga="League Two", event="gross unten")]
    got = {k["event"] for k in LS.kandidaten(wetten, {})}
    assert "gross unten" in got
    assert "gross oben" not in got, "Ebene 1 gehoert in die andere Schublade, nicht hierher"


def test_kandidaten_zeigen_auch_die_verlierer():
    """Ohne Ausgangsfilter — sonst waere die Liste ihre eigene Erfolgsmeldung."""
    wetten = ([w("championship", 2000.0) for _ in range(20)]
              + [w("championship", 30000.0, pnl=-30000.0, event="daneben")])
    assert any(k["event"] == "daneben" for k in LS.kandidaten(wetten, {}))


def test_kreuz_trennt_die_gegenlaeufigen_ebenen():
    """Der Grund fuer zwei Schubladen: gemischt heben sich die Reihen auf."""
    wetten = []
    for i in range(20):
        wetten.append(w("premier-league", 2000.0, liga="Premier League"))
        wetten.append(w("championship", 2000.0, liga="Championship"))
    # oben gross und schlecht, unten gross und gut
    for i in range(6):
        wetten.append(w("premier-league", 20000.0, liga="Premier League", pnl=-20000.0,
                        event="oben%d" % i))
        wetten.append(w("championship", 20000.0, liga="Championship", pnl=+20000.0,
                        event="unten%d" % i))
    k = LS.kreuz(wetten, {})
    assert k["1"][">6x"]["roi"] < 0
    assert k["2"][">6x"]["roi"] > 0


def test_beide_richtungen_koennen_ein_urteil_tragen():
    """Folgen belegt die Untergrenze ueber null, dagegenhalten die OBERgrenze unter null.

    Mit der Untergrenze allein waere eine Reihe, die stabil verliert, auf ewig „kein Urteil" —
    obwohl sie genau die Aussage traegt, um die es hier geht.
    """
    # Genug kleine Zeilen, damit der Median NICHT von den grossen mitgezogen wird — sonst
    # faellt jeder grosse Einsatz in die unterste Spalte und der Test misst etwas anderes.
    wetten = [w("premier-league", 2000.0, liga="Premier League") for _ in range(200)]
    # 40 grosse Einsaetze oben, alle daneben: die Obergrenze muss unter null landen
    wetten += [w("premier-league", 20000.0, liga="Premier League", pnl=-20000.0,
                 quote=2.0, event="oben%d" % i) for i in range(40)]
    z = LS.kreuz(wetten, {})["1"][">6x"]
    assert z["flachOg"] is not None and z["flachOg"] < 0
    assert z["belegtGegen"] is True and z["belegt"] is False


def test_kreuz_gibt_unter_30_keine_untergrenze():
    """Ein Punktschaetzer ist kein Beleg — der harte Boden gilt auch hier."""
    wetten = [w("championship", 2000.0, liga="Championship") for _ in range(20)]
    wetten += [w("championship", 20000.0, liga="Championship", pnl=+20000.0, event="x%d" % i)
               for i in range(5)]
    z = LS.kreuz(wetten, {})["2"][">6x"]
    assert z["n"] == 5 and z["flachUg"] is None and z["flachOg"] is None
    assert z["belegt"] is False and z["belegtGegen"] is False


def test_block_meldet_ligen_ohne_ebene():
    wetten = [w("gibt-es-nicht", 2000.0) for _ in range(3)]
    b = LS.block(wetten, {})
    assert b["nOhneEbene"] == 1 and "gibt-es-nicht" in b["ohneEbene"]


def test_alle_ligen_im_echten_ledger_haben_eine_ebene():
    """Der Wachhund gegen stilles Veralten: taucht eine neue Fussball-Liga auf, faellt sie
    hier auf, und nicht erst in einer Tabelle, in der sie nicht vorkommt."""
    import json
    p = ROOT / "stake_bet_ledger.json"
    if not p.exists():
        import pytest
        pytest.skip("kein Ledger im Arbeitsverzeichnis")
    rows = (json.load(open(p, encoding="utf-8")) or {}).get("wetten") or []
    fehlt = sorted({r.get("ligaSlug") for r in rows
                    if r.get("sport") == "soccer" and r.get("ligaSlug")
                    and LS.stufe(r.get("ligaSlug"), r.get("sport")) is None})
    assert not fehlt, ("Fussball-Ligen ohne Ebene in stake_liga_stufe.py: %s"
                       % ", ".join(fehlt[:20]))
