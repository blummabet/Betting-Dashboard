#!/usr/bin/env python3
"""
generate_match_pages.py
Generates modern static HTML event pages for each fixture that has picks.

Output: matches/{home-slug}-vs-{away-slug}-{dateIso}.html
Run:    python generate_match_pages.py
"""

import json, os, re, math
from datetime import datetime

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(BASE, "matches")
os.makedirs(OUT, exist_ok=True)

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
    for s,d in [("ä","ae"),("ö","oe"),("ü","ue"),("ß","ss"),("á","a"),
                ("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n"),("ç","c")]:
        text = text.replace(s, d)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")

def fmt_odds(v):
    try: return f"{float(v):.2f}"
    except: return "—"

def safe_float(v, default=None):
    try: return float(v)
    except: return default

def kelly_quarter(odds, model_odds):
    try:
        o, m = float(odds), float(model_odds)
        if o <= 1 or m <= 0: return None
        p = 1.0 / m; q = 1.0 - p; b = o - 1.0
        return max(0.0, (b * p - q) / b / 4.0)
    except: return None

def initials(name):
    words = name.split()
    if len(words) == 1: return name[:2].upper()
    return "".join(w[0] for w in words if w[0].isalpha())[:3].upper()

# ─── Probability Donut SVG ────────────────────────────────────────────────────
def donut_svg(h_pct, d_pct, a_pct, size=140, stroke=13):
    total = (h_pct or 0) + (d_pct or 0) + (a_pct or 0)
    if total < 1: h_pct, d_pct, a_pct, total = 40, 25, 35, 100
    h = (h_pct or 0) / total
    d = (d_pct or 0) / total
    a = (a_pct or 0) / total
    cx = cy = size / 2
    r = (size - stroke) / 2
    gap = 3  # degrees gap between segments

    def arc(start_deg, span_deg, color):
        if span_deg < 2: return ""
        s = math.radians(start_deg - 90)
        e = math.radians(start_deg + span_deg - gap - 90)
        x1 = cx + r * math.cos(s); y1 = cy + r * math.sin(s)
        x2 = cx + r * math.cos(e); y2 = cy + r * math.sin(e)
        lg = 1 if span_deg - gap > 180 else 0
        return (f'<path d="M{x1:.2f},{y1:.2f} A{r},{r} 0 {lg},1 {x2:.2f},{y2:.2f}"'
                f' fill="none" stroke="{color}" stroke-width="{stroke}" stroke-linecap="round"/>')

    h_deg = h * 360; d_deg = d * 360; a_deg = a * 360
    return f"""<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" style="flex-shrink:0">
  <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#ffffff0a" stroke-width="{stroke}"/>
  {arc(0, h_deg, "#00d4a1")}
  {arc(h_deg, d_deg, "#e3b341")}
  {arc(h_deg + d_deg, a_deg, "#a78bfa")}
  <text x="{cx}" y="{cy - 9}" text-anchor="middle" font-size="10" fill="#8b949e" font-family="system-ui">Prognose</text>
  <text x="{cx}" y="{cy + 8}" text-anchor="middle" font-size="13" font-weight="800" fill="#e6edf3" font-family="system-ui">{int(round(h_pct))}–{int(round(d_pct))}–{int(round(a_pct))}</text>
</svg>"""

# ─── Visual stat comparison bar ───────────────────────────────────────────────
def stat_bar(label, h_val, a_val, higher_is_better=True, fmt=None):
    fmt = fmt or (lambda x: f"{x:.2f}" if isinstance(x, float) else str(x))
    try:
        hf = float(h_val) if h_val is not None else None
        af = float(a_val) if a_val is not None else None
    except: hf = af = None

    if hf is None and af is None:
        return ""

    total = (hf or 0) + (af or 0)
    h_bar = round((hf or 0) / total * 100) if total > 0 else 50
    a_bar = 100 - h_bar

    h_winning = hf is not None and af is not None and (
        (higher_is_better and hf > af) or (not higher_is_better and hf < af))
    a_winning = hf is not None and af is not None and not h_winning and hf != af

    h_c = "#00d4a1" if h_winning else "#8b949e"
    a_c = "#00d4a1" if a_winning else "#8b949e"
    h_str = fmt(h_val) if h_val is not None else "—"
    a_str = fmt(a_val) if a_val is not None else "—"

    return f"""<div class="sbar-row">
  <span class="sbar-val" style="color:{h_c}">{h_str}</span>
  <div class="sbar-center">
    <div class="sbar-label">{label}</div>
    <div class="sbar-track">
      <div class="sbar-fill-h" style="width:{h_bar}%;background:{h_c}20;border-right:2px solid {h_c}"></div>
      <div class="sbar-fill-a" style="width:{a_bar}%;background:{a_c}20;border-left:2px solid {a_c}"></div>
    </div>
  </div>
  <span class="sbar-val" style="color:{a_c};text-align:left">{a_str}</span>
</div>"""

# ─── AI Text Generator ────────────────────────────────────────────────────────
def generate_match_analysis(entry, prematch_fix, home_stats, away_stats):
    """Generates a 3–4 sentence German match analysis from available data."""
    home = entry["home"]
    away = entry["away"]
    picks = [p for p in entry.get("picks", []) if p.get("conf") in ("high","medium")]

    sentences = []

    # ── 1. Favorite & context ─────────────────────────────────────────────────
    odds = (prematch_fix or {}).get("odds") or {}
    hw = safe_float(odds.get("hw") or odds.get("pinn_hw"))
    aw = safe_float(odds.get("aw") or odds.get("pinn_aw"))
    dr = safe_float(odds.get("dr") or odds.get("pinn_dr"))

    h_elo = safe_float((home_stats or {}).get("elo"))
    a_elo = safe_float((away_stats or {}).get("elo"))
    elo_diff = abs(h_elo - a_elo) if h_elo and a_elo else None

    if hw and aw:
        if hw < aw:
            fav = home; fav_odds = hw; dog_odds = aw
            role = "als Favorit"
        else:
            fav = away; fav_odds = aw; dog_odds = hw
            role = "als Favorit"

        if fav_odds <= 1.50:
            strength = "klarer Favorit"
        elif fav_odds <= 1.85:
            strength = "leichter Favorit"
        else:
            strength = "Außenseiter"

        if elo_diff and elo_diff >= 100:
            elo_note = f" (Elo-Differenz: {int(elo_diff)} Punkte)"
        elif elo_diff and elo_diff >= 50:
            elo_note = f" (Elo-Differenz: {int(elo_diff)} Punkte)"
        else:
            elo_note = ""

        sentences.append(
            f"{fav} geht {role} in diese Partie — Kurs {fmt_odds(fav_odds)} "
            f"gegenüber {fmt_odds(dog_odds)} für {away if fav == home else home}"
            f"{elo_note}."
        )
    else:
        sentences.append(f"{home} empfängt {away} — ein Spiel mit mehreren Wett-Winkeln.")

    # ── 2. Top pick & value ───────────────────────────────────────────────────
    high_picks = [p for p in picks if p.get("conf") == "high"]
    top_pick = (high_picks or picks)[0] if picks else None

    if top_pick:
        market = top_pick.get("market", "")
        odds_v = safe_float(top_pick.get("odds"))
        modds_v = safe_float(top_pick.get("modelOdds"))
        is_value = top_pick.get("value") == "value"

        if odds_v and modds_v:
            model_prob = round(100 / modds_v)
            market_prob = round(100 / odds_v)
            edge = model_prob - market_prob
            kf = kelly_quarter(odds_v, modds_v)
            kelly_str = f", Quarter-Kelly: {kf*100:.1f}% Einsatz" if kf and kf > 0.005 else ""
            value_str = " — rechnerischer Value-Bereich" if is_value else ""
            sentences.append(
                f"Unser stärkster Pick ist <strong>{market}</strong> @ {fmt_odds(odds_v)}: "
                f"das Modell sieht {model_prob}% Wahrscheinlichkeit, der Markt impliziert nur {market_prob}% "
                f"(+{edge} Prozentpunkte Vorteil){value_str}{kelly_str}."
            )
        elif odds_v:
            sentences.append(
                f"Unser Top-Pick: <strong>{market}</strong> @ {fmt_odds(odds_v)}."
            )

    # ── 3. Sharp Money / Line movement ───────────────────────────────────────
    odds_open = (prematch_fix or {}).get("odds_open") or {}
    open_hw = safe_float(odds_open.get("hw") or odds_open.get("pinn_hw_fair"))
    open_aw = safe_float(odds_open.get("aw") or odds_open.get("pinn_aw_fair"))
    cur_hw = safe_float(odds.get("hw") or odds.get("pinn_hw"))
    cur_aw = safe_float(odds.get("aw") or odds.get("pinn_aw"))

    move_sentences = []
    if open_hw and cur_hw and abs(cur_hw - open_hw) / open_hw > 0.03:
        chg = (cur_hw - open_hw) / open_hw * 100
        dir_txt = "gesunken" if chg < 0 else "gestiegen"
        move_sentences.append(f"{home} Heimsieg {fmt_odds(open_hw)}→{fmt_odds(cur_hw)} ({chg:+.1f}%)")
    if open_aw and cur_aw and abs(cur_aw - open_aw) / open_aw > 0.03:
        chg = (cur_aw - open_aw) / open_aw * 100
        move_sentences.append(f"{away} Auswärtssieg {fmt_odds(open_aw)}→{fmt_odds(cur_aw)} ({chg:+.1f}%)")

    if move_sentences:
        sentences.append("Sharps haben die Linie bewegt: " + ", ".join(move_sentences) + ".")

    # ── 4. H2H pattern ───────────────────────────────────────────────────────
    h2h = (prematch_fix or {}).get("h2h") or {}
    if h2h.get("games", 0) >= 4:
        g = h2h["games"]
        hw_r = h2h.get("homeWins", 0) / g
        aw_r = h2h.get("awayWins", 0) / g
        o25_r = h2h.get("over25Rate", 0)
        btts_r = h2h.get("bttsRate", 0)
        avg_g = h2h.get("avgGoals", 0)

        h2h_notes = []
        if hw_r >= 0.65:
            h2h_notes.append(f"{home} dominiert den direkten Vergleich ({int(hw_r*100)}% Siege aus {g} Spielen)")
        elif aw_r >= 0.65:
            h2h_notes.append(f"{away} dominiert historisch ({int(aw_r*100)}% Siege aus {g} Spielen)")
        if btts_r >= 0.65:
            h2h_notes.append(f"Beide Teams treffen in {int(btts_r*100)}% der Direktduelle")
        elif o25_r >= 0.65:
            h2h_notes.append(f"Over 2.5 in {int(o25_r*100)}% der letzten {g} Begegnungen (∅ {avg_g:.1f} Tore)")
        elif avg_g < 1.8:
            h2h_notes.append(f"Historisch torarm: nur ∅ {avg_g:.1f} Tore pro Spiel in {g} Duellen")

        if h2h_notes:
            sentences.append("; ".join(h2h_notes) + ".")

    # ── 5. Injury context ─────────────────────────────────────────────────────
    inj = (prematch_fix or {}).get("injurySummary") or {}
    h_inj = inj.get("home", {})
    a_inj = inj.get("away", {})
    h_total = (h_inj or {}).get("total", 0)
    a_total = (a_inj or {}).get("total", 0)

    if h_total >= 3 or a_total >= 3:
        inj_parts = []
        if h_total >= 3:
            inj_parts.append(f"{home} mit {h_total} Ausfällen")
        if a_total >= 3:
            inj_parts.append(f"{away} mit {a_total} Ausfällen")
        sentences.append("Verletzungslage beachten: " + " und ".join(inj_parts) + ".")
    elif h_total == 0 and a_total == 0:
        pass  # no news is good news, skip

    # Fallback if only 1–2 sentences
    if len(sentences) < 2 and picks:
        sentences.append(
            f"Das Modell sieht {len(picks)} verwertbare Wett-Winkel mit ausreichender Konfidenz."
        )

    return " ".join(sentences[:4])

# ─── CSS ──────────────────────────────────────────────────────────────────────
CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#080c10;
  --card:#0f1419;
  --card2:#141b22;
  --card3:#1a2332;
  --border:#1e2d3d;
  --border2:#243040;
  --accent:#00d4a1;
  --accent2:#00b389;
  --red:#f85149;
  --yellow:#e3b341;
  --text:#e8edf3;
  --muted:#6b7a8d;
  --muted2:#8b9ab0;
  --green:#3fb950;
  --blue:#58a6ff;
  --purple:#a78bfa;
}
html{-webkit-text-size-adjust:100%}
body{
  background:var(--bg);
  color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Inter',sans-serif;
  min-height:100vh;
  padding-bottom:80px;
  overflow-x:hidden;
}
a{color:var(--accent);text-decoration:none}

/* ── Nav ── */
.top-nav{
  background:rgba(8,12,16,0.92);
  backdrop-filter:blur(20px);
  -webkit-backdrop-filter:blur(20px);
  border-bottom:1px solid var(--border);
  padding:12px 16px;
  display:flex;align-items:center;justify-content:space-between;
  position:sticky;top:0;z-index:200;gap:8px;
}
.nav-back{
  display:flex;align-items:center;gap:6px;
  font-size:13px;font-weight:500;color:var(--muted2);
  padding:6px 10px;border-radius:8px;border:1px solid var(--border);
  background:var(--card);transition:all .15s;
}
.nav-back:hover{color:var(--text);border-color:var(--border2)}
.nav-league{font-size:12px;color:var(--muted);letter-spacing:.2px}

/* ── Hero ── */
.hero{
  position:relative;
  background:linear-gradient(180deg, #0a1628 0%, #080c10 100%);
  border-bottom:1px solid var(--border);
  overflow:hidden;
  padding:32px 16px 24px;
}
.hero::before{
  content:'';position:absolute;inset:0;
  background:radial-gradient(ellipse 80% 60% at 20% 50%, #00d4a108 0%, transparent 60%),
             radial-gradient(ellipse 60% 60% at 80% 50%, #a78bfa06 0%, transparent 60%);
  pointer-events:none;
}
.hero-inner{position:relative;max-width:860px;margin:0 auto}
.hero-teams{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:20px}
.hero-team{flex:1;text-align:center}
.hero-team.home{text-align:right}
.hero-team.away{text-align:left}
.team-circle{
  width:52px;height:52px;border-radius:50%;
  display:inline-flex;align-items:center;justify-content:center;
  font-size:14px;font-weight:800;color:#e8edf3;
  margin-bottom:10px;
  border:2px solid var(--border2);
}
.team-circle.home{background:linear-gradient(135deg,#0a2a1e,#0f1e28);border-color:#00d4a130}
.team-circle.away{background:linear-gradient(135deg,#1a0a28,#0f1428);border-color:#a78bfa30}
.hero-team-name{font-size:15px;font-weight:700;color:var(--text);line-height:1.2;margin-bottom:4px}
.hero-team-elo{font-size:11px;color:var(--muted);font-weight:500}
.hero-center{
  flex-shrink:0;display:flex;flex-direction:column;align-items:center;gap:6px;
  padding:0 4px;
}
.hero-kickoff{font-size:11px;color:var(--muted);margin-top:4px}
.prob-pills{
  display:flex;gap:6px;justify-content:center;flex-wrap:wrap;margin-top:4px;
}
.prob-pill{
  display:flex;align-items:center;gap:5px;
  padding:4px 10px;border-radius:20px;font-size:11px;font-weight:700;
  border:1px solid;
}
.prob-pill.home{background:#00d4a110;color:#00d4a1;border-color:#00d4a130}
.prob-pill.draw{background:#e3b34110;color:#e3b341;border-color:#e3b34130}
.prob-pill.away{background:#a78bfa10;color:#a78bfa;border-color:#a78bfa30}
.prob-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.prob-pill.home .prob-dot{background:#00d4a1}
.prob-pill.draw .prob-dot{background:#e3b341}
.prob-pill.away .prob-dot{background:#a78bfa}

/* ── AI Analysis ── */
.ai-section{
  max-width:860px;margin:0 auto;padding:0 12px;
}
.ai-card{
  margin:16px 0;
  background:linear-gradient(135deg,#0a1f18,#0a1428);
  border:1px solid #00d4a120;
  border-radius:14px;padding:18px 20px;
  position:relative;overflow:hidden;
}
.ai-card::before{
  content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,#00d4a1,#a78bfa,transparent);
}
.ai-header{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.ai-icon-wrap{
  width:28px;height:28px;border-radius:8px;
  background:#00d4a115;border:1px solid #00d4a130;
  display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0;
}
.ai-label{font-size:11px;font-weight:700;color:#00d4a1;text-transform:uppercase;letter-spacing:1px}
.ai-text{font-size:13px;color:var(--muted2);line-height:1.7}
.ai-text strong{color:var(--accent);font-weight:700}

/* ── Content ── */
.content{max-width:860px;margin:0 auto;padding:0 12px}

/* ── Section ── */
.section{
  background:var(--card);
  border:1px solid var(--border);
  border-radius:16px;
  padding:18px;
  margin-bottom:14px;
  position:relative;overflow:hidden;
}
.section::before{
  content:'';position:absolute;top:0;left:0;width:3px;bottom:0;
  background:linear-gradient(180deg,var(--accent),transparent);
  border-radius:16px 0 0 16px;
}
.section-title{
  font-size:13px;font-weight:700;color:var(--text);
  margin-bottom:14px;display:flex;align-items:center;gap:8px;
  text-transform:uppercase;letter-spacing:.6px;
}
.section-title .sticon{
  width:24px;height:24px;border-radius:7px;
  display:flex;align-items:center;justify-content:center;
  font-size:13px;flex-shrink:0;
}

/* ── Pick cards ── */
.pick-card{
  position:relative;border-radius:12px;
  padding:14px 16px;margin-bottom:10px;overflow:hidden;
}
.pick-card.high{background:linear-gradient(135deg,#001a13,#0a1419);border:1px solid #00d4a125}
.pick-card.medium{background:linear-gradient(135deg,#1a1400,#0f1419);border:1px solid #e3b34125}
.pick-card.high::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--accent);border-radius:12px 0 0 12px}
.pick-card.medium::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--yellow);border-radius:12px 0 0 12px}
.pick-top{display:flex;align-items:flex-start;gap:10px;margin-bottom:10px}
.pick-icon{font-size:20px;flex-shrink:0;margin-top:1px}
.pick-info{flex:1;min-width:0}
.pick-market{font-size:14px;font-weight:700;color:var(--text);margin-bottom:3px}
.pick-conf{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px}
.pick-conf.high{color:var(--accent)}
.pick-conf.medium{color:var(--yellow)}
.pick-pills{display:flex;gap:6px;flex-wrap:wrap}
.pill{
  padding:4px 10px;border-radius:8px;font-size:12px;font-weight:600;
  border:1px solid;white-space:nowrap;
}
.pill-odds{background:#ffffff08;border-color:var(--border2);color:var(--text)}
.pill-model{background:#00d4a108;border-color:#00d4a130;color:var(--accent)}
.pill-kelly{background:#a78bfa08;border-color:#a78bfa30;color:var(--purple)}
.pill-value{background:#3fb95008;border-color:#3fb95030;color:var(--green)}

/* ── Stats bars ── */
.sbar-row{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.sbar-val{font-size:13px;font-weight:700;min-width:42px;text-align:right;white-space:nowrap}
.sbar-center{flex:1;min-width:0}
.sbar-label{font-size:10px;color:var(--muted);text-align:center;margin-bottom:4px;text-transform:uppercase;letter-spacing:.4px}
.sbar-track{height:8px;border-radius:4px;overflow:hidden;background:#ffffff06;display:flex}
.sbar-fill-h{height:100%;transition:width .3s}
.sbar-fill-a{height:100%;transition:width .3s}
.stats-header{display:flex;justify-content:space-between;margin-bottom:14px}
.stats-header-name{font-size:13px;font-weight:700;color:var(--muted2)}

/* ── Odds movement ── */
.odds-scroller{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0 -4px;padding:0 4px}
.odds-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;min-width:300px}
.odds-card{
  background:var(--card2);border:1px solid var(--border);
  border-radius:10px;padding:11px 12px;
}
.odds-card-label{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;margin-bottom:8px}
.odds-values{display:flex;align-items:flex-end;gap:6px;margin-bottom:6px}
.odds-open{font-size:12px;color:var(--muted2);text-decoration:line-through}
.odds-cur{font-size:18px;font-weight:800;color:var(--text)}
.odds-move{font-size:11px;font-weight:700;padding:2px 6px;border-radius:6px;display:inline-block}
.odds-move.up{background:#f8514915;color:var(--red)}
.odds-move.down{background:#3fb95015;color:var(--green)}
.odds-move.neutral{background:#ffffff08;color:var(--muted)}

/* ── H2H ── */
.h2h-top{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}
.h2h-kpi{
  flex:1;min-width:70px;text-align:center;
  background:var(--card2);border:1px solid var(--border);
  border-radius:10px;padding:10px 8px;
}
.h2h-kpi .kpi-val{font-size:20px;font-weight:800;color:var(--text);line-height:1}
.h2h-kpi .kpi-lbl{font-size:10px;color:var(--muted);margin-top:4px;line-height:1.3}
.h2h-bar{height:10px;border-radius:5px;overflow:hidden;display:flex;margin-bottom:14px}
.h2h-bar-h{background:var(--accent)}
.h2h-bar-d{background:var(--yellow)}
.h2h-bar-a{background:var(--purple)}
.h2h-results-label{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px}
.h2h-dots{display:flex;gap:5px;flex-wrap:wrap}
.h2h-dot{
  width:28px;height:28px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  font-size:11px;font-weight:800;color:#080c10;flex-shrink:0;
}

/* ── Prediction bars ── */
.pred-bar{margin-bottom:12px}
.pred-bar-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:5px}
.pred-bar-name{font-size:12px;color:var(--muted2)}
.pred-bar-pct{font-size:14px;font-weight:800}
.pred-track{height:8px;border-radius:4px;background:#ffffff06;overflow:hidden}
.pred-fill{height:100%;border-radius:4px}

/* ── Injuries ── */
.inj-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.inj-team{background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:12px}
.inj-team-name{font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px}
.inj-player{
  font-size:12px;padding:7px 10px;border-radius:7px;
  background:#f8514910;border-left:3px solid #f8514950;
  margin-bottom:6px;color:var(--text);
}
.inj-pos{font-size:10px;font-weight:700;color:var(--red);margin-bottom:2px}
.inj-reason{font-size:10px;color:var(--muted);margin-top:2px}
.inj-clean{
  font-size:12px;color:var(--green);
  display:flex;align-items:center;gap:5px;padding:4px 0;
}

/* ── Polymarket ── */
.poly-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
.poly-link-btn{
  font-size:11px;color:var(--blue);
  padding:4px 10px;border-radius:6px;border:1px solid #58a6ff30;
  background:#58a6ff08;
}
.poly-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px}
.poly-card{
  background:var(--card2);border:1px solid var(--border);
  border-radius:10px;padding:12px;
}
.poly-name{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.3px;margin-bottom:8px;line-height:1.3}
.poly-pct{font-size:24px;font-weight:800;color:var(--accent);line-height:1;margin-bottom:6px}
.poly-bar-track{height:4px;border-radius:2px;background:#ffffff08;overflow:hidden}
.poly-bar-fill{height:100%;border-radius:2px;background:var(--accent)}

/* ── Footer ── */
.page-footer{
  text-align:center;font-size:11px;color:var(--muted);
  margin-top:24px;padding-top:16px;border-top:1px solid var(--border);
}

/* ── Mobile ── */
@media(max-width:480px){
  .hero{padding:20px 12px 18px}
  .hero-team-name{font-size:13px}
  .team-circle{width:44px;height:44px;font-size:12px}
  .section{padding:14px 12px}
  .pick-market{font-size:13px}
  .sbar-val{font-size:12px;min-width:36px}
  .h2h-kpi .kpi-val{font-size:17px}
  .h2h-kpi{min-width:58px;padding:8px 6px}
  .inj-grid{grid-template-columns:1fr}
  .odds-card{padding:9px 10px}
  .odds-cur{font-size:15px}
  .poly-grid{grid-template-columns:repeat(2,1fr)}
  .prob-pill{font-size:10px;padding:3px 8px}
}
"""

# ─── Render ───────────────────────────────────────────────────────────────────
def render_page(entry, pmatch, hs, as_, poly):
    home        = entry["home"]
    away        = entry["away"]
    league      = entry["league"]
    league_name = entry.get("leagueName", league)
    league_flag = entry.get("leagueFlag", "")
    date_str    = entry.get("date", "")
    date_iso    = entry.get("dateIso", "")
    match_score = entry.get("matchScore", 0)
    picks       = entry.get("picks", [])
    visible     = [p for p in picks if p.get("conf") in ("high","medium")]
    time_str    = (pmatch or {}).get("time", "")

    odds = (pmatch or {}).get("odds") or {}

    # ── Probabilities ─────────────────────────────────────────────────────────
    ap = (pmatch or {}).get("apiPrediction") or {}
    hw_fair = safe_float(odds.get("hw_fair") or odds.get("pinn_hw_fair"))
    dr_fair = safe_float(odds.get("dr_fair") or odds.get("pinn_dr_fair"))
    aw_fair = safe_float(odds.get("aw_fair") or odds.get("pinn_aw_fair"))

    if hw_fair and dr_fair and aw_fair:
        tot = 1/hw_fair + 1/dr_fair + 1/aw_fair
        h_prob = round(100 / hw_fair / tot)
        d_prob = round(100 / dr_fair / tot)
        a_prob = round(100 / aw_fair / tot)
    else:
        h_prob = ap.get("pctHome") or 35
        d_prob = ap.get("pctDraw") or 25
        a_prob = ap.get("pctAway") or 40

    # ── Hero ──────────────────────────────────────────────────────────────────
    h_elo = safe_float((hs or {}).get("elo"))
    a_elo = safe_float((as_ or {}).get("elo"))
    h_elo_str = f"Elo {int(h_elo)}" if h_elo else ""
    a_elo_str = f"Elo {int(a_elo)}" if a_elo else ""

    donut = donut_svg(h_prob, d_prob, a_prob)

    hero_html = f"""
<div class="hero">
  <div class="hero-inner">
    <div class="hero-teams">
      <div class="hero-team home">
        <div class="team-circle home">{initials(home)}</div>
        <div class="hero-team-name">{home}</div>
        <div class="hero-team-elo">{h_elo_str}</div>
      </div>
      <div class="hero-center">
        {donut}
        <div class="hero-kickoff">{'📅 ' + date_str + (' &nbsp;🕐 ' + time_str if time_str else '')}</div>
      </div>
      <div class="hero-team away">
        <div class="team-circle away">{initials(away)}</div>
        <div class="hero-team-name">{away}</div>
        <div class="hero-team-elo">{a_elo_str}</div>
      </div>
    </div>
    <div class="prob-pills">
      <div class="prob-pill home"><div class="prob-dot"></div>{home.split()[-1]} {h_prob}%</div>
      <div class="prob-pill draw"><div class="prob-dot"></div>Unent. {d_prob}%</div>
      <div class="prob-pill away"><div class="prob-dot"></div>{away.split()[-1]} {a_prob}%</div>
    </div>
  </div>
</div>"""

    # ── AI Analysis ───────────────────────────────────────────────────────────
    ai_text = generate_match_analysis(entry, pmatch, hs, as_)
    ai_html = f"""
<div class="ai-section">
  <div class="ai-card">
    <div class="ai-header">
      <div class="ai-icon-wrap">🧠</div>
      <span class="ai-label">Match-Analyse</span>
      <span style="font-size:10px;color:var(--muted);margin-left:auto">CocoBet Modell</span>
    </div>
    <div class="ai-text">{ai_text}</div>
  </div>
</div>"""

    # ── Picks ─────────────────────────────────────────────────────────────────
    if visible:
        picks_inner = ""
        for p in visible:
            conf   = p.get("conf","")
            market = p.get("market","—")
            icon   = p.get("icon","🎯")
            o      = safe_float(p.get("odds"))
            mo     = safe_float(p.get("modelOdds"))
            is_val = p.get("value") == "value"
            conf_lbl = "★★★ HIGH" if conf=="high" else "★★ MEDIUM"

            pills = ""
            if o:  pills += f'<span class="pill pill-odds">🎯 {fmt_odds(o)}</span>'
            if mo: pills += f'<span class="pill pill-model">⚙ {fmt_odds(mo)}</span>'
            kf = kelly_quarter(o, mo)
            if kf and kf > 0.005:
                pills += f'<span class="pill pill-kelly">🏦 {kf*100:.1f}%</span>'
            if is_val:
                pills += '<span class="pill pill-value">✓ Value</span>'

            picks_inner += f"""
<div class="pick-card {conf}">
  <div class="pick-top">
    <div class="pick-icon">{icon}</div>
    <div class="pick-info">
      <div class="pick-market">{market}</div>
      <div class="pick-conf {conf}">{conf_lbl}</div>
    </div>
  </div>
  <div class="pick-pills">{pills}</div>
</div>"""
    else:
        picks_inner = '<p style="font-size:13px;color:var(--muted)">Kein Pick mit ausreichender Konfidenz.</p>'

    picks_section = f"""
<div class="section">
  <div class="section-title">
    <div class="sticon" style="background:#00d4a115;border:1px solid #00d4a130">🎯</div>
    Picks
  </div>
  {picks_inner}
</div>"""

    # ── Stats ─────────────────────────────────────────────────────────────────
    h_form = safe_float((hs or {}).get("homeWinRate"))
    a_form = safe_float((as_ or {}).get("awayWinRate"))
    stats_rows = ""
    stats_rows += stat_bar("xG (Heim / Ausw)", (hs or {}).get("xG_home"), (as_ or {}).get("xG_away"),
                           fmt=lambda x: f"{x:.2f}" if x else "—")
    stats_rows += stat_bar("xGA (niedriger = besser)", (hs or {}).get("xGA_home"), (as_ or {}).get("xGA_away"),
                           higher_is_better=False,
                           fmt=lambda x: f"{x:.2f}" if x else "—")
    stats_rows += stat_bar("Siegquote", h_form, a_form,
                           fmt=lambda x: f"{round(x*100)}%" if x else "—")
    stats_rows += stat_bar("Clean Sheets", (hs or {}).get("cleanSheetHome"), (as_ or {}).get("cleanSheetAway"),
                           fmt=lambda x: f"{round(x*100)}%" if x else "—")
    stats_rows += stat_bar("Elo-Rating", (hs or {}).get("elo"), (as_ or {}).get("elo"),
                           fmt=lambda x: str(int(x)) if x else "—")
    stats_rows += stat_bar("Formation", (hs or {}).get("formation"), (as_ or {}).get("formation"),
                           fmt=lambda x: str(x) if x else "—")

    stats_section = f"""
<div class="section">
  <div class="section-title">
    <div class="sticon" style="background:#58a6ff15;border:1px solid #58a6ff30">📊</div>
    Team-Vergleich
  </div>
  <div class="stats-header">
    <span class="stats-header-name">{home}</span>
    <span class="stats-header-name">{away}</span>
  </div>
  {stats_rows}
</div>"""

    # ── Odds Movement ─────────────────────────────────────────────────────────
    odds_open = (pmatch or {}).get("odds_open") or {}
    open_hw = safe_float(odds_open.get("hw") or odds_open.get("pinn_hw_fair"))
    open_dr = safe_float(odds_open.get("dr") or odds_open.get("pinn_dr_fair"))
    open_aw = safe_float(odds_open.get("aw") or odds_open.get("pinn_aw_fair"))
    cur_hw  = safe_float(odds.get("hw") or odds.get("pinn_hw"))
    cur_dr  = safe_float(odds.get("dr") or odds.get("pinn_dr"))
    cur_aw  = safe_float(odds.get("aw") or odds.get("pinn_aw"))
    cur_o25 = safe_float(odds.get("o25"))
    cur_u25 = safe_float(odds.get("u25"))

    def odds_card(label, o_val, c_val):
        if c_val is None: return ""
        move_txt = "—"; dir_cls = "neutral"
        if o_val and c_val:
            chg = (c_val - o_val) / o_val * 100
            if abs(chg) >= 0.5:
                dir_cls = "up" if chg > 0 else "down"
                move_txt = f"{'↑' if chg>0 else '↓'} {chg:+.1f}%"
            else:
                move_txt = "→ stabil"
        open_html = f'<span class="odds-open">{fmt_odds(o_val)}</span>' if o_val else ""
        return f"""<div class="odds-card">
  <div class="odds-card-label">{label}</div>
  <div class="odds-values">{open_html}<span class="odds-cur">{fmt_odds(c_val)}</span></div>
  <span class="odds-move {dir_cls}">{move_txt}</span>
</div>"""

    odds_cards = (
        odds_card("1 Heimsieg", open_hw, cur_hw) +
        odds_card("X Unentsch.", open_dr, cur_dr) +
        odds_card("2 Auswärts", open_aw, cur_aw) +
        odds_card("Over 2.5", None, cur_o25) +
        odds_card("Under 2.5", None, cur_u25)
    )

    odds_section = f"""
<div class="section">
  <div class="section-title">
    <div class="sticon" style="background:#e3b34115;border:1px solid #e3b34130">📈</div>
    Linien-Bewegung
  </div>
  <div class="odds-scroller">
    <div class="odds-grid">{odds_cards}</div>
  </div>
</div>"""

    # ── H2H ───────────────────────────────────────────────────────────────────
    h2h = (pmatch or {}).get("h2h") or {}
    if h2h.get("games"):
        g  = h2h["games"] or 1
        hw = h2h.get("homeWins", 0)
        dw = h2h.get("draws", 0)
        aw = h2h.get("awayWins", 0)
        hw_pct = hw / g * 100; dw_pct = dw / g * 100; aw_pct = aw / g * 100
        avg_g  = h2h.get("avgGoals", 0)
        o25_r  = h2h.get("over25Rate", 0)
        btts_r = h2h.get("bttsRate", 0)
        last   = h2h.get("lastResults", [])

        dot_colors = {"W":"#00d4a1","D":"#e3b341","L":"#f85149"}
        dots_html  = "".join(
            f'<div class="h2h-dot" style="background:{dot_colors.get(r,"#8b949e")}">{r}</div>'
            for r in last[:7]
        )

        h2h_section = f"""
<div class="section">
  <div class="section-title">
    <div class="sticon" style="background:#a78bfa15;border:1px solid #a78bfa30">🔄</div>
    Direktvergleich (H2H)
  </div>
  <div class="h2h-top">
    <div class="h2h-kpi"><div class="kpi-val" style="color:var(--accent)">{hw}</div><div class="kpi-lbl">{home.split()[-1]}<br>Siege</div></div>
    <div class="h2h-kpi"><div class="kpi-val" style="color:var(--yellow)">{dw}</div><div class="kpi-lbl">Unent-<br>schieden</div></div>
    <div class="h2h-kpi"><div class="kpi-val" style="color:var(--purple)">{aw}</div><div class="kpi-lbl">{away.split()[-1]}<br>Siege</div></div>
    <div class="h2h-kpi"><div class="kpi-val">{avg_g:.1f}</div><div class="kpi-lbl">∅ Tore<br>/Spiel</div></div>
    <div class="h2h-kpi"><div class="kpi-val">{int(o25_r*100)}%</div><div class="kpi-lbl">Over<br>2.5</div></div>
    <div class="h2h-kpi"><div class="kpi-val">{int(btts_r*100)}%</div><div class="kpi-lbl">BTTS<br>Rate</div></div>
  </div>
  <div class="h2h-bar">
    <div class="h2h-bar-h" style="width:{hw_pct:.1f}%"></div>
    <div class="h2h-bar-d" style="width:{dw_pct:.1f}%"></div>
    <div class="h2h-bar-a" style="width:{aw_pct:.1f}%"></div>
  </div>
  <div class="h2h-results-label">Letzte {len(last)} Direktbegegnungen (Heimteam-Perspektive)</div>
  <div class="h2h-dots">{dots_html}</div>
</div>"""
    else:
        h2h_section = ""

    # ── API Prediction ────────────────────────────────────────────────────────
    if ap:
        ph = ap.get("pctHome"); pd = ap.get("pctDraw"); pa = ap.get("pctAway")

        def pred_bar_html(label, val, color):
            v = val or 0
            return f"""<div class="pred-bar">
  <div class="pred-bar-header">
    <span class="pred-bar-name">{label}</span>
    <span class="pred-bar-pct" style="color:{color}">{v}%</span>
  </div>
  <div class="pred-track"><div class="pred-fill" style="width:{v}%;background:{color}"></div></div>
</div>"""

        comp_cards = ""
        for cname, cdata, ccolor in [
            ("Form",    ap.get("compForm"), "#58a6ff"),
            ("Angriff", ap.get("compAtt"),  "#3fb950"),
            ("Abwehr",  ap.get("compDef"),  "#f85149"),
        ]:
            if cdata:
                hv = cdata.get("home", 50); av = cdata.get("away", 50)
                comp_cards += f"""<div style="background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:10px 12px">
  <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;margin-bottom:8px">{cname}</div>
  <div style="display:flex;justify-content:space-between;align-items:center">
    <span style="font-size:16px;font-weight:800;color:{ccolor}">{hv}%</span>
    <span style="font-size:10px;color:var(--muted)">vs</span>
    <span style="font-size:16px;font-weight:800;color:{ccolor}">{av}%</span>
  </div>
</div>"""

        poisson_note = ""
        poh = ap.get("poissonHome"); poa = ap.get("poissonAway")
        if poh and poa:
            poisson_note = f'<div style="margin-top:12px;padding:10px 12px;background:var(--card2);border:1px solid var(--border);border-radius:10px;font-size:12px;color:var(--muted2)">Poisson: {home.split()[-1]} {poh}% · {away.split()[-1]} {poa}%</div>'

        pred_section = f"""
<div class="section">
  <div class="section-title">
    <div class="sticon" style="background:#3fb95015;border:1px solid #3fb95030">🤖</div>
    Modell-Prognose
  </div>
  {pred_bar_html(f'Heimsieg ({home.split()[-1]})', ph, '#00d4a1')}
  {pred_bar_html('Unentschieden', pd, '#e3b341')}
  {pred_bar_html(f'Auswärtssieg ({away.split()[-1]})', pa, '#a78bfa')}
  {poisson_note}
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;margin-top:12px">{comp_cards}</div>
</div>"""
    else:
        pred_section = ""

    # ── Injuries ──────────────────────────────────────────────────────────────
    inj = (pmatch or {}).get("injuries") or {}
    hi = inj.get("home", []); ai = inj.get("away", [])

    def inj_side(players, team):
        html = f'<div class="inj-team-name">{team}</div>'
        if not players:
            html += '<div class="inj-clean">✓ Keine gemeldeten Ausfälle</div>'
        else:
            for pl in players[:6]:
                pos    = pl.get("position","?")
                name   = pl.get("player","?")
                reason = pl.get("reason","") or pl.get("type","")
                html += f'<div class="inj-player"><div class="inj-pos">{pos}</div><strong>{name}</strong><div class="inj-reason">{reason}</div></div>'
        return html

    inj_section = f"""
<div class="section">
  <div class="section-title">
    <div class="sticon" style="background:#f8514915;border:1px solid #f8514930">🏥</div>
    Verletzungen & Ausfälle
  </div>
  <div class="inj-grid">
    <div class="inj-team">{inj_side(hi, home)}</div>
    <div class="inj-team">{inj_side(ai, away)}</div>
  </div>
</div>"""

    # ── Polymarket ────────────────────────────────────────────────────────────
    poly_section = ""
    if poly:
        mkt   = poly.get("markets", {})
        e_url = poly.get("eventUrl", "")
        order = [
            ("Heimsieg",""),("Unentschieden",""),("Auswärtssieg",""),
            ("Over 2.5 Tore",""),("Under 2.5 Tore",""),
            ("Beide Teams treffen",""),("Over 3.5 Tore",""),
        ]
        cards = ""
        for name, _ in order:
            price = mkt.get(name)
            if price is None: continue
            pct_v = round(price * 100)
            short = name.replace(" Tore","").replace("Beide Teams treffen","BTTS")
            cards += f"""<div class="poly-card">
  <div class="poly-name">{short}</div>
  <div class="poly-pct">{pct_v}%</div>
  <div class="poly-bar-track"><div class="poly-bar-fill" style="width:{pct_v}%"></div></div>
</div>"""
        if cards:
            link_btn = f'<a href="{e_url}" target="_blank" class="poly-link-btn">🔗 Polymarket</a>' if e_url else ""
            poly_section = f"""
<div class="section">
  <div class="poly-header">
    <div class="section-title" style="margin-bottom:0">
      <div class="sticon" style="background:#a78bfa15;border:1px solid #a78bfa30">🟣</div>
      Polymarket-Preise
    </div>
    {link_btn}
  </div>
  <div class="poly-grid">{cards}</div>
</div>"""

    # ── Score badge in nav ─────────────────────────────────────────────────────
    score_color = "#00d4a1" if match_score >= 11 else "#e3b341" if match_score >= 8.5 else "#8b949e"

    # ── Assemble ──────────────────────────────────────────────────────────────
    ts = datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#080c10">
<title>{home} vs {away} — CocoBet</title>
<style>{CSS}</style>
</head>
<body>

<nav class="top-nav">
  <a class="nav-back" href="../betting-dashboard.html">← Dashboard</a>
  <div style="display:flex;align-items:center;gap:10px">
    <span style="font-size:11px;font-weight:700;color:{score_color};background:{score_color}18;border:1px solid {score_color}35;padding:3px 10px;border-radius:20px">Score {match_score:.1f}</span>
    <span class="nav-league">{league_flag} {league_name}</span>
  </div>
</nav>

{hero_html}
{ai_html}

<div class="content">
{picks_section}
{stats_section}
{odds_section}
{h2h_section}
{pred_section}
{inj_section}
{poly_section}
<div class="page-footer">
  Generiert: {ts} · <a href="../betting-dashboard.html">← Zurück zum Dashboard</a>
</div>
</div>

</body>
</html>"""

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    gen = skip = 0
    for entry in picks_list:
        home    = entry["home"]
        away    = entry["away"]
        league  = entry["league"]
        d_iso   = entry.get("dateIso","")

        good = [p for p in entry.get("picks",[]) if p.get("conf") in ("high","medium")]
        if not good: skip += 1; continue

        pmatch = get_prematch(home, away)
        hs     = get_stats(league, home)
        as_    = get_stats(league, away)
        poly   = get_poly(home, away)

        html = render_page(entry, pmatch, hs, as_, poly)

        slug = f"{slugify(home)}-vs-{slugify(away)}-{d_iso}"
        with open(os.path.join(OUT, f"{slug}.html"), "w", encoding="utf-8") as f:
            f.write(html)
        gen += 1
        print(f"  ✓ {home} vs {away}")

    print(f"\n✅ {gen} Seiten generiert, {skip} übersprungen.")

if __name__ == "__main__":
    main()
