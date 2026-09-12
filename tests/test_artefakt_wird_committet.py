"""Was ein Producer schreibt, muss der Workflow auch committen — sonst ist der Lauf umsonst.

🔴 12.09.2026 (Lucas, Plattform-Audit). Das Dominanz-Band hatte kein Gedaechtnis: weder
`poly_dominanz_seen.json` noch `_ledger.json` noch `_record.json` standen in einer `git add`-Zeile
von `poly-global-scan.yml`. Auf einem frischen Runner bedeutet das leerer Dedup-Stand bei JEDEM
Lauf — derselbe Markt darf immer wieder pushen. Genau das war Lucas' Beschwerde („jetzt kommen halt
viele solcher pushs"), und die Ursache war nicht die Schwelle, sondern das fehlende Buch.

Im selben Lauf gefunden: `shortlist_push_ledger.json` (zwei Tage vorher gebaut, Stats-Seite liest
es seit dem 10.09. — die Datei ist nie im Repo angekommen, der Kanal war also von „falsch" auf
„leer" umgestellt), `poly_money_klein.json`, und `poly_money_broad_live(.history).json`, die `main()`
schreibt und poly-global-scan wegwirft.

Es gibt schon `test_workflow_git_add.py`. Der prueft die FORM der git-add-Zeilen (eine Datei pro
Zeile, kein klebendes `2>`, keine offene Klammer) — also ob `git add` funktioniert. Er kann nicht
sehen, ob eine Datei ueberhaupt genannt wird. Das ist die Luecke, die dieser Test schliesst:

    **Jede .json, die ein Skript des Workflows schreibt, muss derselbe Workflow committen.**

Damit greift der Wachter auch fuer Dateien, die es heute noch nicht gibt: wer morgen ein neues Buch
anlegt, wird hier rot, bevor es still ins Leere schreibt. Die Ausnahmen stehen unten MIT Grund —
eine Ausnahme ohne Grund ist derselbe Fehler, nur mit Haken dran.
"""
import ast
import json
import re
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
WF = WURZEL / ".github" / "workflows"
JSON_TOK = re.compile(r"[A-Za-z0-9_./-]+\.json")

# Helfer, die eine Datei SCHREIBEN bzw. LESEN. Beides explizit, und alles Dritte ist ein Fehler
# (s. test_kein_unbekannter_datei_helfer): ein neuer Schreib-Helfer, der hier nicht steht, wuerde
# sonst stillschweigend als „liest nur" durchgehen — und das ist genau die Blindheit, die dieser
# Test verhindern soll. Lieber ein lauter Test als ein Waechter mit Loch.
SCHREIBER = {"_save", "_schreibe", "_dump", "write_json_atomic", "_write", "_save_seen",
             "write_json_guarded", "dump"}
LESER = {"_load", "_lade", "load", "load_json", "_lazy", "_load_seen", "load_picks",
         "_mtime_age_h", "build_cache_index", "isinstance"}
KLEMPNEREI = {"file", "join", "str", "Path", "replace", "discard", "add", "glob", "open"}

# ── Ausnahmen: Datei wird geschrieben, aber bewusst NICHT von diesem Workflow committet ──────
# Jede Zeile braucht einen Grund. „Faellt mir gerade nicht ein" ist keiner.
AUSNAHMEN = {
    ("manage-wm-poly.yml", "wm2026-data.json"):
        "Owner ist fetch-wm-data.yml; hier bewusst nicht committet, um das Race zu vermeiden "
        "(steht so im Workflow-Kommentar, Phase 1).",
    ("update-dashboard.yml", "matches_today.json"):
        "Zwischendatei innerhalb des Laufs, nicht im Repo getrackt.",
    ("update-dashboard.yml", "league_fallback_cache.json"):
        "Cache; baut sich aus der API neu auf. Kein Buch, kein Zustand, der verloren gehen kann.",
    ("fetch-wm-data.yml", "wm2026-player-props.json"):
        "WM ist vorbei, die Datei steht auf {}. Beim naechsten Turnier wieder aufnehmen.",
}
# `telegram-log.json` schreiben sieben Workflows ueber die gemeinsame Sende-Hilfe, committet wird
# sie nur von update-liga / update-mls / telegram-manual. Der Log ist damit unvollstaendig — als
# Fehlerklasse notiert (Audit 12.09.), aber kein Buch, an dem eine Auszahlung haengt. Bewusst EINE
# Ausnahme statt sieben, damit sie beim Aufraeumen nicht in Einzelteilen uebersehen wird.
GEMEINSAMER_LOG = "telegram-log.json"


def _json_name(knoten, konstanten):
    """Loest einen Ausdruck zu einem .json-Dateinamen auf — `"x.json"`, `BASE / "x.json"`,
    `BASE / KLEIN_FILE`, `str(PFAD)`. Gibt None zurueck, wenn nichts Sicheres herauskommt."""
    if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str) \
            and knoten.value.endswith(".json"):
        return knoten.value
    if isinstance(knoten, ast.Name):
        return konstanten.get(knoten.id)
    if isinstance(knoten, ast.BinOp) and isinstance(knoten.op, ast.Div):
        return _json_name(knoten.right, konstanten) or _json_name(knoten.left, konstanten)
    if isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Name) \
            and knoten.func.id in ("str", "Path") and knoten.args:
        return _json_name(knoten.args[0], konstanten)
    return None


def _analysiere(py):
    """(geschriebene Dateien, unbekannte Helfer) eines Moduls."""
    baum = ast.parse(py.read_text(encoding="utf-8"))
    konstanten = {}
    for _ in range(3):          # Konstanten koennen auf Konstanten zeigen
        for n in ast.walk(baum):
            if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                    and isinstance(n.targets[0], ast.Name):
                wert = _json_name(n.value, konstanten)
                if wert:
                    konstanten[n.targets[0].id] = wert
    schreibt, unbekannt = set(), set()
    for n in ast.walk(baum):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
        if not name:
            continue
        ziel = None
        for arg in n.args:
            ziel = _json_name(arg, konstanten)
            if ziel:
                break
        if not ziel:
            continue
        if name == "open":
            modus = n.args[1] if len(n.args) > 1 else None
            if isinstance(modus, ast.Constant) and isinstance(modus.value, str) \
                    and ("w" in modus.value or "a" in modus.value):
                schreibt.add(ziel)
        elif name in SCHREIBER:
            schreibt.add(ziel)
        elif name in LESER or name in KLEMPNEREI:
            pass
        else:
            unbekannt.add((py.name, name))
    return schreibt, unbekannt


def _logische_zeilen(txt):
    """Fortsetzungszeilen (`\\` am Ende) zu EINER Zeile ziehen — sonst sieht der Scanner
    `git add \\` ohne Dateinamen und die Liste darunter ohne `git add`."""
    raus, puffer = [], ""
    for z in txt.split("\n"):
        kern = z.split("#")[0]
        if kern.rstrip().endswith("\\"):
            puffer += kern.rstrip()[:-1] + " "
            continue
        raus.append(puffer + kern)
        puffer = ""
    if puffer:
        raus.append(puffer)
    return raus


def _committet(txt, registry):
    """(committete Dateien, bewusst verworfene Dateien) eines Workflows."""
    raus, verworfen = set(), set()
    zeilen = _logische_zeilen(txt)
    for i, zeile in enumerate(zeilen):
        if re.search(r"\bgit checkout\s+--\s+", zeile):
            verworfen |= set(JSON_TOK.findall(zeile))
        if "git add" in zeile:
            raus |= set(JSON_TOK.findall(zeile))
        if re.search(r"\bfor\s+\w+\s+in\b", zeile):
            rumpf, k = [], i
            while k + 1 < len(zeilen) and "done" not in zeilen[k]:
                k += 1
                rumpf.append(zeilen[k])
            if any("git add" in r for r in rumpf):
                raus |= set(JSON_TOK.findall(zeile))
    for kategorie in re.findall(r"--bash-list\s+([a-z_]+)", txt):
        raus |= set((registry.get("categories") or {}).get(kategorie, {}).get("files", []))
    return raus, verworfen


SKRIPT = re.compile(r"([A-Za-z0-9_]+)\.py\b")
LAEUFT = re.compile(r"(python3?\s|PYTHON\s*\}\}\s|\$[A-Z_]*PYTHON\s)")


def _skripte(txt):
    treffer = set()
    for z in txt.split("\n"):
        zs = z.strip()
        if zs.startswith("#"):
            continue
        if LAEUFT.search(zs):
            treffer |= set(SKRIPT.findall(zs))
    return treffer


def _durchlauf():
    registry = json.loads((WURZEL / "state_files_registry.json").read_text(encoding="utf-8"))
    luecken, unbekannt, gesehen = [], set(), 0
    for wf in sorted(WF.glob("*.yml")):
        txt = wf.read_text(encoding="utf-8")
        ok, verworfen = _committet(txt, registry)
        schreibt = set()
        for s in _skripte(txt):
            py = WURZEL / (s + ".py")
            if not py.exists():
                continue
            sw, un = _analysiere(py)
            schreibt |= sw
            unbekannt |= un
        gesehen += len(schreibt)
        for datei in sorted(schreibt):
            if datei in ok or datei in verworfen:
                continue
            if datei == GEMEINSAMER_LOG:
                continue
            if (wf.name, datei) in AUSNAHMEN:
                continue
            luecken.append((wf.name, datei))
    return luecken, unbekannt, gesehen


class TestArtefaktWirdCommittet(unittest.TestCase):
    def setUp(self):
        self.luecken, self.unbekannt, self.gesehen = _durchlauf()

    def test_jede_geschriebene_datei_wird_committet(self):
        text = "\n".join(f"  {wf} schreibt {d}, committet sie aber nicht" for wf, d in self.luecken)
        self.assertEqual(self.luecken, [],
                         "\nDer Lauf schreibt Dateien, die nie im Repo ankommen — auf dem naechsten "
                         "Runner sind sie weg:\n" + text +
                         "\n\nEntweder in die git-add-Liste des Workflows aufnehmen oder mit Grund "
                         "in AUSNAHMEN eintragen.")

    def test_kein_unbekannter_datei_helfer(self):
        """Gegen das Loch im Waechter: ein neuer Schreib-Helfer darf nicht still als Leser gelten."""
        text = "\n".join(f"  {modul}: {fn}()" for modul, fn in sorted(self.unbekannt))
        self.assertEqual(sorted(self.unbekannt), [],
                         "\nUnbekannte Funktion bekommt einen .json-Pfad. Solange sie weder in "
                         "SCHREIBER noch in LESER steht, weiss dieser Test nicht, ob sie schreibt "
                         "— und ein Waechter, der raet, ist keiner:\n" + text)

    def test_der_scanner_erkennt_die_schreibvorgaenge_wirklich(self):
        """Gegenprobe, und die wichtigere Haelfte des Waechters: der Test oben waere auch dann
        gruen, wenn der Erkenner gar nichts mehr FINDET. Deshalb hier an echten Modulen nagelen,
        und zwar ueber alle drei Aufloesungswege — Konstante, `BASE / NAME`, Literal."""
        self.assertGreater(self.gesehen, 40,
                           "Der Schreib-Erkenner findet fast nichts mehr — vermutlich ist die "
                           "Aufloesung der Pfad-Konstanten kaputt, nicht das Repo sauber.")
        whale = _analysiere(WURZEL / "poly_whale_watch.py")[0]
        for pflicht in ("poly_dominanz_ledger.json", "poly_dominanz_seen.json"):
            self.assertIn(pflicht, whale,
                          f"{pflicht} wird von poly_whale_watch.py geschrieben, der Erkenner "
                          f"sieht es aber nicht mehr — ab hier prueft der Waechter Luft.")
        broad = _analysiere(WURZEL / "poly_money_broad.py")[0]
        self.assertIn("poly_money_klein.json", broad,
                      "`write_json_atomic(BASE / KLEIN_FILE, …)` wird nicht mehr aufgeloest — "
                      "genau dieser Pfad-Weg hat den Fund vom 12.09. zuerst verdeckt.")

    def test_die_dominanz_dateien_sind_wirklich_drin(self):
        """Der konkrete Fund vom 12.09. — als Nagel, damit er nicht durch eine spaetere
        Umstellung der git-add-Liste wieder herausfaellt."""
        registry = json.loads((WURZEL / "state_files_registry.json").read_text(encoding="utf-8"))
        txt = (WF / "poly-global-scan.yml").read_text(encoding="utf-8")
        committet = _committet(txt, registry)[0]
        for pflicht in ("poly_dominanz_ledger.json", "poly_dominanz_seen.json",
                        "poly_dominanz_record.json", "poly_money_klein.json",
                        "shortlist_push_ledger.json"):
            self.assertIn(pflicht, committet, f"{pflicht} wird wieder nicht committet")

    def test_jede_ausnahme_wird_noch_gebraucht(self):
        """Eine Ausnahme, deren Datei niemand mehr schreibt, ist Altlast — und Altlasten in einer
        Ausnahmeliste sind der Ort, an dem der naechste echte Fund untergeht."""
        registry = json.loads((WURZEL / "state_files_registry.json").read_text(encoding="utf-8"))
        verwaist = []
        for (wf_name, datei), grund in AUSNAHMEN.items():
            wf = WF / wf_name
            if not wf.exists():
                verwaist.append(f"{wf_name} gibt es nicht mehr ({datei})")
                continue
            txt = wf.read_text(encoding="utf-8")
            schreibt = set()
            for s in _skripte(txt):
                py = WURZEL / (s + ".py")
                if py.exists():
                    schreibt |= _analysiere(py)[0]
            if datei not in schreibt:
                verwaist.append(f"{wf_name} schreibt {datei} nicht mehr — Ausnahme kann raus")
        self.assertEqual(verwaist, [], "\n" + "\n".join(verwaist))


if __name__ == "__main__":
    unittest.main()
