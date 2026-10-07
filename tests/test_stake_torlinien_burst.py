"""🔴 07.10.2026 (Lucas: „wieso war es eigentlich kein Burst? … ja will sowas für over under").

Deportivo Riestra Afbc Reserve – Independiente Rivadavia de Mendoza Reserve, vor Anpfiff:
10 Wetten, ~28 K$, ALLE auf Over, verteilt auf 2.25 / 2.5 / 2.75 / 3. Der Auswahl-Burst sah vier
Linien, der Spiel-Burst verlangte >=2 Wetten mit Mannschaft. Kein Alarm — obwohl das Fenster
17:34-17:51 UTC 4 Wetten, 18,5 K$ und 2,7x Norm trug.

Fehlerklasse: eine Einheit, die die Beobachtung nach der falschen Achse zerschneidet (Linie statt
Richtung). Dazu beim Bau gefunden: ein gemeinsamer Buch-Deckel, an dem die seltenen Arten gegen
die haeufigen still verlieren.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stake_burst_push as S  # noqa: E402

NOW = datetime(2026, 10, 7, 17, 55, tzinfo=timezone.utc)
NORM = {"Liga Profesional, Reserves": 1700.0}
RIESTRA = [  # die echten Zeilen aus stake_bet_ledger.json, 07.10.2026
    ("2026-10-07T17:01:32Z", 1999.80, 1.93, "Over 2.5"),
    ("2026-10-07T17:01:32Z", 1999.80, 2.19, "Over 2.75"),
    ("2026-10-07T17:01:32Z", 1999.80, 1.70, "Over 2.25"),
    ("2026-10-07T17:04:55Z", 1090.87, 1.93, "Over 2.5"),
    ("2026-10-07T17:06:28Z", 1000.00, 1.66, "Over 2.25"),
    ("2026-10-07T17:11:49Z", 1700.00, 1.85, "Over 2.5"),
    ("2026-10-07T17:34:38Z", 4399.56, 1.68, "Over 2.75"),
    ("2026-10-07T17:49:18Z", 7999.20, 1.68, "Over 2.75"),
    ("2026-10-07T17:50:14Z", 4999.50, 1.88, "Over 3"),
    ("2026-10-07T17:51:44Z", 1066.72, 1.67, "Over 2.75"),
]


def _w(i, ts, usd, q, auswahl, markt="Asian Total", ev="ev-riestra", phase="vor"):
    return {"id": "sport:%d" % i, "ts": ts, "einsatzUsd": usd, "quote": q, "beinQuote": q,
            "kat": "Fußball", "sport": "soccer", "liga": "Liga Profesional, Reserves",
            "ligaSlug": "liga-profesional-reserves", "nBeine": 1, "kombi": False,
            "event": "Deportivo Riestra Afbc Reserve - Independiente Rivadavia de Mendoza Reserve",
            "eventId": ev, "markt": markt, "auswahl": auswahl, "phase": phase,
            "anpfiff": "2026-10-07T18:00:00Z"}


def _riestra():
    return [_w(i, *z) for i, z in enumerate(RIESTRA)]


def _tor(w, **kw):
    return S.tor_bursts(w, norm=NORM, now=NOW, gesperrt=[], **kw)


def test_der_fall_vom_07_10_feuert():
    b = _tor(_riestra())
    assert len(b) == 1
    assert b[0]["richtung"] == "Over" and len(b[0]["wetten"]) == 4
    assert round(b[0]["summe"]) == 18465 and b[0]["faktor"] > 2.5


def test_der_spiel_burst_bleibt_wie_er_ist():
    """Er misst Richtung auf eine MANNSCHAFT — Torlinien gehoeren in die eigene Einheit."""
    assert S.spiel_bursts(_riestra(), norm=NORM, now=NOW, gesperrt=[]) == []


def test_gegenrichtung_im_fenster_verwirft():
    w = _riestra() + [_w(99, "2026-10-07T17:45:00Z", 1500, 2.0, "Under 3.5")]
    assert _tor(w) == []


def test_andere_maerkte_stoeren_nicht_und_zaehlen_nicht():
    w = _riestra() + [_w(98, "2026-10-07T17:40:00Z", 9000, 1.9, "Deportivo Riestra Reserves",
                         markt="1x2")]
    b = _tor(w)
    assert len(b) == 1 and all(S.richtung_tore(x) == "Over" for x in b[0]["wetten"])


def test_nur_spieltor_linien():
    assert S.richtung_tore({"markt": "Asian Total", "auswahl": "Over 2.75"}) == "Over"
    assert S.richtung_tore({"markt": "Total Goals", "auswahl": "Under 3.5"}) == "Under"
    for m, a in (("1st Half - Asian Total", "Over 1.5"), ("Total Corners", "Over 9.5"),
                 ("Spain Total", "Over 2.5"), ("Total & Both Teams to Score", "Over 2.5 & Yes"),
                 ("Asian Handicap", "Over 2.5")):
        assert S.richtung_tore({"markt": m, "auswahl": a}) is None, m


def test_ohne_norm_kein_urteil():
    assert S.tor_bursts(_riestra(), norm={}, now=NOW, gesperrt=[]) == []


def test_zu_alt_wird_nicht_gemeldet():
    spaet = datetime(2026, 10, 7, 19, 0, tzinfo=timezone.utc)
    assert S.tor_bursts(_riestra(), norm=NORM, now=spaet, gesperrt=[]) == []


def test_karte_nennt_richtung_linien_und_kleine_liga():
    t = S.build_tor_card(_tor(_riestra())[0])
    assert "OVER" in t and "Over 2.75" in t and "Over 3" in t
    assert "kleine Liga" in t and "nur Trades" in t


def test_buchzeile_eigene_art_und_phase():
    z = S.tor_buch_zeile(_tor(_riestra())[0], NOW.isoformat())
    assert z["art"] == "tore" and z["k"] == "tore:ev-riestra" and z["phase"] == "vor"
    assert len(z["betIds"]) == 4 and z["status"] == "pending"


def test_bilanz_je_art_und_phase():
    led = [{"art": "tore", "phase": "vor", "rendite": 0.5},
           {"art": "tore", "phase": "live", "rendite": -1.0},
           {"art": "klein", "phase": "vor", "rendite": -1.0}]
    assert S.art_bilanz(led, "tore", "vor") == {"n": 1, "roi": 0.5, "ug": None}
    assert S.art_bilanz(led, "tore")["n"] == 2


def test_seltene_buchart_ueberlebt_den_deckel():
    """Gegentest zum alten `led[-LEDGER_KEEP:]`: 900 Spiel-Zeilen nach 5 Tor-Zeilen."""
    led = [{"art": "tore", "k": "t%d" % i} for i in range(5)] + \
          [{"art": "spiel", "k": "s%d" % i} for i in range(900)]
    raus = S.buch_kuerzen(led, keep=800)
    assert sum(1 for z in raus if z["art"] == "tore") == 5
    assert sum(1 for z in raus if z["art"] == "spiel") == 800
    assert raus[0]["k"] == "t0"                      # Reihenfolge bleibt


def test_main_bucht_tore_und_kuerzt_je_art():
    src = Path(S.__file__).read_text(encoding="utf-8")
    assert "tor_bursts(wetten" in src and "tor_buch_zeile(b, now_iso)" in src
    assert "_save(LEDGER_FILE, buch_kuerzen(led))" in src
