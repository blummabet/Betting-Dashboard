"""Whale-Watch: je Spiel EINE Karte pro Lauf (04.10.2026, Lucas: „beim selben Lauf mehrmals
dieselbe Nachricht … bei E-Sport bei grossen Events … andere Nachrichten gehen unter").

Fehlerklasse: gedeckelt nach dem, der handelt (je Wallet), statt nach dem, worueber man liest
(je Spiel). Der alte Lauf schickte fuenf Wallets auf dasselbe Match als fuenf volle Karten."""
import inspect

import poly_whale_watch as P


def pos(w, usd, key="cs2-spirit-faze-2026-10-04", side="Spirit", price=0.55):
    return {"wallet": w, "key": key, "side": side, "league": "ESPORTS", "firstPrice": price, "usd": usd}


def test_ein_spiel_eine_karte_groesste_fuehrt():
    cand = [("a", pos("0xa", 9000), False),
            ("b", pos("0xb", 4000, side="FaZe"), False),
            ("c", pos("0xc", 3000, key="cs2-spirit-faze-2026-10-04-map-1-winner"), True),
            ("d", pos("0xd", 2000, key="lol-t1-geng-2026-10-04"), False)]
    g = P.nach_spiel_buendeln(cand)
    assert [x[0] for x in g] == ["a", "d"], "Sub-Markt (Map 1) gehoert zum selben Spiel"
    assert [w[0] for w in g[0][3]] == ["b", "c"] and g[1][3] == []


def test_karte_listet_die_weiteren_kurz():
    weitere = [("b", pos("0xbbbbbbbbbbbbbbbbbb", 4000, side="FaZe", price=0.45), False),
               ("c", pos("0xc", 3000, key="cs2-spirit-faze-2026-10-04-map-1-winner"), True)]
    card = P.build_card(pos("0xa", 9000), {}, False, {}, weitere=weitere)
    assert "Im selben Lauf, selbes Spiel</b> (2 weitere Einstiege)" in card
    assert "<b>FaZe</b> @ 45¢" in card and "$4" in card
    assert "stockt auf" in card and "map 1 winner" in card
    assert card.count("→ Markt öffnen") == 1


def test_ohne_weitere_bleibt_die_karte_wie_bisher():
    assert P.build_card(pos("0xa", 9000), {}, False, {}) == P.build_card(pos("0xa", 9000), {}, False, {}, weitere=[])
    assert "selbes Spiel" not in P.build_card(pos("0xa", 9000), {}, False, {})


def test_main_markiert_alle_gebuendelten_als_gemeldet():
    src = inspect.getsource(P.main)
    assert "nach_spiel_buendeln(cand)" in src and "for pkey, pos, restock in cand[:MAX_ALERTS]" not in src
    assert "[(pkey, pos, restock)] + list(weitere)" in src, "sonst kommen die Gebuendelten im naechsten Lauf einzeln"


# ── 60-Min-Sperre je Spiel: Nachschlag statt voller Karte ──────────────────────────────────
def test_spiel_zuletzt_findet_auch_nebenmaerkte():
    seen = {"0xa|cs2-spirit-faze-2026-10-04|Spirit": {"ts": "2026-10-04T10:00:00Z"},
            "0xb|cs2-spirit-faze-2026-10-04-map-1-winner|FaZe": {"ts": "2026-10-04T10:40:00Z"},
            "0xc|lol-t1-geng-2026-10-04|T1": {"ts": "2026-10-04T11:00:00Z"}}
    t = P.spiel_zuletzt(seen, "cs2-spirit-faze-2026-10-04")
    assert t.isoformat().startswith("2026-10-04T10:40")
    assert P.spiel_zuletzt(seen, "dota-x-y-2026-10-04") is None


def test_nachschlag_ist_kurz_und_nennt_alle_neuen():
    card = P.build_kurz_card(pos("0xa", 9000), [("b", pos("0xb", 4000, side="FaZe"), False)], {}, {}, 23)
    assert "Nachschlag" in card and "vor 23 Min" in card
    assert "<b>Spirit</b>" in card and "<b>FaZe</b>" in card
    assert "Im selben Lauf" not in card and "30T" in card
    assert card.count("\n") <= 6, "Nachschlag soll eine Handvoll Zeilen sein, keine volle Karte"


def test_main_nutzt_die_sperre():
    src = inspect.getsource(P.main)
    assert "spiel_zuletzt(seen, _spiel)" in src and "_vor < SPIEL_SPERRE_MIN" in src
    assert P.SPIEL_SPERRE_MIN == 60
