"""19.07.2026 — Maker-Order-Lebenszyklus: das Loch, das maker_enabled bisher blockierte.

Eine ruhende Limit-Order spart den Spread, kostet aber Fill-Sicherheit. Bleibt sie unerfüllt bis
kurz vor Anpfiff, hätten wir den Steam-Move verpasst. Diese Tests sichern die drei Entscheidungen
(warten / stornieren+crossen / stornieren-abgelaufen) UND die zwei Fehler, die hier echtes Geld
kosten würden:
  · niemals crossen, OHNE vorher die ruhende Order zu stornieren (sonst DOPPELTE Position);
  · nach gescheitertem Storno NICHT platzieren (sonst zwei Orders, beide könnten füllen).
"""
import poly_entry as PE
import poly_resting as PR
import manage_poly_maker_orders as M


# ── Persistenz ───────────────────────────────────────────────────────────────

def test_record_ist_idempotent():
    orders = []
    e = {"orderId": "A", "tokenId": "T", "price": 0.5, "size": 10, "stakeUsdc": 5,
         "market": "Heimsieg", "matchKey": "H-A", "kickoff": "2026-07-20T18:00:00Z"}
    orders = PR.record(orders, e)
    orders = PR.record(orders, e)          # zweiter Lauf, gleiche Order
    assert len(orders) == 1, "gleiche Order dupliziert → Register überzählt"
    assert orders[0]["status"] == "resting"


def test_active_filtert_endzustaende():
    orders = [{"orderId": "A", "status": "resting"}, {"orderId": "B", "status": "filled"},
              {"orderId": "C", "status": "escalated"}]
    act = PR.active(orders)
    assert [o["orderId"] for o in act] == ["A"], "nur ruhende Orders gehören in den Monitor"


def test_set_status_schreibt_extra():
    orders = [{"orderId": "A", "status": "resting"}]
    PR.set_status(orders, "A", "escalated", escalatedTo="B")
    assert orders[0]["status"] == "escalated" and orders[0]["escalatedTo"] == "B"


# ── Reconcile-Schleife mit Fakes ─────────────────────────────────────────────

class FakeClient:
    def __init__(self, status_by_id=None, cancel_ok=True):
        self._status = status_by_id or {}
        self._cancel_ok = cancel_ok
        self.cancelled = []

    def get_order(self, oid):
        return {"status": self._status.get(oid, "open")}

    def cancel(self, oid):
        if not self._cancel_ok:
            raise RuntimeError("cancel abgelehnt")
        self.cancelled.append(oid)


def _order(oid, hours_to_ko):
    from datetime import datetime, timedelta, timezone
    ko = (datetime.now(timezone.utc) + timedelta(hours=hours_to_ko)).isoformat()
    return {"orderId": oid, "tokenId": "T"+oid, "price": 0.5, "size": 10,
            "stakeUsdc": 5.0, "market": "Heimsieg", "matchKey": "H-A",
            "kickoff": ko, "status": "resting"}


CFG = PE.EntryConfig(maker_enabled=True, taker_escalate_hours=1.5)


def test_gefuellte_order_wird_position():
    orders = [_order("A", 6)]
    client = FakeClient(status_by_id={"A": "matched"})
    placed = []
    orders, stats = M.reconcile(orders, client, lambda o: placed.append(o) or {"orderId": "X", "status": "placed"}, cfg=CFG)
    assert stats["filled"] == 1
    assert orders[0]["status"] == "filled"
    assert not placed and not client.cancelled, "gefüllte Order darf weder storniert noch neu platziert werden"


def test_viel_zeit_wird_gewartet():
    orders = [_order("A", 6)]
    client = FakeClient()
    orders, stats = M.reconcile(orders, client, lambda o: {"status": "placed"}, cfg=CFG)
    assert stats["wait"] == 1 and orders[0]["status"] == "resting"
    assert not client.cancelled, "es ist noch Zeit — nicht anfassen"


def test_kurz_vor_anpfiff_storno_dann_taker():
    """Der Kern: unerfüllt & knapp → stornieren UND als Taker neu."""
    orders = [_order("A", 0.5)]
    client = FakeClient()
    placed = []
    def place(o):
        placed.append(o["orderId"]); return {"orderId": "TAKER1", "status": "placed"}
    orders, stats = M.reconcile(orders, client, place, cfg=CFG)
    assert stats["escalated"] == 1
    assert client.cancelled == ["A"], "Maker-Order muss zuerst storniert werden"
    assert placed == ["A"], "danach als Taker neu platziert"
    assert orders[0]["status"] == "escalated" and orders[0]["escalatedTo"] == "TAKER1"


def test_reihenfolge_storno_vor_platzierung():
    """Doppel-Position verhindern: Storno MUSS vor der Taker-Order kommen."""
    seq = []
    class Track(FakeClient):
        def cancel(self, oid): seq.append("cancel"); super().cancel(oid)
    orders = [_order("A", 0.5)]
    M.reconcile(orders, Track(), lambda o: seq.append("place") or {"orderId": "T", "status": "placed"}, cfg=CFG)
    assert seq == ["cancel", "place"], "Taker vor Storno → kurzzeitig zwei offene Orders"


def test_storno_gescheitert_dann_NICHT_platzieren():
    """Wenn das Stornieren scheitert, darf KEINE Taker-Order raus — sonst zwei offene Orders,
    beide könnten füllen (doppelter Einsatz, doppeltes Risiko)."""
    orders = [_order("A", 0.5)]
    client = FakeClient(cancel_ok=False)
    placed = []
    orders, stats = M.reconcile(orders, client, lambda o: placed.append(o) or {"status": "placed"}, cfg=CFG)
    assert placed == [], "nach gescheitertem Storno wurde trotzdem platziert → Doppel-Position"
    assert orders[0]["status"] == "resting", "bleibt ruhend → nächster Lauf versucht es erneut"


def test_anpfiff_vorbei_storno_ohne_nachlegen():
    orders = [_order("A", -1)]
    client = FakeClient()
    placed = []
    orders, stats = M.reconcile(orders, client, lambda o: placed.append(o) or {"status": "placed"}, cfg=CFG)
    assert stats["expired"] == 1 and client.cancelled == ["A"]
    assert placed == [], "ins laufende Spiel wird nicht gecrosst"
    assert orders[0]["status"] == "expired"


def test_extern_verschwundene_order():
    orders = [_order("A", 6)]
    client = FakeClient(status_by_id={"A": "cancelled"})
    orders, stats = M.reconcile(orders, client, lambda o: {"status": "placed"}, cfg=CFG)
    assert stats["gone"] == 1 and orders[0]["status"] == "cancelled"


def test_force_taker_ueberspringt_maker():
    """Die Wieder-Platzierung MUSS den Maker-Schritt überspringen — sonst legt sie wieder eine
    ruhende Order statt zu crossen, und wir drehen uns im Kreis."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "polymarket_bet.py").read_text("utf-8")
    assert "force_taker" in src and "if force_taker else _maker_intent" in src, \
        "force_taker greift nicht → Eskalation legt erneut einen Maker-Order"
