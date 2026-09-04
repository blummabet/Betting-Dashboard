#!/usr/bin/env python3
"""
uebersicht_integrity.py — Ausgabe-Korrektheits-Batterie fuer die Uebersicht.

Vorgeschichte (04.09.2026, Lucas): „mir waere es wichtig fehlerfrei zu sein, weil sonst ist die
ganze Arbeit in Wahrheit umsonst."

Die Betfair-, Poly- und WM-Pipelines haben je eine Guard-Batterie auf ihre eigenen Daten. Die
UEBERSICHT hatte keine — dabei ist sie die Flaeche, auf die Lucas zuerst schaut, und sie ist die
einzige, die Daten aus ELF Engines zu Saetzen verdichtet. Genau dort entstehen die Fehler:

    04.09.2026, drei Funde an einem Tag, alle derselben Bauart —
    ein Satz oder ein Ranking behauptet etwas, das die Zahl daneben widerlegt:

      · „Beste Streaks" sortierte nach Laenge und schrieb die Grundrate dazu — fuenfmal
        derselbe Markt, der haeufigste im Angebot, als „heisseste Serien".
      · „keine Schublade hat ihre Untergrenze ueber null" — Liga·ABWAEGEN stand bei
        ROI-UG +3,7 %; blockiert hatte die CLV-Bedingung.
      · „🎮 Poly Public n155 · 70 % · +5,0 %" — das ist die Vorschau, die NICHTS sendet;
        das echte Push-Buch stand bei n=3.

Kein einziger davon war ein Absturz, eine Fehlrechnung oder ein Datenfehler. Es waren immer
BEHAUPTUNGEN, die zum Schreibzeitpunkt stimmten und danach still veralteten. Ein Unit-Test faengt
davon nur, was jemand zu testen dachte; diese Batterie prueft die LIVE-Artefakte bei jedem Lauf.

Leitprinzip (wie bei den anderen dreien): Wenn eine Aussage auf der Uebersicht von den Daten nicht
mehr gedeckt ist, MUSS es sichtbar werden — nicht still danebenstehen.

REIN/testbar: `run_checks(ctx)` bekommt die Artefakte als dict und macht keine Datei-Zugriffe.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATUS_FILE = "uebersicht_integrity.json"


def _lade(name: str, default=None):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return default


# ── Die Guards ────────────────────────────────────────────────────────────────
# Jeder traegt den Vorfall, aus dem er entstanden ist. Ein Guard ohne Vorfall ist eine Meinung.

def _c(label, severity, failures, hinweis=""):
    return {"label": label, "severity": severity, "failures": failures,
            "nFail": len(failures), "ok": not failures, "hinweis": hinweis}


def check_serien_rangfolge(ctx):
    """04.09.2026 — „Beste Streaks" zeigte fuenfmal „Team trifft 15x · Grundrate 82 %".

    Die Kachel sortierte nach LAENGE und schrieb die Grundrate selbst daneben. Laenge ist ueber
    Maerkte hinweg nicht vergleichbar: „Team trifft" gelingt im Liga-Schnitt in vier von fuenf
    Spielen, „Zu null" in einem von vier. Ohne `zufallPct` faellt die Uebersicht auf genau diese
    Sortierung zurueck — der Guard schlaegt an, BEVOR das jemand auf dem Board sieht.
    """
    fails = []
    for name in ("ligaStreaks", "mlsStreaks"):
        d = ctx.get(name) or {}
        st = d.get("streaks") or []
        if not st:
            continue
        ohne = [s for s in st if not isinstance(s.get("zufallPct"), (int, float))]
        if len(ohne) > len(st) * 0.5:
            fails.append(f"{name}: {len(ohne)}/{len(st)} Serien ohne zufallPct — die Uebersicht "
                         f"faellt auf die Laengen-Sortierung zurueck (der Fehler vom 04.09.)")
        if (d.get("_meta") or {}).get("sortiert") != "zufallPct":
            fails.append(f"{name}: _meta.sortiert ist '{(d.get('_meta') or {}).get('sortiert')}' "
                         f"statt 'zufallPct' — Produzent und Anzeige rangieren verschieden")
    return _c("Serien werden nach Seltenheit rangiert, nicht nach Laenge", "error", fails)


def check_freigabe_grund(ctx):
    """04.09.2026 — „keine Schublade hat ihre Untergrenze ueber null" war schlicht falsch.

    Liga·ABWAEGEN stand bei n=46, ROI +24,4 %, ROI-UG +3,7 %; gescheitert ist sie an der
    CLV-Bedingung. Der Satz wird seither aus den Daten bestimmt — dieser Guard prueft, dass die
    DATEN das ueberhaupt hergeben: ohne `roiLb`/`clvLb` je Schublade kann die Uebersicht den
    Grund nicht nennen und faellt auf eine Behauptung zurueck.
    """
    f = ctx.get("freigabe") or {}
    alle = f.get("alle") or []
    fails = []
    if not alle:
        return _c("Freigabe-Grund ist aus den Daten ableitbar", "warn",
                  ["freigabe.json hat keine Schubladen — Ebene 1 kann nichts begruenden"])
    minN = ((f.get("regeln") or {}).get("minN")) or 30
    reif = [r for r in alle if (r.get("n") or 0) >= minN]
    ohne_roi = [r for r in reif if "roiLb" not in r]
    if ohne_roi:
        fails.append(f"{len(ohne_roi)}/{len(reif)} reife Schubladen ohne Feld roiLb — "
                     f"der Blockierungsgrund waere wieder geraten")
    # Und die inhaltliche Probe: wenn eine reife Schublade die ROI-Huerde nimmt, darf nirgends
    # mehr „keine hat ihre Untergrenze ueber null" stehen. Das prueft der Frontend-Test; hier
    # wird nur gemeldet, DASS der Fall vorliegt — damit er nicht unbemerkt bleibt.
    roi_ok = [r for r in reif if isinstance(r.get("roiLb"), (int, float)) and r["roiLb"] > 0]
    hinweis = ""
    if roi_ok:
        hinweis = ("Fall liegt aktuell vor: " + ", ".join(r["schublade"] for r in roi_ok[:3])
                   + " nehmen die ROI-Huerde und scheitern an CLV — der Satz auf Ebene 1 muss das sagen")
    return _c("Freigabe-Grund ist aus den Daten ableitbar", "error", fails, hinweis)


def check_poly_kachel_ist_keine_kanalbilanz(ctx):
    """04.09.2026 — „🎮 Poly Public n155 · 70 % · +5,0 %" ganz oben im Puls.

    Das ist der Track der Public-KANDIDATEN — eine Vorschau, die nichts sendet (poly-wallets.js
    sagt es selbst). Das echte Push-Buch stand bei n=3. Lucas hatte dieselbe Verwechslung am
    Morgen im Track-Record gemeldet; in der Uebersicht stand sie noch.
    """
    p = (ctx.get("pulse") or {}).get("poly")
    fails = []
    if not p:
        return _c("Poly-Kachel gibt sich nicht als Kanal-Bilanz aus", "warn",
                  [], "kein Poly-Block im Puls — nichts zu pruefen")
    if p.get("sendet") is not False:
        fails.append("pulse.poly.sendet ist nicht False — die Vorschau kann wieder als "
                     "Kanal-Bilanz gelesen werden (Fund vom 04.09.)")
    if "gesendetN" not in p:
        fails.append("pulse.poly.gesendetN fehlt — die Zahl der WIRKLICH gesendeten Pushs "
                     "steht nicht daneben")
    return _c("Poly-Kachel gibt sich nicht als Kanal-Bilanz aus", "error", fails)


def check_stake_kategorien(ctx):
    """04.09.2026 — „Chicago Cubs – Milwaukee Brewers" stand trotz US-Sport-Sperre in einer Kachel.

    Die Alt-Zeile trug keine Kategorie, der Filter las `kat || ''` und liess sie durch. Seit
    `ledger_mischen()` nachtraegt, verlaesst sich das Frontend darauf. Faellt das Nachtragen aus,
    fliegen die Zeilen jetzt still RAUS statt durch — besser, aber trotzdem meldenswert.
    """
    fails = []
    d = ctx.get("stake") or {}
    w = d.get("wetten") or []
    ohne = [x for x in w if not x.get("kat")]
    if ohne:
        fails.append(f"{len(ohne)}/{len(w)} Stake-Wetten ohne kat — das Frontend blendet sie "
                     f"aus (unbekannt ist keine Erlaubnis), aber der Feed verliert sie")
    return _c("Jede Stake-Wette traegt ihre Sportart", "error", fails)


def check_betfair_urteil(ctx):
    """04.09.2026 — die Fade-Schwelle stand an VIER Stellen, drei davon von einem Test gleich
    gehalten, die vierte (`_tMute`) bei -0,05 statt -0,10.

    Das Urteil faellt seither einmal im Produzenten und wandert als `urteil` mit. Fehlt das Feld,
    lesen drei Flaechen nichts — und irgendwer baut die Schwelle nach.
    """
    t = ctx.get("bfTrack") or {}
    fails = []
    g = t.get("global")
    if not isinstance(g, dict):
        return _c("Betfair-Buckets tragen ihr Urteil mit", "warn", [], "kein bfTrack geladen")
    if "urteil" not in g:
        fails.append("betfair_track_record.json ohne Feld `urteil` — die drei Verbraucher "
                     "koennen nur noch selbst vergleichen (Fund vom 04.09.)")
    blm = t.get("byLeagueMarket") or {}
    mit_ug = [v for v in blm.values() if isinstance(v.get("roiUg"), (int, float))]
    ohne_urteil = [v for v in mit_ug if not v.get("urteil")]
    if ohne_urteil:
        fails.append(f"{len(ohne_urteil)} Buckets mit Untergrenze, aber ohne Urteil")
    return _c("Betfair-Buckets tragen ihr Urteil mit", "error", fails)


def check_quellen_haben_zeitstempel(ctx):
    """03.09.2026 — die Frische-Anzeige war „erfuellt, aber nicht gemessen".

    `_ageMin` konnte `asof` nicht lesen, also war das Alter immer null: der Guard galt als
    erfuellt (Feld in der Liste), gemessen wurde nie. Eine Quelle ohne lesbaren Zeitstempel
    verschwindet still aus der Frische-Zeile, statt als veraltet aufzufallen.
    """
    ZEIT = ("generatedAt", "updatedAt", "asof", "aktualisiert", "capturedAt", "stand")
    fails = []
    for name in ("betfair", "bfTrack", "bfOverview", "freigabe", "pulse", "moneyMap",
                 "ligaStreaks", "mlsStreaks", "stake", "stakeAus"):
        d = ctx.get(name)
        if not isinstance(d, dict):
            continue
        flach = {k for k in d}
        tief = set((d.get("_meta") or {}) if isinstance(d.get("_meta"), dict) else {})
        if not (flach | tief) & set(ZEIT):
            fails.append(f"{name}: kein lesbarer Zeitstempel ({'/'.join(ZEIT[:3])}…) — "
                         f"faellt still aus der Frische-Zeile")
    return _c("Jede Quelle der Uebersicht traegt einen Zeitstempel", "warn", fails)


UEBERSICHT_CHECKS = [
    check_serien_rangfolge,
    check_freigabe_grund,
    check_poly_kachel_ist_keine_kanalbilanz,
    check_stake_kategorien,
    check_betfair_urteil,
    check_quellen_haben_zeitstempel,
]


def run_checks(ctx: dict) -> list:
    """REIN: alle Guards gegen einen Artefakt-Kontext. Ein abstuerzender Guard darf die
    Batterie nicht kippen — er meldet sich selbst als Fehler."""
    out = []
    for fn in UEBERSICHT_CHECKS:
        try:
            out.append(fn(ctx or {}))
        except Exception as e:
            out.append(_c(fn.__name__, "error", [f"Guard selbst gecrasht: {e}"]))
    return out


def build_ctx_from_disk() -> dict:
    return {
        "betfair": _lade("betfair_prices.json", {}),
        "bfTrack": _lade("betfair_track_record.json", {}),
        "bfOverview": _lade("betfair_overview.json", {}),
        "freigabe": _lade("freigabe.json", {}),
        "pulse": _lade("dashboard_pulse.json", {}),
        "moneyMap": _lade("money_map.json", {}),
        "ligaStreaks": _lade("liga_streaks.json", {}),
        "mlsStreaks": _lade("mls_streaks.json", {}),
        "stake": _lade("stake_highroller.json", {}),
        "stakeAus": _lade("stake_auswertung.json", {}),
    }


def main() -> int:
    res = run_checks(build_ctx_from_disk())
    nfail = sum(1 for c in res if not c["ok"])
    print(f"=== Uebersicht-Integritaet: {len(res) - nfail}/{len(res)} Checks ok "
          f"({len(UEBERSICHT_CHECKS)} Guards registriert) ===\n")
    for c in res:
        icon = "OK " if c["ok"] else ("ERR" if c["severity"] == "error" else "warn")
        print(f"[{icon}] {c['label']}: {c['nFail']} Fehler ({c['severity']})")
        for f in c["failures"][:6]:
            print(f"     - {f}")
        if c.get("hinweis"):
            print(f"     ℹ️  {c['hinweis']}")
    (BASE / STATUS_FILE).write_text(json.dumps(
        {"checks": res, "nFail": nfail,
         "generatedAt": datetime.now(timezone.utc).isoformat()},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{STATUS_FILE} geschrieben ({nfail} Warnungen/Fehler).")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
