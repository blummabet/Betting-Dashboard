# -*- coding: utf-8 -*-
"""poly_gegenseite.py — was ein Push wert ist, wenn eine zweite bewiesene Wallet dagegenhaelt.

18.09.2026. Lucas schickt zwei Karten aus demselben Spiel, wenige Minuten auseinander:

    Liquid v 3DMAX · 🐋🔥 Grosser Einstieg · $31.1K auf 3DMAX @49c  · Wallet 0x29b5 (Rang #16)
    Liquid v 3DMAX · 🔥 Scharfe Wallet     · $13.9K auf Liquid @50c · Wallet 0x30c7

Dazu: „Ich werd solche Einsaetze nie verstehen. Beide Top Wallets."

Die Frage ist berechtigt und sie ist messbar. Dieses Modul misst sie gegen den echten Bestand:
`poly_money_broad_close.json` haelt je Markt die Wale MIT SEITE und, nach der Aufloesung, die
`resolvedPrices` — daraus steht der Gewinner fest.

Gemessen am 18.09. ueber 3.659 aufgeloeste Maerkte, „bewiesen" nach demselben Mass, mit dem eine
Wallet ueberhaupt in einen Push kommt (`poly_whale_watch._is_smart`):

    unumkaempft   516 Positionen   69,0 % richtig
    umkaempft     208 Positionen   51,9 % richtig      (90 Maerkte)
    Differenz                     -17,1 pp   Band [-22,1, -12,0]   (Bootstrap ueber Maerkte)

Zwei Dinge dazu, damit die Zahl nicht mehr behauptet als sie kann:

1. Dass umkaempfte Maerkte gegen 50 % laufen, ist zum Teil ARITHMETIK und keine Entdeckung:
   sitzen bewiesene Wallets auf beiden Seiten, gewinnt per Konstruktion eine und verliert eine.
   Genau deshalb ist Folgen dort ein Muenzwurf — die Messung sagt, was es kostet, nicht dass es
   ueberrascht.
2. Die 69 % der unumkaempften Seite sind nach oben verzerrt: „bewiesen" wird am heutigen
   kumulativen Record gemessen, und der enthaelt diese Positionen. Die DIFFERENZ ist davon viel
   weniger betroffen, weil in beiden Gruppen dieselben Wallets stehen.

Was dabei sonst noch herauskam, und was die Karten erklaert: umkaempfte Maerkte sind die
DICHTEREN und die AUSGEGLICHENEREN. Median-Volumen $64K gegen $36K, Median-Preisabstand der
beiden Seiten 0,16 gegen 0,21. Ein Konto, das $31K unterbringen will, findet genau dort Platz —
bei einem Preis nahe 50 und einem Buch, das die Groesse schluckt. Das ist keine Ueberzeugung
ueber den Ausgang, das ist die Stelle, an der die Groesse hinpasst.
"""
from __future__ import annotations
import json
import math
import random
from pathlib import Path

BASE = Path(__file__).resolve().parent
CLOSE_FILE = BASE / "poly_money_broad_close.json"
TRACK_FILE = BASE / "poly_wallet_track.json"
OUT_FILE = BASE / "poly_gegenseite.json"

MIN_MAERKTE = 30        # darunter wird nichts behauptet
MIN_EINIG = 30          # dasselbe fuer die Gegenprobe (mehrere Wallets auf derselben Seite)
BOOT = 3000
SEED = 20260918         # fest, damit zwei Laeufe auf denselben Daten dasselbe Band liefern


def _gewinner(m) -> str | None:
    """Gewinnerseite aus den Aufloesungspreisen. Liegt in `poly_money_broad`, nicht hier."""
    try:
        import poly_money_broad as P
    except Exception:
        return None
    return P.winner_from_prices((m or {}).get("resolvedPrices") or {})


def beobachtungen(close: dict, ist_bewiesen) -> list:
    """Je aufgeloestem Markt EIN Eintrag: {key, umkaempft, treffer:[bool,...]}. REIN/testbar.

    `ist_bewiesen(wallet) -> bool` wird injiziert — das Mass fuer „bewiesen" gehoert dorthin, wo
    ueber den Push entschieden wird, und nicht ein zweites Mal hierher.
    """
    out = []
    for key, m in (close or {}).items():
        if not isinstance(m, dict) or not m.get("resolved"):
            continue
        win = _gewinner(m)
        if not win:
            continue
        seiten = {}
        for w in (m.get("whales") or []):
            if not isinstance(w, dict):
                continue
            seite = w.get("side")
            wallet = str(w.get("wallet") or "").lower()
            if not seite or not wallet or not ist_bewiesen(wallet):
                continue
            seiten.setdefault(seite, 0)
            seiten[seite] += 1
        if not seiten:
            continue
        treffer = [s == win for s, c in seiten.items() for _ in range(c)]
        umk = len(seiten) >= 2
        # Wie viele bewiesene Wallets stehen auf der EINEN Seite? Nur dann eine Zahl, wenn es
        # genau eine Seite gibt — bei Streit ist „wie viele sind sich einig" keine Frage mehr.
        n_seite = None if umk else list(seiten.values())[0]
        out.append({"key": key, "umkaempft": umk, "treffer": treffer, "nSeite": n_seite})
    return out


def _quote(gruppe) -> tuple:
    n = sum(len(e["treffer"]) for e in gruppe)
    w = sum(sum(e["treffer"]) for e in gruppe)
    return ((w / n) if n else None), n, w


def _band(um: list, un: list, runs: int = BOOT) -> tuple:
    """Bootstrap der DIFFERENZ, gezogen ueber MAERKTE (nicht ueber Positionen).

    Zwei Positionen desselben Marktes haengen aneinander — sie teilen denselben Ausgang. Ueber
    Positionen zu ziehen wuerde das Band zu eng machen; das ist derselbe Griff wie in
    `poly_konvergenz._ug`.
    """
    if not um or not un:
        return (None, None, None)
    r = random.Random(SEED)
    diffs = []
    for _ in range(runs):
        a = [um[r.randrange(len(um))] for _ in range(len(um))]
        b = [un[r.randrange(len(un))] for _ in range(len(un))]
        qa, qb = _quote(a)[0], _quote(b)[0]
        if qa is None or qb is None:
            continue
        diffs.append(qa - qb)
    if not diffs:
        return (None, None, None)
    diffs.sort()
    lo = diffs[int(0.025 * len(diffs))]
    hi = diffs[min(len(diffs) - 1, int(0.975 * len(diffs)))]
    return (sum(diffs) / len(diffs), lo, hi)


def einigkeit_urteil(n_einig: int, diff, lo) -> tuple:
    """(urteil, grund) fuer die andere Richtung: mehrere bewiesene Wallets auf DERSELBEN Seite.

    18.09.2026 (Lucas: „was ist, wenn zwei Top Wallets auf dieselbe Seite gehen? Haben wir das
    extra bedacht?"). Nein, hatten wir nicht — auf der Karte stand dazu kein Wort, waehrend der
    Streitfall seit August einen Marker hat. Die Gegenprobe zur Sperre gehoert aber dazu: wenn
    Widerspruch etwas kostet, muss man auch fragen, ob Zustimmung etwas bringt.

    Hier muss die UNTERgrenze ueber null liegen — spiegelbildlich zur Sperre, wo die Obergrenze
    unter null liegen muss. Dieselbe Strenge in beide Richtungen.
    """
    if n_einig < MIN_EINIG:
        return ("zu wenig Daten", "erst %d Maerkte mit Einigkeit, noetig sind %d"
                % (n_einig, MIN_EINIG))
    if diff is None or lo is None:
        return ("zu wenig Daten", "kein Band berechenbar")
    if lo > 0:
        return ("Einigkeit traegt",
                "sind sich mehrere bewiesene Wallets einig, trifft die Seite %.1f pp oefter; "
                "die Untergrenze des Bandes liegt bei %.1f pp und damit noch ueber null"
                % (100 * diff, 100 * lo))
    return ("nicht entschieden",
            "die Differenz liegt bei %.1f pp, aber das Band reicht bis %.1f pp — unter null"
            % (100 * diff, 100 * lo))


def urteil(n_um: int, diff, hi) -> tuple:
    """(urteil, grund). REIN. Ein Punktschaetzer entscheidet auch hier nichts — das Band muss
    ganz unter null liegen, sonst heisst es „nicht entschieden"."""
    if n_um < MIN_MAERKTE:
        return ("zu wenig Daten", "erst %d umkaempfte Maerkte, noetig sind %d" % (n_um, MIN_MAERKTE))
    if diff is None or hi is None:
        return ("zu wenig Daten", "kein Band berechenbar")
    if hi < 0:
        return ("umkaempft ist schlechter",
                "in umkaempften Maerkten trifft eine bewiesene Wallet %.1f pp seltener; "
                "die Obergrenze des Bandes liegt bei %.1f pp und damit noch unter null"
                % (-100 * diff, 100 * hi))
    return ("nicht entschieden",
            "die Differenz liegt bei %.1f pp, aber das Band reicht bis %.1f pp — ueber null"
            % (100 * diff, 100 * hi))


def bericht(close: dict, ist_bewiesen) -> dict:
    zeilen = beobachtungen(close, ist_bewiesen)
    um = [z for z in zeilen if z["umkaempft"]]
    un = [z for z in zeilen if not z["umkaempft"]]
    q_um, n_um, w_um = _quote(um)
    q_un, n_un, w_un = _quote(un)
    diff, lo, hi = _band(um, un)
    u, grund = urteil(len(um), diff, hi)
    # Die Gegenprobe: unter den UNUMKAEMPFTEN Maerkten die mit mehreren einigen Wallets gegen
    # die mit einer einzigen. Umkaempfte gehoeren hier nicht hinein — dort ist die Frage eine
    # andere, und sie faellt ohnehin schon unter das Urteil oben.
    einig = [z for z in un if (z.get("nSeite") or 1) >= 2]
    allein = [z for z in un if (z.get("nSeite") or 1) < 2]
    q_ei, n_ei, w_ei = _quote(einig)
    q_al, n_al, w_al = _quote(allein)
    e_diff, e_lo, e_hi = _band(einig, allein)
    e_u, e_grund = einigkeit_urteil(len(einig), e_diff, e_lo)
    def _arm(q, n, w, mk):
        return {"maerkte": mk, "n": n, "wins": w,
                "hit": None if q is None else round(q, 4),
                "hitPct": None if q is None else round(100 * q, 1)}
    return {
        "maerkte": len(zeilen),
        "umkaempft": _arm(q_um, n_um, w_um, len(um)),
        "unumkaempft": _arm(q_un, n_un, w_un, len(un)),
        "diffPP": None if diff is None else round(100 * diff, 1),
        "lo": None if lo is None else round(100 * lo, 1),
        "hi": None if hi is None else round(100 * hi, 1),
        "urteil": u,
        "grund": grund,
        "minMaerkte": MIN_MAERKTE,
        "einigkeit": {
            "einig": _arm(q_ei, n_ei, w_ei, len(einig)),
            "allein": _arm(q_al, n_al, w_al, len(allein)),
            "diffPP": None if e_diff is None else round(100 * e_diff, 1),
            "lo": None if e_lo is None else round(100 * e_lo, 1),
            "hi": None if e_hi is None else round(100 * e_hi, 1),
            "urteil": e_u,
            "grund": e_grund,
            "minMaerkte": MIN_EINIG,
        },
    }


def _laden(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    close = _laden(CLOSE_FILE)
    track = _laden(TRACK_FILE) or {}
    scores = track.get("scores") or {}
    if not isinstance(close, dict) or not scores:
        print("ℹ️  poly_gegenseite: keine Close-Historie oder keine Scores — nichts zu tun")
        return 0
    import poly_whale_watch as W
    def bewiesen(wallet):
        return W._is_smart(scores.get(wallet))
    r = bericht(close, bewiesen)
    OUT_FILE.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print("⚔️  Gegenseite: %s — umkaempft %s%% (n=%s, %s Maerkte) gegen unumkaempft %s%% (n=%s), "
          "Differenz %s pp, Band [%s, %s]"
          % (r["urteil"], r["umkaempft"]["hitPct"], r["umkaempft"]["n"], r["umkaempft"]["maerkte"],
             r["unumkaempft"]["hitPct"], r["unumkaempft"]["n"], r["diffPP"], r["lo"], r["hi"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
