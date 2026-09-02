"""Modul-lokale Helfer mit falscher Argumentzahl (02.09.2026).

🔴 Anlass: in `poly_money_broad.py` stand `_load(CLOSE_FILE, {})`. Dort nimmt `_load` aber nur EIN
Argument — in `killer.py` und `freigabe.py` nimmt dasselbe `_load` zwei. Ich hatte die Signatur aus
einem Nachbarmodul angenommen.

Das Tückische ist nicht der Fehler, sondern WO er hochkam: ganz am Ende von `main()`, nach dem
gesamten Fetch, nach 18.607 Marktzeilen und allen Holder-Calls — und **vor jedem Schreibvorgang**.
Der Lauf war rot, `poly_money_broad.json` blieb stehen, und alles Nachgelagerte (Wallet-Track,
Punktestand, Shortlist) hungerte, während der Job im 30-Minuten-Takt weiter startete.

⭐ Ein halb identischer Helfername über mehrere Module ist eine Falle, die kein Import-Check und
kein Unit-Test der reinen Funktionen findet — nur der echte Lauf oder dieser Test hier.
"""
import ast
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
# Helfer, die in mehreren Modulen mit UNTERSCHIEDLICHER Signatur existieren.
BEOBACHTET = ("_load", "_dump", "_write", "_now", "_ts")


def _arity(fn):
    """(min, max) Positionsargumente einer FunctionDef; max=None bei *args."""
    a = fn.args
    pos = len(a.posonlyargs) + len(a.args)
    mind = pos - len(a.defaults)
    return mind, (None if a.vararg else pos)


class TestLokaleHelferArität(unittest.TestCase):
    def test_jeder_aufruf_passt_zur_eigenen_definition(self):
        fehler = []
        for py in sorted(WURZEL.glob("*.py")):
            try:
                baum = ast.parse(py.read_text(encoding="utf-8"))
            except SyntaxError as e:
                fehler.append(f"{py.name}: nicht parsebar ({e})")
                continue
            defs = {n.name: _arity(n) for n in baum.body
                    if isinstance(n, ast.FunctionDef) and n.name in BEOBACHTET}
            if not defs:
                continue
            for k in ast.walk(baum):
                if not (isinstance(k, ast.Call) and isinstance(k.func, ast.Name)):
                    continue
                nm = k.func.id
                if nm not in defs:
                    continue
                if any(isinstance(x, ast.Starred) for x in k.args):
                    continue                      # *args am Aufruf: nicht statisch prüfbar
                n = len(k.args)
                mind, maxd = defs[nm]
                if n < mind or (maxd is not None and n > maxd):
                    grenze = f"{mind}" if mind == maxd else f"{mind}–{maxd if maxd is not None else '∞'}"
                    fehler.append(f"{py.name}:{k.lineno}: {nm}() mit {n} Argument(en) aufgerufen, "
                                  f"definiert sind {grenze} — vermutlich die Signatur eines "
                                  f"Nachbarmoduls angenommen.")
        self.assertEqual(fehler, [], "\n" + "\n".join(fehler))

    def test_der_test_wuerde_den_echten_fall_finden(self):
        """Gegenprobe — sonst wäre ein leeres Ergebnis auch bei kaputtem Test grün."""
        quelle = ("def _load(name):\n    return {}\n\n"
                  "def main():\n    return _load('x.json', {})\n")
        baum = ast.parse(quelle)
        defs = {n.name: _arity(n) for n in baum.body
                if isinstance(n, ast.FunctionDef) and n.name in BEOBACHTET}
        rufe = [k for k in ast.walk(baum)
                if isinstance(k, ast.Call) and isinstance(k.func, ast.Name) and k.func.id == "_load"]
        self.assertEqual(defs["_load"], (1, 1))
        self.assertEqual(len(rufe[0].args), 2, "genau der Fall vom 02.09.2026")


if __name__ == "__main__":
    unittest.main()
