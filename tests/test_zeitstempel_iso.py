"""Ein Zeitstempel, den jemand LIEST, ist ISO. Menschenlesbares gehoert daneben, nicht hinein.

🔴 12.09.2026 (Lucas, Plattform-Audit). `mls_poly_prices.json` trug
`generatedAt: "12.09.2026 15:39 UTC"`. Das Frontend parst dieses Feld — und V8 liest „12.09.2026"
als **9. Dezember**, drei Monate in der Zukunft. `_pwDsAlterH()` rechnete daraus ein Alter von
**−2.110 h**.

Das ist die unangenehme Variante des Fehlers: nicht „die Warnung kam zu selten", sondern ein
negatives Alter liegt unter JEDER Schwelle — das Veraltet-Banner des Datensatzes konnte gar nicht
feuern, egal wie alt die Daten wurden. Ein Waechter, der strukturell stumm ist, sieht genauso aus
wie einer, der nichts zu melden hat.

Betroffen waren sechs Dateien aus fuenf Producern. Die schreiben jetzt ISO; wo der deutsche Text
fuer die Anzeige gebraucht wurde, steht er in einem eigenen `*Human`-Feld. Dieser Test haelt die
Regel fuer ALLE Artefakte fest — auch fuer die, die es noch nicht gibt.
"""
import json
import re
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent

# Felder, die irgendwo geparst werden. `*Human` ist bewusst ausgenommen — das ist der Ort,
# an dem ein deutsches Datum hingehoert.
GELESEN = {"generatedAt", "asof", "updatedAt", "updated_at", "dataUpdatedAt", "picksUpdatedAt",
           "oddsUpdatedAt", "timestamp", "geprueftAm", "capturedAt", "sentAt", "postedAt",
           "resolvedAt", "settledAt", "firstSeen", "lastRun", "startAb"}
DEUTSCH = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}")
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}|$)")

# Producer, die so ein Feld schreiben. Direkt am Quelltext geprueft, damit der Test auch dann
# anschlaegt, wenn das Artefakt gerade nicht im Repo liegt.
PRODUCER_MUSTER = re.compile(
    r'"(%s)"\s*:\s*[^,\n]*strftime\(\s*["\'][^"\']*%%d\.%%m\.%%Y' % "|".join(sorted(GELESEN)))


# Artefakte, die den alten Stempel NOCH tragen — ihr Producer schreibt bereits ISO, sie warten
# nur auf ihren naechsten Lauf. Kein Freibrief: `test_die_liste_raeumt_sich_selbst` wirft jeden
# Eintrag raus, sobald die Datei ISO traegt, und `test_jeder_wartende_producer_schreibt_ISO`
# prueft, dass hier wirklich nur Wartezeit steht und kein ungefixter Producer.
# Lokale Artefakte werden bewusst NICHT von Hand umgeschrieben — Pipeline-Ausgabe gehoert der
# Pipeline.
WARTET_AUF_LAUF = {
    "validator_summary.json": "check_picks_logic.py / update_dashboard.py — beide schreiben ISO, "
                              "das committete Artefakt stammt noch aus einem Lauf davor",
    "wm_poly_prices.json": "fetch_wm_poly_prices.py (WM) — WM beendet, laeuft erst wieder 2030",
    "wm_poly_positions.json": "manage_wm_poly_positions.py — WM beendet",
    "wm_weather.json": "fetch_wm_weather.py — WM beendet",
}


def _artefakte():
    for pfad in sorted(WURZEL.glob("*.json")):
        if pfad.stat().st_size > 40_000_000:
            continue
        try:
            yield pfad, json.loads(pfad.read_text(encoding="utf-8"))
        except Exception:
            continue


def _zeitfelder(objekt, pfad="", tiefe=0):
    if tiefe > 3:
        return
    if isinstance(objekt, dict):
        for k, v in objekt.items():
            if k in GELESEN and isinstance(v, str) and v:
                yield pfad + k, v
            elif isinstance(v, (dict, list)):
                yield from _zeitfelder(v, pfad + k + ".", tiefe + 1)
    elif isinstance(objekt, list):
        for eintrag in objekt[:3]:
            yield from _zeitfelder(eintrag, pfad + "[].", tiefe + 1)


class TestZeitstempelSindISO(unittest.TestCase):
    def test_kein_artefakt_traegt_ein_deutsches_datum_in_einem_gelesenen_feld(self):
        fehler = []
        for pfad, daten in _artefakte():
            for feld, wert in _zeitfelder(daten):
                if DEUTSCH.match(wert) and pfad.name not in WARTET_AUF_LAUF:
                    fehler.append(f"{pfad.name}: {feld} = {wert!r} — V8 liest das als "
                                  f"MONAT.TAG und landet Monate daneben")
        self.assertEqual(fehler, [], "\n" + "\n".join(fehler)
                         + "\n\nISO ins gelesene Feld, Menschenlesbares in ein `*Human`-Feld.")

    def test_kein_producer_schreibt_ein_deutsches_datum_in_ein_gelesenes_feld(self):
        """Die wichtigere Haelfte: das Artefakt kann gerade fehlen, der Producer bleibt."""
        fehler = []
        for py in sorted(WURZEL.glob("*.py")):
            for nr, zeile in enumerate(py.read_text(encoding="utf-8").split("\n"), 1):
                if zeile.lstrip().startswith("#"):
                    continue            # ein Kommentar darf den Fehler beschreiben
                if PRODUCER_MUSTER.search(zeile):
                    fehler.append(f"{py.name}:{nr}: {zeile.strip()[:120]}")
        self.assertEqual(fehler, [], "\n" + "\n".join(fehler))

    def test_der_scanner_findet_ueberhaupt_zeitfelder(self):
        """Gegenprobe: der Test oben waere auch dann gruen, wenn gar nichts geprueft wird."""
        gefunden = sum(1 for _, d in _artefakte() for _ in _zeitfelder(d))
        self.assertGreater(gefunden, 50,
                           "Der Zeitfeld-Scanner findet fast nichts mehr — dann prueft dieser "
                           "Test Luft, nicht das Repo.")

    def test_die_gefundenen_stempel_sind_wirklich_lesbar(self):
        """Nicht nur „nicht deutsch", sondern parsbar. Sonst rutscht das naechste Format durch,
        das V8 auch nicht versteht."""
        krumm = []
        for pfad, daten in _artefakte():
            for feld, wert in _zeitfelder(daten):
                if not ISO.match(wert) and pfad.name not in WARTET_AUF_LAUF:
                    krumm.append(f"{pfad.name}: {feld} = {wert!r}")
        self.assertEqual(krumm, [], "\nWeder ISO noch erkennbar:\n" + "\n".join(krumm))


class TestDieWarteListeVerrottetNicht(unittest.TestCase):
    def test_die_liste_raeumt_sich_selbst(self):
        """Sobald eine Datei ISO traegt, gehoert ihr Eintrag raus — sonst deckt die Liste
        irgendwann einen echten Rueckfall."""
        fertig = []
        for name in sorted(WARTET_AUF_LAUF):
            pfad = WURZEL / name
            if not pfad.exists():
                continue
            try:
                daten = json.loads(pfad.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not any(DEUTSCH.match(w) for _, w in _zeitfelder(daten)):
                fertig.append(f"{name} traegt jetzt ISO — Eintrag aus WARTET_AUF_LAUF entfernen")
        self.assertEqual(fertig, [], "\n" + "\n".join(fertig))

    def test_jeder_wartende_producer_schreibt_ISO(self):
        """Hier darf nur Wartezeit stehen, kein ungefixter Producer. Sonst waere die Liste
        genau das, was sie verhindern soll."""
        offen = []
        for py in sorted(WURZEL.glob("*.py")):
            for zeile in py.read_text(encoding="utf-8").split("\n"):
                if zeile.lstrip().startswith("#"):
                    continue
                if PRODUCER_MUSTER.search(zeile):
                    offen.append(py.name)
        self.assertEqual(sorted(set(offen)), [],
                         "\nEin Producer schreibt weiterhin ein deutsches Datum in ein gelesenes "
                         "Feld — dann ist WARTET_AUF_LAUF keine Wartezeit, sondern ein Deckel:\n"
                         + "\n".join(sorted(set(offen))))


class TestDasFrontendHaeltBeideFormateAus(unittest.TestCase):
    """Guertel zum Hosentraeger: die Producer schreiben ISO, aber alte Dateien liegen noch im
    Repo. Der Parser muss beides koennen — und ein Datum in der ZUKUNFT abweisen, statt daraus
    Frische zu machen."""

    def test_der_parser_versteht_das_deutsche_altformat(self):
        js = (WURZEL / "poly-wallets.js").read_text(encoding="utf-8")
        self.assertIn("function _pwZeit(", js)
        self.assertIn("t > Date.now() + 3600e3", js,
                      "ein Zeitstempel in der Zukunft ist kaputt, nicht frisch — genau daran ist "
                      "das Banner drei Monate lang gescheitert")


if __name__ == "__main__":
    unittest.main()
