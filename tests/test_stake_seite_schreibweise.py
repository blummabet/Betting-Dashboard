"""🔴 24.09.2026 (Lucas: „Das finden wir nicht im stake burst?").

Ein Fremd-Radar meldete Deportivo Riestra Reserve gegen Barracas Central Reserve: 12 Wetten,
26.276 $. Wir hatten MEHR — 14 Zeilen und 39.347 $ auf dasselbe Spiel in 57 Minuten, jede
einzelne im Ledger. Gemeldet haben wir nichts.

Der Burst fiel an genau einer Stelle durch:

    event   „Deportivo Riestra Afbc Reserve - CA Barracas Central Reserve"
    auswahl „Deportivo Riestra Reserves (-1.5)"

`seite()` verlangte den vollen Mannschaftsnamen woertlich in der Auswahl. „Afbc Reserve" gegen
„Reserves": dieselbe Mannschaft, zwei Schreibweisen, kein Treffer. Damit war `gerichtet` fuer
ALLE 14 Zeilen null, jedes Fenster fiel an `len(seiten) != 1` durch — obwohl eines davon
28.360 $ bei Faktor 1,82 getragen haette.

Fehlerklasse: *eine Zuordnung, die auf Zeichengleichheit besteht, wo die Quelle zwei
Schreibweisen fuehrt.* Dieselbe, an der am 01.09. der MLS-Anker hing.

Ueber das ganze Ledger (20.000 Zeilen, 18.–24.09.): 531 Zeilen bekommen eine Seite, keine
einzige verliert oder wechselt sie, und es kommen 8 Spiel-Bursts dazu — darunter Celta Vigo
gegen Racing Santander mit 237.329 $ und Kasimpasa gegen Konyaspor mit 209.052 $.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import stake_burst_push as SB  # noqa: E402

BASE = pathlib.Path(__file__).resolve().parent.parent


def w(event, auswahl):
    return {"event": event, "auswahl": auswahl}


# ── Der Fall selbst ─────────────────────────────────────────────────────────────────────

def test_zwei_schreibweisen_derselben_mannschaft():
    s = SB.seite(w("Deportivo Riestra Afbc Reserve - CA Barracas Central Reserve",
                   "Deportivo Riestra Reserves (-1.5)"))
    assert s == "Deportivo Riestra Afbc Reserve", s


def test_eine_neutrale_wette_bleibt_neutral():
    """None heisst „kein Team genannt" — nicht „unbekannt" und nicht „Gegenseite"."""
    assert SB.seite(w("Deportivo Riestra Afbc Reserve - CA Barracas Central Reserve",
                      "Over 2.5")) is None


def test_der_burst_feuert_jetzt():
    """Gegen die echten Zeilen: 8 Wetten, 28.360 $, Faktor 1,82, eine Seite."""
    import datetime as dt
    f = BASE / "stake_bet_ledger.json"
    if not f.exists():
        return
    rows = [x for x in (json.loads(f.read_text(encoding="utf-8")).get("wetten") or [])
            if "Riestra" in str(x.get("event") or "")]
    if len(rows) < 8:
        return                      # das rollierende Fenster hat den Fall verlassen
    now = max(SB._ts(x["ts"]) for x in rows) + dt.timedelta(minutes=1)
    b = SB.spiel_bursts(rows, now=now)
    assert len(b) == 1, b
    assert b[0]["summe"] > 25000 and b[0]["nGerichtet"] >= 2


# ── Die Vorsicht, die bleiben musste ────────────────────────────────────────────────────

def test_ein_gemeinsames_wort_entscheidet_nichts():
    """Der Grund, warum `seite` ueberhaupt streng ist: „Deportivo" passt auf beide."""
    assert SB.seite(w("Deportivo La Coruna - Deportivo Alaves", "Deportivo")) is None


def test_aber_der_volle_name_entscheidet_weiterhin():
    assert SB.seite(w("Deportivo La Coruna - Deportivo Alaves",
                      "Deportivo La Coruna")) == "Deportivo La Coruna"


def test_eine_auswahl_die_beide_nennt_gibt_keine_seite():
    assert SB.seite(w("Roma - Lazio", "Roma / Lazio")) is None


# ── Die zwei Fehlversuche auf dem Weg, jeder mit seinem Fall ────────────────────────────

def test_ein_kurzes_wort_darf_nicht_weggefiltert_werden():
    """Erster Versuch: „Kern = Woerter ab vier Zeichen". Das loeste Lucas' Fall und nahm
    167 E-Sport-Zeilen die Seite — „lgd" ist drei Zeichen, uebrig blieb „gaming", und das
    haben beide. Ein Filter, der das Unterscheidende wegwirft, weil es kurz ist."""
    assert SB.seite(w("LGD Gaming - Xtreme Gaming", "Xtreme Gaming")) == "Xtreme Gaming"
    assert SB.seite(w("LGD Gaming - Xtreme Gaming", "LGD Gaming")) == "LGD Gaming"


def test_die_rauschliste_darf_nicht_das_signal_enthalten():
    """Zweiter Versuch: „atletico" stand in der Rauschliste. Nach Abzug blieb „madrid",
    und das haben beide — „Atletico Madrid" verlor seine Seite."""
    assert SB.seite(w("Atletico Madrid - Real Madrid", "Atletico Madrid")) == "Atletico Madrid"
    assert SB.seite(w("Atletico Madrid - Real Madrid", "Real Madrid")) == "Real Madrid"


def test_ein_laengerer_name_in_der_auswahl_trifft_auch():
    """Der Feed schreibt „Inter" im Spielnamen und „Internazionale" in der Auswahl."""
    assert SB.seite(w("Roma - Inter", "Internazionale")) == "Inter"
    assert SB.seite(w("Roma - Inter", "Internazionale (2.5)")) == "Inter"


def test_ein_kurzer_anfang_trifft_nicht():
    """Sonst passt jedes Kuerzel auf jedes laengere Wort."""
    assert SB._trifft({"re"}, {"realmadrid"}) is False
    assert SB._trifft({"real"}, {"realmadrid"}) is True


def test_ein_rechtsform_kuerzel_auf_nur_einer_seite_stoert_nicht():
    assert SB.seite(w("IJsselmeervogels - VV Gemert",
                      "VV IJsselmeervogels")) == "IJsselmeervogels"


# ── Die Gegenprobe am echten Bestand ────────────────────────────────────────────────────

def test_keine_zeile_des_ledgers_verliert_ihre_seite():
    """Der Umbau darf nur hinzufuegen. Was vorher eine Seite hatte, behaelt sie."""
    f = BASE / "stake_bet_ledger.json"
    if not f.exists():
        return
    rows = json.loads(f.read_text(encoding="utf-8")).get("wetten") or []

    def alt(x):
        a = str((x or {}).get("auswahl") or "").lower()
        if not a:
            return None
        tr = [t for t in SB._teams((x or {}).get("event")) if t and t.lower() in a]
        return tr[0] if len(tr) == 1 else None

    verloren = [x for x in rows if alt(x) and not SB.seite(x)]
    gewechselt = [x for x in rows if alt(x) and SB.seite(x) and alt(x) != SB.seite(x)]
    assert not verloren, [(x.get("event"), x.get("auswahl")) for x in verloren[:5]]
    assert not gewechselt, [(x.get("event"), x.get("auswahl")) for x in gewechselt[:5]]
    assert sum(1 for x in rows if SB.seite(x)) > sum(1 for x in rows if alt(x))
