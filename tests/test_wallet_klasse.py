"""🔴 25.09.2026 (Lucas: „da kommen oft Wallets rein mit Nummer 110 und die setzen 3000 Euro —
was soll das sein? Was bringt mir das?").

Nachgemessen — und die Antwort war nicht die erwartete:

    Rang  1-10   Ø-Einsatz $82.762   Trefferquote 59 %
    Rang 11-30   Ø-Einsatz $18.754   Trefferquote 51 %   <- die SCHLECHTESTE Quote
    Rang 61-100  Ø-Einsatz  $2.720   Trefferquote 63 %
    Rang 101+    Ø-Einsatz  $3.202   Trefferquote 62 %

    Korrelation Rang <-> Einsatzgröße  r = -0,29
    Korrelation Rang <-> Trefferquote  r = +0,20

Der Rang sortiert nach absolutem 30-Tage-Sportprofit. Profit skaliert mit Einsatz — eine Wallet
mit $3.000 je Wette kann strukturell nie gut ranken. „#110" hieß also nie „schlecht", sondern
„setzt klein". Daneben stand eine MEDAILLE, und die liest sich wie eine Note.

Fehlerklasse: *eine Zahl, die etwas anderes behauptet als sie misst.*
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import poly_whale_watch as PW  # noqa: E402


def _w(n=38, wins=25, usd_je=2900, pnl=-36300, gewinn30=4000):
    return {"n": n, "wins": wins, "usd": n * usd_je, "clvSumPP": 0.0, "pnl": pnl,
            "fenster30": {"gewinn": gewinn30, "n": 26, "wins": 18}}


# ── Die Sorte ───────────────────────────────────────────────────────────────────────
def test_zwei_sorten_gehen_durch_dasselbe_tor():
    """Beide sind bewiesen — unterschieden wird nur, was sie unterscheidet: das Geld."""
    klein, gross = _w(usd_je=2900), _w(usd_je=82762)
    assert PW._is_smart(klein) and PW._is_smart(gross)
    assert PW.wallet_klasse(klein) == "treffer"
    assert PW.wallet_klasse(gross) == "geld"


def test_nicht_bewiesen_hat_gar_keine_sorte():
    assert PW.wallet_klasse({"n": 3, "wins": 3, "usd": 300000}) is None
    assert PW.wallet_klasse(None) is None
    assert PW.klasse_kurz({"n": 3, "wins": 3, "usd": 300000}) == ""


def test_die_grenze_ist_die_schon_gesetzte_und_keine_neue():
    """$25.000 ist `PUB_MIN_USD_TRACKED` — Lucas' Schwelle für „groß genug fürs Public".
    Eine zweite erfundene Zahl wäre eine Schwelle, die an zwei Stellen steht."""
    assert PW.KLASSE_GELD_GRENZE == PW.PUB_MIN_USD_TRACKED == 25000
    assert PW.wallet_klasse(_w(usd_je=24999)) == "treffer"
    assert PW.wallet_klasse(_w(usd_je=25000)) == "geld"


def test_unbekannte_groesse_ist_kein_grosses_geld():
    """Fehlende Information ist keine Erlaubnis — auch nicht für ein Abzeichen."""
    ohne = {"n": 38, "wins": 25, "clvSumPP": 0.0, "pnl": 1,
            "fenster30": {"gewinn": 4000}}
    assert PW.schnitt_einsatz(ohne) is None
    assert PW.wallet_klasse(ohne) == "treffer"
    assert "Trefferquote" in PW.klasse_kurz(ohne)
    assert "je Wette" not in PW.klasse_kurz(ohne)   # keine erfundene Zahl


def test_die_sorte_haengt_an_der_wallet_nicht_an_den_anderen():
    """Ein Rang kippt, wenn eine ANDERE Wallet eine gute Woche hat — dann hätte das Symbol
    gewechselt, ohne dass sich an dieser Wallet etwas geändert hat. Deshalb Ø-Einsatz."""
    w = _w(usd_je=2900)
    assert PW.wallet_klasse(w) == PW.wallet_klasse(dict(w))     # kein Kontext im Spiel
    import inspect
    src = inspect.getsource(PW.wallet_klasse)
    assert "rank" not in src.lower() and "rang" not in src.lower()


# ── Die Anzeige ─────────────────────────────────────────────────────────────────────
def test_abzeichen_und_einsatz_stehen_im_kopf():
    sc = {"0x994ec8e910b433265f3a46eaf666bfa28b1a6136": _w(usd_je=2900)}
    kopf = PW._wallet_block(sc, "0x994ec8e910b433265f3a46eaf666bfa28b1a6136", 106)[0]
    assert "🎯" in kopf and "Trefferquote" in kopf
    assert "$2.9K" in kopf
    assert "🏅" not in kopf          # keine Medaille für die kleine Sorte
    assert "Geld-Rang #106" in kopf  # der Rang sagt jetzt, was er misst


def test_grosses_geld_behaelt_die_medaille():
    sc = {"0xb8e3000000000000000000000000000000000aaf2": _w(n=72, wins=55, usd_je=82762,
                                                           pnl=900000, gewinn30=120000)}
    kopf = PW._wallet_block(sc, "0xb8e3000000000000000000000000000000000aaf2", 4)[0]
    assert "🏅" in kopf and "Großes Geld" in kopf
    assert "🎯" not in kopf


def test_der_rang_nennt_nicht_mehr_eine_note():
    """Vorher: „🏅 #106". Eine Medaille neben „✅ bewiesen" liest sich wie eine Bewertung."""
    assert PW._rang_kurz(106) == "💰 Geld-Rang #106"
    assert PW._rang_kurz(1) == "💰 Geld-Rang #1"
    assert "🏅" not in PW._rang_kurz(106)
    assert "🥇" not in PW._rang_kurz(1)
    assert PW._rang_kurz(None) == "" and PW._rang_kurz(0) == ""


def test_die_top_zeile_nennt_die_liste_die_sie_meint():
    sc = {"0xb8e3000000000000000000000000000000000aaf2": _w(n=72, wins=55, usd_je=82762,
                                                           pnl=900000, gewinn30=120000)}
    z = PW._top_wallet_line(sc, "0xb8e3000000000000000000000000000000000aaf2") \
        if hasattr(PW, "_top_wallet_line") else None
    if z:
        assert "Sharp-Rangliste" not in z
        assert "Geld" in z
