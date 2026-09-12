"""Eine Schwelle, die nie erreicht wurde, ist keine Schwelle — sondern ein Aus-Schalter.

🔴 12.09.2026 (Lucas, Plattform-Audit). `generate_wm_picks.py` hebt ein ABWÄGEN auf BET, wenn die
Conviction `_conv_threshold` erreicht: bei Steam-Picks die Profil-Schwelle, sonst hart 8.

    wm2026        steam_bet_threshold = 6
    liga_default  steam_bet_threshold = 8
    mls_default   steam_bet_threshold = 8

Gemessen am echten Bestand erreicht Liga **nie mehr als 6** — ueber 332 Picks in liga-data.json und
101 Eintraege im Signal-Ledger. Grund steht in den Familien-Punkten:

    context       feuert in  2 % der Liga-Picks (max 1 von 3)
    market        feuert in  4 % der Liga-Picks (max 1 von 1)
    model_stack   feuert in 99 % (max 3)
    sharp_money   feuert in 100 % (max 3)

Die Signale der beiden toten Familien (Travel, Wetter, Anreiz, Hoehe) sind WM-Signale; in Liga gibt
es sie gar nicht. Erreichbar sind also 3+3 = 6, und die Schwelle steht auf 8. **In 332 Liga-Picks
gab es null Hochstufungen**, und die Karte zeichnete trotzdem einen Zielmarker bei 8.

⚠️ Und der naheliegende Fix waere der falsche. Die Schwelle einfach auf 6 zu senken, wuerde Picks
genau in die Schublade lassen, die als einzige NICHTS traegt — gemessen am Liga-Ledger:

    conv 4   n=52   Treffer 65,4 %   ROI +13,5 %   UG  −7,4 %
    conv 5   n=34   Treffer 76,5 %   ROI +37,2 %   UG +12,9 %   ← einzige belegte Schublade
    conv 6   n=15   Treffer 60,0 %   ROI  +0,0 %   UG −36,9 %   ← die erreichbare Spitze

Die Skala steigt in Liga nicht monoton; ihre Spitze ist die schwaechste Stufe. Deshalb aendert
dieser Durchgang **keine Schwelle** — er macht den toten Zustand nur sichtbar und legt Lucas die
Zahlen vor. Was die Karte angeht, ist der Fehler behoben: sie zeigt die Schwelle, die fuer DIESEN
Pick gilt (`convBetSchwelle`), und wenn keine da ist, gar keinen Marker statt eines falschen.
"""
import json
import re
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
CONFIG = WURZEL / "cocobet_config.json"

# Datensatz -> (Profil, Datendatei, Ledger)
DATENSAETZE = {
    "liga": ("liga_default", "liga-data.json", "liga_signal_ledger.json"),
    "mls":  ("mls_default",  "mls-data.json",  "mls_signal_ledger.json"),
    "wm":   ("wm2026",       "wm2026-data.json", "wm_signal_ledger.json"),
}

# Bekannt tote Schwellen — MIT Messung, damit niemand sie fuer eine Entscheidung haelt.
# Ein Eintrag hier heisst: „wissen wir, liegt bei Lucas, nicht stillschweigend akzeptiert."
TOT_BEKANNT = {
    "liga": "Erreichbar sind 6 (context feuert in 2 %, market in 4 % — beides WM-Signalfamilien). "
            "Schwelle 8 → 0 Hochstufungen in 332 Picks. Senken waere NICHT belegt: conv 6 ist im "
            "Liga-Ledger die schwaechste Schublade (n=15, ROI +0,0 %, UG −36,9 %). "
            "Entscheidung liegt bei Lucas (12.09.2026).",
}


def _profil_schwelle(profil):
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cs = ((cfg.get("profiles") or {}).get(profil) or {}).get("conviction_score") or {}
    return cs.get("steam_bet_threshold")


def _convictions(*dateien):
    raus = []
    for name in dateien:
        pfad = WURZEL / name
        if not pfad.exists():
            continue
        daten = json.loads(pfad.read_text(encoding="utf-8"))

        def lauf(o, tiefe=0):
            if tiefe > 6:
                return
            if isinstance(o, dict):
                if isinstance(o.get("convictionScore"), (int, float)):
                    raus.append(o["convictionScore"])
                for v in o.values():
                    lauf(v, tiefe + 1)
            elif isinstance(o, list):
                for v in o:
                    lauf(v, tiefe + 1)
        lauf(daten)
    return raus


class TestSchwelleErreichbar(unittest.TestCase):
    def test_jede_bet_schwelle_wurde_schon_einmal_erreicht(self):
        tot = []
        for ds, (profil, daten, ledger) in DATENSAETZE.items():
            schwelle = _profil_schwelle(profil)
            werte = _convictions(daten, ledger)
            if schwelle is None or len(werte) < 50:
                continue            # zu wenig Bestand fuer eine Aussage
            if max(werte) < schwelle and ds not in TOT_BEKANNT:
                tot.append(f"{ds}: Schwelle {schwelle}, hoechste je erreichte Conviction "
                           f"{max(werte)} (n={len(werte)}) — die Hochstufung kann nie feuern.")
        self.assertEqual(tot, [], "\n" + "\n".join(tot)
                         + "\n\nEntweder die Schwelle belegen und senken, oder mit Messung in "
                           "TOT_BEKANNT eintragen. Stillschweigend stehen lassen ist die eine "
                           "Variante, die nicht geht.")

    def test_die_bekannten_toten_schwellen_sind_noch_tot(self):
        """Sonst verrottet die Liste: erreicht Liga eines Tages die 8, gehoert der Eintrag raus —
        und die Begruendung darin ist dann falsch, nicht nur ueberfluessig."""
        veraltet = []
        for ds, grund in TOT_BEKANNT.items():
            profil, daten, ledger = DATENSAETZE[ds]
            schwelle = _profil_schwelle(profil)
            werte = _convictions(daten, ledger)
            if not werte or schwelle is None:
                continue
            if max(werte) >= schwelle:
                veraltet.append(f"{ds} erreicht inzwischen {max(werte)} ≥ {schwelle} — "
                                f"Eintrag gehoert raus.")
        self.assertEqual(veraltet, [], "\n" + "\n".join(veraltet))

    def test_liga_erreicht_wirklich_nur_sechs(self):
        """Der Fund selbst, als Nagel. Verschiebt sich das, ist die Begruendung oben veraltet."""
        werte = _convictions("liga-data.json", "liga_signal_ledger.json")
        self.assertGreater(len(werte), 200, "zu wenig Liga-Picks fuer die Aussage")
        self.assertLessEqual(max(werte), 6,
                             "Liga erreicht jetzt mehr als 6 — dann gehoert TOT_BEKANNT neu "
                             "bewertet, nicht nur dieser Test.")


class TestKarteZeigtDieEchteSchwelle(unittest.TestCase):
    """Die zweite Haelfte: die Karte hat bisher „fuer Top-Wette: 8+" gezeichnet — auch bei einem
    WM-Steam-Pick, fuer den 6 gilt, und in Liga auf einem Balken, der die 8 nie erreicht."""

    def setUp(self):
        self.js = (WURZEL / "wm2026-renderer.js").read_text(encoding="utf-8")

    def test_kein_hartes_acht_mehr_im_conviction_block(self):
        self.assertNotIn("8+ = Top-Wette", self.js)
        self.assertNotIn("für Top-Wette: 8+", self.js)
        self.assertNotIn("Bei 8+/10 darf ein ABWÄGEN", self.js)

    def test_die_karte_liest_die_schwelle_vom_pick(self):
        # Karte (heroPick) und Modal (pick) je einmal — gezaehlt wird die Zuweisung an
        # `const schwelle`, nicht jede Erwaehnung des Feldes.
        zuweisungen = re.findall(r"const schwelle = [^;]+convBetSchwelle", self.js, re.S)
        self.assertEqual(len(zuweisungen), 2,
                         f"Karte UND Modal muessen die Schwelle vom Pick lesen — gefunden: "
                         f"{len(zuweisungen)}")

    def test_ohne_schwelle_wird_kein_marker_geraten(self):
        """Ein falscher Zielmarker ist schlechter als keiner — das war der ganze Fehler.

        Geprueft wird die ZEILE, in der der Marker entsteht: sie muss von `schwelle` abhaengen.
        Ein Marker, der bedingungslos gerendert wird, sitzt sonst wieder bei festen 80 %
        (so stand es im CSS: `.cc-conv-target{left:80%}`)."""
        self.assertIn("Schwelle nicht hinterlegt", self.js)
        marker = [z for z in self.js.split("\n") if "conv-target" in z or "conv-modal-target" in z]
        self.assertTrue(marker, "der Zielmarker ist ganz verschwunden")
        for z in marker:
            self.assertIn("schwelle", z.lower(),
                          f"Zielmarker ohne Schwellen-Bezug: {z.strip()[:110]}")

    def test_der_producer_stempelt_die_schwelle_an_den_pick(self):
        py = (WURZEL / "generate_wm_picks.py").read_text(encoding="utf-8")
        self.assertIn('p["convBetSchwelle"] = _conv_threshold', py,
                      "ohne Stempel kann die Karte die Schwelle nicht kennen — und raet wieder")


if __name__ == "__main__":
    unittest.main()
