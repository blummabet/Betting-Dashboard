#!/usr/bin/env python3
"""compute_streaks.py — Serien-/Streak-Content (28.06.2026, Lucas).

Aktive Team-Serien aus den Form-Sequenzen (fetch_wm_form: o25Seq/bttsSeq, most-recent-first):
  • Über 2,5 / Unter 2,5 Tore in Folge
  • Beide treffen (Ja/Nein) in Folge

EHRLICH: eine Serie allein ist KEIN Edge (Gambler's Fallacy). Darum bekommt jede Serie einen
daten-basierten **Continuation-Indikator** aus der Grundrate (over25Rate/bttsRate über ~15 Spiele):
stützt die Grundrate die Serie → „intakt"; läuft die Serie gegen die Grundrate → „wackelt"
(eher Zufall/Regression). So wird aus Content ein begründeter Hinweis.

Reine Content-Schicht: NICHT im P&L/Lern-Loop. Dataset-aware. Schreibt {wm_,liga_}streaks.json.
Ecken-Serien folgen, sobald Ecken pro Spiel erfasst sind (cornersForm hat nur Schnitte).
Lauf 1×/Woche (engl. Woche 2×) nach fetch_wm_form.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone

import cocobet_dataset as D

OUT = D.file("wm_streaks.json", "liga_streaks.json")

MIN_LEN = 3     # ab dieser Länge zeigen
STRONG_LEN = 5  # ab hier „starke" Serie (für die Cards-Sektion)

# 04.07.2026 (Lucas: „Streaks zu starken Zahlen machen"): xG-Deckung. Eine Über-Serie, deren
# letzte Spiele auch per xG über der Linie lagen, ist echtes Team-Profil; eine aus Glückstoren
# (xG unter der Linie) ist ein Regressions-Kandidat. xgBacked fließt ins streak_momentum-Signal
# (ungedeckte Serien werden dort stark gedämpft). Nur für Tor-Total-Serien (over25/under25).
_OU_TOTAL_LINE = 2.5


def _team_xg_totals(wm: dict) -> dict:
    """{teamId: [xgTotal, ...] most-recent-first} aus gespielten Fixtures (Gruppe + K.-o.).
    xgTotal = home+away xG des Spiels (result.stats.xgTotal, real oder xgSim-Fallback)."""
    games = []  # (date, teamId, xgTotal)
    def _scan(fx):
        r = (fx or {}).get("result") or {}
        st = r.get("stats") or {}
        xt = st.get("xgTotal")
        if xt is None:
            hx, ax = st.get("homeXg"), st.get("awayXg")
            xt = (hx + ax) if isinstance(hx, (int, float)) and isinstance(ax, (int, float)) else None
        if xt is None:
            return
        d = fx.get("date") or (fx.get("kickoff") or "")[:10] or ""
        for tid in (fx.get("home"), fx.get("away")):
            if tid:
                games.append((d, str(tid), float(xt)))
    for g in (wm.get("groups") or {}).values():
        for fx in (g.get("fixtures") or []):
            _scan(fx)
    for fx in (wm.get("koFixtures") or []):
        _scan(fx)
    out: dict = {}
    for d, tid, xt in sorted(games, key=lambda x: x[0], reverse=True):
        out.setdefault(tid, []).append(xt)
    return out


def _xg_backed(streak_type: str, xg_window: list) -> bool | None:
    """Ist die Serie von xG gedeckt? True/False für over25/under25, sonst None (n/a)."""
    if not xg_window:
        return None
    if streak_type == "over25":
        over = sum(1 for x in xg_window if x > _OU_TOTAL_LINE)
        return over / len(xg_window) >= 0.5
    if streak_type == "under25":
        under = sum(1 for x in xg_window if x < _OU_TOTAL_LINE)
        return under / len(xg_window) >= 0.5
    return None

# Tor-/BTTS-/Team-Märkte aus form (mit venueSeq). (key, seq-Feld, Ziel, Markt, Grundrate, target_false)
FORM_MARKETS = [
    ("over25",     "o25Seq",    True,  "Über 2,5 Tore",        "over25Rate",     False),
    ("under25",    "o25Seq",    False, "Unter 2,5 Tore",       "over25Rate",     True),
    ("bttsYes",    "bttsSeq",   True,  "Beide Teams treffen",  "bttsRate",       False),
    ("bttsNo",     "bttsSeq",   False, "Beide treffen — Nein", "bttsRate",       True),
    ("scored",     "scoredSeq", True,  "Team trifft",          "scoredRate",     False),
    ("cleanSheet", "csSeq",     True,  "Zu null",              "cleanSheetRate", False),
    # 25.07.2026 (Lucas: „5 Siege in Folge sollten die 1X2 beeinflussen"): Ergebnis-Serien.
    ("win",        "wonSeq",      True, "Sieg-Serie",           "winRate",        False),
    ("unbeaten",   "unbeatenSeq", True, "Ungeschlagen",         "unbeatenRate",   False),
]


def _lead_run(seq: list, target: bool) -> int:
    """Länge der führenden (jüngsten) Serie, in der seq[i] == target."""
    n = 0
    for v in (seq or []):
        if bool(v) == target:
            n += 1
        else:
            break
    return n


# Matchup-Gewichtung (29.06.2026, Lucas: „lebendige" Serien): Status aus Eigentendenz UND
# nächstem Gegner. Eigene Serie ist die Basis (höheres Gewicht), Gegner moduliert.
MATCHUP_OWN_W = 0.6
MATCHUP_OPP_W = 0.4


def _state(underlying: float, length: int) -> str:
    """Status-Schwellen für eine Stütz-Rate (0..1)."""
    if underlying >= 0.60:
        return "intakt"
    if underlying <= 0.45 or (length >= 8 and underlying < 0.55):
        return "wackelt"
    return "neutral"


def _continuation(rate, target_is_false: bool, length: int) -> dict:
    """Eigentendenz: Stützt die eigene Grundrate die Serie? rate = Roh-Rate (z.B. over25Rate)."""
    if rate is None:
        return {"state": "neutral", "ratePct": None, "label": "zu wenig Daten"}
    underlying = (1.0 - rate) if target_is_false else rate   # Rate FÜR die Serien-Richtung
    pct = round(underlying * 100)
    return {"state": _state(underlying, length), "ratePct": pct, "label": f"Eigentendenz {pct}%"}


def _matchup_continuation(cont: dict, opp_pct, target_is_false: bool, length: int) -> tuple:
    """Status aus Eigentendenz + Gegner-Stütze. opp_pct = Roh-Gegnermetrik (%, aus _opp_rate_pct).
    Gibt (continuation_dict, oppSupportPct, matchupPct) zurück. Ohne Gegnerdaten = Eigentendenz pur."""
    own = cont.get("ratePct")
    if own is None or opp_pct is None:
        return cont, None, None
    own_f = own / 100.0
    # Gegner-Stütze FÜR die Serien-Richtung: bei Under/Nein-Serien (target_false) zählt das Gegenteil.
    opp_support = (1.0 - opp_pct / 100.0) if target_is_false else (opp_pct / 100.0)
    combined = MATCHUP_OWN_W * own_f + MATCHUP_OPP_W * opp_support
    state = _state(combined, length)
    opp_support_pct = round(opp_support * 100)
    matchup_pct = round(combined * 100)
    label = f"Eigen {own}% + Gegner {opp_support_pct}% → {matchup_pct}%"
    return ({"state": state, "ratePct": own, "label": label}, opp_support_pct, matchup_pct)


def _filter_venue(seq, venue_seq, venue):
    """Sequenz auf Heim ('H') / Auswärts ('A') filtern (Reihenfolge erhalten). 'all' = ganze Reihe.
    Ohne/fehljustierte venue_seq → ganze Reihe (Fallback)."""
    if venue == "all" or not venue_seq or len(venue_seq) != len(seq):
        return seq
    return [seq[i] for i in range(len(seq)) if venue_seq[i] == venue]


def _next_fixtures(wm):
    """Team-ID → nächstes anstehendes Spiel {oppId, oppName, atHome, date} (frühestes ab heute)."""
    from datetime import date as _date
    today = _date.today().isoformat()
    teams = {}
    for g in (wm.get("groups") or {}).values():
        for t in (g.get("teams") or []):
            teams[str(t.get("id"))] = t.get("name") or str(t.get("id"))
    nf = {}

    def _consider(home, away, d, ko, pkey):
        for tid, opp, at_home in ((home, away, True), (away, home, False)):
            if not tid:
                continue
            prev = nf.get(str(tid))
            if not prev or ko < prev["_ko"]:
                nf[str(tid)] = {"oppId": str(opp), "oppName": teams.get(str(opp), str(opp)),
                                "atHome": at_home, "date": d, "_ko": ko, "pickKey": pkey}

    for gkey, g in (wm.get("groups") or {}).items():
        for fx in (g.get("fixtures") or []):
            d = fx.get("date") or ""
            if not d or d < today:
                continue
            ko = fx.get("kickoff") or (d + "T00:00:00Z")
            md = fx.get("matchday")
            home, away = fx.get("home"), fx.get("away")
            # Pick-Key wie in wm["picks"]: "GROUP-MD-HOME-AWAY" (Stufe 2: Signale des Spiels).
            pkey = f"{gkey}-{md}-{home}-{away}" if md is not None else None
            _consider(home, away, d, ko, pkey)

    # 04.07.2026 (Lucas: „Streak-Card kommt immer nach dem Spiel"): K.-o.-Spiele liegen in
    # koFixtures, nicht in groups. Ohne sie fand in der K.-o.-Phase KEIN Team ein „nächstes Spiel"
    # → jede Serien-Card verlor Gegner + Datum → las sich wie ein Nachbericht statt Vorschau.
    for kf in (wm.get("koFixtures") or []):
        home, away = kf.get("home"), kf.get("away")
        if not (home and away):
            continue   # unaufgelöstes Bracket-Spiel
        _ko = kf.get("kickoff") or ""
        d = kf.get("date") or (_ko[:10] if _ko else "")
        if not d or d < today:
            continue
        rnd = kf.get("round")
        pkey = f"KO-{rnd}-{home}-{away}"
        _consider(home, away, d, _ko or (d + "T00:00:00Z"), pkey)

    for v in nf.values():
        v.pop("_ko", None)
    return nf


def _opp_rate_pct(key, opp_id, form, cf):
    """Komplementäre Grundrate des nächsten Gegners (adamchoi-Paarung) in %."""
    of = form.get(str(opp_id)) or {}
    oc = cf.get(str(opp_id)) or {}
    if key in ("over25", "under25"):
        r = of.get("over25Rate")
    elif key in ("bttsYes", "bttsNo"):
        r = of.get("bttsRate")
    elif key == "scored":                      # Team trifft → Gegner kassiert (1 − clean sheet)
        r = of.get("cleanSheetRate"); r = (1.0 - r) if r is not None else None
    elif key == "cleanSheet":                  # zu null → Gegner trifft nicht (1 − scored)
        r = of.get("scoredRate"); r = (1.0 - r) if r is not None else None
    elif key in ("cornersOver", "cornersUnder"):
        r = oc.get("overLineRate")
    elif key == "cards":
        r = oc.get("cardOverRate")
    elif key == "win":                         # 25.07.2026: Sieg-Serie → Gegner verliert oft (1 − ungeschlagen)
        r = of.get("unbeatenRate"); r = (1.0 - r) if r is not None else None
    elif key == "unbeaten":                    # ungeschlagen → Gegner gewinnt selten (1 − Siegrate)
        r = of.get("winRate"); r = (1.0 - r) if r is not None else None
    else:
        r = None
    return round(r * 100) if r is not None else None


# ── Stufe 2 (29.06.2026, Lucas): Signale/Linie des NÄCHSTEN Spiels → Status lebt mit ──────────
# Bepickt sind nur O/U-2,5 + BTTS → nur diese Streak-Märkte koppeln an die Engine. Der Pick des
# nächsten Spiels bestätigt die Serie (gleiche Richtung) oder widerspricht ihr (Gegenrichtung).
_STREAK_PICK_FAMILY = {"over25": "ou", "under25": "ou", "bttsYes": "btts", "bttsNo": "btts"}
_STREAK_PICK_DIR    = {"over25": "over", "under25": "under", "bttsYes": "yes", "bttsNo": "no"}
SIGNAL_MIN_FIRE = 2   # so viele bestätigende Signale → Status-Overlay


def _pick_family_dir(market_label):
    """Pick-Markt-Label → (Familie, Richtung). Nur O/U + BTTS."""
    m = (market_label or "").lower()
    if "über" in m or "unter" in m or "over" in m or "under" in m:
        return ("ou", "under" if ("unter" in m or "under" in m) else "over")
    if "beide" in m or "btts" in m or "both teams" in m:
        return ("btts", "no" if ("nein" in m or " no" in m or m.endswith("no")) else "yes")
    return (None, None)


def _next_match_signal(picks, pick_key, streak_type):
    """Im nächsten Spiel den Pick zur Streak-Markt-Familie finden: BESTÄTIGT die Serie (gleiche
    Richtung) oder WIDERSPRICHT (Gegenrichtung)? Returns dict {state,count,conviction,names,market} | None."""
    fam = _STREAK_PICK_FAMILY.get(streak_type)
    if not fam or not pick_key:
        return None
    want = _STREAK_PICK_DIR.get(streak_type)
    for p in (picks.get(pick_key) or []):
        if not isinstance(p, dict) or p.get("verdict") not in ("BET", "ABWÄGEN"):
            continue
        pf, pd = _pick_family_dir(p.get("market"))
        if pf != fam:
            continue
        names = [s.get("name") for s in (p.get("signals") or [])
                 if isinstance(s, dict) and s.get("name") and (s.get("weighted_score") or 0)]
        return {
            "state": "confirm" if pd == want else "contradict",
            "count": int(p.get("signalCountPos") or 0),
            "conviction": p.get("convictionScore"),
            "names": names[:6],
            "market": p.get("market"),
        }
    return None


def build_streaks(wm: dict) -> dict:
    form = wm.get("form") or {}
    cf = wm.get("cornersForm") or {}
    lookup = {}
    for gkey, g in (wm.get("groups") or {}).items():
        gname = g.get("name") or gkey
        for t in (g.get("teams") or []):
            lookup[str(t.get("id"))] = {"team": t.get("name") or str(t.get("id")),
                                        "league": gkey, "leagueName": gname,
                                        "flag": t.get("flag") or ""}
    next_fx = _next_fixtures(wm)
    picks = wm.get("picks") or {}   # Stufe 2: Signale/Linie des nächsten Spiels
    xg_totals = _team_xg_totals(wm)  # 04.07.2026: xG-Deckung pro Team (most-recent-first)
    streaks = []

    def _emit(tid, seq, venue_seq, target, market, rate, target_false, key):
        meta = lookup.get(str(tid)) or {"team": str(tid), "league": "?", "leagueName": "?", "flag": ""}
        _has_venue = bool(venue_seq) and len(venue_seq) == len(seq)
        for venue in ("all", "H", "A"):
            if venue != "all" and not _has_venue:
                continue   # ohne venueSeq keine Heim/Auswärts-Duplikate
            fseq = _filter_venue(seq, venue_seq, venue)
            length = _lead_run(fseq, target)
            if length < MIN_LEN:
                continue
            cont = _continuation(rate, target_false, length)
            # seqViz: letzte ~8 Spiele dieser Richtung als Punkte (True=Treffer), most-recent-first.
            # Führende True = die aktuelle Serie, das erste False zeigt, wo sie begann.
            seq_viz = [bool(x) == target for x in fseq[:8]]
            # xG-Deckung nur für Tor-Total-Serien (over25/under25); Fenster = die aktive Serie.
            xgb = _xg_backed(key, (xg_totals.get(str(tid)) or [])[:length])
            s = {
                "teamId": str(tid), "team": meta["team"], "flag": meta.get("flag", ""),
                "league": meta["league"], "leagueName": meta["leagueName"],
                "type": key, "market": market, "length": length, "venue": venue,
                "strong": length >= STRONG_LEN, "continuation": cont,
                "ratePct": cont["ratePct"], "seq": seq_viz, "xgBacked": xgb,
            }
            nf = next_fx.get(str(tid))
            if nf:
                opp_pct = _opp_rate_pct(key, nf["oppId"], form, cf)
                s["next"] = {"oppId": nf["oppId"], "oppName": nf["oppName"], "atHome": nf["atHome"],
                             "date": nf["date"], "oppRatePct": opp_pct}
                # Stufe 1 — lebendiger Status: Eigentendenz × nächster Gegner (29.06.2026, Lucas).
                mcont, opp_support_pct, matchup_pct = _matchup_continuation(cont, opp_pct, target_false, length)
                s["continuation"] = mcont
                if opp_support_pct is not None:
                    s["oppSupportPct"] = opp_support_pct   # Gegner-Stütze FÜR die Richtung (für 2. Balken-Farbe)
                    s["matchupPct"] = matchup_pct
                # Stufe 2 — Signale/Linie des nächsten Spiels überschreiben den Status, wenn sie
                # deutlich (≥SIGNAL_MIN_FIRE) bestätigen oder widersprechen.
                sig = _next_match_signal(picks, nf.get("pickKey"), key)
                if sig:
                    s["signalInfo"] = sig
                    if sig["count"] >= SIGNAL_MIN_FIRE:
                        if sig["state"] == "confirm":
                            s["continuation"]["state"] = "intakt"
                            s["continuation"]["label"] += " · Signale bestätigen"
                        elif sig["state"] == "contradict":
                            s["continuation"]["state"] = "wackelt"
                            s["continuation"]["label"] += " · Linie/Signale dagegen"
            streaks.append(s)

    # Tor-/BTTS-/Team-Märkte (form, venueSeq)
    for tid, f in form.items():
        if not isinstance(f, dict):
            continue
        vseq = f.get("venueSeq")
        for key, seqfield, target, market, ratefield, tf in FORM_MARKETS:
            seq = f.get(seqfield)
            if seq:
                _emit(tid, seq, vseq, target, market, f.get(ratefield), tf, key)

    # Ecken + Karten (cornersForm)
    for tid, c in cf.items():
        if not isinstance(c, dict):
            continue
        cline = c.get("cornerLine", 9.5)
        cl_s = str(cline).replace(".", ",")
        cseq, cvenue, crate = c.get("cornerOverSeq"), c.get("cornerVenueSeq"), c.get("overLineRate")
        if cseq:
            _emit(tid, cseq, cvenue, True,  f"Über {cl_s} Ecken",  crate, False, "cornersOver")
            _emit(tid, cseq, cvenue, False, f"Unter {cl_s} Ecken", crate, True,  "cornersUnder")
        kline = c.get("cardLine", 3.5)
        kl_s = str(kline).replace(".", ",")
        kseq, kvenue, krate = c.get("cardOverSeq"), c.get("cardVenueSeq"), c.get("cardOverRate")
        if kseq:
            _emit(tid, kseq, kvenue, True, f"Über {kl_s} Karten", krate, False, "cards")

    # längste zuerst; bei Gleichstand „intakt" vor dem Rest
    _order = {"intakt": 0, "neutral": 1, "wackelt": 2}
    streaks.sort(key=lambda s: (-s["length"], _order.get(s["continuation"]["state"], 1)))
    return {
        "_meta": {"dataset": D.active_dataset(), "generatedAt": datetime.now(timezone.utc).isoformat(),
                  "minLen": MIN_LEN, "strongLen": STRONG_LEN},
        "streaks": streaks,
    }


def main() -> None:
    wm = json.loads(D.data_file().read_text(encoding="utf-8"))
    out = build_streaks(wm)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    n = len(out["streaks"])
    strong = sum(1 for s in out["streaks"] if s["strong"])
    print(f"✅ Streaks ({D.active_dataset()}): {n} aktive Serien (≥{MIN_LEN}), {strong} stark (≥{STRONG_LEN}) → {OUT.name}")


if __name__ == "__main__":
    main()
