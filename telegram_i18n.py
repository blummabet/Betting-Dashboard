#!/usr/bin/env python3
"""telegram_i18n.py — Übersetzungsschicht für den Public-Telegram-Content (04.07.2026, Lucas:
„Picks deutsch UND englisch für internationale Gruppen").

Reine Lookup-/Übersetzungs-Funktionen (keine Sends). telegram_wm.py rendert Morning-Card + Recap
zweisprachig, indem es lang='de'|'en' durchreicht. lang='de' bleibt 1:1 wie bisher (regressionsfrei),
'en' nutzt diese Tabellen. Team-Namen (national) + Markt-Bezeichnungen liegen auf Deutsch in den
Pick-Daten und werden hier für EN übersetzt (sonst Denglisch)."""
from __future__ import annotations
import re

# ── National-Team-Namen (FIFA-Code → Englisch). Fallback = deutscher Name (z.B. Vereine). ──
EN_TEAM = {
    "ARG": "Argentina", "AUS": "Australia", "AUT": "Austria", "BEL": "Belgium",
    "BIH": "Bosnia & H.", "BRA": "Brazil", "CAN": "Canada", "CIV": "Ivory Coast",
    "COD": "DR Congo", "COL": "Colombia", "CPV": "Cape Verde", "CRO": "Croatia",
    "CUW": "Curaçao", "CZE": "Czechia", "DZA": "Algeria", "ECU": "Ecuador",
    "EGY": "Egypt", "ENG": "England", "ESP": "Spain", "FRA": "France",
    "GER": "Germany", "GHA": "Ghana", "HTI": "Haiti", "IRN": "Iran", "IRQ": "Iraq",
    "JOR": "Jordan", "JPN": "Japan", "KOR": "South Korea", "MAR": "Morocco",
    "MEX": "Mexico", "NED": "Netherlands", "NOR": "Norway", "NZL": "New Zealand",
    "PAN": "Panama", "POR": "Portugal", "PRY": "Paraguay", "QAT": "Qatar",
    "SAU": "Saudi Arabia", "SCO": "Scotland", "SEN": "Senegal", "SUI": "Switzerland",
    "SWE": "Sweden", "TUN": "Tunisia", "TUR": "Türkiye", "URU": "Uruguay",
    "USA": "USA", "UZB": "Uzbekistan", "ZAF": "South Africa",
}

# ── Runden-Labels (deutsch → englisch) ──
ROUND_EN = {
    "Sechzehntelfinale": "Round of 32", "Achtelfinale": "Round of 16",
    "Viertelfinale": "Quarter-final", "Halbfinale": "Semi-final",
    "Finale": "Final", "Spiel um Platz 3": "Third-place Play-off",
    "K.O.-Runde": "Knockout", "K.-o.-Runde": "Knockout",
}

# ── Markt-Übersetzung (längste Tokens zuerst → keine Teil-Treffer) ──
_MARKET_TOKENS = [
    ("Beide Teams treffen", "Both Teams to Score"),
    ("Doppelte Chance", "Double Chance"),
    ("DNB: Heimteam", "DNB: Home"), ("DNB: Auswärtsteam", "DNB: Away"),
    ("AH Heim", "AH Home"), ("AH Auswärts", "AH Away"),
    ("Heimsieg", "Home Win"), ("Auswärtssieg", "Away Win"),
    ("Unentschieden", "Draw"),
    ("Über", "Over"), ("Unter", "Under"),
    ("Tore", "Goals"), ("Ecken", "Corners"), ("Karten", "Cards"),
    ("Ja", "Yes"), ("Nein", "No"),
]


def market_label(market: str, lang: str = "de") -> str:
    if lang != "en" or not market:
        return market
    out = market
    for de, en in _MARKET_TOKENS:
        out = re.sub(rf"(?<![A-Za-zÄÖÜäöü]){re.escape(de)}(?![A-Za-zÄÖÜäöü])", en, out)
    return out.replace(",", ".")   # „2,5" → „2.5" für internationales Publikum


def team_name(tid: str, de_name: str, lang: str = "de") -> str:
    if lang == "en":
        return EN_TEAM.get(str(tid), de_name)
    return de_name


def round_label(de_label: str, lang: str = "de") -> str:
    if lang == "en":
        return ROUND_EN.get(de_label, de_label)
    return de_label


# ── Fixe Strings ──
L = {
    "de": {
        "morning_head":  "🌍 <b>WM 2026 — Heute · {n} Spiel{p}</b>",
        "morning_n_plural": "e",
        "bets_line":     "🟢 <b>{n} BET{p}</b> — Engine und Signale überzeugt\n",
        "no_bet":        "👀 Heute kein BET — die Engine wartet auf den richtigen Moment\n",
        "group_head":    "━━ Gruppe {g} · Spieltag {md} ━━",
        "no_edge":       "🔇 Kein Pick mit ausreichend Edge",
        "bet":           "BET",
        "lean":          "Abwägen:",
        "signals_for":   "   💡 {n} Signale dafür{neg}",
        "signals_neg":   ", {n} dagegen",
        "safer":         "   🛡 Sicherer: {market} @{odds}",
        "top_pick":      "🎯 Top-Pick", "main_pick": "⭐ Main-Pick", "insurance": "🛡 Insurance",
        "signals_short": "Signale dafür",
        "pinn_for":      "stützt Pick", "pinn_against": "gegen Pick",
        "pinn_fresh":    " (frisch)", "pinn_old": " (älter)", "pinn_line": "   🔥 Pinnacle {dir}{age}",
        "footer":        "\n🤖 CocoBet · datengetriebenes Pick-Modell mit 19 Signalen",
        "recap_head":    "📊 <b>WM 2026 Recap — {date}</b>\n",
        "recap_today":   "💰 Heutiger Tag: {pnl}",
        "recap_push":    "Push",
        "recap_footer":  "\n🤖 CocoBet WM 2026",
        "record":        "📈 WM-Bilanz: {w}W-{l}L-{p}P | ROI: {roi} | P&L: {pnl}",
    },
    "en": {
        "morning_head":  "🌍 <b>World Cup 2026 — Today · {n} game{p}</b>",
        "morning_n_plural": "s",
        "bets_line":     "🟢 <b>{n} BET{p}</b> — engine and signals convinced\n",
        "no_bet":        "👀 No BET today — the engine is waiting for the right spot\n",
        "group_head":    "━━ Group {g} · Matchday {md} ━━",
        "no_edge":       "🔇 No pick with enough edge",
        "bet":           "BET",
        "lean":          "Lean:",
        "signals_for":   "   💡 {n} signals in favour{neg}",
        "signals_neg":   ", {n} against",
        "safer":         "   🛡 Safer: {market} @{odds}",
        "top_pick":      "🎯 Top pick", "main_pick": "⭐ Main pick", "insurance": "🛡 Insurance",
        "signals_short": "signals",
        "pinn_for":      "backs the pick", "pinn_against": "against the pick",
        "pinn_fresh":    " (fresh)", "pinn_old": " (older)", "pinn_line": "   🔥 Pinnacle {dir}{age}",
        "footer":        "\n🤖 CocoBet · data-driven pick model, 19 signals",
        "recap_head":    "📊 <b>World Cup 2026 Recap — {date}</b>\n",
        "recap_today":   "💰 Today: {pnl}",
        "recap_push":    "Push",
        "recap_footer":  "\n🤖 CocoBet World Cup 2026",
        "record":        "📈 WC record: {w}W-{l}L-{p}P · ROI {roi}",
    },
}

_SIG_NARRATIVE_EN = {
    "weather_signal": "🌡 weather helps", "travel_burden": "✈ travel hurts opponent",
    "pressure_index": "🎯 table pressure", "form_trend": "📈 form fits",
    "xg_strength": "🥅 xG edge", "h2h_pattern": "🤝 H2H pattern fits",
    "injury": "🩹 injuries help", "apif_predictions": "📊 external model agrees",
    "lead_lag_bias": "📡 sharp lag (Bet365 behind)", "public_static_bias": "🎲 public bias vs pick",
    "incentive_signal": "🏆 incentive backs it", "lineup_signal": "📋 lineup confirms",
}


def sig_narrative(lang: str) -> dict:
    return _SIG_NARRATIVE_EN if lang == "en" else None   # None → telegram_wm nutzt sein DE-Dict


def upset_label(score: int, lang: str = "de") -> str:
    if lang == "en":
        if score >= 8: return "🔥🔥 BIG UPSET POSSIBLE"
        if score >= 6: return "🔥 UPSET ALERT"
        if score >= 4: return "⚠️ Even matchup"
        return ""
    if score >= 8: return "🔥🔥 GROSSER UPSET MÖGLICH"
    if score >= 6: return "🔥 UPSET ALERT"
    if score >= 4: return "⚠️ Ausgeglichenes Spiel"
    return ""


def pick_intro_en(market_de: str, market_en: str, home: str, away: str, fav: str | None) -> str | None:
    """Englische Pick-konsistente Einleitung (Spiegel von telegram_wm._pick_intro)."""
    m = (market_de or "").lower()
    favc = f"{fav} are favoured, but " if fav else ""
    if "unter" in m or "under" in m:
        return f"{favc}the model expects a tight, low-scoring game — value on <b>{market_en}</b>."
    if "über" in m or "uber" in m or "over" in m:
        return f"The model expects an open, high-scoring game — value on <b>{market_en}</b>."
    if "beide teams treffen" in m or "btts" in m:
        return f"The model sees goals at both ends — value on <b>{market_en}</b>."
    backs = None
    if any(t in m for t in ("heimsieg", "ah heim", "dnb: heim")) or "1x" in m:
        backs = home
    elif any(t in m for t in ("auswärtssieg", "auswaertssieg", "ah auswärt", "dnb: auswärt")) or "x2" in m:
        backs = away
    if backs:
        if fav and backs != fav:
            return f"{favc}{backs} are underrated by the market — value on the underdog side <b>{market_en}</b>."
        return f"The model backs {backs} — value on <b>{market_en}</b>."
    return None
