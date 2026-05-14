#!/usr/bin/env python3
"""
generate_match_pages.py
Architecture: 1 shared template (matches/match.html) + 1 JSON per fixture (matches/data/{slug}.json)

Design changes  → edit match.html only (1 file)
Data updates    → only changed JSONs touched
Link format     → matches/match.html?m={slug}

Run: python generate_match_pages.py
"""

import json, os, re, math
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "matches", "data")
os.makedirs(DATA_DIR, exist_ok=True)

def load(name):
    p = os.path.join(BASE, name)
    if not os.path.exists(p): return None
    with open(p, encoding="utf-8") as f: return json.load(f)

picks_list  = load("picks_output.json") or []
prematch    = load("prematch-data.json") or {}
stats_cache = load("stats_cache.json") or {}
poly_raw    = load("polymarket_prices.json") or {}

fixtures_list = prematch.get("fixtures", [])
poly_matches  = poly_raw.get("matches", {})

prematch_idx = {}
for fix in fixtures_list:
    key = f"{fix['homeTeamName']}|{fix['awayTeamName']}"
    prematch_idx[key] = fix

def get_prematch(home, away): return prematch_idx.get(f"{home}|{away}")
def get_stats(league, team):  return stats_cache.get(league, {}).get(team, {})
def get_poly(home, away):
    e = poly_matches.get(f"{home}|{away}")
    return e if (e and e.get("found")) else None

# ─── Utilities ────────────────────────────────────────────────────────────────
def slugify(text):
    text = text.lower()
    for s, d in [("ä","ae"),("ö","oe"),("ü","ue"),("ß","ss"),("á","a"),
                 ("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n"),("ç","c")]:
        text = text.replace(s, d)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")

def sf(v, default=None):
    try: return float(v)
    except: return default

def fmt(v, decimals=2):
    try: return f"{float(v):.{decimals}f}"
    except: return "—"

def initials(name):
    w = name.split()
    return ("".join(x[0] for x in w if x[0].isalpha())[:3] if len(w)>1 else name[:2]).upper()

def kelly_quarter(odds, model_odds):
    try:
        o, m = float(odds), float(model_odds)
        if o<=1 or m<=0: return None
        p=1/m; q=1-p; b=o-1
        return max(0.0, (b*p-q)/b/4)
    except: return None

# ─── AI Text Generator ────────────────────────────────────────────────────────
def generate_ai_text(entry, pmatch, hs, as_):
    home  = entry["home"]
    away  = entry["away"]
    picks = [p for p in entry.get("picks",[]) if p.get("conf") in ("high","medium")]
    odds  = (pmatch or {}).get("odds") or {}
    sentences = []

    # 1. Favorite
    hw = sf(odds.get("hw") or odds.get("pinn_hw"))
    aw = sf(odds.get("aw") or odds.get("pinn_aw"))
    h_elo = sf((hs or {}).get("elo"))
    a_elo = sf((as_ or {}).get("elo"))
    elo_diff = abs(h_elo - a_elo) if h_elo and a_elo else None

    if hw and aw:
        fav, fav_o, dog_o = (home, hw, aw) if hw < aw else (away, aw, hw)
        elo_note = f" (Elo-Differenz: {int(elo_diff)} Punkte)" if elo_diff and elo_diff>=50 else ""
        sentences.append(
            f"{fav} geht als Favorit in diese Partie — Kurs {fmt(fav_o)} "
            f"gegenüber {fmt(dog_o)}{elo_note}."
        )
    else:
        sentences.append(f"{home} empfängt {away} — Analyse auf Basis verfügbarer Daten.")

    # 2. Top pick
    high_p = [p for p in picks if p.get("conf")=="high"]
    top = (high_p or picks)[0] if picks else None
    if top:
        market = top.get("market","")
        o = sf(top.get("odds")); mo = sf(top.get("modelOdds"))
        is_val = top.get("value")=="value"
        if o and mo:
            m_prob = round(100/mo); mk_prob = round(100/o); edge = m_prob - mk_prob
            kf = kelly_quarter(o, mo)
            k_note = f", Quarter-Kelly: {kf*100:.1f}% Einsatz" if kf and kf>0.005 else ""
            v_note = " — rechnerischer Value-Bereich" if is_val else ""
            sentences.append(
                f"Top-Pick: <strong>{market}</strong> @ {fmt(o)} — "
                f"Modell sieht {m_prob}% Wahrscheinlichkeit vs. {mk_prob}% impliziert "
                f"(+{edge} Prozentpunkte Vorteil){v_note}{k_note}."
            )
        elif o:
            sentences.append(f"Top-Pick: <strong>{market}</strong> @ {fmt(o)}.")

    # 3. Sharp line movement
    odds_open = (pmatch or {}).get("odds_open") or {}
    open_hw = sf(odds_open.get("hw") or odds_open.get("pinn_hw_fair"))
    open_aw = sf(odds_open.get("aw") or odds_open.get("pinn_aw_fair"))
    cur_hw = sf(odds.get("hw") or odds.get("pinn_hw"))
    cur_aw = sf(odds.get("aw") or odds.get("pinn_aw"))
    moves = []
    if open_hw and cur_hw and abs(cur_hw-open_hw)/open_hw > 0.03:
        chg = (cur_hw-open_hw)/open_hw*100
        moves.append(f"{home} {fmt(open_hw)}→{fmt(cur_hw)} ({chg:+.1f}%)")
    if open_aw and cur_aw and abs(cur_aw-open_aw)/open_aw > 0.03:
        chg = (cur_aw-open_aw)/open_aw*100
        moves.append(f"{away} {fmt(open_aw)}→{fmt(cur_aw)} ({chg:+.1f}%)")
    if moves:
        sentences.append("Sharps haben die Linie bewegt: " + ", ".join(moves) + ".")

    # 4. H2H / injury
    h2h = (pmatch or {}).get("h2h") or {}
    if h2h.get("games",0) >= 4:
        g=h2h["games"]; hw_r=h2h.get("homeWins",0)/g; aw_r=h2h.get("awayWins",0)/g
        o25=h2h.get("over25Rate",0); btts=h2h.get("bttsRate",0); avg=h2h.get("avgGoals",0)
        notes = []
        if hw_r>=0.65: notes.append(f"{home} dominiert H2H ({int(hw_r*100)}% Siege aus {g} Spielen)")
        elif aw_r>=0.65: notes.append(f"{away} dominiert H2H ({int(aw_r*100)}% Siege aus {g} Spielen)")
        if btts>=0.65: notes.append(f"BTTS in {int(btts*100)}% der Duelle")
        elif o25>=0.65: notes.append(f"Over 2.5 in {int(o25*100)}% der Duelle (∅ {avg:.1f} Tore)")
        elif avg<1.8: notes.append(f"Torarm: ∅ {avg:.1f} Tore/Spiel in {g} Duellen")
        if notes: sentences.append("; ".join(notes) + ".")

    inj = (pmatch or {}).get("injurySummary") or {}
    h_tot = (inj.get("home") or {}).get("total",0)
    a_tot = (inj.get("away") or {}).get("total",0)
    if h_tot>=3 or a_tot>=3:
        parts = []
        if h_tot>=3: parts.append(f"{home} mit {h_tot} Ausfällen")
        if a_tot>=3: parts.append(f"{away} mit {a_tot} Ausfällen")
        sentences.append("Verletzungslage: " + " und ".join(parts) + ".")

    if len(sentences)<2 and picks:
        sentences.append(f"{len(picks)} verwertbare Wett-Winkel mit ausreichender Konfidenz.")

    return " ".join(sentences[:4])

# ─── Build match JSON payload ─────────────────────────────────────────────────
def build_payload(entry, pmatch, hs, as_, poly):
    home        = entry["home"]
    away        = entry["away"]
    league      = entry["league"]
    league_name = entry.get("leagueName", league)
    league_flag = entry.get("leagueFlag", "")
    date_str    = entry.get("date","")
    date_iso    = entry.get("dateIso","")
    match_score = entry.get("matchScore", 0)
    picks       = entry.get("picks",[])
    time_str    = (pmatch or {}).get("time","")
    odds        = (pmatch or {}).get("odds") or {}
    odds_open   = (pmatch or {}).get("odds_open") or {}
    ap          = (pmatch or {}).get("apiPrediction") or {}

    # probabilities
    hw_fair = sf(odds.get("hw_fair") or odds.get("pinn_hw_fair"))
    dr_fair = sf(odds.get("dr_fair") or odds.get("pinn_dr_fair"))
    aw_fair = sf(odds.get("aw_fair") or odds.get("pinn_aw_fair"))
    if hw_fair and dr_fair and aw_fair:
        tot = 1/hw_fair + 1/dr_fair + 1/aw_fair
        h_prob = round(100/hw_fair/tot)
        d_prob = round(100/dr_fair/tot)
        a_prob = round(100/aw_fair/tot)
    else:
        h_prob = ap.get("pctHome") or 35
        d_prob = ap.get("pctDraw") or 25
        a_prob = ap.get("pctAway") or 40

    # picks
    picks_out = []
    for p in picks:
        if p.get("conf") not in ("high","medium"): continue
        o = sf(p.get("odds")); mo = sf(p.get("modelOdds"))
        kf = kelly_quarter(o, mo)
        picks_out.append({
            "market":    p.get("market",""),
            "icon":      p.get("icon","🎯"),
            "conf":      p.get("conf",""),
            "odds":      fmt(o) if o else "—",
            "modelOdds": fmt(mo) if mo else None,
            "kelly":     round(kf*100,1) if kf and kf>0.005 else None,
            "value":     p.get("value")=="value",
            "modelProb": round(100/mo) if mo else None,
            "mktProb":   round(100/o) if o else None,
        })

    # stats bars
    def sbar(label, hv, av, higher_better=True, fmt_fn=None):
        fmt_fn = fmt_fn or (lambda x: f"{x:.2f}" if isinstance(x,float) else str(x))
        hf = sf(hv); af = sf(av)
        if hf is None and af is None: return None
        tot = (hf or 0) + (af or 0)
        h_bar = round((hf or 0)/tot*100) if tot>0 else 50
        h_win = hf is not None and af is not None and ((higher_better and hf>af) or (not higher_better and hf<af))
        a_win = hf is not None and af is not None and not h_win and hf!=af
        return {
            "label": label,
            "homeVal": fmt_fn(hv) if hv is not None else "—",
            "awayVal": fmt_fn(av) if av is not None else "—",
            "homeBar": h_bar, "awayBar": 100-h_bar,
            "homeWin": h_win, "awayWin": a_win,
        }

    pct_fmt = lambda x: f"{round(float(x)*100)}%" if x is not None else "—"
    stats_bars = [x for x in [
        sbar("xG (Heim / Ausw)",       (hs or {}).get("xG_home"),        (as_ or {}).get("xG_away")),
        sbar("xGA (niedriger = besser)",(hs or {}).get("xGA_home"),       (as_ or {}).get("xGA_away"), False),
        sbar("Siegquote",               (hs or {}).get("homeWinRate"),     (as_ or {}).get("awayWinRate"),  fmt_fn=pct_fmt),
        sbar("Clean Sheets",            (hs or {}).get("cleanSheetHome"),  (as_ or {}).get("cleanSheetAway"), fmt_fn=pct_fmt),
        sbar("Elo",                     (hs or {}).get("elo"),             (as_ or {}).get("elo"),
             fmt_fn=lambda x: str(int(x)) if x else "—"),
        sbar("Formation",               (hs or {}).get("formation"),       (as_ or {}).get("formation"),
             fmt_fn=lambda x: str(x) if x else "—"),
    ] if x]

    # odds movement
    def ocard(label, open_v, cur_v):
        if cur_v is None: return None
        o = sf(open_v); c = sf(cur_v)
        move = "—"; dir_ = "neutral"
        if o and c:
            chg = (c-o)/o*100
            if abs(chg)>=0.5:
                dir_ = "up" if chg>0 else "down"
                move = f"{'↑' if chg>0 else '↓'} {chg:+.1f}%"
            else:
                move = "→ stabil"
        return {"label":label,"open":fmt(o) if o else None,"cur":fmt(c),"move":move,"dir":dir_}

    open_hw = sf(odds_open.get("hw") or odds_open.get("pinn_hw_fair"))
    open_dr = sf(odds_open.get("dr") or odds_open.get("pinn_dr_fair"))
    open_aw = sf(odds_open.get("aw") or odds_open.get("pinn_aw_fair"))
    odds_cards = [x for x in [
        ocard("1 Heimsieg",   open_hw, sf(odds.get("hw") or odds.get("pinn_hw"))),
        ocard("X Unentsch.",  open_dr, sf(odds.get("dr") or odds.get("pinn_dr"))),
        ocard("2 Auswärts",   open_aw, sf(odds.get("aw") or odds.get("pinn_aw"))),
        ocard("Over 2.5",     None,    sf(odds.get("o25"))),
        ocard("Under 2.5",    None,    sf(odds.get("u25"))),
    ] if x]

    # h2h
    h2h_raw = (pmatch or {}).get("h2h") or {}
    h2h = None
    if h2h_raw.get("games"):
        g=h2h_raw["games"] or 1
        hw=h2h_raw.get("homeWins",0); dw=h2h_raw.get("draws",0); aw=h2h_raw.get("awayWins",0)
        h2h = {
            "games":g,"homeWins":hw,"draws":dw,"awayWins":aw,
            "homeBar":round(hw/g*100),"drawBar":round(dw/g*100),"awayBar":round(aw/g*100),
            "avgGoals":h2h_raw.get("avgGoals",0),
            "over25Rate":int((h2h_raw.get("over25Rate") or 0)*100),
            "bttsRate":int((h2h_raw.get("bttsRate") or 0)*100),
            "lastResults":h2h_raw.get("lastResults",[])[:7],
        }

    # prediction
    pred = None
    if ap:
        comp = {}
        for k,label in [("compForm","Form"),("compAtt","Angriff"),("compDef","Abwehr")]:
            if ap.get(k): comp[label]=ap[k]
        pred = {
            "home":ap.get("pctHome"),"draw":ap.get("pctDraw"),"away":ap.get("pctAway"),
            "poissonHome":ap.get("poissonHome"),"poissonAway":ap.get("poissonAway"),
            "comp":comp,
        }

    # injuries
    inj_raw = (pmatch or {}).get("injuries") or {}
    def fmt_inj(players):
        return [{"pos":p.get("position","?"),"name":p.get("player","?"),
                 "reason":p.get("reason","") or p.get("type","")} for p in (players or [])[:6]]
    injuries = {"home":fmt_inj(inj_raw.get("home",[])),"away":fmt_inj(inj_raw.get("away",[]))}

    # polymarket
    poly_out = None
    if poly:
        mkt = poly.get("markets",{})
        order = ["Heimsieg","Unentschieden","Auswärtssieg","Over 2.5 Tore","Under 2.5 Tore",
                 "Beide Teams treffen","Over 3.5 Tore","Beide Teams treffen: Nein"]
        cards = []
        for name in order:
            price = mkt.get(name)
            if price is None: continue
            short = (name.replace(" Tore","").replace("Beide Teams treffen: Nein","BTTS Nein")
                     .replace("Beide Teams treffen","BTTS"))
            cards.append({"name":short,"pct":round(price*100)})
        if cards:
            poly_out = {"cards":cards,"url":poly.get("eventUrl","")}

    return {
        "meta": {
            "home":home,"away":away,"league":league,
            "leagueName":league_name,"leagueFlag":league_flag,
            "date":date_str,"dateIso":date_iso,"time":time_str,
            "matchScore":match_score,
            "homeInitials":initials(home),"awayInitials":initials(away),
            "homeElo":int(h_elo) if (h_elo:=sf((hs or {}).get("elo"))) else None,
            "awayElo":int(a_elo) if (a_elo:=sf((as_ or {}).get("elo"))) else None,
        },
        "probabilities":{"home":h_prob,"draw":d_prob,"away":a_prob},
        "aiText":generate_ai_text(entry, pmatch, hs, as_),
        "picks":picks_out,
        "stats":stats_bars,
        "oddsCards":odds_cards,
        "h2h":h2h,
        "prediction":pred,
        "injuries":injuries,
        "poly":poly_out,
        "generatedAt":datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC"),
    }

# ─── Write JSON files ─────────────────────────────────────────────────────────
def main():
    gen = skip = 0
    slugs = []
    for entry in picks_list:
        home   = entry["home"]; away = entry["away"]
        league = entry["league"]; d_iso = entry.get("dateIso","")
        good = [p for p in entry.get("picks",[]) if p.get("conf") in ("high","medium")]
        if not good: skip+=1; continue

        pmatch = get_prematch(home, away)
        payload = build_payload(entry, pmatch, get_stats(league,home), get_stats(league,away), get_poly(home,away))

        slug = f"{slugify(home)}-vs-{slugify(away)}-{d_iso}"
        slugs.append(slug)
        out = os.path.join(DATA_DIR, f"{slug}.json")
        with open(out,"w",encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",",":"))
        gen+=1
        print(f"  ✓ {home} vs {away}")

    # Write index for match.html to list available slugs (optional)
    with open(os.path.join(BASE,"matches","index.json"),"w",encoding="utf-8") as f:
        json.dump({"slugs":slugs,"generated":datetime.utcnow().isoformat()}, f)

    print(f"\n✅ {gen} JSON-Dateien generiert, {skip} übersprungen.")
    print(f"   Output: matches/data/*.json  +  matches/index.json")
    print(f"   Template: matches/match.html  (einmalig, separat)")

if __name__ == "__main__":
    main()
