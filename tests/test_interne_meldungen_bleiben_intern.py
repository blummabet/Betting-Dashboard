"""🔴 21.09.2026 (Lucas: „Wie kann so eine Nachricht aber in public gehen").

Die tägliche Störungsmeldung vom 06:14 UTC stand im ÖFFENTLICHEN Kanal. Wörtlich darin:
Wallet-Adressen, Markt-Keys („spl-kha-riy-2026-09-07-more-markets"), „4 gesendete Public-Pushes
ohne Ledger-Zeile — sie fehlen in der Bilanz", „131/326 'bewiesene' Wallets sind netto-NEGATIV".
Das ist der Innenzustand der Plattform, an Abonnenten.

Der Weg dahin war kein Fehler im Sendecode, sondern sein STANDARDWERT:

    CHAT_ID = (os.environ.get('TELEGRAM_CHAT_ID') or '-1003819239615')

und `TELEGRAM_CHAT_ID` ist seit dem 04.08.2026 bewusst NICHT als Secret gesetzt, damit der
öffentliche Pfad ohne Secret funktioniert (Kommentar in betfair_alerts.py:1321). Wer also
nichts wählt, sendet an alle — `stoerungsmeldung.py` hat nichts gewählt.

Fehlerklasse: ein Standard-Empfänger, der der öffentliche Kanal ist.

Dieser Test prüft nicht die eine Datei, sondern die Regel: JEDES Modul, das sich mit
`NUR_INTERN = True` als intern markiert, darf den öffentlich-vorbelegten Sender nicht benutzen
— und der interne Sender darf nie im öffentlichen Kanal landen, auch dann nicht, wenn jemand
`TELEGRAM_CHAT_ID` auf genau diese ID setzt.
"""
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import telegram_bot as TB

# Die oeffentlichen Sender: vorbelegt auf PUBLIC_CHAT_ID, wenn niemand etwas waehlt.
OEFFENTLICHE_SENDER = ("tg_send", "tg_send_photo", "tg_send_text")


def _interne_module():
    """Alle Module mit `NUR_INTERN = True` im Kopf."""
    rx = re.compile(r"^NUR_INTERN\s*=\s*True\s*$", re.M)
    return [p for p in sorted(BASE.glob("*.py"))
            if rx.search(p.read_text(encoding="utf-8"))]


class TestDieMarkeBindet(unittest.TestCase):
    def test_es_gibt_ueberhaupt_interne_module(self):
        """Sonst prüft der Test still nichts — die häufigste Art, wie ein Wächter verschwindet."""
        self.assertTrue(_interne_module(), "kein Modul traegt NUR_INTERN = True")

    def test_die_stoerungsmeldung_ist_darunter(self):
        self.assertIn("stoerungsmeldung.py", [p.name for p in _interne_module()])

    def test_kein_internes_modul_benutzt_den_oeffentlichen_sender(self):
        schuldig = []
        for p in _interne_module():
            src = p.read_text(encoding="utf-8")
            # Nur echte Verwendungen, keine Kommentarzeilen und keine Doku.
            code = "\n".join(z for z in src.splitlines() if not z.lstrip().startswith("#"))
            for name in OEFFENTLICHE_SENDER:
                if re.search(r"\b(?:import\s+%s\b|%s\s*\()" % (name, name), code):
                    schuldig.append("%s -> %s" % (p.name, name))
        self.assertEqual(schuldig, [], "interne Module am oeffentlichen Sender: %s" % schuldig)


class TestDerInterneSenderFaelltNieInsOeffentliche(unittest.TestCase):
    def test_ohne_eigenen_kanal_wird_nicht_gesendet(self):
        """Fail-closed. Eine nicht gesendete Diagnose kostet einen Blick ins Log; eine
        versehentlich oeffentliche kostet mehr."""
        with mock.patch.dict("os.environ", {"TELEGRAM_OPS_CHAT_ID": "",
                                            "TELEGRAM_TRADES_CHAT_ID": ""}, clear=False), \
             mock.patch.object(TB, "TELEGRAM_TOKEN", "t"), \
             mock.patch.object(TB, "_tg_post", side_effect=AssertionError("hat gesendet!")):
            self.assertFalse(TB.tg_send_ops("geheim"))

    def test_der_oeffentliche_kanal_zaehlt_nicht_als_eigener(self):
        """Auch wenn jemand die oeffentliche ID als Ops-Kanal einsetzt: dann lieber schweigen."""
        with mock.patch.dict("os.environ", {"TELEGRAM_OPS_CHAT_ID": TB.PUBLIC_CHAT_ID,
                                            "TELEGRAM_TRADES_CHAT_ID": TB.PUBLIC_CHAT_ID},
                             clear=False):
            self.assertEqual(TB.ops_chat_id(), "")

    def test_mit_eigenem_kanal_geht_es_genau_dorthin(self):
        gesehen = {}
        with mock.patch.dict("os.environ", {"TELEGRAM_OPS_CHAT_ID": "-100999",
                                            "TELEGRAM_TRADES_CHAT_ID": "-100777"}, clear=False), \
             mock.patch.object(TB, "TELEGRAM_TOKEN", "t"), \
             mock.patch.object(TB, "_tg_post",
                               side_effect=lambda t, c: gesehen.update(text=t, chat=c) or True):
            self.assertTrue(TB.tg_send_ops("diagnose"))
        self.assertEqual(gesehen["chat"], "-100999", "OPS hat Vorrang vor TRADES")
        self.assertNotEqual(gesehen["chat"], TB.PUBLIC_CHAT_ID)

    def test_der_trades_kanal_ist_der_rueckfall(self):
        gesehen = {}
        with mock.patch.dict("os.environ", {"TELEGRAM_OPS_CHAT_ID": "",
                                            "TELEGRAM_TRADES_CHAT_ID": "-100777"}, clear=False), \
             mock.patch.object(TB, "TELEGRAM_TOKEN", "t"), \
             mock.patch.object(TB, "_tg_post",
                               side_effect=lambda t, c: gesehen.update(chat=c) or True):
            TB.tg_send_ops("x")
        self.assertEqual(gesehen["chat"], "-100777")

    def test_ohne_token_wird_ebenfalls_nicht_gesendet(self):
        with mock.patch.dict("os.environ", {"TELEGRAM_OPS_CHAT_ID": "-100999"}, clear=False), \
             mock.patch.object(TB, "TELEGRAM_TOKEN", ""), \
             mock.patch.object(TB, "_tg_post", side_effect=AssertionError("hat gesendet!")):
            self.assertFalse(TB.tg_send_ops("x"))


class TestDerOeffentlicheSenderBleibtWieErWar(unittest.TestCase):
    """Der Fix darf den oeffentlichen Pfad nicht mit abschalten — dort ist der Rueckfall gewollt."""

    def test_er_sendet_weiter_an_den_oeffentlichen_kanal(self):
        gesehen = {}
        with mock.patch.object(TB, "TELEGRAM_TOKEN", "t"), \
             mock.patch.object(TB, "CHAT_ID", TB.PUBLIC_CHAT_ID), \
             mock.patch.object(TB, "_tg_post",
                               side_effect=lambda t, c: gesehen.update(chat=c) or True):
            self.assertTrue(TB.tg_send("Tipp des Tages"))
        self.assertEqual(gesehen["chat"], TB.PUBLIC_CHAT_ID)


if __name__ == "__main__":
    unittest.main()
