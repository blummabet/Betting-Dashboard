"""Eine Sperrliste fuer Stake UND Polymarket — und jede Kopie sagt dasselbe.

🔴 27.09.2026 (Übersicht-Check): Stake sperrte {US-Sport, Cricket}, Poly {US-Sport, Kampfsport}.
Folge: „Takuma Inoue – Tenshin Nasukawa" stand in „Stake · größtes Geld", waehrend Poly dieselbe
Sportart ausblendete — und umgekehrt Cricket. Lucas: „Kampfsport und Cricket … nimm sowohl als
auch raus". Die Listen leben in zwei Sprachen (Stake-Sammler in Python, Poly in poly-wallets.js,
das der Emitter laedt) plus fuenf Rueckfall-Kopien. Dieser Test haelt sie gleich.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOLL = {"US-Sport", "Kampfsport", "Cricket"}


def _js_liste(datei, name):
    src = (ROOT / datei).read_text(encoding="utf-8")
    m = re.search(name + r"\s*=\s*\[([^\]]*)\]", src)
    assert m, f"{name} in {datei} nicht gefunden"
    return set(re.findall(r"'([^']+)'", m.group(1)))


def test_stake_sammler():
    import stake_highroller_fetch as S
    assert set(S.GESPERRT) == SOLL


def test_poly_quelle_und_alle_rueckfaelle_sind_gleich():
    import poly_whale_watch as W
    import poly_cross_sport_watch as C
    import stake_burst_push as B
    kopien = {
        "poly-wallets.js PW_BLOCKED_BET_CATS": _js_liste("poly-wallets.js", "PW_BLOCKED_BET_CATS"),
        "polymarket-tab.js _POLY_HEUTE_BET_FALLBACK": _js_liste("polymarket-tab.js", "_POLY_HEUTE_BET_FALLBACK"),
        "stake-radar.js SR_GESPERRT_FALLBACK": _js_liste("stake-radar.js", "SR_GESPERRT_FALLBACK"),
        "main-dashboard.js _mdStakeWetten": set(re.findall(r"'([^']+)'", re.search(
            r"d\.gesperrt \|\| \[([^\]]*)\]", (ROOT / "main-dashboard.js").read_text(encoding="utf-8")).group(1))),
        "poly_whale_watch.BLOCKED_FALLBACK": set(W.BLOCKED_FALLBACK),
        "poly_cross_sport_watch._BLOCKED_FALLBACK": set(C._BLOCKED_FALLBACK),
        "stake_burst_push.GESPERRT_FALLBACK": set(B.GESPERRT_FALLBACK),
    }
    abweichend = {k: sorted(v) for k, v in kopien.items() if v != SOLL}
    assert not abweichend, abweichend


def test_gegenbeweis_der_alte_stand_waere_rot():
    """Der Zustand vom 27.09. morgens haette hier nicht bestanden."""
    alt_stake, alt_poly = {"US-Sport", "Cricket"}, {"US-Sport", "Kampfsport"}
    assert alt_stake != SOLL and alt_poly != SOLL
