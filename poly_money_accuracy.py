#!/usr/bin/env python3
"""
poly_money_accuracy.py — Liegt das Poly-Geld richtig? (19.07.2026, Lucas).

## Die Frage

Wir kennen für jeden Poly-Markt den PREIS und die GELD-VERTEILUNG (wie viel USDC auf jeder Seite
liegt). Der Preis ist die letzte gehandelte Meinung; das Geld ist die aufgelaufene Positionierung.
Auf einem CLOB können die auseinanderlaufen — viel Geld sitzt auf einer Seite, während der Preis
woanders steht. Frage: **gewinnt die Seite mit dem Geld auch?** Und schärfer: **sagt das Geld mehr
als der Preis, oder ist es nur Rauschen, das der Preis eh schon enthält?**

Das ist der empirische Test unserer eigenen These „Polymarket ist die Trade-Gegenseite, kein
Sharp-Anker". Liegt das Geld systematisch richtig → es ist ein Signal. Liegt es nicht besser als
der Preis → bestätigt, dass es dummes Geld ist, das wir faden dürfen.

## Wie gemessen wird — zwei Schritte

1. **Einfrieren (`capture`)**: Die Geld-Verteilung ist flüchtig (Snapshot). Wie bei den
   Closing-Lines frieren wir sie NAH AM ANPFIFF ein (`{ds}_poly_money_close.json`) — pro Ausgang
   den Geld-Anteil UND den Poly-Preis. So haben wir eine faire, zeitkonsistente Momentaufnahme.
2. **Auflösen (`evaluate`)**: gegen den Ausgang. Metriken:
   · Geld-Mehrheit-Trefferquote: gewinnt die Seite mit dem meisten Geld?
   · Preis-Favorit-Trefferquote: die Baseline (gewinnt der günstigste Preis?).
   · **Brier Geld vs. Brier Preis**: wer ist besser kalibriert (niedriger = besser)? DAS ist die
     eigentliche Antwort — ist das Geld schärfer als der Preis oder nicht.
   · Uneinigkeits-Bucket: wenn Geld-Favorit ≠ Preis-Favorit, wer gewinnt öfter? Der reinste Test.

⚠️ Daten-Hunger: es zählt nur, was wir SEIT dem Einfrieren gesammelt haben. Anfangs winzige
Stichprobe — Urteil erst über Wochen, wie beim Wallet-Track-Record. Read-only, kein Geld.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D
from safe_write import write_json_atomic

BASE = Path(__file__).resolve().parent

CAPTURE_WINDOW_H = 3.0   # so nah am Anpfiff frieren wir die Geld-Verteilung ein
MIN_TOTAL_USD    = 5_000  # dünner Markt → Verteilung nicht aussagekräftig
_OUT = ("home", "draw", "away")


def _now():
    return datetime.now(timezone.utc)


def _norm3(vals: dict):
    """{home,draw,away} → faire Wahrscheinlichkeiten (Summe 1). Fehlende Seite = 0."""
    xs = {k: float(vals.get(k) or 0) for k in _OUT}
    s = sum(xs.values())
    if s <= 0:
        return None
    return {k: v / s for k, v in xs.items()}


def _norm(vals: dict, keys):
    """Wie _norm3, aber über BELIEBIGE Ausgangs-Labels (nicht nur home/draw/away) — nötig für den
    breiten Cross-Sport-Scan, wo Ausgänge Teamnamen o.ä. heißen."""
    xs = {}
    for k in keys:
        try:
            xs[k] = float(vals.get(k) or 0)
        except (TypeError, ValueError):
            xs[k] = 0.0
    s = sum(xs.values())
    if s <= 0:
        return None
    return {k: v / s for k, v in xs.items()}


def capture(smartmoney: dict, prices: dict, frozen: dict, now=None) -> dict:
    """Geld-Verteilung + Preis nah am Anpfiff einfrieren. REIN.

    Aktualisiert bis zum Anpfiff immer den KLASSENBESTEN (dichtesten) Snapshot — so steht am Ende
    die ehrlichste Nah-am-Anpfiff-Momentaufnahme, nicht ein 3h-alter Zwischenstand."""
    now = now or _now()
    out = dict(frozen or {})
    pmap = (prices or {}).get("prices") or {}

    for key, m in (smartmoney.get("matches") or {}).items():
        htk = m.get("hoursToKickoff")
        try:
            htk = float(htk)
        except (TypeError, ValueError):
            continue
        if not (0 < htk <= CAPTURE_WINDOW_H):
            continue                      # nur im Anpfiff-Fenster, nach Anpfiff nicht mehr anfassen
        try:
            total = float(m.get("totalUsd") or 0)
        except (TypeError, ValueError):
            total = 0.0
        if total < MIN_TOTAL_USD:
            continue

        prev = out.get(key)
        if prev is not None and prev.get("hoursToKickoff", 99) <= htk:
            continue                      # wir haben schon einen dichteren Snapshot

        oc = m.get("outcomes") or {}
        shares = {k: (oc.get(k) or {}).get("share") for k in _OUT}
        pe = pmap.get(key) or {}
        prices_oc = {"home": pe.get("hw"), "draw": pe.get("dr"), "away": pe.get("aw")}
        out[key] = {
            "shares": {k: shares.get(k) for k in _OUT},
            "prices": prices_oc,
            "totalUsd": round(total),
            "hoursToKickoff": round(htk, 2),
            "capturedAt": now.isoformat(),
        }
    return out


# ── Güte des Geld-Splits ───────────────────────────────────────────────────────
# 02.09.2026 (Lucas-Audit „Großes Geld"). Der Split wurde bis heute ungeprüft als Aussage
# ausgegeben. Nachgemessen zerfällt er in zwei Hälften, und keine war das, was oben drüberstand:
#
#   · ZWEI Ausgänge (Tennis, E-Sport, MLB, Over/Under), n=1.262: |Geld% − Preis| Median 0,0pp,
#     1262 von 1262 unter 1pp. Struktur, kein Zufall: bei komplementären Tokens hält jede
#     Ja-Aktie eine Nein-Aktie als Gegenstück, also ist Wert_A/Wert_B zwangsläufig p/(1−p).
#     „Geld liegt auf X 68% (69¢)" sagt dieselbe Zahl zweimal.
#   · DREI Ausgänge (Fußball 1X2): grob schiefe Splits, die kein Preis hergibt — `lal-osa-get`
#     hatte Osasuna (44,5¢) mit $745.597 gegen Getafe (22,5¢) mit $13.006.
#
# ⚠️ KORREKTUR am selben Tag, bevor daraus eine Kennzahl wurde: der erste Anlauf maß die „Güte"
# als sum(shares)/totalUsd und nannte das Abdeckung. `totalUsd` ist aber das gehandelte VOLUMEN
# (volumeNum, kumulierter Umsatz), nicht die offene Position — die beiden stehen in keinem festen
# Verhältnis, und ein Markt mit viel Hin und Her sähe automatisch „schlecht erfasst" aus. Die
# Zahl hätte plausibel ausgesehen und nichts gemessen. Genau die Sorte Kennzahl, die dieses
# Projekt sonst überall verbietet.
#
# Was der Abruf WIRKLICH weiß: ob seine Halter-Liste zu Ende war. /holders liefert seitenweise;
# eine volle letzte Seite heißt „da ist noch mehr". Das schreibt _alle_holder als `trunc` mit —
# eine direkte Beobachtung statt einer hergeleiteten Quote.
#
#   art = "leer"        → keine Seiten-Aufteilung vorhanden
#         "preis_echo"  → zwei Ausgänge; der Geld-Anteil IST der Preis
#         "belastbar"   → Halter-Listen vollständig (oder bereits normalisierte Anteile)
#         "abgeschnitten" → mindestens ein Ausgang war abgeschnitten; der Split ist unvollständig
#         "unbekannt"   → aus der Zeit vor `trunc`; wir wissen es schlicht nicht
#
# „unbekannt" ist bewusst NICHT „belastbar". Fehlende Information ist keine Erlaubnis.


def split_guete(shares, total_usd=None, trunc=None):
    """Wie belastbar ist der Geld-Split dieses Marktes? REIN/testbar."""
    sh = {k: v for k, v in (shares or {}).items() if isinstance(v, (int, float))}
    if len(sh) < 2:
        return {"art": "leer", "trunc": trunc}
    summe = float(sum(sh.values()))
    if summe <= 0:
        return {"art": "leer", "trunc": trunc}
    if len(sh) == 2:
        return {"art": "preis_echo", "trunc": trunc}
    # Zwei Konventionen fuettern dieselbe Funktion: capture() hier friert bereits NORMALISIERTE
    # Anteile ein (Summe 1, kommt fertig aus dem Smartmoney-Feed und ist per Konstruktion
    # vollstaendig), poly_money_broad friert Dollar-Werte aus /holders ein. Eine Summe von ~1 bei
    # einem vierstelligen Marktvolumen kann keine Dollar-Summe sein — daran sind sie sicher zu
    # trennen.
    try:
        tot = float(total_usd or 0)
    except (TypeError, ValueError):
        tot = 0.0
    if abs(summe - 1.0) < 0.02 and tot > 10:
        return {"art": "belastbar", "trunc": False}
    if trunc is True:
        return {"art": "abgeschnitten", "trunc": True}
    if trunc is False:
        return {"art": "belastbar", "trunc": False}
    return {"art": "unbekannt", "trunc": None}


# ── Liga aus dem Slug lernen (02.09.2026, Lucas-Audit) ────────────────────────
# `SOCCER` war mit 318 von 819 Zeilen (39%) der groesste Eimer der Liga-Tabelle — und traegt
# keinen Liganamen. Die wichtigste Zeile sagte damit nichts. Die Slugs kennen die Liga aber
# (`lal-…`, `elc-…`, `ucl-…`), und wir muessen sie nicht raten: dieselben Praefixe tauchen
# anderswo im Datensatz MIT gesetztem Liga-Label auf. Also lernen wir die Zuordnung aus den
# eigenen Daten statt aus einer handgepflegten Liste, die still veraltet.
#
# Zwei Sicherungen, damit aus dem Lernen kein Raten wird: mindestens LIGA_MIN_BELEGE Belege und
# eine klare Mehrheit. Was das nicht erfuellt, bleibt getrennt, aber unbenannt ("SOCCER:MEX") —
# getrennt und ehrlich ist besser als zusammengeworfen oder falsch benannt.
LIGA_GENERISCH = {"SOCCER", "FOOTBALL", ""}
LIGA_MIN_BELEGE = 3
LIGA_MIN_ANTEIL = 0.6


def _slug_praefix(key):
    t = str(key or "").split("-")
    return t[0].lower() if t and t[0] else ""


def liga_lernen(eintraege):
    """{praefix: LIGA} aus allen Eintraegen mit spezifischem Liga-Label. REIN/testbar.

    `eintraege` ist iterierbar ueber (key, label). Nur Praefixe mit genug Belegen und klarer
    Mehrheit werden gelernt.
    """
    zaehler = {}
    for key, lg in eintraege:
        lg = str(lg or "").upper()
        if not lg or lg in LIGA_GENERISCH:
            continue
        pre = _slug_praefix(key)
        if not pre:
            continue
        zaehler.setdefault(pre, {})
        zaehler[pre][lg] = zaehler[pre].get(lg, 0) + 1
    out = {}
    for pre, c in zaehler.items():
        gesamt = sum(c.values())
        top, n = max(c.items(), key=lambda kv: kv[1])
        if n >= LIGA_MIN_BELEGE and n / gesamt >= LIGA_MIN_ANTEIL:
            out[pre] = top
    return out


def liga_label(key, league, gelernt=None):
    """Das Liga-Label fuer eine Zeile — spezifisch, wenn es eins gibt. REIN/testbar."""
    lg = str(league or "").upper()
    if lg and lg not in LIGA_GENERISCH:
        return lg
    pre = _slug_praefix(key)
    if not pre:
        return lg or None
    gel = (gelernt or {}).get(pre)
    if gel:
        return gel
    return (lg or "SOCCER") + ":" + pre.upper()


# 02.09.2026 (Lucas-Audit): seit der Güte-Schranke werden nur noch Märkte gewertet, deren Split
# überhaupt etwas anderes sagen kann als der Preis — statt 1.426 sind das aktuell 27. Auf so einer
# Stichprobe ist ein Brier-Vergleich ein Punktschätzer, und ein Punktschätzer ist kein Beleg.
# Darum bekommt das Urteil eine Mindest-Stichprobe, global wie je Liga. Darunter steht „noch kein
# Urteil" — nicht „gleichauf", denn gleichauf wäre eine Aussage.
URTEIL_MIN_N = 30          # global
URTEIL_MIN_N_LIGA = 20     # je Liga


def _verdict(bm, bp):
    """Brier-Vergleich → Urteil. Niedriger = besser; Marge, damit Rauschen nichts auslöst."""
    if bm < bp - 0.01:
        return "geld_schaerfer"   # Geld sagt mehr als der Preis → echtes Signal
    if bm > bp + 0.01:
        return "preis_besser"     # Geld schlechter als Preis → dummes Geld, faden ok
    return "gleichauf"            # Geld schon im Preis → kein Zusatznutzen


def evaluate(frozen: dict, results: dict, min_odds: float = 1.0, leagues: dict | None = None) -> dict:
    """Eingefrorene Geld-/Preis-Verteilungen gegen den Ausgang. REIN.

    results:  {matchKey: "home"|"draw"|"away"}  (Gewinner-Ausgang)
    min_odds: nur Märkte werten, deren Favorit MINDESTENS diese Quote hat (Lucas: „1.1 hat logo
              öfter recht — nimm min 1.35"). Ein Favorit mit Quote < min_odds ist zu klar, um
              etwas über die Klugheit der Masse auszusagen. Default 1.0 = kein Filter.
              Zusätzlich: pro Liga aufgeschlüsselt (byLeague), wenn die Einträge ein `league`-Tag
              tragen — „wo hat die Masse mehr recht?".
    leagues:  {matchKey: Liga-Label} — Fallback für eingefrorene Einträge OHNE `league`-Feld.
              25.08.2026 (Audit-Befund 16): der Producer schrieb das Feld nie, also war byLeague
              per Konstruktion immer leer. Die Liga kommt jetzt beim Auswerten aus den Fixtures
              dazu — damit wird auch die BEREITS eingefrorene Historie rückwirkend nutzbar."""
    fav_prob_cap = 1.0 / max(min_odds, 1e-9)   # Favorit-Wahrscheinlichkeit darüber = zu klar
    # 02.09.2026: Praefix→Liga aus dem GANZEN eingefrorenen Bestand lernen, nicht nur aus den
    # gewerteten Zeilen — sonst kennt die Zuordnung genau die Ligen nicht, die sie aufloesen soll.
    _gelernt = liga_lernen(((k, (v or {}).get("league") or (leagues or {}).get(k))
                            for k, v in (frozen or {}).items() if isinstance(v, dict)))
    n = 0
    money_hit = price_hit = 0
    brier_money = brier_price = 0.0
    disagree = {"n": 0, "moneyWon": 0, "priceWon": 0, "neither": 0}
    rows = []
    by_league = {}
    # 02.09.2026 (Lucas-Audit): mitschreiben, WARUM ein Markt nicht gewertet wurde. Ein Urteil,
    # das auf einem Bruchteil der Maerkte steht, muss sagen, wie gross der Bruchteil war.
    guete = {"belastbar": 0, "preis_echo": 0, "abgeschnitten": 0, "unbekannt": 0, "leer": 0}

    for key, f in (frozen or {}).items():
        winner = results.get(key)
        shares_d, prices_d = f.get("shares") or {}, f.get("prices") or {}
        # Ausgänge outcome-agnostisch aus den Daten ableiten (home/draw/away ODER Teamnamen).
        keys = [k for k in set(shares_d) | set(prices_d)
                if isinstance((shares_d.get(k) if shares_d.get(k) is not None else prices_d.get(k)), (int, float))]
        if winner not in keys:
            continue
        mp = _norm(shares_d, keys)
        pp = _norm(prices_d, keys)
        if not mp or not pp:
            continue
        if max(pp.values()) > fav_prob_cap:
            continue                       # Favorit zu klar (Quote < min_odds) → nicht aussagekräftig

        # 02.09.2026 (Lucas-Audit „Großes Geld"): Nur Maerkte werten, deren Geld-Split ueberhaupt
        # etwas anderes sagen KANN als der Preis.
        #   · preis_echo (2 Ausgaenge): Geld-Anteil ist rechnerisch der Preis. Beide gegeneinander
        #     zu messen ist keine Messung, sondern eine Tautologie — sie zieht das Gesamturteil
        #     mechanisch Richtung „gleichauf" und verwaessert die Maerkte, wo es zaehlt.
        #   · abgeschnitten: mindestens eine Halter-Liste war nicht zu Ende. Der Split ist dann
        #     unvollstaendig, und das Fehlende sitzt nicht zufaellig verteilt.
        #   · unbekannt: erfasst, bevor der Abruf die Vollstaendigkeit mitschrieb. Nichtwissen
        #     ist keine Erlaubnis — solche Zeilen zaehlen mit, aber sie urteilen nicht.
        g = split_guete(shares_d, f.get("totalUsd"), (f.get("splitGuete") or {}).get("trunc"))
        guete[g["art"]] = guete.get(g["art"], 0) + 1
        if g["art"] != "belastbar":
            continue

        n += 1
        onehot = {k: (1.0 if k == winner else 0.0) for k in keys}
        bm_i = sum((mp[k] - onehot[k]) ** 2 for k in keys)
        bp_i = sum((pp[k] - onehot[k]) ** 2 for k in keys)
        brier_money += bm_i
        brier_price += bp_i

        money_fav = max(keys, key=lambda k: mp[k])
        price_fav = max(keys, key=lambda k: pp[k])
        m_ok, p_ok = (money_fav == winner), (price_fav == winner)
        money_hit += m_ok
        price_hit += p_ok
        if money_fav != price_fav:
            disagree["n"] += 1
            disagree["moneyWon" if m_ok else "priceWon" if p_ok else "neither"] += 1

        lg = liga_label(key, f.get("league") or (leagues or {}).get(key), _gelernt)
        if lg:
            b = by_league.setdefault(lg, {"n": 0, "moneyHit": 0, "bm": 0.0, "bp": 0.0})
            b["n"] += 1; b["moneyHit"] += m_ok; b["bm"] += bm_i; b["bp"] += bp_i

        rows.append({"key": key, "league": lg, "winner": winner,
                     "moneyFav": money_fav, "priceFav": price_fav,
                     "moneyShare": round(mp[money_fav], 3), "priceProb": round(pp[price_fav], 3),
                     "moneyOK": m_ok, "priceOK": p_ok, "totalUsd": f.get("totalUsd")})

    if n == 0:
        return {"n": 0, "verdict": "zu wenig Daten", "minOdds": min_odds, "byLeague": [],
                "guete": guete}

    bm, bp = brier_money / n, brier_price / n
    league_rows = []
    for lg, b in by_league.items():
        if b["n"] < URTEIL_MIN_N_LIGA:
            continue                       # zu dünn für ein Liga-Urteil
        lbm, lbp = b["bm"] / b["n"], b["bp"] / b["n"]
        league_rows.append({"league": lg, "n": b["n"], "moneyHitRate": round(b["moneyHit"] / b["n"], 3),
                            "brierMoney": round(lbm, 4), "brierPrice": round(lbp, 4),
                            "verdict": _verdict(lbm, lbp)})
    league_rows.sort(key=lambda r: r["brierPrice"] - r["brierMoney"], reverse=True)  # wo Geld am meisten schlägt

    return {
        "n": n,
        "minOdds": min_odds,
        "moneyHitRate": round(money_hit / n, 3),
        "priceHitRate": round(price_hit / n, 3),
        "brierMoney": round(bm, 4),
        "brierPrice": round(bp, 4),
        "disagree": disagree,
        "verdict": _verdict(bm, bp) if n >= URTEIL_MIN_N else "zu wenig Daten",
        "urteilMinN": URTEIL_MIN_N,
        "byLeague": league_rows,
        "guete": guete,
        "rows": sorted(rows, key=lambda r: -(r.get("totalUsd") or 0))[:40],
    }


# ── Ergebnis-Lookup ──────────────────────────────────────────────────────────

def results_lookup(data: dict) -> dict:
    """{homeId-awayId: winner} aus den aufgelösten Fixtures (groups + koFixtures)."""
    out = {}
    fixtures = []
    for g in (data.get("groups") or {}).values():
        fixtures += g.get("fixtures") or []
    fixtures += data.get("koFixtures") or []
    for fx in fixtures:
        r = fx.get("result") or {}
        if r.get("status") not in ("FT", "AET", "PEN"):
            continue
        hs, as_ = r.get("home_score"), r.get("away_score")
        if hs is None or as_ is None:
            continue
        winner = "home" if hs > as_ else "away" if as_ > hs else "draw"
        out[f"{fx.get('home')}-{fx.get('away')}"] = winner
    return out


def leagues_lookup(data: dict, valid=None) -> dict:
    """{homeId-awayId: Liga-Code} aus den Fixtures. Der Gruppenschlüssel IST bei den
    Klub-Datensätzen die Liga (ENG/ESP/GER/ITA/FRA, MLS).

    `valid` (optional): nur diese Codes werden als Liga akzeptiert. Ohne den Filter würden bei
    der WM die Gruppen A–H als „Ligen“ durchgehen — ein falsches Label ist schlimmer als keines.
    """
    out = {}
    for gname, g in (data.get("groups") or {}).items():
        if valid is not None and gname not in valid:
            continue
        for fx in (g.get("fixtures") or []):
            h, a = fx.get("home"), fx.get("away")
            if h and a:
                out[f"{h}-{a}"] = gname
    return out


_LOAD_FAILED: set[str] = set()   # 25.08.2026 (Audit): „fehlt“ und „kaputt“ sind NICHT dasselbe


def _load(name):
    """Lädt eine JSON-Datei. Ein LESE-FEHLER wird gemerkt, damit niemand die Datei danach
    überschreibt — der eingefrorene Schluss-Snapshot ist nicht rekonstruierbar."""
    try:
        d = json.loads((BASE / name).read_text(encoding="utf-8"))
        _LOAD_FAILED.discard(name)
        return d
    except FileNotFoundError:
        _LOAD_FAILED.discard(name)       # noch nie geschrieben — das ist der Normalfall am Anfang
        return {}
    except Exception as e:
        print(f"\u26a0\ufe0f {name} ist da, aber nicht lesbar ({e}) — wird NICHT überschrieben.")
        _LOAD_FAILED.add(name)
        return {}


def main() -> int:
    sm = _load(D.file("wm_poly_smartmoney.json", "liga_poly_smartmoney.json").name)
    pr = _load(D.file("wm_poly_prices.json", "liga_poly_prices.json").name)
    data = _load(D.data_file().name)

    close_file = D.file("wm_poly_money_close.json", "liga_poly_money_close.json")
    prev = _load(close_file.name)
    frozen = capture(sm, pr, prev) if sm else prev
    if close_file.name in _LOAD_FAILED:
        # Der alte Stand ist da, nur unlesbar. Ihn jetzt mit einem Teil-Stand zu ersetzen wäre
        # der eigentliche Datenverlust — lieber diesen Lauf ohne Einfrieren beenden.
        print(f"\u26d4 {close_file.name} nicht lesbar — Schluss-Snapshot bleibt unangetastet.")
    else:
        write_json_atomic(close_file, frozen, indent=1)

    rep = evaluate(frozen, results_lookup(data),
                   leagues=leagues_lookup(data, set(D.leagues())))
    rep["dataset"] = D.active_dataset()
    rep["generatedAt"] = _now().isoformat()
    out = D.file("wm_poly_money_accuracy.json", "liga_poly_money_accuracy.json")
    write_json_atomic(out, rep, indent=1)

    print(f"=== Liegt das Poly-Geld richtig? ({rep['dataset'].upper()}) ===")
    print(f"Eingefroren: {len(frozen)} Märkte · aufgelöst: {rep['n']}")
    if rep["n"]:
        print(f"Geld-Mehrheit trifft: {rep['moneyHitRate']*100:.0f}%  ·  "
              f"Preis-Favorit trifft: {rep['priceHitRate']*100:.0f}%")
        print(f"Brier Geld {rep['brierMoney']} vs. Preis {rep['brierPrice']}  →  {rep['verdict']}")
        d = rep["disagree"]
        if d["n"]:
            print(f"Uneinig ({d['n']}): Geld gewann {d['moneyWon']}, Preis {d['priceWon']}")
    print(f"💾 {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
