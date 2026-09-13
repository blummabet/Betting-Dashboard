"""🔴 12.09.2026 (Lucas: „Vor allem am iPhone ladet die Übersichtsseite beim ersten Aufruf recht
langsam. Und bevor Übersicht ist mmn der einsprungspunkt die alte Card Seite, mit dieser komischen
grünen infoleiste … Ja im privaten tab ist auch Kurz quasi national zu sehen, bevor es dann auf
Übersicht springt.")

## Was da passierte

Der Einstieg IST die Uebersicht — entschieden hat das aber `showView('home')`, und das lief erst
nach `window.load` + 60 ms: also nach 22 nacheinander geladenen Skripten, zwei CDN-Bibliotheken
und allen Bildern. Bis dahin zeigte die Seite den Startzustand des Markups, und darin waren
Sub-Navi und League-Navi (beides National) SICHTBAR. Am iPhone sind das Sekunden, im privaten Tab
ohne Cache noch mehr — deshalb sah Lucas dort „kurz quasi national".

## Die Fehlerklasse

    Das statische Markup behauptet eine Ansicht, die der View-Switcher erst spaeter bestimmt.

Sie ist aelter als dieser Vorfall: im Juni wurde derselbe Effekt schon einmal mit einem
`_hideOldNav()` in JavaScript bekaempft (Kommentar im HTML: „sonst beim Direktaufruf sichtbar").
Das hat den Zeitpunkt verschoben, nicht die Ursache beseitigt — JavaScript kann nun mal erst
laufen, wenn es geladen ist. Der Startzustand gehoert ins Markup.

## Warum der Test am Quelltext haengt

Weil genau der erste Paint gemeint ist. Ein Test, der die Seite rendert und danach schaut, sieht
immer den Zustand NACH dem Switcher — also nie den Fehler. Gemessen wird deshalb, was im
ausgelieferten HTML steht, bevor eine Zeile JavaScript gelaufen ist.
"""
import re
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
HTML = WURZEL / "season-finish-v2.html"
UI = WURZEL / "ui.js"


def _ohne_kommentare(quelle):
    """Ganze Kommentarzeilen raus. Sonst liest der Test einen Namen aus einem Kommentar mit —
    genau das ist beim Bauen dieses Tests passiert: die Notiz „…Panel raus" nannte den Namen in
    Anfuehrungszeichen, und der Test hielt ihn fuer einen Eintrag der Liste."""
    return "\n".join("" if z.lstrip().startswith("//") else z for z in quelle.splitlines())


def _liste_aus_ui(name):
    """Ein Array-Literal aus ui.js lesen — damit der Test mitwaechst, wenn dort ein Panel dazukommt."""
    quelle = _ohne_kommentare(UI.read_text(encoding="utf-8"))
    m = re.search(r"const %s = \[(.*?)\];" % name, quelle, flags=re.DOTALL)
    assert m, f"{name} nicht in ui.js gefunden — der Test haengt an einem Namen, den es nicht mehr gibt"
    return re.findall(r"'([^']+)'", m.group(1))


def _panel_map():
    quelle = _ohne_kommentare(UI.read_text(encoding="utf-8"))
    m = re.search(r"const panelMap = \{(.*?)\};", quelle, flags=re.DOTALL)
    assert m, "panelMap nicht in ui.js gefunden"
    return dict(re.findall(r"'([^']+)':\s*'([^']+)'", m.group(1)))


def _start_ansicht():
    """Die Ansicht, mit der die Seite startet — aus dem Boot-Aufruf im HTML gelesen."""
    quelle = HTML.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"_bootHome.*?showView\('([a-z-]+)'\)", quelle, flags=re.DOTALL)
    assert m, "kein _bootHome mit showView(...) im HTML — Startansicht unbekannt"
    return m.group(1)


def _start_tag(html, element_id):
    m = re.search(r'<[a-zA-Z]+[^>]{0,600}?id="%s"[^>]{0,600}?>' % re.escape(element_id), html)
    return m.group(0) if m else None


def _statisch_versteckt(tag):
    return "display:none" in (tag or "").replace(" ", "")


class TestDerErstePaintZeigtKeineFremdeAnsicht(unittest.TestCase):
    def setUp(self):
        self.html = HTML.read_text(encoding="utf-8", errors="replace")
        self.start = _start_ansicht()
        self.panels = _liste_aus_ui("_ALL_PANELS")
        self.sichtbares_panel = _panel_map().get(self.start)

    def test_nur_das_panel_der_startansicht_ist_im_markup_sichtbar(self):
        offen = []
        for pid in self.panels:
            if pid == self.sichtbares_panel:
                continue
            tag = _start_tag(self.html, pid)
            if tag is None:
                continue   # Panel-ID ohne Markup faengt test_jede_panel_id_existiert
            if not _statisch_versteckt(tag):
                offen.append(pid)
        self.assertEqual(offen, [], "\nDiese Panels sind beim ersten Paint sichtbar, obwohl die "
                                    "Startansicht '%s' sie ausblendet:\n  %s\n\n"
                                    "`style=\"display:none\"` ins Markup — showView setzt beim "
                                    "Anzeigen `style.display = ''` und hebt es damit auf."
                         % (self.start, ", ".join(offen)))

    def test_die_national_navigation_ist_im_markup_versteckt(self):
        """Sub-Navi und League-Navi gehoeren zur National-Ansicht — genau das, was Lucas
        aufblitzen sah. `showView` nimmt sie weg; im Markup duerfen sie gar nicht erst da sein."""
        for eid in ("subNav", "leagueNav"):
            with self.subTest(element=eid):
                tag = _start_tag(self.html, eid)
                self.assertIsNotNone(tag, f"#{eid} gibt es nicht mehr — Test anpassen")
                self.assertTrue(_statisch_versteckt(tag),
                                f"#{eid} ist beim ersten Paint sichtbar")

    def test_das_panel_der_startansicht_laesst_sich_ueberhaupt_zeigen(self):
        """Die Gegenprobe — und die Falle, in die man beim Fixen laeuft: `showView` zeigt ein
        Panel mit `style.display = ''`. Das schlaegt eine INLINE-Regel, aber keine aus dem
        Stylesheet. Wer ein Panel per CSS versteckt, versteckt es fuer immer."""
        stil = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", self.html, flags=re.DOTALL))
        stil = re.sub(r"/\*.*?\*/", " ", stil, flags=re.DOTALL)
        tot = []
        for pid in self.panels:
            for m in re.finditer(r"#%s[^{,]*\{([^}]*)\}" % re.escape(pid), stil):
                if "display:none" in m.group(1).replace(" ", ""):
                    tot.append(pid)
        self.assertEqual(sorted(set(tot)), [],
                         "\nPer Stylesheet versteckte Panels — showView kann sie nicht mehr "
                         "zeigen (`style.display = ''` faellt auf genau diese Regel zurueck): %s"
                         % ", ".join(sorted(set(tot))))

    def test_die_startansicht_wartet_nicht_auf_load(self):
        """Der zweite Teil desselben Fundes: die Entscheidung hing an `window.load`. Selbst mit
        sauberem Markup waere die Uebersicht dann erst nach allen Skripten und Bildern da."""
        m = re.search(r"\(function _bootHome\(\).*?\}\)\(\);", self.html, flags=re.DOTALL)
        self.assertIsNotNone(m, "_bootHome nicht gefunden")
        block = m.group(0)
        self.assertNotIn("setTimeout(go, 60)", block,
                         "die Startansicht haengt wieder an einem Timer nach `load`")
        self.assertTrue(re.search(r"if \(!go\(\)\)", block),
                        "_bootHome muss SOFORT versuchen zu schalten und `load` nur als "
                        "Rueckfall nehmen")

    def test_die_versteckte_ansicht_wird_nicht_im_voraus_gerendert(self):
        """4 MB liga-data.json fuer ein Panel, das der Einstieg sofort wieder ausblendet —
        und wegen `cache: no-store` ein zweites Mal, obwohl die Uebersicht dieselbe Datei holt."""
        m = re.search(r"\(function _bootNationalCards\(\).*?\}\)\(\);", self.html, flags=re.DOTALL)
        self.assertIsNotNone(m, "_bootNationalCards nicht gefunden")
        ohne_kommentar = "\n".join(z for z in m.group(0).splitlines()
                                   if not z.lstrip().startswith("//"))
        self.assertNotIn("initNationalCards()", ohne_kommentar,
                         "die National-Cards werden wieder beim Start gerendert, obwohl der "
                         "Einstieg die Uebersicht ist — showView ruft sie beim Oeffnen auf")

    def test_jede_panel_id_existiert_im_markup(self):
        """Sonst prueft der Test oben stillschweigend nichts mehr."""
        fehlt = [p for p in self.panels if _start_tag(self.html, p) is None]
        self.assertEqual(fehlt, [], "Panel-IDs aus ui.js ohne Markup: %s" % ", ".join(fehlt))


if __name__ == "__main__":
    unittest.main()
