#!/usr/bin/env python3
"""
tiktok_card_templates.py — CocoBet TikTok-Card HTML-Templates
================================================================

Zwei Karten-Typen:
  · hook_card(...)  → Mystery-Hook für die ersten 3-5 Sek im TikTok
                       Riesige Zahl, Box mit Glow, "Wer ist das?", 1 Highlight
  · info_card(...)  → Reveal mit Details — Flagge, Name, 3 Stat-Boxen, Closing-Line

Stil basiert auf Lucas' Screenshot (Yamal Hook-Card):
  · Dark Theme #0a0e18 / #080d18
  · Akzent-Grün #00d4a1 oder anderes je nach Angle
  · Box mit subtle radial glow um die Riesenzahl
  · 360×640 vertical (TikTok-Format)

Theme-Mapping (Angle → Farbe + Badge-Text):
  naechste_aera      → grün     "● NÄCHSTE ÄRA"
  letzte_wm          → rot      "🔴 LETZTE WM"
  geheimfavorit      → lila     "🟣 GEHEIMFAVORIT"
  dark_horse         → orange   "🟠 DARK HORSE"
  hidden_gem         → türkis   "💎 HIDDEN GEM"
  verlierer_garantie → grau     "⬇️ VERLIERER-GARANTIE"
  killer_stat        → gelb     "⚡ KILLER-STAT"
"""
from __future__ import annotations

import base64
from pathlib import Path

# ── Logo als base64-Data-URL einbetten ────────────────────────────────────────
# So sind die HTMLs self-contained — Playwright braucht keinen extra file-Pfad
# und der TikTok-Card-Look hängt nicht von einem Asset-Ordner ab.
_LOGO_PATH = Path(__file__).parent / "cocobet-logo.png"
_LOGO_DATA_URL = ""
try:
    if _LOGO_PATH.exists():
        _b64 = base64.b64encode(_LOGO_PATH.read_bytes()).decode("ascii")
        _LOGO_DATA_URL = f"data:image/png;base64,{_b64}"
except Exception:
    _LOGO_DATA_URL = ""


def _logo_block(size: int = 54) -> str:
    """Liefert <img>-Tag oder Fallback-Kreis."""
    if _LOGO_DATA_URL:
        return (
            f'<img src="{_LOGO_DATA_URL}" alt="CocoBet" '
            f'style="width:{size}px;height:{size}px;border-radius:50%;'
            f'object-fit:cover;box-shadow:0 0 24px rgba(245,197,24,0.20);'
            f'display:block;">'
        )
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:50%;'
        f'background:#f5c518;display:flex;align-items:center;justify-content:center;'
        f'font-size:9px;font-weight:900;color:#000;letter-spacing:1px;'
        f'box-shadow:0 0 24px rgba(245,197,24,0.25);">COCO<br>BET</div>'
    )

# ── Theme-Definitionen ────────────────────────────────────────────────────────
THEMES = {
    "naechste_aera": {
        "accent": "#22c55e",      # grün
        "accentRgb": "34,197,94",
        "badge": "● WM 2026 · NÄCHSTE ÄRA",
        "badgeBg": "rgba(34,197,94,0.10)",
        "badgeBorder": "rgba(34,197,94,0.35)",
    },
    "letzte_wm": {
        "accent": "#f85149",
        "accentRgb": "248,81,73",
        "badge": "🔴 LETZTE WM",
        "badgeBg": "rgba(248,81,73,0.10)",
        "badgeBorder": "rgba(248,81,73,0.35)",
    },
    "geheimfavorit": {
        "accent": "#a371f7",
        "accentRgb": "163,113,247",
        "badge": "🟣 GEHEIMFAVORIT",
        "badgeBg": "rgba(163,113,247,0.10)",
        "badgeBorder": "rgba(163,113,247,0.35)",
    },
    "dark_horse": {
        "accent": "#f0883e",
        "accentRgb": "240,136,62",
        "badge": "🟠 DARK HORSE",
        "badgeBg": "rgba(240,136,62,0.10)",
        "badgeBorder": "rgba(240,136,62,0.35)",
    },
    "hidden_gem": {
        "accent": "#4cc9f0",
        "accentRgb": "76,201,240",
        "badge": "💎 HIDDEN GEM",
        "badgeBg": "rgba(76,201,240,0.10)",
        "badgeBorder": "rgba(76,201,240,0.35)",
    },
    "verlierer_garantie": {
        "accent": "#8b949e",
        "accentRgb": "139,148,158",
        "badge": "⬇️ VERLIERER-GARANTIE",
        "badgeBg": "rgba(139,148,158,0.10)",
        "badgeBorder": "rgba(139,148,158,0.35)",
    },
    "killer_stat": {
        "accent": "#f5c518",
        "accentRgb": "245,197,24",
        "badge": "⚡ KILLER-STAT",
        "badgeBg": "rgba(245,197,24,0.10)",
        "badgeBorder": "rgba(245,197,24,0.35)",
    },
    "bizarre": {
        "accent": "#ec4899",         # pink-magenta für die Fun-Rubrik
        "accentRgb": "236,72,153",
        "badge": "🤡 BIZARRE-QUOTE",
        "badgeBg": "rgba(236,72,153,0.10)",
        "badgeBorder": "rgba(236,72,153,0.40)",
    },
    "player_pick": {
        "accent": "#00d4a1",          # mintgrün — wie Lucas-Yamal-Hook
        "accentRgb": "0,212,161",
        "badge": "🎯 SPIELER-PICK",
        "badgeBg": "rgba(0,212,161,0.10)",
        "badgeBorder": "rgba(0,212,161,0.40)",
    },
    "track_record": {
        "accent": "#3fb950",          # echtes GitHub-Grün
        "accentRgb": "63,185,80",
        "badge": "📊 TRACK-RECORD",
        "badgeBg": "rgba(63,185,80,0.10)",
        "badgeBorder": "rgba(63,185,80,0.40)",
    },
    "track_record_neg": {
        "accent": "#f85149",
        "accentRgb": "248,81,73",
        "badge": "📊 TRACK-RECORD",
        "badgeBg": "rgba(248,81,73,0.10)",
        "badgeBorder": "rgba(248,81,73,0.40)",
    },
    "daily_picks": {
        "accent": "#00d4a1",
        "accentRgb": "0,212,161",
        "badge": "⚡ DAILY PICKS",
        "badgeBg": "rgba(0,212,161,0.10)",
        "badgeBorder": "rgba(0,212,161,0.40)",
    },
}


def hook_card(
    theme: str,
    big_number: str,
    sub_title: str,
    hook_line_1: str,
    hook_line_2: str,
    mystery_question: str,
    highlight_fact: str,
    cta: str = "ANTWORT IM VIDEO",
    series_tag: str | None = None,
) -> str:
    """
    Hook-Card im Lucas-Style.

    Args:
        theme:           Theme-Key aus THEMES (z.B. "naechste_aera")
        big_number:      Riesige Zahl im Center-Glow (z.B. "19" oder "1.37")
        sub_title:       Unter der Zahl (z.B. "JAHRE ALT · ERSTE WM")
        hook_line_1:     Erster Hook-Satz (z.B. "Bereits Stammspieler")
        hook_line_2:     Zweiter Hook-Satz (z.B. "bei Nr. 2 der Welt.")
        mystery_question: Curiosity-Frage (z.B. "Wer ist das?")
        highlight_fact:  Der eine Killer-Fakt im Highlight-Kasten
        cta:             Call-to-Action unten
        series_tag:      z.B. "TAG 2 / 7" für Story-Serien (None für Standalone)

    Liefert: kompletter HTML-String, 360×640
    """
    t = THEMES.get(theme, THEMES["naechste_aera"])
    accent = t["accent"]
    rgb = t["accentRgb"]

    series_html = ""
    if series_tag:
        series_html = (
            f'<div style="position:absolute;top:14px;left:18px;font-size:9px;'
            f'font-weight:800;letter-spacing:1.5px;color:{accent};opacity:.7;'
            f'border:1px solid rgba({rgb},.3);border-radius:6px;padding:3px 8px;">'
            f'{series_tag}</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Hook</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  background:#0a0e18;
  display:flex; align-items:center; justify-content:center;
  min-height:100vh;
  font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}}
.card {{
  width:360px; height:640px;
  background:
    radial-gradient(circle at 50% 38%, rgba({rgb},0.10) 0%, transparent 45%),
    linear-gradient(180deg, #0a0e18 0%, #080d18 100%);
  border-radius:24px;
  padding:34px 28px 28px;
  position:relative; overflow:hidden;
  display:flex; flex-direction:column;
  border:1px solid rgba(255,255,255,0.04);
  background-image:
    radial-gradient(circle at 50% 38%, rgba({rgb},0.10) 0%, transparent 45%),
    linear-gradient(rgba(255,255,255,0.014) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.014) 1px, transparent 1px);
  background-size: auto, 24px 24px, 24px 24px;
}}

.logo {{
  display:flex; justify-content:center; margin-bottom:24px;
}}

.badge {{
  display:flex; justify-content:center; margin-bottom:30px;
}}
.badge-inner {{
  font-size:11px; font-weight:700; letter-spacing:2px;
  color:{accent};
  background:{t["badgeBg"]};
  border:1px solid {t["badgeBorder"]};
  border-radius:24px; padding:9px 22px;
}}

.number-box {{
  border:1px solid rgba({rgb},0.30);
  border-radius:14px;
  padding:34px 20px 28px;
  text-align:center;
  margin-bottom:28px;
  background:rgba({rgb},0.025);
  box-shadow:
    inset 0 0 32px rgba({rgb},0.06),
    0 0 48px rgba({rgb},0.08);
  position:relative;
}}
.number {{
  font-size:104px; font-weight:900;
  color:{accent}; line-height:1;
  letter-spacing:-3px;
  text-shadow: 0 0 28px rgba({rgb},0.45);
}}
.number-sub {{
  font-size:11px; font-weight:600;
  color:rgba(255,255,255,0.32);
  margin-top:10px; letter-spacing:2.5px;
  text-transform:uppercase;
}}

.hook {{
  text-align:center; margin-bottom:14px;
  font-size:22px; font-weight:800;
  color:#fff; line-height:1.3;
  letter-spacing:-.3px;
}}
.hook .acc {{ color:{accent}; }}
.hook .yellow {{ color:#f5c518; }}

.mystery {{
  text-align:center;
  font-size:16px; font-weight:600;
  color:rgba(255,255,255,0.45);
  margin-bottom:28px;
}}

.highlight {{
  border:1px solid rgba(245,197,24,0.35);
  border-radius:10px;
  padding:12px 16px;
  text-align:center;
  background:rgba(245,197,24,0.06);
  margin-bottom:auto;
}}
.highlight-text {{
  font-size:13px; font-weight:700;
  color:#f5c518;
}}

.cta {{
  font-size:11px; font-weight:600;
  color:rgba(255,255,255,0.25);
  text-align:center;
  letter-spacing:3px;
  border-top:1px solid rgba(255,255,255,0.05);
  padding-top:14px; margin-top:18px;
}}

.brand {{
  font-size:10px; font-weight:700;
  color:rgba(255,255,255,0.18);
  text-align:center;
  letter-spacing:4px;
  margin-top:14px;
  text-transform:uppercase;
}}
</style>
</head>
<body>
<div class="card">
  {series_html}
  <div class="logo">{_logo_block(54)}</div>
  <div class="badge"><div class="badge-inner">{t["badge"]}</div></div>

  <div class="number-box">
    <div class="number">{big_number}</div>
    <div class="number-sub">{sub_title}</div>
  </div>

  <div class="hook">
    {hook_line_1}<br>
    {hook_line_2}
  </div>

  <div class="mystery">{mystery_question}</div>

  <div class="highlight">
    <div class="highlight-text">⚡ {highlight_fact}</div>
  </div>

  <div class="cta">{cta}</div>
  <div class="brand">cocobet</div>
</div>
</body>
</html>
"""


def bizarre_info_card(
    theme: str,
    flag: str,
    team_name: str,
    quote_str: str,         # z.B. "1 : 3.501"
    chance_pct: str,        # z.B. "0,029 %"
    comparisons: list,      # [(emoji, text, "0,2 %"), ...]
    closing_line: str,
    quote_line: str,
    series_tag: str | None = None,
) -> str:
    """
    Spezielles Layout für Bizarre-Quoten-Karten:
    - Hero: riesige Chance-% + Quote
    - Liste von 5-6 absurden Vergleichen mit Probability-Pill rechts
    - Closing-Hook + Quote
    """
    t = THEMES.get(theme, THEMES["bizarre"])
    accent = t["accent"]
    rgb = t["accentRgb"]

    series_html = ""
    if series_tag:
        series_html = (
            f'<div style="position:absolute;top:14px;left:18px;font-size:9px;'
            f'font-weight:800;letter-spacing:1.5px;color:{accent};opacity:.7;'
            f'border:1px solid rgba({rgb},.3);border-radius:6px;padding:3px 8px;">'
            f'{series_tag}</div>'
        )

    comp_html = ""
    for emoji, text, prob in comparisons:
        comp_html += (
            f'<div style="display:flex;align-items:center;gap:8px;padding:8px 4px;'
            f'border-bottom:1px solid rgba(255,255,255,0.05);">'
            f'<div style="font-size:18px;flex-shrink:0;width:24px;text-align:center;">{emoji}</div>'
            f'<div style="font-size:11px;color:rgba(255,255,255,.82);line-height:1.4;flex:1;">{text}</div>'
            f'<div style="font-size:11px;font-weight:800;color:{accent};font-family:\'SF Mono\',Menlo,monospace;'
            f'background:rgba({rgb},0.10);border:1px solid rgba({rgb},0.25);'
            f'border-radius:5px;padding:2px 7px;flex-shrink:0;">{prob}</div>'
            f'</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><title>Bizarre Info</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0a0e18; display:flex; align-items:center; justify-content:center; min-height:100vh;
       font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
.card {{
  width:360px; height:640px;
  background:
    radial-gradient(circle at 50% 22%, rgba({rgb},0.10) 0%, transparent 50%),
    linear-gradient(180deg, #0a0e18 0%, #080d18 100%);
  background-image:
    radial-gradient(circle at 50% 22%, rgba({rgb},0.10) 0%, transparent 50%),
    linear-gradient(rgba(255,255,255,0.014) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.014) 1px, transparent 1px);
  background-size: auto, 24px 24px, 24px 24px;
  border-radius:24px; padding:24px 22px 20px;
  position:relative; overflow:hidden;
  display:flex; flex-direction:column;
  border:1px solid rgba(255,255,255,0.04);
}}
.top {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; }}
.brand-top {{ font-size:11px; font-weight:800; letter-spacing:3px; color:#f5c518; }}
.badge-top {{ font-size:10px; font-weight:700; letter-spacing:1px; color:{accent};
  background:{t["badgeBg"]}; border:1px solid {t["badgeBorder"]}; border-radius:18px; padding:5px 12px; }}

.flag {{ font-size:42px; text-align:center; line-height:1; margin-bottom:4px; }}
.name {{ font-size:18px; font-weight:800; color:#fff; text-align:center; letter-spacing:-.3px; margin-bottom:10px; }}

.hero-box {{ border:1px solid rgba({rgb},0.30); background:rgba({rgb},0.05);
  border-radius:12px; padding:14px 16px 12px; text-align:center; margin-bottom:14px;
  box-shadow: inset 0 0 28px rgba({rgb},0.06); }}
.hero-pct {{ font-size:46px; font-weight:900; color:{accent}; line-height:1; letter-spacing:-2px;
  text-shadow: 0 0 22px rgba({rgb},0.40); }}
.hero-quote {{ font-size:11px; color:rgba(255,255,255,.40); margin-top:5px; letter-spacing:1.5px;
  text-transform:uppercase; font-weight:600; }}
.hero-quote strong {{ color:rgba(255,255,255,.75); }}

.list-title {{ font-size:9px; color:rgba(255,255,255,.32); text-align:center; letter-spacing:1.8px;
  text-transform:uppercase; margin-bottom:6px; font-weight:700; }}
.comp-list {{ margin-bottom:14px; }}

.closing-box {{ border:1px solid rgba({rgb},0.25); background:rgba({rgb},0.05);
  border-radius:9px; padding:10px 12px; margin-bottom:12px; }}
.closing-text {{ font-size:11px; color:rgba(255,255,255,.78); line-height:1.55; }}
.closing-text strong {{ color:{accent}; }}

.quote {{ font-size:14px; font-weight:800; color:#fff; text-align:center; line-height:1.35;
  margin-bottom:auto; }}
.quote .acc {{ color:{accent}; }}

.footer {{ display:flex; justify-content:space-between; border-top:1px solid rgba(255,255,255,0.05);
  padding-top:10px; margin-top:14px; }}
.footer .ft {{ font-size:9px; color:rgba(255,255,255,.22); }}
</style></head>
<body>
<div class="card">
  {series_html}
  <div class="top">
    <div class="brand-top">COCOBET</div>
    <div class="badge-top">{t["badge"]}</div>
  </div>

  <div class="flag">{flag}</div>
  <div class="name">{team_name} wird Weltmeister</div>

  <div class="hero-box">
    <div class="hero-pct">{chance_pct}</div>
    <div class="hero-quote">Chance <strong>{quote_str}</strong></div>
  </div>

  <div class="list-title">Was eher passiert</div>
  <div class="comp-list">{comp_html}</div>

  <div class="closing-box">
    <div class="closing-text">{closing_line}</div>
  </div>

  <div class="quote">{quote_line}</div>

  <div class="footer">
    <div class="ft">Outright-Wahrscheinlichkeiten · 02.06.26</div>
    <div class="ft">cocobet</div>
  </div>
</div>
</body>
</html>
"""


def info_card(
    theme: str,
    flag: str,
    name: str,
    role_line: str,
    stat1_val: str, stat1_lbl: str,
    stat2_val: str, stat2_lbl: str,
    stat3_val: str, stat3_lbl: str,
    closing_line: str,
    quote_line: str,
    data_source: str = "",
    series_tag: str | None = None,
) -> str:
    """
    Info-Card — Reveal mit Details.

    Args:
        theme:        Theme-Key
        flag:         Flagge-Emoji (z.B. "🇪🇸")
        name:         Vollständiger Name
        role_line:    "SPANIEN · FLÜGEL" o.ä.
        stat1-3_val:  Drei zentrale Stats (Tore, Assists, Score/90 etc.)
        stat1-3_lbl:  Labels darunter
        closing_line: Faktischer Closing-Satz (z.B. "Mit 16 jüngster EM-Torschütze")
        quote_line:   Pointierter Hook am Ende (z.B. "Ronaldo's letzte. Yamal's erste.")
        data_source:  Klein unten, z.B. "Daten: Spanien 2024/25"
        series_tag:   z.B. "TAG 2 / 7"
    """
    t = THEMES.get(theme, THEMES["naechste_aera"])
    accent = t["accent"]
    rgb = t["accentRgb"]

    series_html = ""
    if series_tag:
        series_html = (
            f'<div style="position:absolute;top:14px;left:18px;font-size:9px;'
            f'font-weight:800;letter-spacing:1.5px;color:{accent};opacity:.7;'
            f'border:1px solid rgba({rgb},.3);border-radius:6px;padding:3px 8px;">'
            f'{series_tag}</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Info</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  background:#0a0e18;
  display:flex; align-items:center; justify-content:center;
  min-height:100vh;
  font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}}
.card {{
  width:360px; height:640px;
  background:
    radial-gradient(circle at 50% 30%, rgba({rgb},0.08) 0%, transparent 50%),
    linear-gradient(180deg, #0a0e18 0%, #080d18 100%);
  background-image:
    radial-gradient(circle at 50% 30%, rgba({rgb},0.08) 0%, transparent 50%),
    linear-gradient(rgba(255,255,255,0.014) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.014) 1px, transparent 1px);
  background-size: auto, 24px 24px, 24px 24px;
  border-radius:24px;
  padding:26px 24px 22px;
  position:relative; overflow:hidden;
  display:flex; flex-direction:column;
  border:1px solid rgba(255,255,255,0.04);
}}
.top {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; }}
.brand-top {{ font-size:11px; font-weight:800; letter-spacing:3px; color:#f5c518; }}
.badge-top {{
  font-size:10px; font-weight:700; letter-spacing:1px;
  color:{accent};
  background:{t["badgeBg"]};
  border:1px solid {t["badgeBorder"]};
  border-radius:18px; padding:5px 12px;
}}

.flag {{ font-size:54px; text-align:center; margin-bottom:6px; line-height:1; }}
.name {{
  font-size:28px; font-weight:900; color:#fff;
  text-align:center; letter-spacing:-.5px; margin-bottom:4px;
}}
.role {{
  text-align:center; font-size:11px; color:rgba(255,255,255,0.35);
  letter-spacing:2.5px; text-transform:uppercase; margin-bottom:22px;
}}

.divider {{
  height:1px; background:rgba(255,255,255,0.06);
  margin-bottom:20px;
}}

.stats {{
  display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; margin-bottom:22px;
}}
.stat {{
  background:rgba(255,255,255,0.025);
  border:1px solid rgba(255,255,255,0.06);
  border-radius:10px;
  padding:14px 8px; text-align:center;
}}
.stat-val {{
  font-size:30px; font-weight:900; line-height:1;
  color:{accent};
}}
.stat-val.blue {{ color:#60a5fa; }}
.stat-val.yellow {{ color:#f5c518; }}
.stat-lbl {{
  font-size:9px; font-weight:600;
  color:rgba(255,255,255,0.32);
  letter-spacing:1px; text-transform:uppercase;
  margin-top:8px; line-height:1.4;
}}

.fact-box {{
  border:1px solid rgba({rgb},0.30);
  background:rgba({rgb},0.06);
  border-radius:10px;
  padding:14px 16px; margin-bottom:18px;
}}
.fact-box .text {{
  font-size:13px; color:rgba(255,255,255,0.85); line-height:1.55;
}}
.fact-box .text strong {{ color:{accent}; }}

.quote {{
  font-size:16px; font-weight:800; color:#fff;
  text-align:center; line-height:1.35;
  margin-bottom:auto;
}}
.quote .acc {{ color:{accent}; }}

.footer {{
  display:flex; justify-content:space-between;
  border-top:1px solid rgba(255,255,255,0.05);
  padding-top:12px; margin-top:16px;
}}
.footer .ft {{ font-size:9px; color:rgba(255,255,255,0.22); }}
</style>
</head>
<body>
<div class="card">
  {series_html}
  <div class="top">
    <div class="brand-top">COCOBET</div>
    <div class="badge-top">{t["badge"]}</div>
  </div>

  <div class="flag">{flag}</div>
  <div class="name">{name}</div>
  <div class="role">{role_line}</div>

  <div class="divider"></div>

  <div class="stats">
    <div class="stat">
      <div class="stat-val">{stat1_val}</div>
      <div class="stat-lbl">{stat1_lbl}</div>
    </div>
    <div class="stat">
      <div class="stat-val blue">{stat2_val}</div>
      <div class="stat-lbl">{stat2_lbl}</div>
    </div>
    <div class="stat">
      <div class="stat-val yellow">{stat3_val}</div>
      <div class="stat-lbl">{stat3_lbl}</div>
    </div>
  </div>

  <div class="fact-box">
    <div class="text">{closing_line}</div>
  </div>

  <div class="quote">{quote_line}</div>

  <div class="footer">
    <div class="ft">{data_source}</div>
    <div class="ft">cocobet</div>
  </div>
</div>
</body>
</html>
"""


def player_pick_card(
    player_name: str,
    team_flag: str,
    team_name: str,
    opponent_flag: str,
    opponent_name: str,
    market_label: str,         # "Anytime Scorer", "Schüsse aufs Tor Over 1.5"
    odds: float,               # z.B. 2.50  (NICHT angezeigt wenn hide_odds=True)
    bookmaker: str,            # "Pinnacle", "bet365" — wird kapitalisiert
    reason_line: str,          # 1-Liner Begründung, max ~80 Zeichen
    confidence: str = "high",  # "high" | "medium" | "low"
    series_tag: str | None = None,
    kickoff_label: str = "",   # "Do 11.06. · 21:00"
    hide_odds: bool = True,    # AUDIT-Fix 05.06.2026: Default true — Konfidenz statt Quote
) -> str:
    """
    Player-Pick-Card im Lucas-Yamal-Style:
    - Top: Liga-Badge, Anpfiff
    - Hero: Spielername riesig + Markt
    - Hero-Box: Quote als große Zahl + Confidence-Pill
    - Match-Zeile: Flag vs Flag mit Namen
    - Reason: 1-Zeiler in Akzentbox
    - Closing-Hook + Footer

    Output: 360×640 vertical HTML (TikTok-Format).
    """
    t = THEMES["player_pick"]
    accent = t["accent"]
    rgb = t["accentRgb"]

    conf_label = {"high": "HOHE KONFIDENZ", "medium": "MITTLERE KONFIDENZ",
                  "low": "BEOBACHTEN"}.get(confidence, "PICK")

    book_disp = (bookmaker or "").replace("_", " ").title() or "Markt"

    series_html = ""
    if series_tag:
        series_html = (
            f'<div style="position:absolute;top:14px;left:18px;font-size:9px;'
            f'font-weight:800;letter-spacing:1.5px;color:{accent};opacity:.7;'
            f'border:1px solid rgba({rgb},.3);border-radius:6px;padding:3px 8px;">'
            f'{series_tag}</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><title>Spieler-Pick</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0a0e18; display:flex; align-items:center; justify-content:center; min-height:100vh;
       font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
.card {{
  width:360px; height:640px;
  background:
    radial-gradient(circle at 50% 30%, rgba({rgb},0.12) 0%, transparent 55%),
    linear-gradient(180deg, #0a0e18 0%, #080d18 100%);
  background-image:
    radial-gradient(circle at 50% 30%, rgba({rgb},0.12) 0%, transparent 55%),
    linear-gradient(rgba(255,255,255,0.012) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.012) 1px, transparent 1px);
  background-size: auto, 24px 24px, 24px 24px;
  border-radius:24px; padding:24px 22px 20px;
  position:relative; overflow:hidden;
  display:flex; flex-direction:column;
  border:1px solid rgba(255,255,255,0.04);
}}
.top {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:18px; }}
.brand-top {{ font-size:11px; font-weight:800; letter-spacing:3px; color:#f5c518; }}
.badge-top {{ font-size:10px; font-weight:700; letter-spacing:1px; color:{accent};
  background:{t["badgeBg"]}; border:1px solid {t["badgeBorder"]}; border-radius:18px; padding:5px 12px; }}

.kickoff-line {{ font-size:9px; color:rgba(255,255,255,.32); letter-spacing:1.5px;
  text-transform:uppercase; text-align:center; margin-bottom:14px; font-weight:600; }}

.player-name {{ font-size:30px; font-weight:900; color:#fff; text-align:center;
  letter-spacing:-1px; line-height:1.05; margin-bottom:8px; }}
.player-team {{ font-size:13px; color:rgba(255,255,255,.55); text-align:center;
  letter-spacing:0.3px; margin-bottom:18px; }}
.player-team .flag {{ font-size:17px; vertical-align:middle; margin-right:5px; }}

.market-pill {{ display:inline-block; font-size:10px; font-weight:800; letter-spacing:1.2px;
  color:rgba(255,255,255,.7); background:rgba(255,255,255,.05);
  border:1px solid rgba(255,255,255,.10); border-radius:14px; padding:5px 12px;
  margin:0 auto 10px; }}
.market-row {{ text-align:center; }}

.hero-box {{ border:1px solid rgba({rgb},0.35); background:rgba({rgb},0.06);
  border-radius:14px; padding:18px 16px 14px; text-align:center; margin-bottom:14px;
  box-shadow: inset 0 0 32px rgba({rgb},0.07); }}
.hero-label {{ font-size:9px; color:rgba(255,255,255,.40); letter-spacing:1.8px;
  text-transform:uppercase; font-weight:700; margin-bottom:4px; }}
.hero-odds {{ font-size:56px; font-weight:900; color:{accent}; line-height:1;
  letter-spacing:-2px; text-shadow: 0 0 28px rgba({rgb},0.45); }}
.hero-book {{ font-size:10px; color:rgba(255,255,255,.45); margin-top:6px; letter-spacing:1.2px;
  text-transform:uppercase; font-weight:600; }}
.hero-book strong {{ color:rgba(255,255,255,.78); }}

.match-row {{ display:flex; align-items:center; justify-content:center; gap:10px;
  margin-bottom:14px; padding:10px 6px;
  border-top:1px solid rgba(255,255,255,0.05);
  border-bottom:1px solid rgba(255,255,255,0.05); }}
.match-side {{ display:flex; align-items:center; gap:6px; }}
.match-side .flag {{ font-size:18px; }}
.match-side .name {{ font-size:11px; color:rgba(255,255,255,.72); font-weight:600; }}
.match-vs {{ font-size:9px; color:rgba(255,255,255,.30); letter-spacing:2px; font-weight:700; }}

.reason-box {{ border:1px solid rgba({rgb},0.22); background:rgba({rgb},0.05);
  border-radius:9px; padding:12px 14px; margin-bottom:auto; }}
.reason-label {{ font-size:8.5px; color:{accent}; letter-spacing:1.8px;
  text-transform:uppercase; font-weight:800; margin-bottom:4px; }}
.reason-text {{ font-size:11.5px; color:rgba(255,255,255,.82); line-height:1.5; }}

.conf-pill {{ display:inline-block; font-size:9px; font-weight:800; letter-spacing:1.5px;
  color:{accent}; background:rgba({rgb},0.10); border:1px solid rgba({rgb},0.30);
  border-radius:5px; padding:3px 9px; text-transform:uppercase;
  position:absolute; top:14px; right:18px; }}

.footer {{ display:flex; justify-content:space-between; border-top:1px solid rgba(255,255,255,0.05);
  padding-top:10px; margin-top:14px; }}
.footer .ft {{ font-size:9px; color:rgba(255,255,255,.22); letter-spacing:.5px; }}
</style></head>
<body>
<div class="card">
  {series_html}
  <div class="top">
    <div class="brand-top">COCOBET</div>
    <div class="badge-top">{t["badge"]}</div>
  </div>

  <div class="kickoff-line">{kickoff_label}</div>

  <div class="player-name">{player_name}</div>
  <div class="player-team"><span class="flag">{team_flag}</span>{team_name}</div>

  <div class="market-row"><div class="market-pill">{market_label}</div></div>

  <div class="hero-box">
    <div class='hero-label'>Konfidenz</div><div class='hero-odds'>{conf_label.split()[0]}</div><div class='hero-book'>Eigene Analyse</div>
  </div>

  <div class="match-row">
    <div class="match-side"><span class="flag">{team_flag}</span><span class="name">{team_name}</span></div>
    <div class="match-vs">VS</div>
    <div class="match-side"><span class="flag">{opponent_flag}</span><span class="name">{opponent_name}</span></div>
  </div>

  <div class="reason-box">
    <div class="reason-label">{conf_label}</div>
    <div class="reason-text">{reason_line}</div>
  </div>

  <div class="footer">
    <div class="ft">Eigene Analyse · live</div>
    <div class="ft">cocobet</div>
  </div>
</div>
</body>
</html>
"""


def track_record_card(
    roi_pct: float,             # (Legacy, ungenutzt — Card ist TikTok-safe ohne €/ROI)
    hit_rate_pct: int,          # Gesamt-Genauigkeit, z.B. 54
    total_picks: int,           # z.B. 195
    resolved_picks: int,        # z.B. 158
    won: int,
    lost: int,
    push: int,
    pnl_eur: float,             # (Legacy, ungenutzt)
    avg_clv_pp: float | None,   # (Legacy, ungenutzt — CLV ist Public-Jargon, raus)
    stake_eur: int = 10,
    equity_curve_points: list[float] | None = None,   # kumulativer Netto-Treffer (+1/−1)
    period_label: str = "WM 2026 · Gruppenphase",
    stand_label: str = "",      # "Stand: 16.06.26 · 18:00"
    round_stats: dict | None = None,     # {"Sechzehntelfinale": {"won":14,"lost":2,"decided":16,"hit_rate":88}, ...}
    highlight_round: str | None = None,  # Runde, die farblich hervorgehoben wird (jüngste starke Runde)
    recent: list | None = None,          # letzte N entschiedene: 1=richtig, 0=daneben
    recent_won: int = 0,
) -> str:
    """
    Screenshot-taugliche Track-Record-Card für TikTok/Telegram (360×640).
    04.07.2026 (Lucas: „geiles Stats-Summary, Gesamt zuerst"): Hero = Gesamt-Genauigkeit +
    Bilanz (X richtig / Y daneben). Darunter Runden-Aufschlüsselung (jüngste starke Runde
    farbig hervorgehoben) + jüngste Form (letzte 10 als Punkte) + Netto-Treffer-Verlauf.
    TikTok-safe: KEINE Quoten/€/ROI/CLV — nur Prognose-Genauigkeit.
    """
    is_pos = hit_rate_pct >= 50
    t = THEMES["track_record" if is_pos else "track_record_neg"]
    accent = t["accent"]
    rgb = t["accentRgb"]

    # ── Runden-Aufschlüsselung (in fester Turnier-Reihenfolge, nur gespielte Runden) ──
    _order = ["Gruppenphase", "Sechzehntelfinale", "Achtelfinale", "Viertelfinale",
              "Halbfinale", "Spiel um Platz 3", "Finale"]
    rows_html = ""
    rs = round_stats or {}
    for rname in _order:
        d = rs.get(rname)
        if not d or d.get("decided", 0) < 1:
            continue
        hr = d.get("hit_rate", 0)
        is_hi = (rname == highlight_round)
        bar_col = accent if is_hi else "rgba(255,255,255,0.28)"
        name_col = accent if is_hi else "rgba(255,255,255,0.78)"
        pct_col = accent if is_hi else "#fff"
        flame = " 🔥" if is_hi else ""
        rows_html += f"""
      <div class="rrow">
        <div class="rname" style="color:{name_col};">{rname}{flame}</div>
        <div class="rbar"><div class="rbar-fill" style="width:{max(4,min(100,hr))}%;background:{bar_col};"></div></div>
        <div class="rrec">{d.get('won',0)}-{d.get('lost',0)}</div>
        <div class="rpct" style="color:{pct_col};">{hr}%</div>
      </div>"""

    # ── Jüngste Form: letzte 10 als Punkte (grün richtig / rot daneben) ──
    dots_html = ""
    rec = list(recent or [])[-10:]
    for v in rec:
        c = accent if v == 1 else "rgba(255,90,95,0.85)"
        dots_html += f'<span class="dot" style="background:{c};"></span>'
    form_line = f"{recent_won} von {len(rec)} richtig" if rec else "Form folgt"

    # ── Netto-Treffer-Verlauf (SVG) ──
    curve_svg = ""
    if equity_curve_points and len(equity_curve_points) >= 2:
        W, H = 312, 58
        pts = [0.0] + list(equity_curve_points)
        min_v = min(min(pts), 0.0)
        max_v = max(max(pts), 0.0)
        rng = (max_v - min_v) or 1.0
        n = len(pts)
        def xp(i): return 4 + (i / max(1, n - 1)) * (W - 8)
        def yp(v): return 4 + (1 - (v - min_v) / rng) * (H - 8)
        path = "M " + " L ".join(f"{xp(i):.1f} {yp(v):.1f}" for i, v in enumerate(pts))
        area = path + f" L {xp(n-1):.1f} {yp(0):.1f} L {xp(0):.1f} {yp(0):.1f} Z"
        zero_y = yp(0)
        last_x, last_y = xp(n-1), yp(pts[-1])
        curve_svg = f"""
        <svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" style="width:100%;height:{H}px;">
          <defs><linearGradient id="trkg" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stop-color="{accent}" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="{accent}" stop-opacity="0"/>
          </linearGradient></defs>
          <line x1="4" y1="{zero_y:.1f}" x2="{W-4}" y2="{zero_y:.1f}"
                stroke="rgba(255,255,255,0.10)" stroke-dasharray="3,3" stroke-width="1"/>
          <path d="{area}" fill="url(#trkg)"/>
          <path d="{path}" stroke="{accent}" stroke-width="2" fill="none"
                stroke-linecap="round" stroke-linejoin="round"/>
          <circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3.5" fill="{accent}"/>
        </svg>"""
    else:
        curve_svg = (
            f'<div style="text-align:center;font-size:10px;color:rgba(255,255,255,.35);'
            f'padding:14px 0;letter-spacing:1px;">Verlauf folgt mit ersten Prognosen</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><title>Track-Record</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0a0e18; display:flex; align-items:center; justify-content:center;
       min-height:100vh; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
.card {{
  width:360px; height:640px;
  background:
    radial-gradient(circle at 50% 26%, rgba({rgb},0.14) 0%, transparent 55%),
    linear-gradient(180deg, #0a0e18 0%, #080d18 100%);
  background-image:
    radial-gradient(circle at 50% 26%, rgba({rgb},0.14) 0%, transparent 55%),
    linear-gradient(rgba(255,255,255,0.012) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.012) 1px, transparent 1px);
  background-size: auto, 24px 24px, 24px 24px;
  border-radius:24px; padding:22px 22px 18px;
  position:relative; overflow:hidden;
  display:flex; flex-direction:column;
  border:1px solid rgba(255,255,255,0.04);
}}
.top {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; }}
.brand-top {{ font-size:11px; font-weight:800; letter-spacing:3px; color:#f5c518; }}
.badge-top {{ font-size:10px; font-weight:700; letter-spacing:1px; color:{accent};
  background:{t["badgeBg"]}; border:1px solid {t["badgeBorder"]}; border-radius:18px; padding:5px 12px; }}

.period {{ font-size:10px; color:rgba(255,255,255,.40); text-align:center;
  letter-spacing:1.8px; text-transform:uppercase; font-weight:700; margin-bottom:10px; }}

.hero {{ text-align:center; margin-bottom:14px; }}
.hero-label {{ font-size:10px; color:rgba(255,255,255,.45); letter-spacing:2.2px;
  text-transform:uppercase; font-weight:800; margin-bottom:2px; }}
.hero-num {{ font-size:76px; font-weight:900; color:{accent}; line-height:1;
  letter-spacing:-3.5px; text-shadow: 0 0 38px rgba({rgb},0.50); }}
.hero-num .unit {{ font-size:32px; font-weight:700; vertical-align:top; margin-left:3px; }}
.hero-sub {{ font-size:13px; color:#fff; margin-top:6px; letter-spacing:.3px; font-weight:800; }}
.hero-sub .g {{ color:{accent}; }}
.hero-sub2 {{ font-size:10px; color:rgba(255,255,255,.45); margin-top:3px; letter-spacing:.4px; }}

.section-lbl {{ font-size:9px; color:rgba(255,255,255,.45); letter-spacing:1.6px;
  text-transform:uppercase; font-weight:800; margin:0 2px 7px; }}
.rounds {{ padding:13px 4px 5px; border-top:1px solid rgba(255,255,255,0.06); }}
.rrow {{ display:grid; grid-template-columns:96px 1fr 34px 38px; align-items:center;
  gap:8px; margin-bottom:9px; }}
.rname {{ font-size:11px; font-weight:700; letter-spacing:.2px; white-space:nowrap; }}
.rbar {{ height:6px; background:rgba(255,255,255,0.06); border-radius:4px; overflow:hidden; }}
.rbar-fill {{ height:100%; border-radius:4px; }}
.rrec {{ font-size:10px; color:rgba(255,255,255,.50); text-align:right; font-weight:600; }}
.rpct {{ font-size:14px; font-weight:900; text-align:right; letter-spacing:-.5px; }}

.form {{ margin-top:auto; padding:12px 4px 4px; border-top:1px solid rgba(255,255,255,0.06); }}
.form-head {{ display:flex; justify-content:space-between; align-items:baseline; margin-bottom:8px; }}
.form-val {{ font-size:11px; font-weight:800; color:{accent}; letter-spacing:.3px; }}
.dots {{ display:flex; gap:5px; margin-bottom:12px; }}
.dot {{ width:20px; height:6px; border-radius:3px; }}
.curve-label {{ font-size:9px; color:rgba(255,255,255,.42); letter-spacing:1.5px;
  text-transform:uppercase; font-weight:800; margin-bottom:3px; padding:0 2px; }}

.footer {{ display:flex; justify-content:space-between; align-items:center;
  border-top:1px solid rgba(255,255,255,0.05); padding-top:9px; margin-top:10px; }}
.footer .ft {{ font-size:9px; color:rgba(255,255,255,.30); letter-spacing:.5px; }}
.footer .ft-stand {{ color:rgba(255,255,255,.55); font-weight:700; }}
</style></head>
<body>
<div class="card">
  <div class="top">
    <div class="brand-top">COCOBET</div>
    <div class="badge-top">{t["badge"]}</div>
  </div>

  <div class="period">{period_label}</div>

  <div class="hero">
    <div class="hero-label">Prognose-Genauigkeit</div>
    <div class="hero-num">{hit_rate_pct}<span class="unit">%</span></div>
    <div class="hero-sub"><span class="g">{won} richtig</span> · {lost} daneben</div>
    <div class="hero-sub2">{resolved_picks} von {total_picks} Prognosen ausgewertet</div>
  </div>

  <div class="rounds">
    <div class="section-lbl">Genauigkeit pro Runde</div>
    {rows_html}
  </div>

  <div class="form">
    <div class="form-head">
      <div class="section-lbl" style="margin:0;">Aktuelle Form · letzte {len(rec)}</div>
      <div class="form-val">{form_line}</div>
    </div>
    <div class="dots">{dots_html}</div>
    <div class="curve-label">Netto-Treffer-Verlauf</div>
    {curve_svg}
  </div>

  <div class="footer">
    <div class="ft ft-stand">{stand_label}</div>
    <div class="ft">cocobet · transparent</div>
  </div>
</div>
</body>
</html>
"""


def daily_picks_card(
    date_label: str,
    n_matches: int,
    hero_pick: dict,
    other_picks: list,
    closing_line: str = "",
    season_phase: str = "WM 2026 Gruppenphase",
    series_tag: str | None = None,
    hide_odds: bool = True,    # AUDIT-Fix 05.06.2026: Default true — keine Quoten in TikTok-Cards
) -> str:
    """Tägliche Picks-Card im CocoBet-Style — 360×640. Hero-Pick + bis 3 weitere.

    hide_odds=True (Default): Quoten + Edge-pp werden NICHT angezeigt — nur Markt-Bezeichnung
    und Konfidenz-Label. Schützt vor Compliance/Wett-Empfehlung-Risiko und macht die Cards
    eher zur "Story" als zur "Quoten-Liste".
    """
    t = THEMES["daily_picks"]
    accent = t["accent"]
    rgb = t["accentRgb"]

    is_bet = hero_pick.get("verdict") == "BET"
    # Verdict-Label vereinfacht (NEU 09.06.2026): Wort-Sprache statt X/10.
    # Lucas-Feedback: "8/10" klingt wie Stake-Angabe + setzt zu hohe Erwartung.
    # Top-Pick (Conviction ≥8 = max Engine-Bestätigung), Main-Pick (normales BET), Beobachten.
    _cs = hero_pick.get("convictionScore")
    if isinstance(_cs, int) and _cs >= 8:
        verdict_label = "🎯 TOP-PICK"
    elif is_bet:
        verdict_label = "💎 MAIN-PICK"
    else:
        verdict_label = "👁 BEOBACHTEN"
    verdict_color = accent if is_bet else "#f5c518"
    verdict_rgb   = rgb if is_bet else "245,197,24"

    series_html = ""
    if series_tag:
        series_html = (
            f'<div style="position:absolute;top:14px;left:18px;font-size:9px;'
            f'font-weight:800;letter-spacing:1.5px;color:{accent};opacity:.7;'
            f'border:1px solid rgba({rgb},.3);border-radius:6px;padding:3px 8px;">'
            f'{series_tag}</div>'
        )

    other_html = ""
    for op in (other_picks or [])[:3]:
        op_verdict = op.get("verdict", "ABWÄGEN")
        op_color = accent if op_verdict == "BET" else "#f5c518"
        op_rgb   = rgb if op_verdict == "BET" else "245,197,24"
        # hide_odds: nur Verdict + Markt, kein @-Symbol und keine Edge-Zahl
        if hide_odds:
            odds_html = ""
            edge_html = ""
        else:
            odds_html = f'<span class="op-odds">@{op.get("odds",0):.2f}</span>'
            edge_str = f"+{op.get('edge_pp', 0)}pp" if op.get('edge_pp') else ""
            edge_html = f'<span class="op-edge">{edge_str}</span>'
        other_html += f"""
        <div class="op-row">
          <div class="op-match">
            <span class="op-flags">{op.get("flag_h","")} {op.get("flag_a","")}</span>
            <span class="op-teams">{op.get("name_h","?")} – {op.get("name_a","?")}</span>
          </div>
          <div class="op-pick-row">
            <span class="op-vrd" style="color:{op_color};background:rgba({op_rgb},0.10);border:1px solid rgba({op_rgb},0.30);">{op_verdict}</span>
            <span class="op-market">{op.get("market","?")}</span>
            {odds_html}
            {edge_html}
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><title>Daily Picks</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0a0e18; display:flex; align-items:center; justify-content:center;
       min-height:100vh; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
.card {{
  width:360px; height:640px;
  background:
    radial-gradient(circle at 50% 25%, rgba({rgb},0.10) 0%, transparent 55%),
    linear-gradient(180deg, #0a0e18 0%, #080d18 100%);
  background-image:
    radial-gradient(circle at 50% 25%, rgba({rgb},0.10) 0%, transparent 55%),
    linear-gradient(rgba(255,255,255,0.012) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.012) 1px, transparent 1px);
  background-size: auto, 24px 24px, 24px 24px;
  border-radius:24px; padding:22px 20px 18px;
  position:relative; overflow:hidden;
  display:flex; flex-direction:column;
  border:1px solid rgba(255,255,255,0.04);
}}
.top {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:16px; }}
.brand-top {{ font-size:11px; font-weight:800; letter-spacing:3px; color:#f5c518; }}
.badge-top {{ font-size:10px; font-weight:700; letter-spacing:1px; color:{accent};
  background:{t["badgeBg"]}; border:1px solid {t["badgeBorder"]}; border-radius:18px; padding:5px 12px; }}
.date-row {{ display:flex; justify-content:space-between; align-items:baseline;
  padding-bottom:10px; border-bottom:1px solid rgba(255,255,255,0.06); margin-bottom:14px; }}
.date-main {{ font-size:18px; font-weight:900; color:#fff; letter-spacing:-0.3px; }}
.date-sub {{ font-size:10px; color:rgba(255,255,255,0.45); font-weight:600;
  text-transform:uppercase; letter-spacing:1.2px; }}
.hero {{ background:rgba({verdict_rgb},0.06); border:1px solid rgba({verdict_rgb},0.30);
  border-radius:12px; padding:14px 14px 12px; margin-bottom:14px; }}
.hero-verdict {{
  display:inline-block;
  font-size:10px; font-weight:800; letter-spacing:1.5px;
  color:{verdict_color};
  background:rgba({verdict_rgb},0.18);
  border:1px solid rgba({verdict_rgb},0.45);
  border-radius:999px;
  padding:4px 10px;
  text-transform:uppercase; margin-bottom:8px;
}}
.hero-match {{ display:flex; align-items:center; gap:8px; margin-bottom:8px; }}
.hero-flag {{ font-size:22px; }}
.hero-teams {{ font-size:14px; font-weight:800; color:#fff; line-height:1.25; flex:1; }}
.hero-meta {{ font-size:10px; color:rgba(255,255,255,0.55); margin-bottom:10px;
  letter-spacing:0.3px; }}
.hero-pick-row {{ display:flex; align-items:baseline; gap:8px; margin-bottom:8px; }}
.hero-market {{ font-size:13px; font-weight:700; color:#fff; flex:1; }}
.hero-odds {{ font-size:26px; font-weight:900; color:{verdict_color};
  font-family:-apple-system,sans-serif; letter-spacing:-0.5px; line-height:1; }}
.hero-edge-row {{ display:flex; gap:6px; align-items:center; padding-top:8px;
  border-top:1px solid rgba(255,255,255,0.05); }}
.hero-edge {{ font-size:11px; font-weight:800; color:{verdict_color};
  background:rgba({verdict_rgb},0.10); border:1px solid rgba({verdict_rgb},0.25);
  border-radius:5px; padding:2px 7px; }}
.hero-story {{ font-size:10.5px; color:rgba(255,255,255,0.65); line-height:1.45;
  flex:1; }}
/* Engine-Strip (NEU 09.06.2026): Conviction-Badge + Sharp-Move + Top-Signal */
.hero-engine-strip {{ display:flex; flex-wrap:wrap; gap:5px; margin-top:8px; padding-top:8px;
  border-top:1px dashed rgba(255,255,255,0.06); }}
.hero-conv {{ font-size:10px; font-weight:800; padding:3px 8px; border-radius:6px; letter-spacing:0.3px; }}
.hero-conv-top {{ background:rgba(0,212,161,0.15); color:#00d4a1; border:1px solid rgba(0,212,161,0.4); }}
.hero-conv-good {{ background:rgba(125,211,252,0.15); color:#7dd3fc; border:1px solid rgba(125,211,252,0.4); }}
.hero-conv-watch {{ background:rgba(255,176,46,0.12); color:#ffb02e; border:1px solid rgba(255,176,46,0.35); }}
.hero-sharp {{ font-size:10px; font-weight:800; color:#ff8a8a; background:rgba(255,107,107,0.12);
  border:1px solid rgba(255,107,107,0.35); border-radius:6px; padding:3px 8px; }}
.hero-top-sig {{ font-size:10px; font-weight:600; color:rgba(255,255,255,0.7);
  background:rgba(255,255,255,0.04); border-radius:6px; padding:3px 8px; }}
.other-label {{ font-size:9px; color:rgba(255,255,255,0.40); letter-spacing:1.5px;
  text-transform:uppercase; font-weight:700; margin-bottom:8px; }}
.op-row {{ background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.04);
  border-radius:9px; padding:9px 11px; margin-bottom:6px; }}
.op-match {{ display:flex; align-items:center; gap:7px; margin-bottom:5px; }}
.op-flags {{ font-size:14px; }}
.op-teams {{ font-size:11.5px; font-weight:700; color:rgba(255,255,255,0.85); }}
.op-pick-row {{ display:flex; align-items:center; gap:7px; }}
.op-vrd {{ font-size:8.5px; font-weight:800; letter-spacing:0.5px;
  padding:1px 5px; border-radius:3px; }}
.op-market {{ font-size:10.5px; color:rgba(255,255,255,0.75); flex:1; line-height:1.3; }}
.op-odds {{ font-size:11px; font-weight:800; color:#fff;
  font-family:'SF Mono',Menlo,monospace; }}
.op-edge {{ font-size:9px; font-weight:800; color:{accent}; letter-spacing:0.3px; }}
.closing {{ margin:auto 0 12px; padding:10px 12px; background:rgba({rgb},0.05);
  border:1px solid rgba({rgb},0.18); border-radius:8px; }}
.closing-txt {{ font-size:11px; color:rgba(255,255,255,0.78); line-height:1.45;
  text-align:center; }}
.closing-txt strong {{ color:{accent}; }}
.footer {{ display:flex; justify-content:space-between; align-items:center;
  border-top:1px solid rgba(255,255,255,0.05); padding-top:10px; }}
.footer .ft {{ font-size:9px; color:rgba(255,255,255,0.30); letter-spacing:0.5px; }}
.footer .ft-stand {{ color:rgba(255,255,255,0.55); font-weight:700; }}
</style></head>
<body>
<div class="card">
  {series_html}
  <div class="top">
    <div class="brand-top">COCOBET</div>
    <div class="badge-top">{t["badge"]}</div>
  </div>
  <div class="date-row">
    <div>
      <div class="date-main">{date_label}</div>
      <div class="date-sub">{season_phase}</div>
    </div>
    <div class="date-sub">{n_matches} {"Spiel" if n_matches == 1 else "Spiele"}</div>
  </div>
  <div class="hero">
    <div class="hero-verdict">{verdict_label}</div>
    <div class="hero-match">
      <span class="hero-flag">{hero_pick.get("flag_h","")}</span>
      <div class="hero-teams">{hero_pick.get("name_h","?")} <span style="color:rgba(255,255,255,0.45);font-weight:400;">vs</span> {hero_pick.get("name_a","?")}</div>
      <span class="hero-flag">{hero_pick.get("flag_a","")}</span>
    </div>
    <div class="hero-meta">{hero_pick.get("time","")} · {hero_pick.get("venue","")}</div>
    <div class="hero-pick-row">
      <div class="hero-market">{hero_pick.get("market","?")}</div>
      {"" if hide_odds else f'<div class="hero-odds">{hero_pick.get("odds",0):.2f}</div>'}
    </div>
    <div class="hero-edge-row">
      {"" if hide_odds else f'<span class="hero-edge">+{hero_pick.get("edge_pp",0)}pp Edge</span>'}
      <span class="hero-story">{hero_pick.get("story","")}</span>
    </div>
    {(lambda sm, sd: (
      f'<div class="hero-engine-strip">'
      + (f'<span class="hero-sharp">🔥 Sharp-Move</span>' if sm else '')
      + (f'<span class="hero-top-sig">{sd}</span>' if sd else '')
      + '</div>'
    ) if (sm or sd) else '')(
      hero_pick.get("sharpMoveActive"),
      hero_pick.get("topSignal"),
    )}
  </div>
  {f'<div class="other-label">Weitere im Blick</div>{other_html}' if other_html else ''}
  <div class="closing">
    <div class="closing-txt">{closing_line or 'Picks aus eigenem Modell · jeder mit Edge-Begründung. <strong>cocobet.</strong>'}</div>
  </div>
  <div class="footer">
    <div class="ft ft-stand">Modell · Eigene Analyse</div>
    <div class="ft">cocobet · transparent</div>
  </div>
</div>
</body>
</html>
"""


# ── Match-Preview-Card (Story-First, OHNE Quoten — NEU 14.06.2026) ────────────
def match_preview_card(
    date_label: str,
    flag_h: str, name_h: str,
    flag_a: str, name_a: str,
    kickoff_label: str,
    venue: str,
    group_label: str,
    angle_label: str,
    accent: str,
    accent_rgb: str,
    story_text: str,
    facts: list,
    season_phase: str = "WM 2026 · Gruppenphase",
) -> str:
    """Pro-Match Story-Preview im CocoBet-Style (360×640) — KEINE Quoten.
    Header → Angle-Badge → Teams (gestapelt, robust für lange Namen) → Anpfiff/Venue
    → 2-Satz-Story (aiPreviews tgSnippet) → 3-4 Auto-Fact-Chips → Footer.
    Lucas 14.06.2026: flexibles Story-Telling-Format, je Spiel eine Card."""
    rgb = accent_rgb
    facts_html = ""
    for f in (facts or [])[:4]:
        facts_html += f'<span class="fact">{f}</span>'
    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><title>Match Preview</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0a0e18; display:flex; align-items:center; justify-content:center;
       min-height:100vh; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
.card {{
  width:360px; height:640px;
  background:
    radial-gradient(circle at 50% 22%, rgba({rgb},0.12) 0%, transparent 55%),
    linear-gradient(180deg, #0a0e18 0%, #080d18 100%);
  background-image:
    radial-gradient(circle at 50% 22%, rgba({rgb},0.12) 0%, transparent 55%),
    linear-gradient(rgba(255,255,255,0.012) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.012) 1px, transparent 1px);
  background-size: auto, 24px 24px, 24px 24px;
  border-radius:24px; padding:22px 20px 18px;
  position:relative; overflow:hidden;
  display:flex; flex-direction:column;
  border:1px solid rgba(255,255,255,0.04);
}}
.top {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; }}
.brand-top {{ font-size:11px; font-weight:800; letter-spacing:3px; color:#f5c518; }}
.badge-top {{ font-size:10px; font-weight:700; letter-spacing:1px; color:{accent};
  background:rgba({rgb},0.10); border:1px solid rgba({rgb},0.35); border-radius:18px; padding:5px 12px; }}
.date-row {{ display:flex; justify-content:space-between; align-items:baseline;
  padding-bottom:10px; border-bottom:1px solid rgba(255,255,255,0.06); margin-bottom:16px; }}
.date-main {{ font-size:18px; font-weight:900; color:#fff; letter-spacing:-0.3px; }}
.date-sub {{ font-size:10px; color:rgba(255,255,255,0.45); font-weight:600;
  text-transform:uppercase; letter-spacing:1.2px; }}
.angle {{ display:inline-block; align-self:flex-start; font-size:11px; font-weight:800;
  letter-spacing:1px; color:{accent}; background:rgba({rgb},0.10);
  border:1px solid rgba({rgb},0.30); border-radius:8px; padding:6px 11px; margin-bottom:18px; }}
.teams {{ text-align:center; margin-bottom:12px; }}
.team {{ display:flex; align-items:center; justify-content:center; gap:10px; }}
.team .tf {{ font-size:34px; line-height:1; }}
.team .tn {{ font-size:23px; font-weight:900; color:#fff; letter-spacing:-0.3px; }}
.vs {{ font-size:12px; font-weight:700; color:rgba(255,255,255,0.40);
  text-transform:uppercase; letter-spacing:2px; margin:7px 0; }}
.meta {{ text-align:center; font-size:11px; color:rgba(255,255,255,0.55);
  letter-spacing:0.3px; margin-bottom:18px; }}
.story {{ font-size:14.5px; line-height:1.55; color:rgba(255,255,255,0.80);
  margin-bottom:18px; }}
.facts {{ display:flex; flex-wrap:wrap; gap:7px; margin-bottom:auto; }}
.fact {{ font-size:11px; color:rgba(255,255,255,0.82); background:rgba(255,255,255,0.03);
  border:1px solid rgba(255,255,255,0.07); border-radius:8px; padding:7px 10px; }}
.footer {{ display:flex; justify-content:space-between; align-items:center;
  border-top:1px solid rgba(255,255,255,0.05); padding-top:11px; margin-top:14px; }}
.footer .ft {{ font-size:9px; color:rgba(255,255,255,0.30); letter-spacing:0.5px; }}
.footer .ft-stand {{ color:{accent}; font-weight:800; }}
</style></head>
<body>
<div class="card">
  <div class="top">
    <div class="brand-top">COCOBET</div>
    <div class="badge-top">⚡ MATCH PREVIEW</div>
  </div>
  <div class="date-row">
    <div>
      <div class="date-main">{date_label}</div>
      <div class="date-sub">{season_phase}</div>
    </div>
    <div class="date-sub">{group_label}</div>
  </div>
  <div class="angle">{angle_label}</div>
  <div class="teams">
    <div class="team"><span class="tf">{flag_h}</span><span class="tn">{name_h}</span></div>
    <div class="vs">vs</div>
    <div class="team"><span class="tf">{flag_a}</span><span class="tn">{name_a}</span></div>
  </div>
  <div class="meta">{kickoff_label}{(" · " + venue) if venue else ""}</div>
  <div class="story">{story_text}</div>
  <div class="facts">{facts_html}</div>
  <div class="footer">
    <div class="ft ft-stand">cocobet.</div>
    <div class="ft">Eigene Analyse · datengetrieben</div>
  </div>
</div>
</body>
</html>
"""


def match_review_card(
    date_label: str,
    flag_h: str, name_h: str, score_h,
    flag_a: str, name_a: str, score_a,
    group_label: str,
    angle_label: str,
    accent: str,
    accent_rgb: str,
    recap_text: str,
    facts: list,
    season_phase: str = "WM 2026 · Gruppenphase",
) -> str:
    """Pro-Match Nachbericht/Review im CocoBet-Style (360×640) — KEINE Quoten, kein Wett-Inhalt.
    Header → Angle-Badge → Teams mit ENDSTAND → Recap-Satz → Stat-Chips (xG/Schüsse/Großchancen).
    Lucas 20.06.2026: ersetzt Killer-Stat/Story als Daily-Content — Review der Vortags-Spiele."""
    rgb = accent_rgb
    facts_html = ""
    for f in (facts or [])[:5]:
        facts_html += f'<span class="fact">{f}</span>'
    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><title>Match Review</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0a0e18; display:flex; align-items:center; justify-content:center;
       min-height:100vh; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
.card {{
  width:360px; height:640px;
  background:
    radial-gradient(circle at 50% 22%, rgba({rgb},0.12) 0%, transparent 55%),
    linear-gradient(180deg, #0a0e18 0%, #080d18 100%);
  background-image:
    radial-gradient(circle at 50% 22%, rgba({rgb},0.12) 0%, transparent 55%),
    linear-gradient(rgba(255,255,255,0.012) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.012) 1px, transparent 1px);
  background-size: auto, 24px 24px, 24px 24px;
  border-radius:24px; padding:22px 20px 18px;
  position:relative; overflow:hidden;
  display:flex; flex-direction:column;
  border:1px solid rgba(255,255,255,0.04);
}}
.top {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; }}
.brand-top {{ font-size:11px; font-weight:800; letter-spacing:3px; color:#f5c518; }}
.badge-top {{ font-size:10px; font-weight:700; letter-spacing:1px; color:{accent};
  background:rgba({rgb},0.10); border:1px solid rgba({rgb},0.35); border-radius:18px; padding:5px 12px; }}
.date-row {{ display:flex; justify-content:space-between; align-items:baseline;
  padding-bottom:10px; border-bottom:1px solid rgba(255,255,255,0.06); margin-bottom:16px; }}
.date-main {{ font-size:18px; font-weight:900; color:#fff; letter-spacing:-0.3px; }}
.date-sub {{ font-size:10px; color:rgba(255,255,255,0.45); font-weight:600;
  text-transform:uppercase; letter-spacing:1.2px; }}
.angle {{ display:inline-block; align-self:flex-start; font-size:11px; font-weight:800;
  letter-spacing:1px; color:{accent}; background:rgba({rgb},0.10);
  border:1px solid rgba({rgb},0.30); border-radius:8px; padding:6px 11px; margin-bottom:16px; }}
.score-row {{ display:flex; align-items:center; justify-content:center; gap:14px; margin-bottom:6px; }}
.score-team {{ flex:1; text-align:center; }}
.score-team .tf {{ font-size:38px; line-height:1; }}
.score-team .tn {{ font-size:15px; font-weight:800; color:#fff; margin-top:6px; letter-spacing:-0.2px; }}
.score-num {{ font-size:46px; font-weight:900; color:#fff; letter-spacing:-1px; line-height:1;
  font-variant-numeric:tabular-nums; white-space:nowrap; }}
.score-num .dash {{ color:rgba(255,255,255,0.35); margin:0 6px; }}
.fulltime {{ text-align:center; font-size:10px; font-weight:700; color:rgba(255,255,255,0.45);
  text-transform:uppercase; letter-spacing:1.5px; margin-bottom:16px; }}
.recap {{ font-size:14.5px; line-height:1.55; color:rgba(255,255,255,0.82); margin-bottom:16px; }}
.facts {{ display:flex; flex-wrap:wrap; gap:7px; margin-bottom:auto; }}
.fact {{ font-size:11px; color:rgba(255,255,255,0.82); background:rgba(255,255,255,0.03);
  border:1px solid rgba(255,255,255,0.07); border-radius:8px; padding:7px 10px; font-variant-numeric:tabular-nums; }}
.footer {{ display:flex; justify-content:space-between; align-items:center;
  border-top:1px solid rgba(255,255,255,0.05); padding-top:11px; margin-top:14px; }}
.footer .ft {{ font-size:9px; color:rgba(255,255,255,0.30); letter-spacing:0.5px; }}
.footer .ft-stand {{ color:{accent}; font-weight:800; }}
</style></head>
<body>
<div class="card">
  <div class="top">
    <div class="brand-top">COCOBET</div>
    <div class="badge-top">📊 SPIEL-REVIEW</div>
  </div>
  <div class="date-row">
    <div>
      <div class="date-main">{date_label}</div>
      <div class="date-sub">{season_phase}</div>
    </div>
    <div class="date-sub">{group_label}</div>
  </div>
  <div class="angle">{angle_label}</div>
  <div class="score-row">
    <div class="score-team"><div class="tf">{flag_h}</div><div class="tn">{name_h}</div></div>
    <div class="score-num">{score_h}<span class="dash">:</span>{score_a}</div>
    <div class="score-team"><div class="tf">{flag_a}</div><div class="tn">{name_a}</div></div>
  </div>
  <div class="fulltime">Endstand</div>
  <div class="recap">{recap_text}</div>
  <div class="facts">{facts_html}</div>
  <div class="footer">
    <div class="ft ft-stand">cocobet.</div>
    <div class="ft">Eigene Analyse · datengetrieben</div>
  </div>
</div>
</body>
</html>
"""


# ── Spieltag-Bilanz-Card (Ergebnis-Promo, wiederverwendbar) ───────────────────
def bilanz_card(
    hit_pct: str,
    record_line: str,
    games: list,
    *,
    theme: str = "track_record",
    badge: str | None = None,
    series_tag: str = "SPIELTAG 1",
    sub_label: str = "Trefferquote",
    sub_detail: str = "",
    cta: str = "ALLE PICKS IM VIDEO",
) -> str:
    """
    Ergebnis-/Bilanz-Card im Lucas-Style — Trefferquote + Spiele mit Flagge,
    Endstand und ✅/❌/↩️ pro Pick. Wiederverwendbar pro Spieltag.

    Args:
        hit_pct:     Große Zahl, z.B. "78%"
        record_line: z.B. "<b>7 Siege</b> · 2 daneben · 1 Cashback"
        games:       Liste von dicts:
                       {"home_flag","home","score","away","away_flag",
                        "marks": ["W","L","P", ...]}   # W=Treffer L=daneben P=Push(Cashback)
        theme:       THEMES-Key (default track_record = grün)
        series_tag:  Label oben links
        sub_label/sub_detail: unter der großen Zahl
        cta:         Fußzeile

    Liefert: kompletter HTML-String, 360×640 (rendert via render_to_png/Playwright
    pixelgenau wie die anderen Cards — SF Pro + Farb-Emoji-Flaggen).
    """
    t = THEMES.get(theme, THEMES["track_record"])
    accent = t["accent"]; rgb = t["accentRgb"]
    badge = badge or "📊 SPIELTAG-BILANZ"
    _SYM = {"W": "✅", "L": "❌", "P": "↩️"}
    rows = ""
    for g in games:
        marks = g.get("marks") or []
        w = sum(1 for m in marks if m == "W")
        dec = sum(1 for m in marks if m in ("W", "L"))
        chips = "".join(f'<span class="mk">{_SYM.get(m,"")}</span>' for m in marks)
        tally = f'{w}/{dec}' if dec else ''
        rows += (
            f'<div class="game"><div class="g-top">'
            f'<span class="team"><span class="flag">{g.get("home_flag","")}</span>{g.get("home","")}</span>'
            f'<span class="score">{g.get("score","")}</span>'
            f'<span class="team team-r">{g.get("away","")}<span class="flag">{g.get("away_flag","")}</span></span>'
            f'</div><div class="marks">{chips}<span class="tally">{tally}</span></div></div>'
        )
    sub_detail_html = f' · {sub_detail}' if sub_detail else ''
    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"><title>Bilanz</title><style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0a0e18; display:flex; align-items:center; justify-content:center; min-height:100vh;
  font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
.card {{ width:360px; height:640px; background-color:#0a0e18;
  background-image:
    radial-gradient(circle at 50% 28%, rgba({rgb},0.10) 0%, transparent 45%),
    linear-gradient(rgba(255,255,255,0.014) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.014) 1px, transparent 1px);
  background-size: auto, 24px 24px, 24px 24px;
  border-radius:24px; padding:22px 22px 14px; position:relative; overflow:hidden;
  display:flex; flex-direction:column; border:1px solid rgba(255,255,255,0.05); }}
.series {{ position:absolute; top:13px; left:15px; font-size:9px; font-weight:800; letter-spacing:1.5px;
  color:{accent}; opacity:.7; border:1px solid rgba({rgb},.3); border-radius:6px; padding:3px 8px; }}
.logo {{ display:flex; justify-content:center; margin-bottom:10px; }}
.badge {{ display:flex; justify-content:center; margin-bottom:12px; }}
.badge-inner {{ font-size:11px; font-weight:700; letter-spacing:2px; color:{accent};
  background:{t["badgeBg"]}; border:1px solid {t["badgeBorder"]}; border-radius:24px; padding:7px 18px; }}
.number-box {{ border:1px solid rgba({rgb},0.30); border-radius:14px; padding:14px 18px 10px; text-align:center;
  margin-bottom:10px; background:rgba({rgb},0.025);
  box-shadow: inset 0 0 32px rgba({rgb},0.06), 0 0 48px rgba({rgb},0.08); }}
.number {{ font-size:68px; font-weight:900; color:{accent}; line-height:1; letter-spacing:-2px;
  text-shadow:0 0 28px rgba({rgb},0.45); }}
.number-sub {{ font-size:10px; font-weight:600; color:rgba(255,255,255,0.34); margin-top:6px;
  letter-spacing:2px; text-transform:uppercase; }}
.bilanz {{ text-align:center; font-size:13px; font-weight:600; color:rgba(255,255,255,0.5); margin-bottom:10px; }}
.bilanz b {{ color:#fff; }}
.game {{ background:rgba(255,255,255,0.025); border:1px solid rgba(255,255,255,0.05); border-radius:12px;
  padding:7px 13px; margin-bottom:6px; }}
.g-top {{ display:flex; align-items:center; justify-content:space-between; }}
.team {{ font-size:16px; font-weight:800; color:#fff; display:flex; align-items:center; gap:7px; width:40%; }}
.team-r {{ justify-content:flex-end; }}
.flag {{ font-size:18px; }}
.score {{ font-size:17px; font-weight:900; color:{accent}; width:20%; text-align:center; }}
.marks {{ display:flex; align-items:center; gap:5px; margin-top:5px; }}
.mk {{ font-size:13px; }}
.tally {{ margin-left:auto; font-size:11px; font-weight:700; color:rgba(255,255,255,0.4); }}
.cta {{ font-size:10px; font-weight:600; color:rgba(255,255,255,0.28); text-align:center; letter-spacing:3px;
  border-top:1px solid rgba(255,255,255,0.05); padding-top:10px; margin-top:auto; }}
.brand {{ font-size:10px; font-weight:700; color:rgba(255,255,255,0.2); text-align:center; letter-spacing:4px;
  margin-top:7px; text-transform:uppercase; }}
</style></head><body>
<div class="card">
  <div class="series">{series_tag}</div>
  <div class="logo">{_logo_block(54)}</div>
  <div class="badge"><div class="badge-inner">{badge}</div></div>
  <div class="number-box"><div class="number">{hit_pct}</div><div class="number-sub">{sub_label}{sub_detail_html}</div></div>
  <div class="bilanz">{record_line}</div>
  {rows}
  <div class="cta">{cta}</div>
  <div class="brand">cocobet</div>
</div>
</body></html>"""


def streak_card(
    team: str,
    team_id: str | None,
    market: str,
    length: int,
    seq: list | None = None,
    state: str = "neutral",
    signal_confirm: bool = False,
    next_opp: str | None = None,
    next_date: str | None = None,
    hook: str = "Hält die Serie?",
    league_name: str = "",
    verb: str = "in Folge",
    flag: str = "",
) -> str:
    """Serien-Spotlight im TikTok-Hochformat (29.06.2026, Lucas: Streaks als Content). 360×640,
    Dark/Orange, Crest + Riesen-Zahl + Verlaufs-Punkte + „Engine bestätigt"-Badge + nächster Gegner
    + Hook. TikTok-safe (KEINE Quoten/€).

    Crest-Logik: numerische team_id (Vereine Liga/MLS) → API-Football-Logo; WM-Nationalteams (Code wie
    „FRA") haben keine numerische ID → Flagge; sonst Initialen."""
    accent, rgb = "#f0883e", "240,136,62"
    if team_id is not None and str(team_id).isdigit():
        crest = (f'<img src="https://media.api-sports.io/football/teams/{team_id}.png" '
                 f'style="width:64px;height:64px;object-fit:contain;" alt="">')
    elif flag:
        crest = f'<div style="font-size:46px;line-height:1;">{flag}</div>'
    else:
        crest = (f'<div style="font-size:24px;font-weight:800;color:{accent};">'
                 f'{(team or "?")[:3].upper()}</div>')
    dots = "".join(
        f'<span style="color:{accent if h else "rgba(255,255,255,.16)"}">●</span>'
        for h in list(seq or [])[::-1][-9:]
    )
    state_col = {"intakt": "#2dd47e", "wackelt": "#e3b341"}.get(state, "#8b949e")
    state_lbl = {"intakt": "Serie intakt", "wackelt": "wackelt"}.get(state, "offen")
    sig_html = (f'<span style="background:rgba(45,212,126,.12);color:#2dd47e;border-radius:6px;'
                f'padding:3px 9px;font-size:11px;font-weight:800;">Engine bestätigt</span>') if signal_confirm else (
                f'<span style="color:{state_col};font-size:11px;font-weight:800;">{state_lbl}</span>')
    next_html = ""
    if next_opp:
        _at = "@" if (next_date and False) else "vs"
        next_html = (
            f'<div style="margin-top:20px;background:rgba(255,255,255,.04);border:1px solid '
            f'rgba(255,255,255,.06);border-radius:12px;padding:11px 14px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<span style="font-size:11px;color:#76819c;">Nächster Test</span>'
            f'<span style="font-size:13px;font-weight:700;color:#f2f5ff;">{next_opp}'
            f'{(" · " + next_date) if next_date else ""}</span></div>'
            f'<div style="margin-top:8px;">{sig_html}</div></div>'
        )
    return f"""<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8"><style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0a0e18; display:flex; align-items:center; justify-content:center; min-height:100vh;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }}
.card {{ width:360px; height:640px; position:relative; overflow:hidden; padding:30px 26px;
  background:
    radial-gradient(circle at 50% 30%, rgba({rgb},0.12) 0%, transparent 46%),
    linear-gradient(180deg,#0a0e18 0%,#080d18 100%); }}
.grid {{ position:absolute; inset:0;
  background-image:linear-gradient(rgba(255,255,255,0.014) 1px,transparent 1px),
    linear-gradient(90deg,rgba(255,255,255,0.014) 1px,transparent 1px);
  background-size:24px 24px; }}
.in {{ position:relative; }}
.top {{ display:flex; align-items:center; justify-content:space-between; }}
.eyebrow {{ font-size:10px; font-weight:800; letter-spacing:2px; color:{accent}; }}
.badge {{ font-size:9px; font-weight:900; letter-spacing:1px; background:#f5c518; color:#000;
  border-radius:5px; padding:3px 7px; }}
.crestwrap {{ display:flex; flex-direction:column; align-items:center; margin-top:30px; }}
.cb {{ width:74px; height:74px; border-radius:50%; background:rgba({rgb},.10); border:2px solid {accent};
  display:flex; align-items:center; justify-content:center; }}
.team {{ font-size:21px; font-weight:800; color:#f2f5ff; margin-top:13px; }}
.league {{ font-size:11px; color:#76819c; margin-top:2px; }}
.numwrap {{ text-align:center; margin-top:24px; }}
.num {{ font-size:80px; font-weight:900; color:{accent}; line-height:1; }}
.num span {{ font-size:36px; }}
.mkt {{ font-size:16px; font-weight:600; color:#f2f5ff; margin-top:4px; }}
.mkt b {{ color:{accent}; }}
.dots {{ margin-top:15px; font-size:15px; letter-spacing:5px; }}
.hook {{ text-align:center; margin-top:24px; font-size:18px; font-weight:800; color:#f2f5ff; }}
.brand {{ position:absolute; bottom:20px; left:0; right:0; text-align:center; font-size:10px;
  font-weight:700; letter-spacing:4px; color:rgba(255,255,255,.22); text-transform:uppercase; }}
</style></head><body>
<div class="card"><div class="grid"></div><div class="in">
  <div class="top"><div class="eyebrow">🔥 SERIE</div><div class="badge">COCOBET</div></div>
  <div class="crestwrap"><div class="cb">{crest}</div>
    <div class="team">{team}</div>{f'<div class="league">{league_name}</div>' if league_name else ''}</div>
  <div class="numwrap"><div class="num">{length}<span>×</span></div>
    <div class="mkt">{verb} <b>{market}</b></div>
    <div class="dots">{dots}</div></div>
  {next_html}
  <div class="hook">{hook}</div>
</div><div class="brand">cocobet</div></div>
</body></html>"""


