"""🔴 12.09.2026 — jede Sende-Schleife braucht eine Grenze, die AN DER SCHLEIFE steht.

Der Vorfall: „Ich hab grad knapp 20 pushes in public bekommen — irgendwelche einzelner zu
Serien. Sowas gabs in der Form noch nie." Ausgeloest hat ihn ein Fix am selben Tag: das
Serien-Buch hatte nie etwas abgerechnet, danach raeumte ein Lauf den Rueckstau aus sechs Wochen
ab — und die Schleife schickte je Zeile eine Nachricht. Zwei weitere Datensaetze haetten am
selben Abend nochmal 80 geschickt.

Die Klasse ist nicht „das Serien-Skript", sondern:

    Eine Schleife sendet je Element, und die Laenge der Liste haengt an einem Zustand, der
    springen kann — ein erster erfolgreicher Lauf, ein zurueckgesetzter Dedup, ein Tag mit
    ungewoehnlich vielen Spielen.

Dedup schuetzt dagegen nicht: er verhindert, dass DIESELBE Sache zweimal kommt; ein Rueckstau
besteht aus lauter verschiedenen Sachen, die alle zum ersten Mal dran sind. Deshalb war der
Vorfall bei intaktem Dedup moeglich, und deshalb reicht „da ist doch ein Dedup" hier nicht als
Begruendung.

Warum der Test am Quelltext haengt und nicht am Verhalten: die gefaehrlichen Laeufe sind genau
die, die es noch nie gegeben hat. Ein Verhaltenstest kann nur pruefen, was er sich ausdenkt;
dieser hier prueft, dass ueberhaupt eine Grenze dasteht — in jeder Schleife, auch in der, die
naechste Woche jemand dazuschreibt.
"""
import ast
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent

# Sende-Funktionen. Wer eine neue baut, traegt sie hier ein — sonst bewacht der Test sie nicht.
SENDER = {"tg_send", "tg_send_text", "tg_send_photo", "send_photo", "tg_post"}

# Schleifen ohne Deckel, mit Grund. Kein Freibrief: `test_jede_ausnahme_wird_noch_gebraucht`
# wirft jeden Eintrag raus, sobald die Schleife einen Deckel hat oder verschwunden ist.
AUSNAHMEN = {
    ("telegram_wm.py", 817): "Schleife ueber TG_LANGS — eine Sprachliste aus der Konfiguration, "
                             "keine Datenmenge. Sie waechst, wenn jemand eine Sprache dazustellt, "
                             "nicht wenn ein Rueckstau abflieszt.",
    ("telegram_wm.py", 851): "dito — dieselbe Sprachliste, Recap-Karte statt Morgenkarte.",
}


def _module_dateien():
    for p in sorted(WURZEL.glob("*.py")):
        yield p


def _deckel_namen(baum):
    """Namen, die in diesem Modul an einen `Deckel(...)` gebunden werden."""
    namen = set()
    for n in ast.walk(baum):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
            f = n.value.func
            nm = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if nm == "Deckel":
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        namen.add(t.id)
    return namen


def _eltern(baum):
    e = {}
    for n in ast.walk(baum):
        for c in ast.iter_child_nodes(n):
            e[c] = n
    return e


def _sende_schleifen():
    """(datei, zeile, gedeckelt) je Sende-Aufruf, der in einer Schleife steht."""
    aus = []
    for p in _module_dateien():
        try:
            baum = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        deckel, eltern = _deckel_namen(baum), _eltern(baum)
        for n in ast.walk(baum):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            nm = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if nm not in SENDER and nm not in deckel:
                continue
            cur, schleifen = n, []
            while cur in eltern:
                cur = eltern[cur]
                if isinstance(cur, (ast.For, ast.While, ast.AsyncFor)):
                    schleifen.append(cur)
            if not schleifen:
                continue
            # Gedeckelt ist: der Send geht durch einen Deckel, ODER eine der umgebenden
            # Schleifen laeuft ueber einen Ausschnitt (`kandidaten[:MAX_ALERTS]`).
            gedeckelt = nm in deckel or any(
                isinstance(l, ast.For) and isinstance(l.iter, ast.Subscript)
                and isinstance(l.iter.slice, ast.Slice) for l in schleifen)
            aus.append((p.name, n.lineno, gedeckelt))
    return aus


class TestJedeSendeSchleifeHatEineGrenze(unittest.TestCase):
    def test_keine_ungedeckelte_sende_schleife(self):
        offen = [f"{d}:{z}" for d, z, ok in _sende_schleifen()
                 if not ok and (d, z) not in AUSNAHMEN]
        self.assertEqual(offen, [], "\nSende-Schleife ohne Grenze:\n" + "\n".join(offen)
                         + "\n\nEntweder ueber einen Ausschnitt laufen (`cand[:MAX]`) oder den "
                           "Send durch `push_deckel.Deckel` schicken. Ein Dedup ist keine "
                           "Grenze — er haelt Wiederholungen zurueck, keinen Rueckstau.")

    def test_jede_ausnahme_wird_noch_gebraucht(self):
        """Sonst deckt die Liste irgendwann eine Schleife, die laengst eine Grenze haben muesste."""
        gefunden = {(d, z): ok for d, z, ok in _sende_schleifen()}
        tot = []
        for schluessel in sorted(AUSNAHMEN):
            if schluessel not in gefunden:
                tot.append(f"{schluessel[0]}:{schluessel[1]} — diese Schleife gibt es nicht mehr "
                           f"(oder sie hat die Zeile gewechselt)")
            elif gefunden[schluessel]:
                tot.append(f"{schluessel[0]}:{schluessel[1]} — hat jetzt eine Grenze, "
                           f"Ausnahme entfernen")
        self.assertEqual(tot, [], "\n" + "\n".join(tot))

    def test_der_waechter_sieht_ueberhaupt_etwas(self):
        """Gegenprobe gegen sich selbst: findet die Suche keine Schleifen mehr (umbenannter
        Sender, kaputtes Parsen), waere dieser Test gruen und wertlos."""
        self.assertGreaterEqual(len(_sende_schleifen()), 10)


class TestDerDeckelSelbst(unittest.TestCase):
    def setUp(self):
        import push_deckel
        self.PD = push_deckel

    def _zaehler(self):
        gesendet = []
        return gesendet, (lambda t: (gesendet.append(t), True)[1])

    def test_laesst_die_ersten_durch_und_haelt_den_rest(self):
        raus, sender = self._zaehler()
        d = self.PD.Deckel(sender, 3, "test")
        ergebnisse = [d(f"m{i}") for i in range(10)]
        self.assertEqual(len(raus), 3)
        self.assertEqual(ergebnisse[:3], [True] * 3)
        self.assertEqual(ergebnisse[3:], [False] * 7)

    def test_das_zurueckgehaltene_wird_gezaehlt(self):
        """Ein stiller Deckel ist nur eine andere Art, Information zu verlieren."""
        _r, sender = self._zaehler()
        d = self.PD.Deckel(sender, 2, "test")
        for i in range(9):
            d(i)
        self.assertEqual((d.gesendet, d.unterdrueckt), (2, 7))
        self.assertIn("7", d.bericht())

    def test_ein_fehlgeschlagener_send_verbraucht_kein_kontingent(self):
        """Sonst frisst ein kaputter Telegram-Token den Deckel auf und die Nachrichten, die
        danach haetten gehen koennen, fallen still weg."""
        d = self.PD.Deckel(lambda t: False, 2, "test")
        for i in range(5):
            d(i)
        self.assertEqual(d.gesendet, 0)
        self.assertFalse(d.voll)

    def test_zurueckgehalten_sieht_aus_wie_nicht_gesendet(self):
        """Der Rueckgabewert ist der ganze Punkt: der Aufrufer setzt seinen Dedup-Stempel nur
        bei True. Waere der Deckel-Fall True, wuerde die Nachricht als erledigt gebucht und
        nie geschickt — aus einer Flut wuerde stiller Verlust."""
        d = self.PD.Deckel(lambda t: True, 1, "test")
        self.assertTrue(d("erste"))
        self.assertFalse(d("zweite"))

    def test_ein_deckel_unter_eins_ist_ein_konfigurationsfehler(self):
        with self.assertRaises(ValueError):
            self.PD.Deckel(lambda t: True, 0, "test")

    def test_bericht_nennt_grenze_und_stand(self):
        d = self.PD.Deckel(lambda t: True, 5, "Serien-Recap")
        d("x")
        self.assertIn("Serien-Recap", d.bericht())
        self.assertIn("1/5", d.bericht())


if __name__ == "__main__":
    unittest.main()
