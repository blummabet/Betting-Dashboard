#!/usr/bin/env python3
"""
bizarre_comparisons.py — Vergleichs-Bibliothek für TikTok-Bizarre-Quoten-Cards

5 Tiers nach Wahrscheinlichkeit:
  Tier 1 (mainstream):  20-50 %   — Sport, Pop, Alltag
  Tier 2 (selten):       5-20 %   — Aussergewöhnlich aber denkbar
  Tier 3 (sehr selten):  1-5  %   — Skurril aber statistisch
  Tier 4 (krass selten): 0,1-1 %  — Nahe Lotto-Niveau
  Tier 5 (Lotto-tier):   0,01-0,1 % — Lotto, Naturereignisse

Jeder Vergleich hat: (emoji, text, prob_pct_string, prob_value_for_sorting)
prob_value_for_sorting ist die Schätzung als Float in % (für Filter-Logik).
"""

# Format: (emoji, text, displayed_pct, value_pct)
TIER_1_MAINSTREAM = [
    ("🏎", "Verstappen wird 2026 wieder F1-Weltmeister",              "≈ 40 %",  40.0),
    ("⚽", "Bayern wird wieder Bundesliga-Meister 2026/27",            "≈ 50 %",  50.0),
    ("🎬", "Tom Cruise stuntet noch persönlich in MI:9",               "≈ 30 %",  30.0),
    ("🎵", "Taylor Swift bringt 2026 noch ein Album raus",             "≈ 30 %",  30.0),
    ("🌧", "Es regnet diese Woche in Wien",                            "≈ 50 %",  50.0),
    ("📺", "Du schaust heute mehr als 1h Netflix",                     "≈ 50 %",  50.0),
    ("🍕", "Du isst diese Woche Pizza",                                "≈ 40 %",  40.0),
    ("🏁", "Hamilton fährt ein Podium-Rennen 2026",                    "≈ 40 %",  40.0),
    ("💻", "Microsoft Word crasht heute irgendwo auf der Welt",        "≈ 80 %",  80.0),
    ("🏆", "Real Madrid gewinnt NICHT die Champions League 2026",      "≈ 60 %",  60.0),
    ("☕", "Du trinkst heute Kaffee",                                  "≈ 60 %",  60.0),
    ("📱", "Du checkst dein Handy in der nächsten Minute",             "≈ 80 %",  80.0),
    ("🛒", "Aldi macht diese Woche Werbung",                           "≈ 95 %",  95.0),
]

TIER_2_SELTEN = [
    ("🇧🇷", "Brasilien wird Weltmeister 2026",                         "≈ 16 %",  16.0),
    ("📱", "ChatGPT antwortet komplett ohne Halluzination",            "≈ 15 %",  15.0),
    ("🦄", "Du siehst heute einen Regenbogen",                         "≈ 10 %",  10.0),
    ("⚽", "Pep Guardiola gewinnt die nächste Champions League",        "≈ 10 %",  10.0),
    ("🥑", "Avocado-Preis steigt diese Woche",                         "≈ 15 %",  15.0),
    ("📱", "Apple stellt 2026 ein neues iPad vor",                     "≈ 10 %",  10.0),
    ("💸", "Bitcoin verdoppelt sich dieses Jahr",                      "≈ 10 %",  10.0),
    ("🍜", "Du findest ein Haar in deiner Suppe diese Woche",          "≈ 5 %",   5.0),
    ("🍔", "McDonalds führt Steak-Burger ein",                         "≈ 5 %",   5.0),
    ("🇩🇪", "Deutschland wird Vorrundenletzter WM 2026",                "≈ 5 %",   5.0),
    ("🇦🇹", "Österreich erreicht das WM-Achtelfinale",                  "≈ 10 %",  10.0),
    ("🎟", "Du gewinnst beim nächsten Glücksspiel-Tipp",               "≈ 10 %",  10.0),
    ("🚗", "Du sitzt heute mindestens 30 Min im Stau",                 "≈ 20 %",  20.0),
]

TIER_3_SEHR_SELTEN = [
    ("✈️", "Dein Ryanair-Flug startet 100 % pünktlich",                "≈ 1 %",   1.0),
    ("🍕", "Du zahlst &gt; 30 € für eine Pizza Margherita",             "≈ 1 %",   1.0),
    ("🇦🇹", "Österreich gewinnt EM 2028",                               "≈ 1 %",   1.0),
    ("🚇", "Wiener U-Bahn fährt eine Stunde 100 % verspätungsfrei",    "≈ 5 %",   5.0),
    ("📱", "Dein Akku hält 24h ohne einmal Aufladen",                  "≈ 3 %",   3.0),
    ("🍌", "Eine Banane kostet &gt; 5 € im Supermarkt",                 "≈ 1 %",   1.0),
    ("🌮", "McDonalds wird Bio-Restaurant",                            "≈ 3 %",   3.0),
    ("🇯🇵", "Japan wird Weltmeister 2026",                              "≈ 3 %",   3.0),
    ("🦘", "Du siehst zufällig ein Känguru in Mitteleuropa",           "≈ 2 %",   2.0),
    ("🛒", "Aldi senkt heute Nutella unter 2 €",                       "≈ 2 %",   2.0),
    ("🚌", "ÖBB-Tageskarte ist heute spontan gratis",                  "≈ 2 %",   2.0),
    ("🎮", "Du findest heute einen seltenen Lego-Stein im Sand",       "≈ 2 %",   2.0),
    ("🍓", "Erdbeere kostet &lt; 1 € pro 500 g",                        "≈ 5 %",   5.0),
]

TIER_4_KRASS_SELTEN = [
    ("❄️", "Es schneit in Wien im August",                             "0,2 %",   0.2),
    ("🌪", "Tornado in Mitteleuropa diese Woche",                      "0,5 %",   0.5),
    ("🐯", "Ein Tiger bricht aus dem Wiener Zoo aus",                  "0,1 %",   0.1),
    ("🎬", "Du triffst Tom Cruise zufällig in Wien",                   "0,2 %",   0.2),
    ("🐳", "Ein Wal verirrt sich in die Donau",                        "0,1 %",   0.1),
    ("🚀", "SpaceX startet diese Woche ohne Verspätung",               "0,5 %",   0.5),
    ("🌋", "Vulkan-Ausbruch in Europa diese Woche",                    "0,1 %",   0.1),
    ("🌧", "Es regnet diese Woche in der Sahara",                      "0,5 %",   0.5),
    ("🍦", "McDonalds-Eismaschine funktioniert weltweit überall",      "0,1 %",   0.1),
    ("📵", "Komplette Twitter-Outage länger als 24h",                  "0,3 %",   0.3),
    ("🎵", "Ein Klassiker von 1960 stürmt heute die Charts",           "0,2 %",   0.2),
    ("🍕", "Eine Pizza-Bestellung kommt vor der Bestellung an",        "0,01 %",  0.01),
]

TIER_5_LOTTO_TIER = [
    ("🎰", "Du knackst Lotto 5 Richtige",                              "0,095 %", 0.095),
    ("🦈", "Du wirst diese Woche von einem Hai gebissen",              "0,003 %", 0.003),
    ("⚡", "Du wirst diese Woche vom Blitz getroffen",                  "0,001 %", 0.001),
    ("💰", "Du gewinnst 100.000 € im EuroJackpot",                     "0,001 %", 0.001),
    ("🛰", "Die ISS stürzt diese Woche unkontrolliert ab",             "0,001 %", 0.001),
    ("👽", "Es gibt diese Woche offiziellen Erstkontakt mit Aliens",   "0,001 %", 0.001),
    ("🌋", "Ein neuer Vulkan entsteht in der Nordsee",                 "0,005 %", 0.005),
    ("🦄", "Ein lebendes Einhorn wird offiziell entdeckt",             "0,001 %", 0.001),
    ("🌌", "Ein Meteorit trifft einen bewohnten Ort in Europa",        "0,01 %",  0.01),
    ("🐉", "Drachen werden in einer Höhle in Asien entdeckt",          "0,001 %", 0.001),
]


# ── Wrapper: alle Tiers in einer Liste mit Tier-Index ─────────────────────────
ALL_TIERS = {
    1: TIER_1_MAINSTREAM,
    2: TIER_2_SELTEN,
    3: TIER_3_SEHR_SELTEN,
    4: TIER_4_KRASS_SELTEN,
    5: TIER_5_LOTTO_TIER,
}


def total_count() -> int:
    return sum(len(v) for v in ALL_TIERS.values())


def pick_for_quote(target_chance_pct: float, n: int = 6, seed: int | None = None) -> list[tuple]:
    """
    Wählt n Vergleiche die alle WAHRSCHEINLICHER sind als target_chance_pct.
    Mix-Strategy:
      · 1× Tier 1 (Punchline-Eröffnung)
      · 2× Tier 2-3 (Alltagsbezug)
      · 2× Tier 4 (vergleichbar selten)
      · 1× Tier 5 ODER eines knapp über target (Punch-Closer)
    Filter: nur Items mit value_pct >= target_chance_pct (sonst wären sie unwahrscheinlicher).
    Liefert sortiert (häufig → selten).
    """
    import random
    if seed is not None:
        random.seed(seed)

    def filter_tier(tier_list):
        return [c for c in tier_list if c[3] >= target_chance_pct]

    pools = {k: filter_tier(v) for k, v in ALL_TIERS.items()}

    picks = []
    # Strategy: 1-Tier1, 2 von Tier2+3, 2 von Tier4, 1 von Tier5 (Fallback wenn Tier leer)
    plan = [
        (1, 1),  # 1 Tier-1
        (2, 1), (3, 1),  # 1 von Tier 2, 1 von Tier 3
        (4, 2),  # 2 von Tier 4
        (5, 1),  # 1 von Tier 5
    ]

    used_ids = set()
    for tier, count in plan:
        avail = [c for c in pools[tier] if id(c) not in used_ids]
        sample = random.sample(avail, min(count, len(avail))) if avail else []
        for s in sample:
            used_ids.add(id(s))
        picks.extend(sample)

    # Falls weniger als n: aus allen verbleibenden Tiers nachfüllen
    if len(picks) < n:
        remaining = []
        for tier in (3, 2, 4, 1, 5):
            remaining.extend([c for c in pools[tier] if id(c) not in used_ids])
        random.shuffle(remaining)
        for c in remaining:
            if len(picks) >= n: break
            picks.append(c)
            used_ids.add(id(c))

    # Sortieren: häufig → selten (für Storytelling-Effekt)
    picks.sort(key=lambda c: -c[3])
    return picks[:n]


if __name__ == "__main__":
    print(f"Total comparisons in library: {total_count()}")
    print("\n=== Sample-Pick für target 0,029 % (Curacao) ===")
    for emoji, text, prob, val in pick_for_quote(0.029, n=6, seed=42):
        print(f"  {emoji}  {text:<55}  {prob:>10}  (val={val})")
