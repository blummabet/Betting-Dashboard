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
    <div class="hero-quote">Quote <strong>{quote_str}</strong></div>
  </div>

  <div class="list-title">Was eher passiert</div>
  <div class="comp-list">{comp_html}</div>

  <div class="closing-box">
    <div class="closing-text">{closing_line}</div>
  </div>

  <div class="quote">{quote_line}</div>

  <div class="footer">
    <div class="ft">Quote: Polymarket Outrights · 02.06.26</div>
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
