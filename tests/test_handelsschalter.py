#!/usr/bin/env python3
"""test_handelsschalter.py — kein Schalter, der Geld ausgibt, darf von allein AN sein.

## Der Vorfall

20.09.2026 (Lucas, nach dem Blick in die Repo-Secrets: „übrigens gibt es dieses secret nicht
nur diese … wie kann das schon wieder sein? puhhh macht mich echt wütend wenn solche sachen
nicht passen").

`LIGA_AUTO_TRIGGER_ENABLED` existiert nicht und hat nie existiert. In
`manage-liga-poly.yml` stand trotzdem:

    AUTO_TRIGGER_ENABLED: ${{ secrets.LIGA_AUTO_TRIGGER_ENABLED || 'true' }}

Der Kommentar daneben sagte „Aus: Secret LIGA_AUTO_TRIGGER_ENABLED=false setzen" — also
genau das Gegenteil dessen, was die Zeile tat. Das Secret WAR der Aus-Schalter, nur war der
Standardzustand ohne ihn: echtes Geld. Sieben Liga-Wetten sind so platziert worden.

## Die Fehlerklasse

    Fehlende Information rendert als harmloser Default — nur ist der Default hier nicht
    harmlos. Ein gelöschtes, vertipptes oder nie angelegtes Secret schaltet den Handel EIN.

Es ist dieselbe Klasse wie beim Stale-Odds-Stop („fehlende Information ist keine Freigabe"),
nur eine Etage höher: dort entscheidet sie über einen Trade, hier über den ganzen Trader.

## Was dieser Test festhält

Jeder Schalter, der ORDERS AUSLÖST, muss ohne Secret AUS sein. Schalter, die nur SCHLIESSEN
(`AUTO_SELL_ENABLED`), dürfen und sollen an sein: ihr Ausfall ist das teurere Ereignis —
Toulouse–Le Havre lief am 19.09. ins Spiel und verlor den vollen Einsatz, weil nicht
verkauft wurde.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
WF = REPO / ".github/workflows"

# Schalter, die einen KAUF auslösen. Der Name allein entscheidet nicht — die Liste steht
# hier, damit ein neuer Schalter bewusst eingetragen werden muss und nicht durch eine
# Namenskonvention durchrutscht.
KAUF_SCHALTER = ("AUTO_TRIGGER_ENABLED", "AUTO_BET", "SHORTLIST_AUTO_BET",
                 "MAKER_ENABLED", "AUTO_BUY")
# Diese schließen nur. Sie dürfen von allein an sein.
VERKAUF_SCHALTER = ("AUTO_SELL_ENABLED",)

ZEILE = re.compile(r"^\s*([A-Z_]+):\s*\$\{\{\s*secrets\.([A-Z_]+)\s*(\|\|\s*'([^']*)')?\s*\}\}")


def schalter_zeilen():
    for datei in sorted(WF.glob("*.yml")):
        for nr, zeile in enumerate(datei.read_text(encoding="utf-8").splitlines(), 1):
            m = ZEILE.match(zeile)
            if m:
                yield datei.name, nr, m.group(1), m.group(2), m.group(4)


class TestHandelsschalter(unittest.TestCase):
    def test_kein_kaufschalter_ist_ohne_secret_an(self):
        schlimm = []
        for datei, nr, name, secret, default in schalter_zeilen():
            if not any(k in name for k in KAUF_SCHALTER):
                continue
            if default is None:
                continue   # kein Default → leer → aus. In Ordnung.
            if str(default).strip().lower() in ("true", "1", "yes", "on"):
                schlimm.append("%s:%d  %s (Secret %s) faellt ohne Secret auf '%s'"
                               % (datei, nr, name, secret, default))
        self.assertEqual(schlimm, [],
                         "\nEin Kauf-Schalter steht ohne Secret auf AN. Ein geloeschtes, "
                         "vertipptes oder nie angelegtes Secret schaltet damit echtes Geld "
                         "ein:\n  " + "\n  ".join(schlimm))

    def test_der_verkauf_darf_von_allein_an_sein(self):
        """Gegenprobe — der Test darf den Zweck nicht abschaffen. Wer den Verkauf mit
        ausschaltet, nimmt den Mechanismus weg, dessen Ausfall Toulouse gekostet hat."""
        gefunden = [(d, n, name, default) for d, n, name, s, default in schalter_zeilen()
                    if name in VERKAUF_SCHALTER]
        self.assertTrue(gefunden, "kein AUTO_SELL_ENABLED in den Workflows gefunden")
        an = [g for g in gefunden if str(g[3]).strip().lower() in ("true", "1", "yes")]
        self.assertTrue(an, "kein einziger Verkaufs-Schalter steht auf an — das ist die "
                            "gefaehrliche Richtung, nicht die sichere")

    def test_der_kommentar_behauptet_nicht_das_gegenteil_der_zeile(self):
        """Am 20.09. stand neben `|| 'true'` der Kommentar „Aus: Secret ... =false setzen".
        Ein Satz, der behauptet, was die Zeile daneben widerlegt — die Klasse, die im
        Uebersicht-Check schon einen eigenen Namen hat."""
        fehler = []
        for datei in sorted(WF.glob("*.yml")):
            zeilen = datei.read_text(encoding="utf-8").splitlines()
            for nr, zeile in enumerate(zeilen, 1):
                m = ZEILE.match(zeile)
                if not m or not any(k in m.group(1) for k in KAUF_SCHALTER):
                    continue
                default = (m.group(4) or "").strip().lower()
                umfeld = " ".join(zeilen[max(0, nr - 9):nr + 1]).lower()
                if default in ("true", "1", "yes") and "=false setzen" in umfeld:
                    fehler.append("%s:%d — Default '%s', Kommentar sagt aber, das Secret sei "
                                  "der Aus-Schalter" % (datei.name, nr, default))
        self.assertEqual(fehler, [], "\n" + "\n".join(fehler))

    def test_liga_steht_auf_papier(self):
        """Der konkrete Fall: ohne Secret muss der Liga-Trader auf Papier laufen."""
        y = (WF / "manage-liga-poly.yml").read_text(encoding="utf-8")
        self.assertIn("LIGA_AUTO_TRIGGER_ENABLED || 'false'", y)


if __name__ == "__main__":
    unittest.main()
