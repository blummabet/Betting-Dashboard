"""wert_scanner.py — Value gegen den entvigten Sharp-Anker. Vorregistriert am 07.09.2026.

Lucas: „wir brauchen eine Lösung, um mehr Edge zu generieren … schaut euch draußen um, was
andere gut machen."

Der Ansatz mit der belastbarsten Evidenz für jemanden, der ausdrücklich NICHT Pinnacle schlagen
und nicht der Erste sein will:

    Pinnacle entvigen  →  faire Wahrscheinlichkeit  →  gegen die BESTE verfügbare Quote halten
    →  spielen, wo der Bestpreis über fair liegt.

Man muss den Markt nicht schlagen. Man muss nur den Preis nehmen, den ein anderes Buch falsch
stellt. Belege:
  · Buchdahl, 111.909 Quotenpaare / 37.303 Spiele / 22 Ligen / 2012-2017:
    alle Value +2,51 % Yield · Schwelle >2 % +5,71 % · Schwelle >4 % +12,05 %
  · Kaunitz/Zhong/Kreiner 2017 (arXiv:1710.02824), peer-reviewed: Backtest 56.435 Wetten
    ROI 3,5 %; Echtgeld 265 Wetten ROI 8,5 %.

WARUM DAS BEI UNS BISHER NICHT GING — gemessen an unseren eigenen 264 Spielen:

`soft_consensus()` schrieb den MEDIAN von 29 Büchern. Der Median trägt die volle Soft-Marge
(Overround-Median 6,63 % gegen 3,74 % bei Pinnacle) und lag

    1X2      6,70 %   ·   Ü/U 2,5   6,19 %   ·   Ü/U 3,5   6,50 %

UNTER dem fairen Preis. In 0,3 % der Fälle lag er überhaupt darüber. Ein Median-Konsens KANN
per Konstruktion fast nie Value zeigen — er ist der Preis, den man NICHT bekommt. Wir haben 29
Bücher je Spiel geholt und 28 davon weggeworfen. Seit dem 07.09. steht `best_*` daneben.

⚠️ EHRLICH DAZU:
  · Der Rückblick ist LEER, nicht positiv: vor dem 07.09. gibt es keine Bestpreise im Bestand.
    Diese Schublade startet bei null und kann sich deshalb auch nicht selbst bestätigen.
  · Kaunitz dokumentiert im selben Paper die Kehrseite: nach 265 Wetten wurden die Konten auf
    1-11 $ Maximaleinsatz limitiert. Wer so spielt, verliert das Buch, nicht das Geld. Das ist
    kein Grund, es nicht zu messen — aber einer, es beim Skalieren zu wissen.
  · Ein Flag, das nur unter EINEM De-Vig-Verfahren steht, ist ein Artefakt der Rechenvorschrift.
    Deshalb steht `streuungPct` an jedem Fund und `robust` sagt, ob es unter ALLEN Verfahren hält.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import devig as D

BASE = Path(__file__).resolve().parent
OUT_FILE = "wert_scanner.json"
VORREG_AB = "2026-09-07"

SCHWELLE = 0.02          # ab hier gilt ein Fund als Kandidat (Buchdahl: +5,71 % Yield ab 2 %)
MIN_BUECHER = 3          # unter drei Büchern ist „das Maximum" ein Ausreißer, keine Auswahl
MAX_QUOTE = 15.0         # Longshots: dort ist jede De-Vig am unsichersten (Streuung bis 12 %)

# (Bezeichnung, Pinnacle-Felder, Best-Felder, Ausgangsnamen)
MAERKTE = (
    ("1X2", ("hw", "dr", "aw"), ("best_hw", "best_dr", "best_aw"), ("Heim", "Remis", "Auswärts")),
    ("Über/Unter 2,5", ("o25", "u25"), ("best_o25", "best_u25"), ("Über 2,5", "Unter 2,5")),
    ("Über/Unter 3,5", ("o35", "u35"), ("best_o35", "best_u35"), ("Über 3,5", "Unter 3,5")),
    ("Über/Unter 1,5", ("o15", "u15"), ("best_o15", "best_u15"), ("Über 1,5", "Unter 1,5")),
    ("Beide treffen", ("bttsY", "bttsN"), ("best_bttsY", "best_bttsN"), ("Ja", "Nein")),
)


def funde(odds_row: dict, schwelle: float = SCHWELLE, min_buecher: int = MIN_BUECHER) -> list:
    """Value-Funde für EIN Spiel. REIN/testbar — nimmt genau den odds-Block aus {ds}-data.json."""
    raus = []
    if not isinstance(odds_row, dict):
        return raus
    for markt, pin_f, best_f, namen in MAERKTE:
        pin = [odds_row.get(f) for f in pin_f]
        if not all(isinstance(x, (int, float)) and x > 1.0 for x in pin):
            continue
        p = D.fair(pin)
        if not p:
            continue
        spread = D.streuung(pin) or [None] * len(pin)
        for i, bf in enumerate(best_f):
            b = odds_row.get(bf)
            nb = odds_row.get("nBooks_" + bf[len("best_"):])
            if not isinstance(b, (int, float)) or b <= 1.0 or b > MAX_QUOTE:
                continue
            if not isinstance(nb, int) or nb < min_buecher:
                continue          # fehlende Bücherzahl ist keine Erlaubnis
            edge = p[i] * b - 1.0
            if edge <= schwelle:
                continue
            # Hält der Fund unter JEDEM De-Vig-Verfahren? Sonst ist er eine Rechenvorschrift.
            robust = True
            for v in D.VERFAHREN:
                pv = D.entvigen(pin, v)
                if pv is None:
                    continue
                if pv[i] * b - 1.0 <= 0:
                    robust = False
                    break
            raus.append({
                "markt": markt, "seite": namen[i],
                "pinnQuote": pin[i], "fairQuote": round(1.0 / p[i], 3),
                "bestQuote": b, "buch": odds_row.get("bestBook_" + bf[len("best_"):]),
                "nBuecher": nb, "edgePct": round(100.0 * edge, 2),
                "streuungPct": spread[i], "robust": robust,
            })
    raus.sort(key=lambda r: -r["edgePct"])
    return raus


def scan(daten: dict, schwelle: float = SCHWELLE) -> list:
    """Alle Spiele eines Datensatzes. Erwartet {ds}-data.json."""
    raus = []
    odds = (daten or {}).get("odds") or {}
    namen = {}
    for gk, g in ((daten or {}).get("groups") or {}).items():
        for f in (g.get("fixtures") or []):
            k = "%s-%s" % (f.get("home"), f.get("away"))
            namen[k] = {"spiel": "%s v %s" % (f.get("homeName"), f.get("awayName")),
                        "liga": g.get("name"), "kickoff": f.get("kickoff"),
                        "fertig": (f.get("result") or {}).get("status") == "FT"}
    for k, row in odds.items():
        meta = namen.get(k) or {}
        if meta.get("fertig"):
            continue
        for f in funde(row, schwelle):
            raus.append({**meta, "key": k, **f})
    raus.sort(key=lambda r: -r["edgePct"])
    return raus


def baue(dateien=("liga-data.json", "mls-data.json")) -> dict:
    alle, geprueft, mit_best = [], 0, 0
    for name in dateien:
        p = BASE / name
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        odds = d.get("odds") or {}
        geprueft += len(odds)
        mit_best += sum(1 for r in odds.values()
                        if isinstance(r, dict) and any(k.startswith("best_") for k in r))
        alle += scan(d)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "regel": {"anker": "Pinnacle, entvigt (Shin für 1X2, multiplikativ für Zwei-Weg)",
                  "gegen": "bestes von ~29 Büchern", "schwellePct": round(100 * SCHWELLE, 1),
                  "minBuecher": MIN_BUECHER, "abDatum": VORREG_AB},
        "spieleGeprueft": geprueft,
        "spieleMitBestpreis": mit_best,
        "funde": alle,
        "robust": [f for f in alle if f["robust"]],
    }


def main() -> int:
    from safe_write import write_json_atomic
    d = baue()
    write_json_atomic(BASE / OUT_FILE, d, indent=1)
    print("=== wert_scanner.py ===")
    print("  %d Spiele geprüft, %d davon mit Bestpreis im Bestand"
          % (d["spieleGeprueft"], d["spieleMitBestpreis"]))
    if not d["spieleMitBestpreis"]:
        print("  ⚠️  Noch kein Bestpreis erfasst — der Fetcher muss einmal gelaufen sein.")
        print("      Das ist die Rollout-Lücke, kein Befund: der Scanner kann nichts finden,")
        print("      wofür die Daten noch gar nicht geschrieben wurden.")
    print("  %d Funde über %.1f %%, davon %d unter ALLEN De-Vig-Verfahren robust"
          % (len(d["funde"]), 100 * SCHWELLE, len(d["robust"])))
    for f in d["funde"][:12]:
        print("   %-26s %-14s %-10s  best %5.2f (%s, %d Bücher) vs fair %5.2f  → %+5.2f %% %s"
              % (str(f.get("spiel"))[:26], f["markt"], f["seite"], f["bestQuote"],
                 f.get("buch") or "?", f["nBuecher"], f["fairQuote"], f["edgePct"],
                 "" if f["robust"] else "⚠️ nur unter manchen Verfahren"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
