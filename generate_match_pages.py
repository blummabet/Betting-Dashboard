#!/usr/bin/env python3
"""
generate_match_pages.py
Generates static HTML event pages for each fixture that has picks.

Output: matches/{home-slug}-vs-{away-slug}-{dateIso}.html
Run:    python generate_match_pages.py
"""

import json
import os
import re
import math
from datetime import datetime

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(BASE, "matches")
os.makedirs(OUT, exist_ok=True)

def load(name):
    p = os.path.join(BASE, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)

picks_list  = load("picks_output.json") or []
prematch    = load("prematch-data.json") or {}
stats_cache = load("stats_cache.json") or {}
poly_raw    = load("polymarket_prices.json") or {}

fixtures_list = prematch.get("fixtures", [])
poly_matches  = poly_raw.get("matches", {})

# ─── Lookup helpers ───────────────────────────────────────────────────────────
# prematch: index by "home|away" (case-sensitive, as in picks_output)
prematch_idx = {}
for fix in fixtures_list:
    key = f"{fix['homeTeamName']}|{fix['awayTeamName']}"
    prematch_idx[key] = fix

def get_prematch(home, away):
    return prematch_idx.get(f"{home}|{away}")

def get_stats(league, team):
    return stats_cache.get(league, {}).get(team, {})

def get_poly(home, away):
    entry = poly_matches.get(f"{home}|{away}")
    if not entry or not entry.get("found"):
        return None
    return entry

# ─── Utilities ────────────────────────────────────────────────────────────────
def slugify(text):
    text = text.lower()
    for src, dst in [("ä","ae"),("ö","oe"),("ü","ue"),("ß","ss"),("á","a"),
                     ("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n"),("ç","c")]:
        text = text.replace(src, dst)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")

def fmt_odds(v):
    if v is None: return "—"
    try: return f"{float(v):.2f}"
    except: return "—"

def pct(v, decimals=0):
    if v is None: return "—"
    try:
        fmt = f"{{:.{decimals}f}}"
        return fmt.format(float(v) * 100) + "%"
    except: return "—"

def pct_int(v):
    """v is already 0–100 integer"""
    if v is None: return "—"
    try: return f"{int(v)}%"
    except: return "—"

def kelly_quarter(odds, model_odds):
    """Returns quarter-Kelly as a fraction (0–1). None if can't compute."""
    try:
        odds = float(odds)
        model_odds = float(model_odds)
        if odds <= 1 or model_odds <= 0: return None
        p = 1.0 / model_odds
        q = 1.0 - p
        b = odds - 1.0
        f = (b * p - q) / b
        return max(0.0, f / 4.0)
    except:
        return None

def conf_badge(conf):
    colors = {"high": "#00d4a1", "medium": "#e3b341", "low": "#8b949e"}
    labels = {"high": "High", "medium": "Medium", "low": "Low"}
    c = colors.get(conf, "#8b949e")
    return f'<span style="background:{c}22;color:{c};border:1px solid {c}44;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;">{labels.get(conf, conf)}</span>'

def move_arrow(open_val, cur_val):
    """Returns (arrow_html, direction_class) comparing opening vs current odds."""
    try:
        o, c = float(open_val), float(cur_val)
        diff = c - o
        pct_chg = diff / o * 100
        if abs(pct_chg) < 0.5:
            return "→", "neutral"
        if diff > 0:
            return f"↑ +{pct_chg:.1f}%", "up"
        return f"↓ {pct_chg:.1f}%", "down"
    except:
        return "—", "neutral"

def h2h_dot(result):
    colors = {"W": "#00d4a1", "D": "#e3b341", "L": "#f85149"}
    c = colors.get(result, "#8b949e")
    return f'<span style="display:inline-block;width:26px;height:26px;border-radius:50%;background:{c};color:#0d1117;font-size:11px;font-weight:800;line-height:26px;text-align:center;">{result}</span>'

# ─── HTML template ────────────────────────────────────────────────────────────
CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--card:#161b22;--card2:#1c2128;--border:#30363d;
  --accent:#00d4a1;--red:#f85149;--yellow:#e3b341;
  --text:#e6edf3;--muted:#8b949e;
  --green:#3fb950;--blue:#58a6ff;--purple:#a78bfa;
}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;min-height:100vh;padding-bottom:60px}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}

/* Nav */
.top-nav{
  background:var(--card);border-bottom:1px solid var(--border);
  padding:12px 20px;display:flex;align-items:center;justify-content:space-between;
  position:sticky;top:0;z-index:100;
}
.top-nav .back{font-size:13px;color:var(--muted);font-weight:500}
.top-nav .back:hover{color:var(--text)}
.top-nav .league-tag{font-size:12px;color:var(--muted)}

/* Match header */
.match-header{
  background:linear-gradient(135deg,#0d2a1f 0%,#0d1117 100%);
  border-bottom:2px solid var(--accent)22;
  padding:32px 20px 24px;text-align:center;
}
.teams-row{display:flex;align-items:center;justify-content:center;gap:16px;margin-bottom:12px}
.team-name{font-size:22px;font-weight:800;flex:1}
.team-name.home{text-align:right}
.team-name.away{text-align:left}
.vs-badge{
  background:var(--card);border:1px solid var(--border);
  border-radius:8px;padding:6px 14px;font-size:13px;color:var(--muted);
  font-weight:600;white-space:nowrap;flex-shrink:0;
}
.match-meta{display:flex;gap:12px;align-items:center;justify-content:center;flex-wrap:wrap;margin-top:10px}
.meta-chip{
  background:var(--card);border:1px solid var(--border);
  border-radius:20px;padding:4px 12px;font-size:12px;color:var(--muted);
}
.score-badge{
  background:#00d4a122;border:1px solid #00d4a144;
  border-radius:20px;padding:4px 14px;font-size:12px;
  color:var(--accent);font-weight:700;
}

/* Content */
.content{max-width:900px;margin:0 auto;padding:24px 16px}
.section{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:20px}
.section-title{font-size:14px;font-weight:700;color:var(--text);margin-bottom:16px;display:flex;align-items:center;gap:8px}

/* Pick cards */
.pick-card{
  background:var(--card2);border:1px solid var(--border);border-radius:10px;
  padding:14px 16px;margin-bottom:10px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;
}
.pick-icon{font-size:18px;flex-shrink:0}
.pick-main{flex:1;min-width:0}
.pick-market{font-size:14px;font-weight:600;color:var(--text)}
.pick-sub{font-size:12px;color:var(--muted);margin-top:3px}
.pick-meta{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.odds-pill{
  background:#ffffff0d;border:1px solid var(--border);
  border-radius:6px;padding:3px 10px;font-size:13px;font-weight:700;color:var(--text);
}
.model-pill{
  background:#00d4a111;border:1px solid #00d4a133;
  border-radius:6px;padding:3px 10px;font-size:12px;color:var(--accent);
}
.kelly-pill{
  background:#a78bfa11;border:1px solid #a78bfa33;
  border-radius:6px;padding:3px 10px;font-size:12px;color:var(--purple);font-weight:700;
}
.value-pill{
  background:#3fb95011;border:1px solid #3fb95033;
  border-radius:6px;padding:3px 10px;font-size:12px;color:var(--green);font-weight:700;
}

/* Comparison table */
.comp-grid{display:grid;grid-template-columns:1fr auto 1fr;gap:0;width:100%}
.comp-row{display:contents}
.comp-label{
  font-size:12px;color:var(--muted);text-align:center;padding:8px 4px;
  border-bottom:1px solid var(--border);
}
.comp-val{
  font-size:13px;font-weight:600;color:var(--text);
  padding:8px 12px;border-bottom:1px solid var(--border);
}
.comp-val.home{text-align:right}
.comp-val.away{text-align:left}
.comp-val.better{color:var(--accent)}
.comp-header{
  font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;
  letter-spacing:0.5px;padding:6px 12px;
}

/* Odds movement */
.odds-table{width:100%;border-collapse:collapse;font-size:13px}
.odds-table th{font-size:11px;color:var(--muted);text-transform:uppercase;font-weight:600;padding:6px 8px;text-align:center;border-bottom:1px solid var(--border)}
.odds-table td{padding:8px;text-align:center;border-bottom:1px solid #30363d55}
.odds-table tr:last-child td{border-bottom:none}
.move-up{color:var(--red)}
.move-down{color:var(--green)}
.move-neutral{color:var(--muted)}

/* H2H */
.h2h-summary{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:16px}
.h2h-stat{text-align:center;flex:1;min-width:80px}
.h2h-stat .val{font-size:20px;font-weight:800;color:var(--text)}
.h2h-stat .lbl{font-size:11px;color:var(--muted);margin-top:2px}
.h2h-record{height:14px;border-radius:7px;overflow:hidden;display:flex;margin-bottom:12px}
.h2h-record .hw{background:var(--accent)}
.h2h-record .dr{background:var(--yellow)}
.h2h-record .aw{background:var(--purple)}
.h2h-dots{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.last-results-label{font-size:11px;color:var(--muted);margin-bottom:8px}

/* Prediction bars */
.pred-bar-wrap{margin-bottom:12px}
.pred-bar-label{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);margin-bottom:4px}
.pred-bar-track{height:10px;border-radius:5px;background:#ffffff0d;overflow:hidden}
.pred-bar-fill{height:100%;border-radius:5px;transition:width .3s}

/* Injuries */
.inj-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:520px){.inj-grid{grid-template-columns:1fr}}
.inj-team-label{font-size:12px;font-weight:700;color:var(--muted);margin-bottom:8px}
.inj-player{
  font-size:12px;color:var(--text);
  padding:6px 10px;background:var(--card2);border-radius:6px;
  border-left:3px solid var(--red);margin-bottom:6px;
}
.inj-reason{font-size:11px;color:var(--muted)}
.no-injuries{font-size:12px;color:var(--green);padding:6px 0}

/* Poly */
.poly-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}
.poly-card{
  background:var(--card2);border:1px solid var(--border);border-radius:8px;padding:12px;
}
.poly-market-name{font-size:11px;color:var(--muted);margin-bottom:6px}
.poly-price{font-size:18px;font-weight:800;color:var(--accent)}
.poly-bar-track{height:6px;border-radius:3px;background:#ffffff0d;overflow:hidden;margin-top:6px}
.poly-bar-fill{height:100%;border-radius:3px;background:var(--accent)}
.poly-link{font-size:11px;color:var(--blue);margin-top:12px;display:block}
"""

def render_page(pick_entry, prematch_fix, home_stats, away_stats, poly):
    home = pick_entry["home"]
    away = pick_entry["away"]
    league = pick_entry["league"]
    league_name = pick_entry.get("leagueName", league)
    league_flag = pick_entry.get("leagueFlag", "")
    date_str = pick_entry.get("date", "")
    date_iso = pick_entry.get("dateIso", "")
    match_score = pick_entry.get("matchScore", 0)
    picks = pick_entry.get("picks", [])

    time_str = ""
    if prematch_fix:
        time_str = prematch_fix.get("time", "")

    # ── Section: Picks ────────────────────────────────────────────────────
    picks_html = ""
    for p in picks:
        conf = p.get("conf", "")
        if conf not in ("high", "medium"):
            continue
        odds  = p.get("odds")
        modds = p.get("modelOdds")
        val   = p.get("value")
        market = p.get("market", "—")
        icon   = p.get("icon", "🎯")

        kf = kelly_quarter(odds, modds)
        kelly_str = f"{kf*100:.1f}% Bankroll" if kf and kf > 0 else None

        sub_parts = []
        if odds:  sub_parts.append(f"Kurs: {fmt_odds(odds)}")
        if modds: sub_parts.append(f"Modell: {fmt_odds(modds)}")

        meta_html = conf_badge(conf)
        if odds:
            meta_html += f' <span class="odds-pill">{fmt_odds(odds)}</span>'
        if modds:
            meta_html += f' <span class="model-pill">⚙ {fmt_odds(modds)}</span>'
        if kelly_str:
            meta_html += f' <span class="kelly-pill">🏦 {kelly_str}</span>'
        if val == "value":
            meta_html += ' <span class="value-pill">✓ Value</span>'

        picks_html += f"""
        <div class="pick-card">
          <div class="pick-icon">{icon}</div>
          <div class="pick-main">
            <div class="pick-market">{market}</div>
          </div>
          <div class="pick-meta">{meta_html}</div>
        </div>"""

    if not picks_html:
        picks_html = '<p style="color:var(--muted);font-size:13px;">Keine High/Medium-Picks für dieses Spiel.</p>'

    # ── Section: Stats Comparison ─────────────────────────────────────────
    def stat_row(label, h_val, a_val, higher_is_better=True, fmt_fn=None):
        fmt = fmt_fn or (lambda x: f"{x:.2f}" if isinstance(x, float) else str(x) if x is not None else "—")
        try:
            h_f = float(h_val) if h_val is not None else None
            a_f = float(a_val) if a_val is not None else None
        except:
            h_f = a_f = None
        h_better = h_f is not None and a_f is not None and (
            (higher_is_better and h_f > a_f) or (not higher_is_better and h_f < a_f)
        )
        a_better = h_f is not None and a_f is not None and not h_better and h_f != a_f
        h_cls = "comp-val home better" if h_better else "comp-val home"
        a_cls = "comp-val away better" if a_better else "comp-val away"
        h_str = fmt(h_val) if h_val is not None else "—"
        a_str = fmt(a_val) if a_val is not None else "—"
        return f"""
        <div class="{h_cls}">{h_str}</div>
        <div class="comp-label">{label}</div>
        <div class="{a_cls}">{a_str}</div>"""

    hs = home_stats
    as_ = away_stats

    # Build stat rows — use home stats for home team, away stats for away team
    stats_html = f"""
    <div class="comp-grid">
      <div class="comp-header home" style="text-align:right">{home}</div>
      <div class="comp-header" style="text-align:center">Statistik</div>
      <div class="comp-header away">{away}</div>
      {stat_row("xG (Heim/Ausw.)", hs.get("xG_home"), as_.get("xG_away"), higher_is_better=True, fmt_fn=lambda x: f"{x:.2f}" if x else "—")}
      {stat_row("xGA (Heim/Ausw.)", hs.get("xGA_home"), as_.get("xGA_away"), higher_is_better=False, fmt_fn=lambda x: f"{x:.2f}" if x else "—")}
      {stat_row("Siegquote (Heim/Ausw.)", hs.get("homeWinRate"), as_.get("awayWinRate"), higher_is_better=True, fmt_fn=lambda x: pct(x) if x is not None else "—")}
      {stat_row("Clean Sheets (Heim/Ausw.)", hs.get("cleanSheetHome"), as_.get("cleanSheetAway"), higher_is_better=True, fmt_fn=lambda x: pct(x) if x is not None else "—")}
      {stat_row("Elo", hs.get("elo"), as_.get("elo"), higher_is_better=True, fmt_fn=lambda x: str(int(x)) if x else "—")}
      {stat_row("Formation", hs.get("formation"), as_.get("formation"), higher_is_better=True, fmt_fn=lambda x: str(x) if x else "—")}
    </div>"""

    # ── Section: Odds Movement ────────────────────────────────────────────
    odds_html = ""
    if prematch_fix:
        odds_cur  = prematch_fix.get("odds") or {}
        odds_open = prematch_fix.get("odds_open") or {}

        # Normalise opening odds keys (legacy format)
        open_hw = odds_open.get("hw") or odds_open.get("pinn_hw_fair")
        open_dr = odds_open.get("dr") or odds_open.get("pinn_dr_fair")
        open_aw = odds_open.get("aw") or odds_open.get("pinn_aw_fair")

        rows_data = [
            ("1 (Heimsieg)",    open_hw, odds_cur.get("hw") or odds_cur.get("pinn_hw")),
            ("X (Unentschieden)", open_dr, odds_cur.get("dr") or odds_cur.get("pinn_dr")),
            ("2 (Auswärtssieg)", open_aw, odds_cur.get("aw") or odds_cur.get("pinn_aw")),
            ("Over 2.5",        odds_open.get("o25"), odds_cur.get("o25")),
            ("Under 2.5",       odds_open.get("u25"), odds_cur.get("u25")),
        ]

        table_rows = ""
        for label, o_val, c_val in rows_data:
            if o_val is None and c_val is None:
                continue
            arrow_txt, direction = move_arrow(o_val, c_val)
            dir_cls = {"up": "move-up", "down": "move-down", "neutral": "move-neutral"}[direction]
            table_rows += f"""
            <tr>
              <td style="text-align:left;color:var(--text)">{label}</td>
              <td>{fmt_odds(o_val)}</td>
              <td>{fmt_odds(c_val)}</td>
              <td class="{dir_cls}" style="font-weight:700;font-size:12px">{arrow_txt}</td>
            </tr>"""

        if table_rows:
            odds_html = f"""
            <table class="odds-table">
              <thead><tr>
                <th style="text-align:left">Markt</th>
                <th>Opening</th>
                <th>Aktuell</th>
                <th>Bewegung</th>
              </tr></thead>
              <tbody>{table_rows}</tbody>
            </table>"""
        else:
            odds_html = '<p style="color:var(--muted);font-size:13px;">Keine Opening-Odds verfügbar.</p>'
    else:
        odds_html = '<p style="color:var(--muted);font-size:13px;">Keine Odds-Daten verfügbar.</p>'

    # ── Section: H2H ─────────────────────────────────────────────────────
    h2h_html = ""
    if prematch_fix and prematch_fix.get("h2h"):
        h2h = prematch_fix["h2h"]
        games = h2h.get("games", 0) or 1
        hw = h2h.get("homeWins", 0)
        dr = h2h.get("draws", 0)
        aw = h2h.get("awayWins", 0)
        hw_pct = hw / games * 100
        dr_pct = dr / games * 100
        aw_pct = aw / games * 100

        last = h2h.get("lastResults", [])
        dots = " ".join(h2h_dot(r) for r in last[:7])

        avg_goals = h2h.get("avgGoals", 0)
        over25 = h2h.get("over25Rate", 0)
        btts   = h2h.get("bttsRate", 0)

        h2h_html = f"""
        <div class="h2h-summary">
          <div class="h2h-stat"><div class="val" style="color:var(--accent)">{hw}</div><div class="lbl">{home}<br>Siege</div></div>
          <div class="h2h-stat"><div class="val" style="color:var(--yellow)">{dr}</div><div class="lbl">Unent-<br>schieden</div></div>
          <div class="h2h-stat"><div class="val" style="color:var(--purple)">{aw}</div><div class="lbl">{away}<br>Siege</div></div>
          <div class="h2h-stat"><div class="val">{avg_goals:.1f}</div><div class="lbl">∅ Tore<br>pro Spiel</div></div>
          <div class="h2h-stat"><div class="val">{int(over25*100)}%</div><div class="lbl">Over 2.5<br>Rate</div></div>
          <div class="h2h-stat"><div class="val">{int(btts*100)}%</div><div class="lbl">BTTS<br>Rate</div></div>
        </div>
        <div class="h2h-record">
          <div class="hw" style="width:{hw_pct:.1f}%"></div>
          <div class="dr" style="width:{dr_pct:.1f}%"></div>
          <div class="aw" style="width:{aw_pct:.1f}%"></div>
        </div>
        <div class="last-results-label">Letzte {len(last)} Direktbegegnungen (Heimteam-Perspektive)</div>
        <div class="h2h-dots">{dots}</div>"""
    else:
        h2h_html = '<p style="color:var(--muted);font-size:13px;">Keine H2H-Daten verfügbar.</p>'

    # ── Section: API Prediction ───────────────────────────────────────────
    pred_html = ""
    if prematch_fix and prematch_fix.get("apiPrediction"):
        ap = prematch_fix["apiPrediction"]

        def pred_bar(label, val, color):
            v = val or 0
            return f"""
            <div class="pred-bar-wrap">
              <div class="pred-bar-label"><span>{label}</span><span style="color:{color};font-weight:700">{v}%</span></div>
              <div class="pred-bar-track"><div class="pred-bar-fill" style="width:{v}%;background:{color}"></div></div>
            </div>"""

        pred_html = pred_bar(f"Heimsieg ({home})", ap.get("pctHome"), "#00d4a1")
        pred_html += pred_bar("Unentschieden", ap.get("pctDraw"), "#e3b341")
        pred_html += pred_bar(f"Auswärtssieg ({away})", ap.get("pctAway"), "#a78bfa")

        # Poisson
        ph = ap.get("poissonHome")
        pa = ap.get("poissonAway")
        if ph and pa:
            pred_html += f"""<div style="margin-top:16px;padding:12px;background:var(--card2);border-radius:8px;font-size:12px;color:var(--muted)">
              <strong style="color:var(--text)">Poisson-Modell</strong><br>
              {home}: {ph}% · {away}: {pa}%
            </div>"""

        # Comparative metrics
        cf = ap.get("compForm", {})
        ca = ap.get("compAtt", {})
        cd = ap.get("compDef", {})
        if cf or ca or cd:
            pred_html += f"""<div style="margin-top:12px;display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px">"""
            for name, data, color in [("Form", cf, "#58a6ff"), ("Angriff", ca, "#3fb950"), ("Abwehr", cd, "#f85149")]:
                if data:
                    hv = data.get("home", 50)
                    av = data.get("away", 50)
                    pred_html += f"""<div style="background:var(--card2);border-radius:8px;padding:10px;font-size:12px">
                      <div style="color:var(--muted);margin-bottom:6px">{name}</div>
                      <div style="display:flex;justify-content:space-between;font-weight:700">
                        <span style="color:{color}">{hv}%</span>
                        <span style="color:var(--muted)">vs</span>
                        <span style="color:{color}">{av}%</span>
                      </div>
                    </div>"""
            pred_html += "</div>"
    else:
        pred_html = '<p style="color:var(--muted);font-size:13px;">Keine Modell-Prognose verfügbar.</p>'

    # ── Section: Injuries ─────────────────────────────────────────────────
    inj_html = ""
    if prematch_fix:
        inj = prematch_fix.get("injuries", {})
        home_inj = inj.get("home", [])
        away_inj = inj.get("away", [])

        def render_inj(players, team_name):
            html = f'<div class="inj-team-label">{team_name}</div>'
            if not players:
                html += '<div class="no-injuries">✓ Keine gemeldeten Ausfälle</div>'
            else:
                for pl in players[:8]:  # cap at 8
                    pos = pl.get("position", "?")
                    name = pl.get("player", "?")
                    reason = pl.get("reason", "") or pl.get("type", "")
                    html += f'<div class="inj-player">{pos} · <strong>{name}</strong><div class="inj-reason">{reason}</div></div>'
            return html

        inj_html = f"""
        <div class="inj-grid">
          <div>{render_inj(home_inj, home)}</div>
          <div>{render_inj(away_inj, away)}</div>
        </div>"""
    else:
        inj_html = '<p style="color:var(--muted);font-size:13px;">Keine Verletzungsdaten verfügbar.</p>'

    # ── Section: Polymarket ───────────────────────────────────────────────
    poly_html = ""
    if poly:
        markets = poly.get("markets", {})
        event_url = poly.get("eventUrl", "")

        # Group by type
        show_markets = [
            ("Heimsieg", "🟢"), ("Unentschieden", "🟡"), ("Auswärtssieg", "🟣"),
            ("Over 2.5 Tore", "⬆"), ("Under 2.5 Tore", "⬇"),
            ("Beide Teams treffen", "⚽"), ("Beide Teams treffen: Nein", "🚫"),
            ("Over 3.5 Tore", "⬆⬆"), ("Over 1.5 Tore", "⬆"),
        ]
        cards = ""
        for name, icon in show_markets:
            price = markets.get(name)
            if price is None:
                continue
            pct_val = int(round(price * 100))
            cards += f"""
            <div class="poly-card">
              <div class="poly-market-name">{icon} {name}</div>
              <div class="poly-price">{pct_val}%</div>
              <div class="poly-bar-track"><div class="poly-bar-fill" style="width:{pct_val}%"></div></div>
            </div>"""

        if cards:
            link = f'<a class="poly-link" href="{event_url}" target="_blank">→ Auf Polymarket ansehen</a>' if event_url else ""
            poly_html = f'<div class="poly-grid">{cards}</div>{link}'
        else:
            poly_html = '<p style="color:var(--muted);font-size:13px;">Keine Polymarket-Preise verfügbar.</p>'
    else:
        poly_section = ""  # whole section hidden if no poly data

    # ── Assemble HTML ─────────────────────────────────────────────────────
    meta_chips = []
    if date_str:
        meta_chips.append(f'<span class="meta-chip">📅 {date_str}</span>')
    if time_str:
        meta_chips.append(f'<span class="meta-chip">🕐 {time_str} Uhr</span>')
    meta_chips.append(f'<span class="score-badge">Score {match_score:.1f}</span>')
    meta_html_str = " ".join(meta_chips)

    poly_section_html = ""
    if poly and poly_html:
        poly_section_html = f"""
      <div class="section">
        <div class="section-title">🟣 Polymarket-Preise</div>
        {poly_html}
      </div>"""

    generated_ts = datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC")

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{home} vs {away} — CocoBet</title>
  <style>{CSS}</style>
</head>
<body>

<nav class="top-nav">
  <a class="back" href="../betting-dashboard.html">← Dashboard</a>
  <span class="league-tag">{league_flag} {league_name}</span>
</nav>

<div class="match-header">
  <div class="teams-row">
    <div class="team-name home">{home}</div>
    <div class="vs-badge">vs</div>
    <div class="team-name away">{away}</div>
  </div>
  <div class="match-meta">{meta_html_str}</div>
</div>

<div class="content">

  <div class="section">
    <div class="section-title">🎯 Picks</div>
    {picks_html}
  </div>

  <div class="section">
    <div class="section-title">📊 Team-Vergleich</div>
    {stats_html}
  </div>

  <div class="section">
    <div class="section-title">📈 Linien-Bewegung (Opening vs. Aktuell)</div>
    {odds_html}
  </div>

  <div class="section">
    <div class="section-title">🔄 Direktvergleich (H2H)</div>
    {h2h_html}
  </div>

  <div class="section">
    <div class="section-title">🤖 Modell-Prognose</div>
    {pred_html}
  </div>

  <div class="section">
    <div class="section-title">🏥 Verletzungen & Ausfälle</div>
    {inj_html}
  </div>

  {poly_section_html}

  <div style="text-align:center;font-size:11px;color:var(--muted);margin-top:20px">
    Generiert: {generated_ts} · <a href="../betting-dashboard.html">← Zurück zum Dashboard</a>
  </div>

</div>
</body>
</html>"""

    return html


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    generated = 0
    skipped   = 0

    for entry in picks_list:
        home     = entry["home"]
        away     = entry["away"]
        league   = entry["league"]
        date_iso = entry.get("dateIso", "")

        # Only generate pages for fixtures with at least one high/medium pick
        picks = entry.get("picks", [])
        good_picks = [p for p in picks if p.get("conf") in ("high", "medium")]
        if not good_picks:
            skipped += 1
            continue

        prematch_fix = get_prematch(home, away)
        home_stats   = get_stats(league, home)
        away_stats   = get_stats(league, away)
        poly         = get_poly(home, away)

        html = render_page(entry, prematch_fix, home_stats, away_stats, poly)

        slug = f"{slugify(home)}-vs-{slugify(away)}-{date_iso}"
        out_path = os.path.join(OUT, f"{slug}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)

        generated += 1
        print(f"  ✓ {home} vs {away}  →  matches/{slug}.html")

    print(f"\n✅ {generated} Seiten generiert, {skipped} ohne gültige Picks übersprungen.")
    print(f"   Output: {OUT}/")


if __name__ == "__main__":
    main()
