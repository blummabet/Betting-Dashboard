# 🟡 Picks Validator — 17.11.2026 02:08

**5 Spiele geprüft** · 🔴 0 Fehler · 🟡 4 Warnungen · 🔵 17 Hinweise

```
=================================================================
  🐕 CocoBet — Picks Logik-Check
  17.11.2026 02:08
  Filter: nächste 3 Tag(e)
=================================================================

─────────────────────────────────────────────────────────────────
  🇧🇪 Jupiler Pro League  (rl=29)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 20.11.2026  Cercle Brugge vs KVC Westerlo
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 20.11.2026  Cercle Brugge vs KVC Westerlo
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 20.11.2026  Cercle Brugge vs KVC Westerlo
     H2H Schnitt=3.4 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 20.11.2026  Cercle Brugge vs KVC Westerlo
     Ø gpg=1.70, H2H Ø=3.4 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 20.11.2026  Cercle Brugge vs KVC Westerlo
     Ø gpg=1.70 (statischer Proxy) → Poisson FV für Over 3.5 = 9.3%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.

─────────────────────────────────────────────────────────────────
  🇪🇸 La Liga  (rl=26)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 20.11.2026  Athletic Club vs Espanyol
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 20.11.2026  Athletic Club vs Espanyol
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.

─────────────────────────────────────────────────────────────────
  🇫🇷 Ligue 1  (rl=24)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [BOTRED_ASYMMETRIC_PRESSURE]
     📅 20.11.2026  Estac Troyes vs Le Havre
     Kellerduell-Narrativ aber asymmetrischer Druck: Le Havre pressureRatio=0.36 vs Estac Troyes pressureRatio=0.29. Nur eine Mannschaft kämpft wirklich — Angle zu vereinfacht.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 20.11.2026  Estac Troyes vs Le Havre
     Estac Troyes: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 20.11.2026  Estac Troyes vs Le Havre
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 20.11.2026  Estac Troyes vs Le Havre
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.

─────────────────────────────────────────────────────────────────
  🇩🇪 Bundesliga  (rl=25)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 20.11.2026  Bayern München vs 1. FC Köln
     Bayern München dominiert H2H 17W/2X/1L in 20 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🔵 HINWEIS [H2H_DOM_GOLD_RED]
     📅 20.11.2026  Bayern München vs 1. FC Köln
     Bayern München dominiert H2H 17W/2X/1L in 20 Spielen. Gold vs Rot, aber H2H-Favorit klar — Angle sollte Pick-Richtung bestätigen, nicht dramatisieren.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 20.11.2026  Bayern München vs 1. FC Köln
     1. FC Köln: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 20.11.2026  Bayern München vs 1. FC Köln
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 20.11.2026  Bayern München vs 1. FC Köln
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 20.11.2026  Bayern München vs 1. FC Köln
     H2H Schnitt=3.5 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 20.11.2026  Bayern München vs 1. FC Köln
     1. FC Köln expA≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇵🇱 Ekstraklasa  (rl=20)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [ASYMMETRIC_STAKE_SCORES]
     📅 20.11.2026  Pogon Szczecin vs Slask Wroclaw
     Score-Differenz 5.0 Punkte: Slask Wroclaw (9.5) vs Pogon Szczecin (4.5). Pick-Richtung sehr klar — Favoritenpflicht prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 20.11.2026  Pogon Szczecin vs Slask Wroclaw
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 20.11.2026  Pogon Szczecin vs Slask Wroclaw
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.

═════════════════════════════════════════════════════════════════
  Geprüft: 5 Spiele
  🟡 4 Warnungen — manuelle Prüfung empfohlen
  🔵 17 Hinweise — Pick-Richtung kontrollieren
═════════════════════════════════════════════════════════════════

```
