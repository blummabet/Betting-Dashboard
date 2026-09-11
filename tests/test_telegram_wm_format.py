"""
test_telegram_wm_format.py — Format-Garantien für die Telegram-WM-Karten (21.06.2026, Lucas:
„schade dass kein Guard das sieht, immer ich muss es sehen"). Fängt die Klasse von Content-
Regressionen, die Lucas manuell entdeckt hat:
  · veralteter fixer Signal-Nenner („X/14 Signale") — wir haben 19 Signale
  · zu viel Elo (rohe Elo-Zahlen, „Elo-Gap N Pkt", „laut Elo-Modell")
  · Tech-Jargon-Fußzeile (Poisson)

Baut die echten Morning-/Recap-Karten aus wm2026-data.json und prüft die Invarianten.
"""
import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

import telegram_wm  # noqa: E402

FORBIDDEN = ["/14", "Elo:", "Elo-Gap", "laut Elo", "Poisson", "Signalen stützen"]


def _all_cards():
    wm = json.loads((BASE / "wm2026-data.json").read_text(encoding="utf-8"))
    dates = set()
    for g in (wm.get("groups") or {}).values():
        for fx in (g.get("fixtures") or []):
            if fx.get("date"):
                dates.add(fx["date"])
    cards = []
    for d in sorted(dates):
        for fn in (telegram_wm.build_morning_card, telegram_wm.build_recap_card):
            try:
                msg = fn(wm, d)
            except Exception:
                msg = None
            if msg:
                cards.append((d, fn.__name__, msg))
    return cards


class TestTelegramWmFormat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = _all_cards()

    def test_at_least_one_card(self):
        self.assertTrue(self.cards, "Keine Karte gebaut — Fixture/Datenproblem")

    def test_no_pick_games_not_listed(self):
        # 21.08.2026 (Lucas): Spiele ohne BET/ABWÄGEN werden nicht mehr gelistet → die „kein Pick"-
        # Zeile (no_edge, DE + EN) darf in keiner Morning-Card mehr vorkommen.
        import json as _json
        wm = _json.loads((BASE / "wm2026-data.json").read_text(encoding="utf-8"))
        dates = sorted({fx["date"] for g in (wm.get("groups") or {}).values()
                        for fx in (g.get("fixtures") or []) if fx.get("date")})
        seen = 0
        for d in dates:
            for lang in ("de", "en"):
                msg = telegram_wm.build_morning_card(wm, d, lang)
                if not msg:
                    continue
                seen += 1
                self.assertNotIn("Kein Pick mit ausreichend", msg, f"DE no_edge @ {d}")
                self.assertNotIn("No pick with enough", msg, f"EN no_edge @ {d}")
        self.assertGreater(seen, 0, "keine Morning-Card gebaut — Fixture-Problem")

    def test_no_forbidden_substrings(self):
        for d, fn, msg in self.cards:
            for bad in FORBIDDEN:
                with self.subTest(date=d, fn=fn, bad=bad):
                    self.assertNotIn(bad, msg, f"{fn} @ {d} enthält verbotenes '{bad}'")

    def test_signal_line_uses_dynamic_count(self):
        # Wenn eine Signal-Zeile vorkommt, dann im neuen Format „N Signale dafür" —
        # nie mit fixem Nenner.
        for d, fn, msg in self.cards:
            if "Signale dafür" in msg or "Signale stützen" in msg:
                with self.subTest(date=d, fn=fn):
                    self.assertIn("Signale dafür", msg)
                    self.assertNotIn("Signale stützen", msg)


if __name__ == "__main__":
    unittest.main()


# ── 10.09.2026: der Cards-Digest wurde entschlackt ──────────────────────────────────────
# Lucas hat das Zielformat vorgegeben. Drei Aenderungen, jede mit einem eigenen Grund.
#
# Diese Klasse prueft AUSGABE, nicht Quelltext. Ein erster Entwurf tat das Gegenteil: er las
# mit `inspect.getsource` nach, ob die ✦-Zeile noch im Code steht, und suchte die Trenner-Regel
# in echten Daten, die im Arbeitsverzeichnis gar nicht liegen — der Test war ein stiller No-Op.
# Beides misst nicht, was Lucas sieht. Der Trenner-Fall wird deshalb GEBAUT (drei Spiele
# desselben Spieltags), statt gehofft.
class TestDigestEntschlackt(unittest.TestCase):

    def _tag_mit_zwei_spielen(self):
        """Ein echter Tag, an dem die Karte MEHR ALS EIN Spiel zeigt — sonst prueft der Test
        nichts. Gibt (wm, tag) zurueck."""
        wm = json.loads((BASE / "wm2026-data.json").read_text(encoding="utf-8"))
        tage = sorted({fx["date"] for g in (wm.get("groups") or {}).values()
                       for fx in (g.get("fixtures") or []) if fx.get("date")})
        for tag in tage:
            k = telegram_wm.build_morning_card(wm, tag, "de")
            if k and k.count("📅") >= 2:
                return wm, tag
        self.skipTest("kein Tag mit zwei gezeigten Spielen in wm2026-data.json")

    def test_der_spieltag_trenner_steht_nur_beim_WECHSEL(self):
        """Bei mehreren Spielen desselben Spieltags stand „━━ Gruppe A · Spieltag 1 ━━" ueber
        JEDEM Spiel und trennte nichts, weil links und rechts davon dasselbe stand."""
        wm, tag = self._tag_mit_zwei_spielen()
        karte = telegram_wm.build_morning_card(wm, tag, "de")
        spiele = karte.count("📅")
        abschnitte = len({z for z in karte.split("\n") if z.startswith("━━ ")})
        self.assertEqual(karte.count("━━ "), abschnitte,
                         "%d Trenner bei %d verschiedenen Abschnitten und %d Spielen"
                         % (karte.count("━━ "), abschnitte, spiele))
        self.assertLess(karte.count("━━ "), spiele,
                        "der Trenner steht immer noch je Spiel statt je Abschnitt")

    def test_bei_ZWEI_spieltagen_steht_der_trenner_wieder_zweimal(self):
        """Gegenprobe: die Regel darf den Trenner nicht einfach unterdruecken.

        Dasselbe Spiel wird auf den naechsten Spieltag umgehaengt — samt seinem Pick, denn
        `pick_key` traegt den Spieltag im Namen; ohne das Mitziehen faellt das Spiel aus der
        Karte und der Test wuerde die falsche Sache messen (genau das ist beim ersten Entwurf
        passiert). Danach MUSS die Ueberschrift wieder zweimal dastehen — sonst haetten wir
        statt einer Wiederholung eine fehlende Ueberschrift, und das waere die schlechtere
        Haelfte des Tauschs.
        """
        wm, tag = self._tag_mit_zwei_spielen()
        vorher = telegram_wm.build_morning_card(wm, tag, "de").count("━━ ")
        picks = wm.setdefault("picks", {})
        ups = wm.setdefault("upsetScores", {})
        ai = wm.setdefault("aiPreviews", {})
        umgehaengt = False
        for gk, g in (wm.get("groups") or {}).items():
            for fx in (g.get("fixtures") or []):
                alt = "%s-%s-%s-%s" % (gk, fx.get("matchday"), fx.get("home"), fx.get("away"))
                if alt not in picks or umgehaengt:
                    continue
                fx["matchday"] = (fx.get("matchday") or 1) + 1
                neu = "%s-%s-%s-%s" % (gk, fx["matchday"], fx["home"], fx["away"])
                for d in (picks, ups, ai):
                    if alt in d:
                        d[neu] = d[alt]
                umgehaengt = True
        self.assertTrue(umgehaengt, "kein Spiel mit Pick zum Umhaengen gefunden")
        karte = telegram_wm.build_morning_card(wm, tag, "de")
        self.assertGreater(karte.count("━━ "), vorher,
                           "ein zweiter Spieltag bekommt keine eigene Ueberschrift")

    def test_die_prosa_zeile_ist_raus(self):
        """„Das Modell sieht Treffer auf beiden Seiten — Value auf Beide Teams treffen — Nein"
        stand eine Zeile ueber „🟡 Abwägen: Beide Teams treffen — Nein @2.18". Eine Uebersetzung
        der Pick-Zeile ins Deutsche, kein zusaetzlicher Inhalt.

        Geprueft wird an ALLEN echten Karten, nicht am Quelltext: das ✦ war das einzige Zeichen,
        mit dem diese Zeile begann, und es kommt sonst nirgends in der Karte vor.
        """
        gebaut = 0
        for d, fn, msg in _all_cards():
            gebaut += 1
            with self.subTest(date=d, fn=fn):
                self.assertNotIn("✦", msg)
        self.assertGreater(gebaut, 0, "keine Karte gebaut — Fixture-Problem")

    def test_der_einsatz_steht_bei_der_begruendung_nicht_in_der_kopfzeile(self):
        """Der Einsatz ist ans Ende der Begruendungszeile gewandert. Wo eine BET-Kopfzeile
        steht, darf der €-Betrag NICHT mehr in derselben Zeile stehen — sonst haette die
        Verschiebung nur eine zweite Fundstelle erzeugt statt die erste zu ersetzen."""
        traf = 0
        for d, fn, msg in _all_cards():
            for zeile in msg.split("\n"):
                if zeile.startswith("🟢 <b>BET"):
                    traf += 1
                    with self.subTest(date=d, zeile=zeile):
                        self.assertNotIn("💶", zeile)
        self.assertGreater(traf, 0, "keine BET-Kopfzeile in den echten Karten gefunden")



# ── 10.09.2026: der Public-Channel ist einsprachig ──────────────────────────────────────
class TestNurDeutschImPublic(unittest.TestCase):
    """Lucas: „bitte deaktivier mal Englisch."

    Jede Morning-Card und jeder Recap ging ZWEIMAL in denselben Channel — einmal deutsch,
    einmal englisch. Weggenommen wird der VERSAND, nicht die Uebersetzung: eine geloeschte
    Uebersetzung waere nicht rueckgaengig zu machen, ein Default ist es.
    """

    def test_der_default_sendet_nur_deutsch(self):
        import importlib, os
        _vorher = os.environ.pop("TG_LANGS", None)
        try:
            importlib.reload(telegram_wm)
            self.assertEqual(telegram_wm.TG_LANGS, ["de"])
        finally:
            if _vorher is not None:
                os.environ["TG_LANGS"] = _vorher
            importlib.reload(telegram_wm)

    def test_englisch_ist_einen_schalter_weit_weg(self):
        """Der Gegenbeweis zur Streichung: sie darf nicht endgueltig sein."""
        import importlib, os
        _vorher = os.environ.get("TG_LANGS")
        os.environ["TG_LANGS"] = "de,en"
        try:
            importlib.reload(telegram_wm)
            self.assertEqual(telegram_wm.TG_LANGS, ["de", "en"])
        finally:
            if _vorher is None:
                os.environ.pop("TG_LANGS", None)
            else:
                os.environ["TG_LANGS"] = _vorher
            importlib.reload(telegram_wm)

    def test_die_englische_karte_wird_weiter_gebaut(self):
        """`telegram_i18n` bleibt vollstaendig — nur der Versand ist aus. Waere die Uebersetzung
        mit weggefallen, koennte TG_LANGS sie nicht zurueckholen."""
        import json as _json
        wm = _json.loads((BASE / "wm2026-data.json").read_text(encoding="utf-8"))
        tage = sorted({fx["date"] for g in (wm.get("groups") or {}).values()
                       for fx in (g.get("fixtures") or []) if fx.get("date")})
        gebaut = 0
        for d in tage:
            en = telegram_wm.build_morning_card(wm, d, "en")
            if en:
                gebaut += 1
                self.assertNotIn("Abwägen", en, "die EN-Karte darf nicht deutsch werden")
        self.assertGreater(gebaut, 0, "keine englische Karte gebaut")


# ── 11.09.2026: die Signatur-Zeile ist raus ──────────────────────────────────────────────
class TestKeineSelbstbeschreibungImFuss(unittest.TestCase):
    """Lucas: „bitte die letzte Zeile weg mit dem datengetrieben Pick Modell."

    Sie stand unter JEDER Morning-Card, sagte nichts, was die Karte nicht schon zeigt — und
    nannte dabei eine hartkodierte Zahl, die seit dem Registry-Umbau falsch war (33 Signale im
    Registry, davon 6 abgeschaltet; im Fuss stand 19).
    """

    def test_die_morning_card_endet_nicht_mit_der_signatur(self):
        gebaut = 0
        for d, fn, msg in _all_cards():
            if fn != "build_morning_card":
                continue
            gebaut += 1
            with self.subTest(date=d):
                self.assertNotIn("datengetriebenes Pick-Modell", msg)
                self.assertNotIn("data-driven pick model", msg)
                self.assertNotIn("19 Signalen", msg)
        self.assertGreater(gebaut, 0, "keine Morning-Card gebaut")

    def test_die_bilanz_zeile_bleibt(self):
        """Gegenprobe zur Streichung: weg soll die Selbstbeschreibung, nicht die gemessene Zahl."""
        mit_bilanz = 0
        for d, fn, msg in _all_cards():
            if fn == "build_morning_card" and "Bilanz" in msg:
                mit_bilanz += 1
        self.assertGreater(mit_bilanz, 0,
                           "die Bilanz-Zeile traegt eine Messung und darf nicht mitgestrichen werden")

    def test_der_baustein_bleibt_fuer_andere_karten_erhalten(self):
        """Die Recap-Karte hat ihren eigenen Fuss. `T[\"footer\"]` bleibt in telegram_i18n stehen —
        geloescht wird der AUFRUF, nicht der Text, sonst faellt die Uebersetzung mit."""
        import telegram_i18n as I
        for lang in ("de", "en"):
            self.assertIn("footer", I.L[lang], lang)
        self.assertIn("recap_footer", I.L["de"])
