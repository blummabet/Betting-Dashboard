"""🔴 24.09.2026 (Lucas: „Kamen 2 Meldungen zum selben Spiel und beide wurden gesetzt …
war schon gefixt, schon wieder kaputt").

Fuego vs EDward Gaming Youth Team, zweimal $5:
    06:13 UTC  Order 0xc1c79cbe77ac9de4576b45dce3a11f5e075d0f368ca834815e985cca7f29b958
    06:18 UTC  Order 0x20e1d0439ed6ce9e66608f…

Und dann das Eigentliche: beide Commits trugen 53 Wetten. Der zweite Lauf hat die Zeile des
ersten nicht ergaenzt, sondern ersetzt — `git pull --no-rebase -X ours` in ci_pull.sh. Die
Order 0xc1c79cbe… stand danach in KEINER Datei des Hauses (ueber alle JSON-Dateien gesucht,
null Treffer). $5 lagen an der Boerse, der Deckel rechnete mit $10 statt $15, und die
Aufloesung waere nie gebucht worden.

Drei verschiedene Fehler, die zusammen einen ergeben — jeder hat hier seinen eigenen Test:
  1. `-X ours` wirft bei Streit eine Seite weg, auch wenn beide Seiten Tatsachen sind.
  2. Die Wallet-Schranke entscheidet aus einem Schnappschuss, der bis zu 20 Minuten alt ist.
  3. Ein Doppelsetzen war nur im Telegram-Kanal zu sehen, nirgends im Haus.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import buecher_union as BU  # noqa: E402
import uebersicht_integrity as U  # noqa: E402

A = {"betKey": "lol-fue-edgy|EDG", "orderId": "0xc1c7", "placedAt": "06:13"}
B = {"betKey": "lol-fue-edgy|EDG", "orderId": "0x20e1", "placedAt": "06:18"}
ALT = {"betKey": "dota|Xtreme", "orderId": "0x8fe8"}


# ── 1. Das Buch verliert keine Zeile mehr ───────────────────────────────────────────────

def test_zwei_orders_auf_denselben_play_ueberleben_beide():
    """Der echte Fall: unser Stand kennt B, der fremde A. Danach muessen beide dastehen."""
    raus = BU.zeilen_vereinen([ALT, B], [ALT, A], ("orderId",))
    assert [z["orderId"] for z in raus] == ["0x8fe8", "0x20e1", "0xc1c7"]


def test_ueber_die_order_vereint_und_nicht_ueber_den_play():
    """Ein Union ueber `betKey` haette eine der beiden Orders wieder verschluckt —
    und den Fehler damit erneut unsichtbar gemacht."""
    raus = BU.zeilen_vereinen([B], [A], ("betKey",))
    assert len(raus) == 1, "ueber den Play vereint heisst: eine Order faellt weg"
    raus2 = BU.zeilen_vereinen([B], [A], ("orderId",))
    assert len(raus2) == 2


def test_unsere_reihenfolge_bleibt():
    """Sonst ist jeder Lauf ein Riesen-Diff und niemand sieht mehr, was dazukam."""
    raus = BU.zeilen_vereinen([ALT, B], [A], ("orderId",))
    assert [z["orderId"] for z in raus[:2]] == ["0x8fe8", "0x20e1"]


def test_dieselbe_zeile_zweimal_bleibt_einmal():
    raus = BU.zeilen_vereinen([A], [A], ("orderId",))
    assert len(raus) == 1


def test_eine_zeile_ohne_identitaet_wird_nie_verworfen():
    """Im Zweifel lieber doppelt: ein Buch darf eher zu viel als zu wenig wissen."""
    ohne = {"betKey": "x"}
    raus = BU.zeilen_vereinen([], [ohne, ohne], ("orderId",))
    assert len(raus) == 2


def test_das_ganze_buch_ueber_seine_spezifikation():
    spec = BU.BUECHER["shortlist_auto_bets_placed.json"]
    unser = {"updatedAt": "b", "bets": [ALT, B]}
    ihr = {"updatedAt": "a", "bets": [ALT, A]}
    neu = BU.vereinen(unser, ihr, spec)
    assert [z["orderId"] for z in neu["bets"]] == ["0x8fe8", "0x20e1", "0xc1c7"]
    assert neu["updatedAt"] == "b", "unsere uebrigen Felder bleiben unsere"


def test_das_wettbuch_wird_ueber_die_order_vereint():
    """Die Spezifikation selbst ist der Fund — nicht irgendein Schluessel."""
    assert BU.BUECHER["shortlist_auto_bets_placed.json"]["id"] == ("orderId",)


def test_ein_dedup_stand_verliert_keinen_schluessel():
    """Einen gesetzten Schluessel zurueckzunehmen heisst: noch einmal senden."""
    raus = BU.abbildung_vereinen({"a": 1}, {"b": 2})
    assert raus == {"a": 1, "b": 2}


def test_alle_buecher_haben_eine_identitaet():
    for name, spec in BU.BUECHER.items():
        if spec.get("abbildung"):
            continue
        assert spec.get("id"), name


# ── 2. Das Doppelsetzen ist zaehlbar ────────────────────────────────────────────────────

def test_doppelter_play_wird_gemeldet():
    assert BU.doppelte_plays([ALT, B, A]) == {"lol-fue-edgy|EDG": ["0x20e1", "0xc1c7"]}


def test_ein_play_eine_order_ist_still_wenn_alles_stimmt():
    assert BU.doppelte_plays([ALT, B]) == {}


def test_dieselbe_order_zweimal_im_buch_ist_kein_doppelter_play():
    assert BU.doppelte_plays([B, dict(B)]) == {}


def test_der_waechter_haengt_in_der_batterie_und_ist_ein_fehler_kein_hinweis():
    assert U.check_ein_play_eine_order in U.UEBERSICHT_CHECKS
    c = U.check_ein_play_eine_order({})
    assert c["severity"] == "error", "zweimal echtes Geld ist keine Warnung"


def test_der_waechter_findet_den_echten_fall():
    p = pathlib.Path(__file__).resolve().parent.parent / "shortlist_auto_bets_placed.json"
    if not p.exists():
        return
    bets = (json.loads(p.read_text(encoding="utf-8")) or {}).get("bets") or []
    orders = {b.get("orderId") for b in bets if isinstance(b, dict)}
    # Die am 24.09. verlorene Order gehoert wieder ins Buch — sie liegt an der Boerse.
    assert any(str(o).startswith("0xc1c79cbe") for o in orders), \
        "die wiederhergestellte Order fehlt erneut"


# ── 3. Die Wallet wird unmittelbar vor der Order gelesen ────────────────────────────────

def test_die_zweite_schranke_liest_frisch_vor_dem_setzen():
    """`depot` wurde EINMAL je Lauf geholt — und zwischen diesem Griff und dem Setzen liegen
    in diesem Job bis zu zwanzig Minuten. Wer handelt, liest zuerst frisch."""
    src = (pathlib.Path(__file__).resolve().parent.parent / "shortlist_auto_bet.py"
           ).read_text(encoding="utf-8")
    vor_order = src.split("from polymarket_bet import place_market_order")[0]
    # der letzte Wallet-Griff vor der Order darf nicht der vom Schleifenanfang sein
    assert vor_order.rstrip().endswith("continue"), "vor der Order wird nichts mehr geprueft"
    letzte = vor_order.rsplit("depot_jetzt = wallet_positionen()", 1)
    assert len(letzte) == 2, "kein frischer Wallet-Griff unmittelbar vor der Order"
    assert "schon_im_depot(tok, depot)" in letzte[1], "frisch gelesen, aber nicht geprueft"


# ── 4. Der Waechter geht wieder aus, wenn der Vorfall abgehakt ist ──────────────────────
# Gelernt am 23.09. beim Beleg-Alarm: ein Waechter, der wegen eines Ereignisses von heute fuer
# immer rot bleibt, wird ab morgen ueberlesen — und dann sieht man den echten nicht.

def test_ein_quittierter_vorfall_ist_still():
    paare = list(BU.QUITTIERT)
    assert paare, "kein Vorfall quittiert — der heutige gehoert dorthin"
    a, b = paare[0]
    assert BU.doppelte_plays([{"betKey": "k", "orderId": a},
                              {"betKey": "k", "orderId": b}]) == {}


def test_ein_neuer_vorfall_am_selben_play_ist_laut():
    """Quittiert wird das Order-PAAR, nicht der Play — sonst deckt ein Freispruch von heute
    jede kuenftige Doppelsetzung derselben Paarung mit ab."""
    a, b = list(BU.QUITTIERT)[0]
    d = BU.doppelte_plays([{"betKey": "k", "orderId": a},
                           {"betKey": "k", "orderId": b},
                           {"betKey": "k", "orderId": "0xNEU"}])
    assert d, "eine dritte Order auf denselben Play muss auffallen"


def test_jeder_quittierte_vorfall_nennt_seinen_grund():
    for paar, grund in BU.QUITTIERT.items():
        assert len(paar) == 2 and all(str(o).startswith("0x") for o in paar), paar
        assert isinstance(grund, str) and len(grund) > 60, paar


def test_der_heutige_vorfall_ist_quittiert_und_die_batterie_ist_still():
    c = U.check_ein_play_eine_order({})
    assert c["nFail"] == 0, c["failures"]
