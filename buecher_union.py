"""Bücher werden VEREINT, nicht überschrieben.

🔴 24.09.2026 (Lucas: „Kamen 2 Meldungen zum selben Spiel und beide wurden gesetzt … war schon
gefixt, schon wieder kaputt").

Fuego vs EDward Gaming Youth Team, zweimal $5 gesetzt:
    06:13 UTC  Order 0xc1c79cbe77ac9de4576b45
    06:18 UTC  Order 0x20e1d0439ed6ce9e66608f

Nachgesehen, was in den Büchern steht:
    Commit 06:13  shortlist_auto_bets_placed.json  53 Wetten, letzte = 0xc1c79cbe…
    Commit 06:18  shortlist_auto_bets_placed.json  53 Wetten, letzte = 0x20e1d043…

Dieselbe Anzahl. Der zweite Lauf hat die Zeile des ersten nicht ergänzt, sondern ersetzt. Die
Order 0xc1c79cbe… steht seither in KEINER Datei des Hauses — gesucht über alle JSON-Dateien,
null Treffer. Fünf Dollar liegen an der Börse, von denen das Haus nichts weiß; der
Einsatz-Deckel („$10.00 / $100" in beiden Meldungen, in Wahrheit $15) rechnet an ihnen vorbei,
und die Auflösung wird nie gebucht.

── Warum das Ersetzen passiert ─────────────────────────────────────────────────────────
`scripts/ci_pull.sh` zieht mit `git pull --no-rebase -X ours`. Hängen sich zwei Läufe an
dieselbe Stelle derselben Datei, ist das ein Konflikt, und `-X ours` heißt: unsere Seite
gewinnt, die andere fliegt weg. Für ein Artefakt, das jeder Lauf ohnehin neu erzeugt (ein
Scan-Abzug), ist das richtig und war es immer. Für ein BUCH ist es das Gegenteil von richtig:
dort ist jede Zeile eine Tatsache, die passiert ist, und zwei Läufe, die je eine Tatsache
mitbringen, haben keinen Konflikt — sie haben zwei Tatsachen.

Fehlerklasse: *ein Zusammenführen, das bei Streit eine Seite wegwirft — auch wenn beide Seiten
Tatsachen sind.*

Das ist ausdrücklich NICHT dieselbe Reparatur wie am 19.09. (`ci_sichern.sh`, „wer handelt,
schreibt sofort"). Die schützt den Beleg davor, mit einem sterbenden Lauf zu verschwinden.
Hier stirbt kein Lauf: ein überlebender Lauf löscht den Beleg eines anderen. Schneller
schreiben hilft dagegen nicht.

── Die Identität einer Zeile ───────────────────────────────────────────────────────────
Vereint wird über das, was eine Zeile zu EINEM Ereignis macht — und das ist bei einer
platzierten Wette die Order, nicht der Play. Genau deshalb überleben hier beide Zeilen, und
genau deshalb kann `doppelte_plays()` danach sagen, dass zweimal auf dasselbe gesetzt wurde.
Ein Union über `betKey` hätte eine der beiden Orders wieder verschluckt — und den Fehler
damit erneut unsichtbar gemacht.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

# Buch -> wie seine Zeilen heissen und was eine Zeile eindeutig macht.
# `liste`: Feld mit der Zeilenliste (None = die Datei IST die Liste).
# `id`:    Felder, die zusammen ein EREIGNIS bezeichnen. Nicht den Play — das Ereignis.
BUECHER = {
    "shortlist_auto_bets_placed.json": {"liste": "bets", "id": ("orderId",)},
    "shortlist_push_ledger.json":      {"liste": None,    "id": ("k", "sentAt")},
    "betfair_public_ledger.json":      {"liste": None,    "id": ("k",)},
    "betfair_rutsch_ledger.json":      {"liste": None,    "id": ("k",)},
    # Dedup-Staende sind flache Abbildungen Schluessel -> Stempel. Auch sie werden vereint:
    # ein Schluessel, den EIN Lauf gesetzt hat, darf ein anderer nicht zuruecknehmen.
    "shortlist_push_seen.json":        {"abbildung": True},
    "betfair_public_seen.json":        {"abbildung": True},
    "betfair_alerts_seen.json":        {"abbildung": True},
    "betfair_rutsch_seen.json":        {"abbildung": True},
    "stake_burst_seen.json":           {"abbildung": True},
}


def _id(zeile, felder):
    if not isinstance(zeile, dict):
        return None
    teile = [zeile.get(f) for f in felder]
    if all(t in (None, "") for t in teile):
        return None
    return tuple(str(t) for t in teile)


def zeilen_vereinen(unser: list, ihr: list, felder) -> list:
    """Unsere Zeilen, dann die fremden, die wir nicht haben. REIN.

    Die Reihenfolge unserer Seite bleibt, damit der Diff klein bleibt. Eine Zeile ohne
    brauchbare Identitaet wird NIE verworfen — im Zweifel steht sie zweimal da, und das ist
    die richtige Richtung: ein Buch darf lieber zu viel als zu wenig wissen.
    """
    unser = [z for z in (unser or [])]
    ihr = [z for z in (ihr or [])]
    haben = set()
    for z in unser:
        i = _id(z, felder)
        if i is not None:
            haben.add(i)
    raus = list(unser)
    for z in ihr:
        i = _id(z, felder)
        if i is None or i not in haben:
            raus.append(z)
            if i is not None:
                haben.add(i)
    return raus


def abbildung_vereinen(unser: dict, ihr: dict) -> dict:
    """Beide Dedup-Staende, unserer gewinnt bei gleichem Schluessel. REIN.

    Ein Schluessel steht fuer „wurde gesendet". Ihn zu verlieren heisst, erneut zu senden —
    deshalb ueberlebt jeder Schluessel beider Seiten.
    """
    raus = dict(ihr or {})
    raus.update(dict(unser or {}))
    return raus


def vereinen(unser, ihr, spec):
    """Ein Buch aus zwei Staenden. REIN. Gibt `unser` unveraendert zurueck, wenn nichts passt."""
    if not spec:
        return unser
    if spec.get("abbildung"):
        if isinstance(unser, dict) and isinstance(ihr, dict):
            return abbildung_vereinen(unser, ihr)
        return unser
    feld = spec.get("liste")
    felder = spec.get("id") or ()
    if feld is None:
        if isinstance(unser, list) and isinstance(ihr, list):
            return zeilen_vereinen(unser, ihr, felder)
        return unser
    if isinstance(unser, dict) and isinstance(ihr, dict):
        neu = dict(unser)
        neu[feld] = zeilen_vereinen(unser.get(feld), ihr.get(feld), felder)
        return neu
    return unser


# Doppelsetzungen, die untersucht und abgehakt sind. Schluessel ist das Order-PAAR, nicht der
# Play: derselbe Play kann spaeter erneut doppelt gesetzt werden, und dann ist es ein neuer
# Vorfall. Ohne diese Liste bliebe der Waechter wegen eines Ereignisses von heute fuer immer
# rot — und einen dauerhaft roten Waechter liest niemand mehr (gelernt am 23.09. beim
# Beleg-Alarm). Ein Eintrag ohne Begruendung ist keiner (Test).
QUITTIERT = {
    ("0x20e1d0439ed6ce9e66608f8f112998359c006c6f514ddb9ff64246fcf3ea1248",
     "0xc1c79cbe77ac9de4576b45dce3a11f5e075d0f368ca834815e985cca7f29b958"):
        "24.09.2026, Fuego vs EDward Gaming Youth Team: zwei Laeufe setzten je $5, weil die "
        "Wallet-Schranke aus einem 20 Minuten alten Schnappschuss entschied. Beide Orders "
        "liegen an der Boerse. Ursache behoben (frischer Wallet-Griff vor der Order, "
        "Buch-Vereinigung statt -X ours); die zweite Position bleibt und wird normal "
        "abgerechnet.",
}


def _paar(orders):
    return tuple(sorted(str(o) for o in orders))


def doppelte_plays(bets) -> dict:
    """Plays, auf die MEHR ALS EINE Order laeuft. REIN. -> {betKey: [orderId, ...]}

    Die Kehrseite der Vereinigung: weil ab jetzt beide Orders im Buch stehen, ist ein
    Doppelsetzen ueberhaupt erst zaehlbar. Vorher hat die zweite Zeile die erste ersetzt, und
    das Buch sah danach vollkommen gesund aus — aufgefallen ist es nur, weil zwei Meldungen
    in Lucas' Telegram standen. Ein Fehler, den nur ein Mensch im Kanal sehen kann, ist nicht
    ueberwacht.

    Gezaehlt wird ueber `betKey` (ein Play), unterschieden ueber `orderId` (ein Ereignis).
    """
    je = {}
    for b in (bets or []):
        if not isinstance(b, dict):
            continue
        k, o = b.get("betKey"), b.get("orderId")
        if not k or not o:
            continue
        je.setdefault(str(k), [])
        if str(o) not in je[str(k)]:
            je[str(k)].append(str(o))
    return {k: v for k, v in je.items()
            if len(v) > 1 and _paar(v) not in QUITTIERT}


def _git_fassung(pfad, ref="FETCH_HEAD", cwd=None):
    """Die Fassung einer Datei aus einer git-Referenz, oder None."""
    try:
        out = subprocess.run(["git", "show", f"{ref}:{pfad}"], cwd=cwd,
                             capture_output=True, text=True, timeout=30)
        if out.returncode != 0 or not out.stdout.strip():
            return None
        return json.loads(out.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    ref = os.environ.get("BUECHER_REF", "FETCH_HEAD")
    geaendert = []
    for pfad in argv:
        name = os.path.basename(pfad)
        spec = BUECHER.get(name)
        if not spec or not os.path.exists(pfad):
            continue
        try:
            with open(pfad, encoding="utf-8") as fh:
                unser = json.load(fh)
        except (OSError, ValueError) as exc:
            print(f"  ⚠️  {name} nicht lesbar ({exc}) — nicht angefasst.")
            continue
        ihr = _git_fassung(pfad, ref)
        if ihr is None:
            continue
        neu = vereinen(unser, ihr, spec)
        if neu != unser:
            with open(pfad, "w", encoding="utf-8") as fh:
                json.dump(neu, fh, ensure_ascii=False, indent=1)
            geaendert.append(name)
    if geaendert:
        print("  🤝 Buch vereint statt ueberschrieben: " + ", ".join(geaendert))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
