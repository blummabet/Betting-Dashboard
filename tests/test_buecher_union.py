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


# ── 🔴 25.09.2026: eine Reparatur, die jeden Lauf neu gemacht werden muss, ist keine ────
# Die Vereinigung schuetzt VORWAERTS. Order 0xc1c79cbe… war da schon aus origin heraus: viermal
# von Hand wiederhergestellt, viermal vom naechsten Rebase verloren, nie angekommen. Gemessen
# an 25 Commits des Buches — in keinem einzigen stand sie.

def test_der_nachtrag_holt_eine_verlorene_zeile_zurueck():
    nach = BU.nachtrag_lesen()
    assert "shortlist_auto_bets_placed.json" in nach, nach.keys()
    zeilen = nach["shortlist_auto_bets_placed.json"]
    assert any(str(z.get("orderId", "")).startswith("0xc1c79cbe") for z in zeilen)


def test_jede_nachgetragene_zeile_nennt_ihre_quelle():
    """Erfunden wird hier nichts: jede Zeile stand woertlich in einem Commit, und der steht dabei."""
    for buch, zeilen in BU.nachtrag_lesen().items():
        for z in zeilen:
            n = z.get("_nachtrag") or {}
            assert n.get("quelle"), (buch, z.get("orderId"))
            assert n.get("grund"), (buch, z.get("orderId"))


def test_der_nachtrag_dupliziert_nicht():
    """Steht die Zeile schon im Buch, bleibt sie einmal drin."""
    zeile = BU.nachtrag_lesen()["shortlist_auto_bets_placed.json"][0]
    spec = BU.BUECHER["shortlist_auto_bets_placed.json"]
    doppelt = BU.vereinen({"bets": [zeile]}, {"bets": [zeile]}, spec)
    assert len(doppelt["bets"]) == 1


def test_das_buch_traegt_die_zeile_jetzt():
    p = pathlib.Path(__file__).resolve().parent.parent / "shortlist_auto_bets_placed.json"
    if not p.exists():
        return
    bets = (json.loads(p.read_text(encoding="utf-8")) or {}).get("bets") or []
    assert any(str(b.get("orderId", "")).startswith("0xc1c79cbe") for b in bets), \
        "die nachgetragene Order fehlt erneut — dann greift der Nachtrag nicht"


def test_der_nachtrag_wird_beim_vereinen_auch_angewandt(tmp_path, monkeypatch):
    """Die Mutationsprobe hat den Aufruf ersatzlos entfernen lassen, ohne dass etwas rot wurde —
    weil das Buch die Zeile auf der Platte schon trug. Geprueft gehoert der WEG dorthin."""
    import shutil
    quelle = pathlib.Path(__file__).resolve().parent.parent
    buch = json.loads((quelle / "shortlist_auto_bets_placed.json").read_text(encoding="utf-8"))
    ohne = {"updatedAt": buch.get("updatedAt"),
            "bets": [b for b in buch["bets"]
                     if not str(b.get("orderId", "")).startswith("0xc1c79cbe")]}
    (tmp_path / "shortlist_auto_bets_placed.json").write_text(
        json.dumps(ohne, ensure_ascii=False), encoding="utf-8")
    shutil.copy(quelle / "buecher_nachtrag.json", tmp_path / "buecher_nachtrag.json")
    monkeypatch.chdir(tmp_path)
    BU.main(["shortlist_auto_bets_placed.json"])
    danach = json.loads((tmp_path / "shortlist_auto_bets_placed.json").read_text(encoding="utf-8"))
    assert any(str(b.get("orderId", "")).startswith("0xc1c79cbe") for b in danach["bets"]), \
        "der Nachtrag hat die Zeile nicht zurueckgeholt"
    assert len(danach["bets"]) == len(ohne["bets"]) + 1


# ── 25.09.2026: die Reparatur formatierte das Buch um, das sie reparierte ─────────────
# Gefunden beim Rebase von 8a9ebe8ee3: 1907 geloeschte / 2205 neue Zeilen fuer EINE
# nachgetragene Order, weil hier fest `indent=1` stand und die Produzenten 0, 1 und 2
# schreiben. Ein Konflikt ueber das ganze Buch laesst `-X ours` genau das wegwerfen, was
# dieses Skript retten soll.

def test_einrueckung_liest_die_schreibweise_aus_der_datei():
    assert BU.einrueckung('{\n  "a": 1\n}') == 2
    assert BU.einrueckung('{\n "a": 1\n}') == 1
    assert BU.einrueckung('{\n"a": 1\n}') == 0
    assert BU.einrueckung("[\n  {\n    \"k\": 1\n  }\n]") == 2
    assert BU.einrueckung("{}") == 1          # einzeilig: kein Urteil moeglich
    assert BU.einrueckung("") == 1
    assert BU.einrueckung('{\n\n  "a": 1\n}') == 2   # Leerzeile zaehlt nicht


def test_jedes_buch_behaelt_beim_vereinen_seine_schreibweise(tmp_path, monkeypatch):
    """Nicht die Einrueckung pruefen, die wir hineinschreiben, sondern die, die wieder
    herauskommt — und zwar fuer alle drei im Haus vorkommenden Schreibweisen."""
    monkeypatch.chdir(tmp_path)
    for einr in (0, 1, 2):
        name = "shortlist_push_ledger.json"
        alt = [{"k": "a", "sentAt": "2026-01-01T00:00:00+00:00"}]
        (tmp_path / name).write_text(json.dumps(alt, ensure_ascii=False, indent=einr),
                                     encoding="utf-8")
        # eine zweite Fassung mit einer weiteren Tatsache, damit wirklich geschrieben wird
        monkeypatch.setattr(BU, "_git_fassung", lambda *a, **k: [
            {"k": "b", "sentAt": "2026-01-02T00:00:00+00:00"}])
        BU.main([name])
        roh = (tmp_path / name).read_text(encoding="utf-8")
        assert len(json.loads(roh)) == 2, "die zweite Tatsache fehlt"
        assert BU.einrueckung(roh, standard=-1) == einr, \
            f"Buch mit indent={einr} kam als indent={BU.einrueckung(roh, standard=-1)} zurueck"


def test_das_buch_auf_der_platte_hat_die_schreibweise_seines_produzenten():
    """`shortlist_auto_bets_placed.json` wird von `safe_write.write_json_atomic` mit dem
    Standard indent=2 geschrieben. Liegt es anders da, hat es etwas anderes umformatiert."""
    p = pathlib.Path(__file__).resolve().parent.parent / "shortlist_auto_bets_placed.json"
    if not p.exists():
        return
    assert BU.einrueckung(p.read_text(encoding="utf-8"), standard=-1) == 2
