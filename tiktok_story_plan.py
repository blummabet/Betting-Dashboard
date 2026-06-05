#!/usr/bin/env python3
"""
tiktok_story_plan.py — Vor-definierte TikTok-Story-Serie

Schedule pro Datum mit Hook + Info Config. Wird von generate_daily_tiktok.py
am Start aufgerufen.

Jeder Tag liefert:
  · theme        (siehe tiktok_card_templates.THEMES)
  · series_tag   z.B. "STORY 4 / 10" (oder None)
  · hook         dict für hook_card()
  · info         dict für info_card()
"""

# Serie startet 2026-06-01 (Yamal). Erste 3 Tage schon manuell gepostet.
# Plan ab Di 2026-06-02 — automatischer Push beginnt hier.

STORY_PLAN = {
    # ─────────────── Bereits manuell gepostet (Referenz) ───────────────
    "2026-06-01": {"posted_manually": True, "topic": "Yamal + Marokko + Modric"},

    # ─────────────── Di 2026-06-02 — Belgien Tor-Maschine ──────────────
    "2026-06-02": {
        "theme": "killer_stat",
        "series_tag": "STORY 4 / 10",
        "hook": {
            "big_number":      "2.8",
            "sub_title":       "xG pro Spiel",
            "hook_line_1":     '<span class="acc">Belgien</span> trifft',
            "hook_line_2":     'jeden Gegner. <span class="yellow">Wieso?</span>',
            "mystery_question":"Wer stoppt diese Maschine?",
            "highlight_fact":  "23 Tore in 8 Quali-Spielen",
        },
        "info": {
            "flag":         "🇧🇪",
            "name":         "Belgien",
            "role_line":    "Gruppe G · Ø 2.88 Tore/Spiel",
            "stat1_val":    "2.8",  "stat1_lbl": "xG / Spiel",
            "stat2_val":    "23",   "stat2_lbl": "Quali-Tore",
            "stat3_val":    "0.9",  "stat3_lbl": "Gegen Ø",
            "closing_line": 'Lukaku-De Bruyne-Doku-Trio wieder fit. <strong>Gegen Iran am 18.06.</strong> erwartet Markt 2.8 Tore — Modell sagt 3.4.',
            "quote_line":   'Tor-Maschine ohne <span class="acc">Stopper</span> in Sicht. ⚽',
            "data_source":  "Daten: WM-Quali 2024/25",
        },
    },

    # ─────────────── Mi 2026-06-03 — Endrick ──────────────
    "2026-06-03": {
        "theme": "naechste_aera",
        "series_tag": "STORY 5 / 10",
        "hook": {
            "big_number":      "18",
            "sub_title":       "Jahre · 70M Ablöse · Real",
            "hook_line_1":     'Er ersetzt <span class="acc">Vinicius</span>',
            "hook_line_2":     'wenn der Reise zu lang wird.',
            "mystery_question":"Wer ist Brasiliens Joker?",
            "highlight_fact":  "11 Tore in 24 Real-Spielen mit 18",
        },
        "info": {
            "flag":         "🇧🇷",
            "name":         "Endrick",
            "role_line":    "Brasilien · Stürmer · Real Madrid",
            "stat1_val":    "18",   "stat1_lbl": "Jahre",
            "stat2_val":    "11",   "stat2_lbl": "Tore Real",
            "stat3_val":    "70M",  "stat3_lbl": "€ Ablöse",
            "closing_line": '<strong>Jüngster Real-Madrid-Stürmer der WM-Geschichte.</strong> Gruppe C mit Marokko + Haiti + Schottland — bekommt Spielminuten garantiert.',
            "quote_line":   'Yamal in <span class="acc">Spanien</span>, Endrick in <span class="acc">Brasilien</span>. 2026 = Wachablöse. 🌱',
            "data_source":  "Daten: Real Madrid 2024/25",
        },
    },

    # ─────────────── Do 2026-06-04 — Argentinien Titel-Verteidigung ──────────────
    # KORRIGIERT 04.06.2026 (3x):
    #   1. Lewandowski/Polen war ursprünglich geplant — Polen NICHT qualifiziert
    #   2. Ronaldo war Backup — von Lucas früh schon manuell gepostet
    #   3. Argentinien als finale Wahl — am 04.06. Mittag MANUELL gepostet
    # → posted_manually=True verhindert dass Auto-Pipeline morgen Argentinien nochmal sendet.
    "2026-06-04": {
        "posted_manually": True,
        "topic": "Argentinien Titel-Verteidigung",
        "theme": "geheimfavorit",
        "series_tag": "STORY 6 / 10",
        "hook": {
            "big_number":      "1962",
            "sub_title":       "Jahr · zuletzt Titel verteidigt",
            "hook_line_1":     'Seit <span class="acc">64 Jahren</span>',
            "hook_line_2":     'hat es niemand geschafft.',
            "mystery_question":"Kann Argentinien Geschichte schreiben?",
            "highlight_fact":  "Brasilien 1958+1962 — der einzige Back-to-Back-Champion",
        },
        "info": {
            "flag":         "🇦🇷",
            "name":         "Argentinien",
            "role_line":    "Argentinien · Gruppe O · Titel-Verteidigung",
            "stat1_val":    "1962", "stat1_lbl": "letzte B2B-Verteidigung",
            "stat2_val":    "38",   "stat2_lbl": "Lautaro Tore Inter",
            "stat3_val":    "0.6",  "stat3_lbl": "Quali-Gegen-Ø",
            "closing_line": 'Messi 39 in einer Bayer-Generation: <strong>Lautaro Martínez und Julián Álvarez führen jetzt.</strong> Gruppe O mit Algerien, Österreich und Jordanien — auf dem Papier dankbar. Quote auf Titel: 4.50 (Polymarket: 23%).',
            "quote_line":   'Verteidigung ist <span class="acc">schwerer</span> als Erobern. 🏆',
            "data_source":  "Daten: Argentinien-Quali 2024/25",
        },
    },

    # ─────────────── Fr 2026-06-05 — Senegal Form ──────────────
    # ⚠️ Senegal-Story "5W/5" war falsch: USA-Niederlage 31.05.2026 fehlte im
    # hartkodierten Wert. Auto-Pipeline hat die Card am 05.06. vormittag schon
    # gesendet — daher posted_manually=True damit kein Re-Post nach dem Fix passiert.
    # FOLLOW-UP: tiktok_story_plan Form-Werte sollten aus wm_form.json live gezogen
    # werden statt hartkodiert (Phantom-Team-Guard fängt nur Existenz, nicht Aktualität).
    "2026-06-05": {
        "posted_manually": True,
        "topic": "Senegal Form (5W/5 war stale — USA-Niederlage 31.5 nicht reflektiert)",
        "theme": "hidden_gem",
        "series_tag": "STORY 7 / 10",
        "hook": {
            "big_number":      "5W",
            "sub_title":       "in 5 Spielen · Senegal",
            "hook_line_1":     'Form-Lauf den niemand',
            "hook_line_2":     'auf dem Schirm hat.',
            "mystery_question":"Wer schlägt Frankreich am 18.06.?",
            "highlight_fact":  "Sané, Mané, Diatta — alle Form bei Bayern/Galatasaray",
        },
        "info": {
            "flag":         "🇸🇳",
            "name":         "Senegal",
            "role_line":    "Gruppe I · gegen Frankreich, Norwegen, Irak",
            "stat1_val":    "5W/5",   "stat1_lbl": "Form last 5",
            "stat2_val":    "0.4",    "stat2_lbl": "Gegen-Ø",
            "stat3_val":    "1767",   "stat3_lbl": "Elo-Wert",
            "closing_line": '<strong>Africa-Cup-Sieger 2021.</strong> Quote auf Senegal-Sieg gegen Frankreich: 5.50 — Modell sieht 4.20. Da sitzt Edge.',
            "quote_line":   'Bookies schlafen. <span class="acc">Senegal schwingt.</span> 🦁',
            "data_source":  "Daten: WM-Quali + Tests 2024/25",
        },
    },

    # ─────────────── Sa 2026-06-06 — Marokko Travel-Wahnsinn ──────────────
    "2026-06-06": {
        "theme": "killer_stat",
        "series_tag": "STORY 8 / 10",
        "hook": {
            "big_number":      "3.942",
            "sub_title":       "km Anreise · ST1 → ST2",
            "hook_line_1":     '<span class="acc">Marokko</span> reist',
            "hook_line_2":     'wie keine andere Nation.',
            "mystery_question":"Brechen sie wieder Geschichte?",
            "highlight_fact":  "NY → LA mit nur 4 Ruhetagen — kritischste Anreise des Turniers",
        },
        "info": {
            "flag":         "🇲🇦",
            "name":         "Marokko Travel",
            "role_line":    "Gruppe C · 3 Spiele in 8 Tagen · 4000km",
            "stat1_val":    "3942", "stat1_lbl": "km ST1→ST2",
            "stat2_val":    "4",    "stat2_lbl": "Tage Rest",
            "stat3_val":    "10/10","stat3_lbl": "Burden-Score",
            "closing_line": 'Studien zeigen: <strong>−10-15% xG nach Long-Haul + wenig Pause.</strong> Unter 2.5 Tore gegen Schottland am 17.06. ist deshalb realer als die Quote zeigt.',
            "quote_line":   'Kein Bookie pricet das ein. <span class="acc">Wir schon.</span> ✈️',
            "data_source":  "Daten: wm_travel_burden.json",
        },
    },

    # ─────────────── So 2026-06-07 — Mbappé Top-Scorer ──────────────
    "2026-06-07": {
        "theme": "dark_horse",
        "series_tag": "STORY 9 / 10",
        "hook": {
            "big_number":      "5.50",
            "sub_title":       "Quote · Top-Scorer WM",
            "hook_line_1":     'Bookies sehen <span class="acc">Mbappé</span>',
            "hook_line_2":     'als großen Favoriten.',
            "mystery_question":"Stimmt das wirklich?",
            "highlight_fact":  "Quali-Tore: Mbappé 9, Haaland 14, Lautaro 12 — Markt täuscht?",
        },
        "info": {
            "flag":         "⚽",
            "name":         "Top-Scorer-Race",
            "role_line":    "WM 2026 · Mbappé vs Haaland vs Lautaro",
            "stat1_val":    "9",    "stat1_lbl": "Mbappé Quali",
            "stat2_val":    "14",   "stat2_lbl": "Haaland Quali",
            "stat3_val":    "12",   "stat3_lbl": "Lautaro Quali",
            "closing_line": '<strong>Frankreich Gruppe I = leicht, aber Mbappé spielt rotiert.</strong> Haaland (Gruppe I gegen Senegal/Irak/Norwegen) hat schwerere Spiele aber 90 Min Minuten-Garantie.',
            "quote_line":   'Quoten lügen. <span class="acc">Stats nicht.</span> 🎯',
            "data_source":  "Daten: Quali 2024/25 + Polymarket",
        },
    },

    # ─────────────── Mo 2026-06-08 — Vinicius Reality ──────────────
    "2026-06-08": {
        "theme": "dark_horse",
        "series_tag": "STORY 10 / 10",
        "hook": {
            "big_number":      "0",
            "sub_title":       "WM-Tore · Vinicius",
            "hook_line_1":     '<span class="acc">Bester Vereinsspieler</span>',
            "hook_line_2":     'der Welt 2024.',
            "mystery_question":"Aber kann er auf der WM-Bühne?",
            "highlight_fact":  "23 Tore Real-Saison vs 4 Tore Brasilien-Quali",
        },
        "info": {
            "flag":         "🇧🇷",
            "name":         "Vinicius Jr",
            "role_line":    "Brasilien · Flügel · Real Madrid",
            "stat1_val":    "23",   "stat1_lbl": "Tore Real 24/25",
            "stat2_val":    "4",    "stat2_lbl": "Tore Brasilien",
            "stat3_val":    "0",    "stat3_lbl": "WM-Tore",
            "closing_line": '<strong>Vinicius-Knick:</strong> für Real liefert er ab, im Brasilien-Trikot wirkt er gehemmt. Bei Quote 9.00 auf "Top-3 WM-Scorer" könnte das die teuerste Wette werden.',
            "quote_line":   'Der Hype ist real. <span class="acc">Die Stats nicht.</span> ⚠️',
            "data_source":  "Daten: 2022-2025 Brasilien-Auftritte",
        },
    },

    # ─────────────── Di 2026-06-09 — Iran Defense ──────────────
    "2026-06-09": {
        "theme": "hidden_gem",
        "series_tag": "STORY 11 / 10",
        "hook": {
            "big_number":      "0.6",
            "sub_title":       "Gegentore Ø · Iran",
            "hook_line_1":     '<span class="acc">Beste Defensive</span>',
            "hook_line_2":     'der Asien-Quali.',
            "mystery_question":"Wer kommt da überhaupt durch?",
            "highlight_fact":  "9 Spiele · 5 zu Null · 0 verlorene Spiele",
        },
        "info": {
            "flag":         "🇮🇷",
            "name":         "Iran",
            "role_line":    "Gruppe G · gegen Belgien, Ägypten, NZ",
            "stat1_val":    "0.6",  "stat1_lbl": "Gegen-Ø",
            "stat2_val":    "5/9",  "stat2_lbl": "Clean Sheets",
            "stat3_val":    "9-0",  "stat3_lbl": "Unbesiegt",
            "closing_line": '<strong>Iran vs Belgien 18.06. — Über 2.5 @1.80 ist Falle.</strong> Belgien-Sturm trifft auf eine der besten Defensiven die noch keiner gesehen hat. Modell sagt Unter 2.5 mit +9pp Edge.',
            "quote_line":   'Defense first. <span class="acc">Quoten last.</span> 🛡',
            "data_source":  "Daten: Asien-Quali 2024/25",
        },
    },

    # ─────────────── Mi 2026-06-10 — Eröffnungsspiel Showdown ──────────────
    "2026-06-10": {
        "theme": "geheimfavorit",
        "series_tag": "FINALE · D-1",
        "hook": {
            "big_number":      "T-1",
            "sub_title":       "MORGEN startet die WM",
            "hook_line_1":     '<span class="acc">Brasilien</span> trifft auf',
            "hook_line_2":     'das <span class="yellow">Schreckgespenst</span> 2022.',
            "mystery_question":"Wer schreibt Geschichte?",
            "highlight_fact":  "Marokko hat 2022 Spanien + Portugal aus der WM geworfen",
        },
        "info": {
            "flag":         "🇧🇷",
            "name":         "BRA vs MAR",
            "role_line":    "Eröffnungsspiel · MetLife Stadium · Fr 18:00 Wien",
            "stat1_val":    "1959", "stat1_lbl": "Elo BRA",
            "stat2_val":    "1778", "stat2_lbl": "Elo MAR",
            "stat3_val":    "+181", "stat3_lbl": "Elo-Diff",
            "closing_line": '<strong>Marokko-Defense kassiert nur 0.3 Gegentore</strong> · Brasilien-xG nur 0.6 nach Trainer-Wechsel. Unter 2.5 Tore @1.85 mit +6pp Edge — der erste Pick steht.',
            "quote_line":   'Morgen früh um 9 kommt der <span class="acc">erste Match-Tag</span>. 🎬',
            "data_source":  "Daten: wm2026-data.json + Polymarket",
        },
    },
}


def _qualified_team_flags() -> tuple[set[str], set[str]]:
    """
    Lädt die qualifizierten WM-Teams aus wm2026-data.json.
    Liefert (names_lower, flag_emojis).
    """
    import json
    from pathlib import Path
    wm_file = Path(__file__).parent / "wm2026-data.json"
    if not wm_file.exists():
        return set(), set()
    try:
        wm = json.loads(wm_file.read_text(encoding="utf-8"))
        names = set()
        flags = set()
        for gdata in (wm.get("groups") or {}).values():
            for t in gdata.get("teams", []):
                if t.get("name"):
                    names.add(t["name"].lower())
                if t.get("id"):
                    names.add(t["id"].lower())
                if t.get("flag"):
                    flags.add(t["flag"])
        return names, flags
    except Exception:
        return set(), set()


# Whitelist von Story-Konzepten die NICHT auf einem spezifischen Team basieren
# (Vergleichs-Stories, Markt-Analysen, Top-Scorer-Races etc.)
_TEAM_AGNOSTIC_NAMES = {
    "top-scorer-race", "wm bilanz", "bra vs mar",
    "marokko travel",   # Travel-Story bezieht sich auf qualifiziertes Team
}


def _story_uses_phantom_team(entry: dict) -> str | None:
    """
    Prüft ob die Story ein Team referenziert das NICHT bei der WM 2026 ist.
    Liefert den Namen des Phantom-Teams oder None wenn alles OK.

    Validation in 2 Stufen:
      1. flag-Emoji muss qualifiziertes WM-Team-Flag sein
      2. Mindestens 1 Token aus name+role_line muss in Team-Namen sein

    Eingebaut 04.06.2026 nachdem eine Lewandowski/Polen-Card rausging —
    Polen hatte sich nicht qualifiziert.
    """
    info = entry.get("info") or {}
    name_lower = (info.get("name") or "").lower()
    if name_lower in _TEAM_AGNOSTIC_NAMES:
        return None   # bewusst team-agnostische Story

    qualified_names, qualified_flags = _qualified_team_flags()
    if not qualified_names:
        return None   # keine WM-Daten verfügbar — kein Check möglich

    # Flag-Check: wenn flag gesetzt UND nicht in qualifizierten Flags → Phantom
    flag = (info.get("flag") or "").strip()
    flag_known = flag and flag in qualified_flags
    flag_generic = flag in ("⚽", "🏳️", "")   # Top-Scorer-Race nutzt generisches Flag
    if flag and not flag_known and not flag_generic:
        return f"Flag {flag} nicht in WM 2026"

    # Token-Check: irgendein Token aus name+role_line muss qualifiziert sein
    full_text = f"{info.get('name','')} {info.get('role_line','')}".lower()
    # Lookup-Tokens — replace separators
    for sep in ("·", ",", "(", ")", "/", "-"):
        full_text = full_text.replace(sep, " ")
    tokens = [t.strip() for t in full_text.split() if len(t) >= 2]

    for tok in tokens:
        if tok in qualified_names:
            return None   # ein Token matched → OK

    # Tokens wie "Lewandowski" sind nicht in qualified_names (das sind Team-Namen)
    # → Fallback: wenn flag bekannt ist UND kein klarer Bruch im Text → OK
    if flag_known:
        return None

    return name_lower or "unknown"


def get_story_for_date(date_str: str) -> dict | None:
    """
    Liefert Story-Config für ein Datum, oder None wenn nichts geplant.

    Phantom-Team-Guard: wenn die Story auf ein Team verweist das NICHT in
    wm2026-data.json::groups[*].teams steht (z.B. Polen 2026), wird die Story
    NICHT ausgeliefert + Warning geloggt. Verhindert peinliche Cards.
    """
    entry = STORY_PLAN.get(date_str)
    if not entry:
        return None
    if entry.get("posted_manually"):
        return None
    phantom = _story_uses_phantom_team(entry)
    if phantom:
        print(f"⚠️  Story für {date_str} referenziert nicht-qualifiziertes Team "
              f"'{phantom}' — Card wird NICHT generiert. Plan korrigieren!")
        return None
    return entry
