"""🔴 12.09.2026 (Lucas: „Vor allem am iPhone ladet die Übersichtsseite beim ersten Aufruf recht
langsam").

## Was gemessen wurde

Die Uebersicht holt ihre Kacheln aus einem `Promise.all` — es rendert also erst, wenn die LETZTE
Datei da ist. Am Messtag waren das 17 Dateien mit zusammen **27 MB**, alle mit `cache: no-store`,
und wegen des 2-Minuten-Refresh alle zwei Minuten erneut. Zwei Dateien trugen 17 MB davon:

    poly_money_broad_close.json   6,0 MB   3.208 Maerkte — gelesen werden die 44 offenen
    betfair_track_record.json    11,1 MB   gelesen wird EIN Feld (byLeagueMarket, 1,0 MB)

## Die Fehlerklasse

    Eine Flaeche laedt das Rohbuch, obwohl sie nur eine Zusammenfassung braucht.

Sie ist nicht auf diese zwei Dateien beschraenkt und sie faellt im Betrieb nie auf: am Rechner
mit Glasfaser rendert auch eine 27-MB-Seite fluessig, und keine Zahl im Dashboard ist falsch. Sie
faellt nur am Handy auf, und dort als „ist halt langsam".

Der Schnitt gehoert dorthin, wo die Daten entstehen — der Produzent schreibt den Ausschnitt mit,
aus demselben Objekt im selben Moment. Ein Schnitt im Frontend haette nichts gebracht: die Bytes
sind dann schon ueber die Leitung.
"""
import os
import re
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent

# Deckel fuer die Summe der Uebersichts-Dateien. Eine Ratsche, kein Naturgesetz: waechst die
# Summe darueber, ist die Antwort ein schlankeres Artefakt und nicht eine groessere Zahl.
BUDGET_MB = 12.0
# Kein einzelnes Artefakt darf die Ladezeit allein bestimmen.
EINZEL_MAX_MB = 5.0

# Rohbuecher, die hier nichts zu suchen haben — mit der schlanken Fassung, die sie ersetzt.
ROHBUECHER = {
    "poly_money_broad_close.json": "poly_money_broad_offen.json",
    "betfair_track_record.json": "betfair_track_kompakt.json",
}


def _fetch_liste():
    """Die Dateien, die `_mdFetch` in ihrem `Promise.all` holt.

    Bei `jfSchlank(klein, gross)` zaehlt die KLEINE: die grosse ist der dokumentierte Rueckfall
    fuer den einen Lauf zwischen Deploy und naechstem Produzenten-Durchgang.
    """
    quelle = (WURZEL / "main-dashboard.js").read_text(encoding="utf-8")
    m = re.search(r"return Promise\.all\(\[(.*?)\]\);", quelle, flags=re.DOTALL)
    assert m, "das Promise.all von _mdFetch ist nicht mehr zu finden"
    block = "\n".join(z for z in m.group(1).splitlines() if not z.lstrip().startswith("//"))
    treffer = re.findall(r"jfSchlank\('([^']+)',\s*'[^']+'\)|jf\('([^']+)'\)", block)
    return [a or b for a, b in treffer]


def _mb(name):
    """Was die Seite an dieser Datei zu PARSEN hat — nach der Normalisierung.

    🔴 22.09.2026: hier stand schlicht die Dateigroesse. Das war die falsche Zahl, und zwar
    doppelt:

      · Ueber die Leitung gehen 1,23 MB statt 12,7 — GitHub liefert gzip. Das Netz war nie
        das Problem; Parse-Zeit und Speicher am Handy sind es.
      · Und seit heute nehmen fuenf Workflows kurz vor `git add` die Einrueckung heraus
        (scripts/json_kompakt.py). Solange der naechste Produzentenlauf nicht durch ist, liegt
        hier noch die eingerueckte Fassung — die Ratsche haette also einen Zustand gemessen,
        den das System gerade selbst beseitigt. Fehlerklasse: eine Messung, die den Zustand
        VOR der eigenen Reparatur festhaelt.

    Deshalb: fuer Dateien, die ein Workflow normalisiert, zaehlt die kompakte Groesse; fuer
    alle anderen die echte. Wer die Normalisierung aus einem Workflow entfernt, sieht die
    Ratsche sofort wieder anziehen — und `tests/test_json_kompakt.py` schlaegt zusaetzlich an.
    """
    p = WURZEL / name
    if not p.exists():
        return None
    roh = p.read_bytes()
    if name not in _normalisiert():
        return len(roh) / 1024 / 1024
    try:
        import json as _j
        kompakt = _j.dumps(_j.loads(roh.decode("utf-8")), ensure_ascii=False,
                           separators=(",", ":")).encode("utf-8")
    except Exception:
        return len(roh) / 1024 / 1024
    return min(len(roh), len(kompakt)) / 1024 / 1024


def _normalisiert():
    """Die Dateien, die irgendein Workflow vor dem Stagen kompakt schreibt."""
    aus = set()
    wf = WURZEL / ".github" / "workflows"
    if not wf.is_dir():
        return aus
    for f in wf.glob("*.yml"):
        for z in f.read_text(encoding="utf-8").splitlines():
            if "scripts/json_kompakt.py" in z:
                aus |= set(re.findall(r"[\w\-]+\.json", z))
    return aus


def _dauerlast(dateien):
    """Was die Seite bei JEDEM automatischen Refresh neu laedt — also ohne die Dateien, die
    `MD_CACHE_MIN` in main-dashboard.js zwischenspeichert.

    Bis zum 22.09.2026 war das dieselbe Zahl wie oben: alle 17 Dateien, alle zwei Minuten,
    mit `no-store` und Cache-Buster. Die schwerste wechselt alle 110 Minuten und wurde 30x
    pro Stunde geholt.
    """
    js = (WURZEL / "main-dashboard.js").read_text(encoding="utf-8")
    if "MD_CACHE_MIN" not in js:
        return None, set()
    block = js.split("var MD_CACHE_MIN")[1].split("};")[0]
    gecacht = set(re.findall(r"'([^']+\.json)':\s*\d+", block))
    summe = sum(g for f, g in ((f, _mb(f)) for f in dateien)
                if g is not None and f not in gecacht)
    return summe, gecacht


class TestDieUebersichtBleibtLeicht(unittest.TestCase):
    def setUp(self):
        self.dateien = _fetch_liste()

    def test_die_liste_wird_ueberhaupt_gefunden(self):
        """Gegenprobe gegen sich selbst: findet die Suche nichts, waeren alle Tests hier gruen."""
        self.assertGreaterEqual(len(self.dateien), 10)

    def test_kein_rohbuch_in_der_uebersicht(self):
        """Der eigentliche Riegel — und der, der auch dann haelt, wenn die Dateien schrumpfen.

        An Groessen allein kann man das nicht festmachen: `betfair_track_record.json` war mal
        klein und ist mit dem Team-Markt-Raster gewachsen, ohne dass jemand die Uebersicht
        angefasst haette. Die Regel ist deshalb, WAS gelesen wird, nicht wie viel.
        """
        drin = [f for f in self.dateien if f in ROHBUECHER]
        self.assertEqual(drin, [], "\nDie Uebersicht laedt wieder ein Rohbuch:\n" + "\n".join(
            f"  {f} — stattdessen {ROHBUECHER[f]}" for f in drin))

    def test_summe_unter_budget(self):
        bekannt = [(f, _mb(f)) for f in self.dateien if _mb(f) is not None]
        summe = sum(g for _f, g in bekannt)
        gross = sorted(bekannt, key=lambda x: -x[1])[:5]
        self.assertLessEqual(summe, BUDGET_MB,
                             "\nDie Uebersicht laedt %.1f MB vor der ersten Kachel (Budget %.1f MB).\n"
                             "Die groessten:\n%s\n\nDer Weg ist ein schlankeres Artefakt beim "
                             "Produzenten, nicht ein groesseres Budget."
                             % (summe, BUDGET_MB,
                                "\n".join(f"  {f:34s} {g:6.1f} MB" for f, g in gross)))

    def test_die_dauerlast_ist_deutlich_kleiner_als_der_erste_aufruf(self):
        """🔴 22.09.2026 (Lucas: „was ist da jetzt mit diesen 12 Megabyte").

        Der erste Aufruf muss alles holen — daran ist nichts zu sparen, und genau darueber ging
        die Beschwerde am 12.09. Was sich sparen laesst, ist die WIEDERHOLUNG: die Seite lud
        alle 17 Dateien alle zwei Minuten erneut, obwohl die schwerste sich alle 110 Minuten
        aendert (gemessen ueber `git log --since='7 days ago'`).

        Diese Ratsche haelt fest, dass der automatische Refresh deutlich weniger traegt als der
        erste Aufruf. Faellt der Abstand zusammen, ist entweder `MD_CACHE_MIN` leer geraeumt
        worden oder eine neue schwere Datei ist ungecacht dazugekommen.
        """
        erst = sum(g for g in (_mb(f) for f in self.dateien) if g is not None)
        dauer, gecacht = _dauerlast(self.dateien)
        self.assertIsNotNone(dauer, "MD_CACHE_MIN fehlt in main-dashboard.js")
        self.assertTrue(gecacht, "kein einziges Artefakt wird zwischengespeichert")
        self.assertLessEqual(dauer, erst * 0.6,
                             "\nDer automatische Refresh laedt %.1f MB von %.1f MB erneut — "
                             "zu viel.\nGecacht sind: %s\nDer Weg ist ein Eintrag in "
                             "MD_CACHE_MIN fuer schwere, traege Dateien (die Aenderungsrate "
                             "prueft tests/frontend/uebersicht-refresh-takt.test.mjs)."
                             % (dauer, erst, ", ".join(sorted(gecacht)) or "—"))

    def test_keine_einzeldatei_bestimmt_die_ladezeit_allein(self):
        zu_gross = [(f, _mb(f)) for f in self.dateien
                    if _mb(f) is not None and _mb(f) > EINZEL_MAX_MB]
        self.assertEqual(zu_gross, [], "\nEinzelne Artefakte ueber %.1f MB:\n%s"
                         % (EINZEL_MAX_MB,
                            "\n".join(f"  {f} — {g:.1f} MB" for f, g in zu_gross)))


class TestDerAusschnittEntstehtBeimProduzenten(unittest.TestCase):
    """Ohne diese Schreibstellen faellt die Uebersicht dauerhaft auf die Rohbuecher zurueck —
    still, denn die Kacheln sehen dann genauso aus wie vorher."""

    def test_betfair_schreibt_die_kompakte_fassung(self):
        quelle = (WURZEL / "betfair_track_record.py").read_text(encoding="utf-8")
        self.assertIn("_write(KOMPAKT_FILE, kompakt(record))", quelle)

    def test_die_kompakte_fassung_ist_subtraktiv_definiert(self):
        """Eine Positivliste veraltet still: ein neues Feld oben fehlt unten, und die Uebersicht
        zeigt es nie. Deshalb wird weggelassen, nicht aufgezaehlt."""
        import betfair_track_record as B
        voll = {"a": 1, "byTeamMarket": {"x": 1}, "brandneu": 42}
        self.assertEqual(B.kompakt(voll), {"a": 1, "brandneu": 42})

    def test_poly_schreibt_beide_dateien_immer_zusammen(self):
        """Getrennte Schreibzeilen waeren die naechste Fehlerklasse: ein Zweig schreibt nur die
        grosse Datei, der Ausschnitt friert ein — und beide traegen Daten, es faellt nichts auf."""
        quelle = (WURZEL / "poly_money_broad.py").read_text(encoding="utf-8")
        ohne_kommentar = "\n".join(z for z in quelle.splitlines()
                                   if not z.lstrip().startswith("#"))
        direkt = len(re.findall(r"write_json_atomic\(\(BASE / CLOSE_FILE\)", ohne_kommentar))
        self.assertEqual(direkt, 1, "der Close-Feed wird an %d Stellen direkt geschrieben — "
                                    "alle ausser der in `close_schreiben` umstellen" % direkt)
        self.assertGreaterEqual(ohne_kommentar.count("close_schreiben(frozen)"), 2)

    def test_der_ausschnitt_traegt_genau_die_offenen_maerkte(self):
        import poly_money_broad as P
        roh = {"a": {"resolved": None, "x": 1}, "b": {"resolved": "YES"}, "c": {"x": 2}}
        self.assertEqual(sorted(P.offene_maerkte(roh)), ["a", "c"],
                         "ohne `resolved`-Feld ist ein Markt offen, nicht erledigt")


if __name__ == "__main__":
    unittest.main()
