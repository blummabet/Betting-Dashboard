"""Zaehler und Nenner der Lern-Gewichte — und wer sie zusammen benutzen darf.

🔴 12.09.2026 (Lucas, Plattform-Audit). Das Bayesian-Panel rechnete
`wins_when_triggered / n_observations`. Die beiden Felder kommen aber aus verschiedenen Toepfen:

    n_observations          = n_live                        (nur echte Ergebnis-Beobachtungen)
    wins/losses             = live + Backtest-Prior + CLV   (update_signal_weights.py:426-433)

Sichtbar war es an einer Unmoeglichkeit: MLS `fixture_congestion` rendert mit der alten Formel
**131 %**. Sieben von 18 Liga- und acht von 21 MLS-Signalen waren betroffen, jedes davon nach
oben — Liga xG stand auf 85 statt 59,1.

Der Frontend-Fix steht in `tests/frontend/bayes-hitrate.test.mjs`. Dieser Test haelt die
ANDERE Haelfte fest: die Bedeutung der Felder im Producer. Aendert sie jemand, faellt die Basis
des Frontend-Fixes weg — und dann soll es hier knallen und nicht auf der Seite.
"""
import json
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
DATEIEN = ["signal_weights.json", "liga_signal_weights.json", "mls_signal_weights.json"]


def _zeilen():
    for name in DATEIEN:
        pfad = WURZEL / name
        if not pfad.exists():
            continue
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        for sig, w in (daten or {}).items():
            if isinstance(w, dict) and isinstance(w.get("wins_when_triggered"), (int, float)):
                yield name, sig, w


class TestZaehlerUndNenner(unittest.TestCase):
    def test_wins_plus_losses_ist_live_plus_prior_plus_clv(self):
        """Die Identitaet, auf der die Trefferquote im Panel beruht."""
        fehler = []
        for name, sig, w in _zeilen():
            summe = (w.get("wins_when_triggered") or 0) + (w.get("losses_when_triggered") or 0)
            teile = ((w.get("n_observations") or 0) + (w.get("n_prior") or 0)
                     + (w.get("n_clv") or 0))
            if abs(summe - teile) > 0.05:
                fehler.append(f"{name}:{sig}: wins+losses={summe:.2f}, "
                              f"n_live+n_prior+n_clv={teile:.2f}")
        self.assertEqual(fehler, [], "\nDie Grundgesamtheit der Gewichte hat sich geaendert. Das "
                         "Panel rechnet wins/(wins+losses) — wenn diese Summe nicht mehr die "
                         "Beobachtungen sind, ist die angezeigte Trefferquote wieder falsch:\n"
                         + "\n".join(fehler))

    def test_n_observations_ist_hoechstens_die_summe(self):
        """Der eigentliche Fund in einem Satz: n_observations ist ein TEIL des Nenners, nie er
        selbst. Wo es kleiner ist, ergibt wins/n_observations eine zu hohe Zahl — deshalb war
        JEDE betroffene Zeile zu gut und keine zu schlecht."""
        fehler = []
        for name, sig, w in _zeilen():
            summe = (w.get("wins_when_triggered") or 0) + (w.get("losses_when_triggered") or 0)
            n = w.get("n_observations") or 0
            if n > summe + 0.05:
                fehler.append(f"{name}:{sig}: n_observations={n} > wins+losses={summe:.2f}")
        self.assertEqual(fehler, [], "\n" + "\n".join(fehler))

    def test_kein_signal_haette_mit_der_alten_formel_ueber_100_prozent(self):
        """Gegenprobe mit Zaehnen: die alte Formel MUSS an den echten Dateien Unmoegliches
        produzieren — sonst prueft dieser Test eine Welt, in der es den Fehler nie gab."""
        unmoeglich = [f"{name}:{sig}" for name, sig, w in _zeilen()
                      if (w.get("n_observations") or 0) > 0
                      and (w.get("wins_when_triggered") or 0) / w["n_observations"] > 1.0]
        self.assertTrue(unmoeglich,
                        "Kein Signal mehr, an dem die alte Formel ueber 100 % liefe. Entweder ist "
                        "der Datenbestand ausgetauscht oder der Producer hat die Felder "
                        "umgestellt — in beiden Faellen gehoert dieser Test neu begruendet, "
                        "nicht stillschweigend behalten.")

    def test_neutral_steht_an_jedem_gelernten_signal(self):
        """Die Farbe im Panel haengt am Nullpunkt des Signals. Fehlt er, faerbt das Panel gar
        nicht — richtig, aber dann steht dort dauerhaft grau statt einer Aussage.

        Gemeint sind nur Signale, die wirklich gelernt haben. Saat-Eintraege mit 0 Beobachtungen
        (polymarket_sharp, steam_lag, betfair_*) zeigen ohnehin „—" und brauchen keinen
        Nullpunkt — ein Test, der sie mitzaehlt, ist dauerhaft rot und damit wertlos."""
        fehlt = [f"{name}:{sig}" for name, sig, w in _zeilen()
                 if ((w.get("wins_when_triggered") or 0) + (w.get("losses_when_triggered") or 0)) > 0
                 and not isinstance(w.get("neutral"), (int, float))]
        self.assertEqual(fehlt, [], "\nOhne `neutral` kann das Panel nicht sagen, ob eine "
                         "Trefferquote gut ist:\n" + "\n".join(fehlt))


if __name__ == "__main__":
    unittest.main()
