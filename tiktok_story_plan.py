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

    # ─────────────── Do 2026-06-04 — Lewandowski letzte WM ──────────────
    "2026-06-04": {
        "theme": "letzte_wm",
        "series_tag": "STORY 6 / 10",
        "hook": {
            "big_number":      "37",
            "sub_title":       "Jahre · Letzte WM",
            "hook_line_1":     'Sein <span class="acc">letzter Lauf</span>',
            "hook_line_2":     'mit dem polnischen Adler.',
            "mystery_question":"Schafft er es ein letztes Mal?",
            "highlight_fact":  "84 Länderspiel-Tore — Rekord seit 1939",
        },
        "info": {
            "flag":         "🇵🇱",
            "name":         "R. Lewandowski",
            "role_line":    "Polen · Stürmer · Barcelona",
            "stat1_val":    "37",   "stat1_lbl": "Jahre alt",
            "stat2_val":    "84",   "stat2_lbl": "Länderspiel-Tore",
            "stat3_val":    "0.92", "stat3_lbl": "Tore / Spiel",
            "closing_line": 'Polen <strong>scheiterte 2022 im Achtelfinale an Frankreich</strong>. Diese WM ist Lewys realistisch letzte Chance auf den großen Knall.',
            "quote_line":   'Mit 41 spielt Ronaldo. Mit 37 holt <span class="acc">Lewy</span> seinen Frieden. 🦅',
            "data_source":  "Daten: Polen 2018-2025",
        },
    },

    # ─────────────── Fr 2026-06-05 — Senegal Form ──────────────
    "2026-06-05": {
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


def get_story_for_date(date_str: str) -> dict | None:
    """Liefert Story-Config für ein Datum, oder None wenn nichts geplant."""
    entry = STORY_PLAN.get(date_str)
    if not entry:
        return None
    if entry.get("posted_manually"):
        return None
    return entry
