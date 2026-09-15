# 🟡 Picks Validator — 15.09.2026 21:24

**21 Spiele geprüft** · 🔴 0 Fehler · 🟡 13 Warnungen · 🔵 65 Hinweise

```
=================================================================
  🐕 CocoBet — Picks Logik-Check
  15.09.2026 21:24
  Filter: nächste 3 Tag(e)
=================================================================

─────────────────────────────────────────────────────────────────
  🇦🇹 Österreich BL  (rl=26)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 18.09.2026  Rapid Vienna vs WSG Wattens
     Liga-Baserate=3.7 → Poisson FV für Über 3.5 Karten = 50.6% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+5.0%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 18.09.2026  Rapid Vienna vs WSG Wattens
     Liga-Baserate=3.7 → Poisson FV für Über 4.5 Karten = 31.3%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 18.09.2026  Rapid Vienna vs WSG Wattens
     H2H Schnitt=3.0 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.

─────────────────────────────────────────────────────────────────
  🇧🇪 Jupiler Pro League  (rl=34)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 18.09.2026  Gent vs Standard Liege
     Gent dominiert H2H 15W/2X/3L in 20 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 18.09.2026  Gent vs Standard Liege
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 18.09.2026  Gent vs Standard Liege
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 18.09.2026  Gent vs Standard Liege
     H2H Schnitt=3.4 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 18.09.2026  Gent vs Standard Liege
     Ø gpg=1.70, H2H Ø=3.4 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 18.09.2026  Gent vs Standard Liege
     Ø gpg=1.70 (statischer Proxy) → Poisson FV für Over 3.5 = 9.3%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.

─────────────────────────────────────────────────────────────────
  🇭🇷 HNL  (rl=29)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [BOTRED_ASYMMETRIC_PRESSURE]
     📅 18.09.2026  Rudes vs NK Slaven Belupo
     Kellerduell-Narrativ aber asymmetrischer Druck: Rudes pressureRatio=0.33 vs NK Slaven Belupo pressureRatio=0.30. Nur eine Mannschaft kämpft wirklich — Angle zu vereinfacht.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 18.09.2026  Rudes vs NK Slaven Belupo
     NK Slaven Belupo: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 18.09.2026  Rudes vs NK Slaven Belupo
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 18.09.2026  Rudes vs NK Slaven Belupo
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.

─────────────────────────────────────────────────────────────────
  🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League  (rl=34)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 18.09.2026  Brentford vs Chelsea
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.

─────────────────────────────────────────────────────────────────
  🇪🇸 La Liga  (rl=32)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 16.09.2026  Atletico Madrid vs Osasuna
     Atletico Madrid dominiert H2H 17W/0X/3L in 20 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 16.09.2026  Atletico Madrid vs Osasuna
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 16.09.2026  Atletico Madrid vs Osasuna
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 16.09.2026  Atletico Madrid vs Osasuna
     Osasuna expA≈1.05 (statischer Proxy) → FV über 1.5 = 28.3%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 16.09.2026  Deportivo La Coruna vs Sevilla
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 16.09.2026  Deportivo La Coruna vs Sevilla
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 16.09.2026  Deportivo La Coruna vs Sevilla
     H2H Schnitt=3.4 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 16.09.2026  Deportivo La Coruna vs Sevilla
     Sevilla expA≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 16.09.2026  Barcelona vs Racing Santander
     Barcelona dominiert H2H 5W/0X/0L in 5 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 16.09.2026  Barcelona vs Racing Santander
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 16.09.2026  Barcelona vs Racing Santander
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 16.09.2026  Barcelona vs Racing Santander
     Racing Santander expA≈1.25 (statischer Proxy) → FV über 1.5 = 35.5%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 16.09.2026  Levante vs Athletic Club
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 16.09.2026  Levante vs Athletic Club
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 16.09.2026  Levante vs Athletic Club
     Ø gpg=1.30, H2H Ø=3.0 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 16.09.2026  Levante vs Athletic Club
     Ø gpg=1.30 (statischer Proxy) → Poisson FV für Over 3.5 = 4.3%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 17.09.2026  Real Betis vs Getafe
     Getafe: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 17.09.2026  Real Betis vs Getafe
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 17.09.2026  Real Betis vs Getafe
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 17.09.2026  Real Betis vs Getafe
     Real Betis expH≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 17.09.2026  Real Betis vs Getafe
     Getafe expA≈1.25 (statischer Proxy) → FV über 1.5 = 35.5%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🟡 WARNUNG [BOTRED_ASYMMETRIC_PRESSURE]
     📅 17.09.2026  Malaga vs Villarreal
     Kellerduell-Narrativ aber asymmetrischer Druck: Villarreal pressureRatio=0.30 vs Malaga pressureRatio=0.29. Nur eine Mannschaft kämpft wirklich — Angle zu vereinfacht.
  🟡 WARNUNG [HOME_POOR_FORM_HIGH_SCORE]
     📅 17.09.2026  Malaga vs Villarreal
     Malaga: formScore=0.22 (sehr schwach) aber matchScore=7.5. Pick-Basis könnte überschätzt sein — Formeinbruch nicht ausreichend gewichtet.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 17.09.2026  Malaga vs Villarreal
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 17.09.2026  Malaga vs Villarreal
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 17.09.2026  Malaga vs Villarreal
     Ø gpg=2.20 (statischer Proxy) → Poisson FV für Over 3.5 = 18.1%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 18.09.2026  Espanyol vs Elche
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 18.09.2026  Espanyol vs Elche
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 18.09.2026  Espanyol vs Elche
     Elche expA≈1.25 (statischer Proxy) → FV über 1.5 = 35.5%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇫🇷 Ligue 1  (rl=30)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 18.09.2026  Monaco vs Lens
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 18.09.2026  Monaco vs Lens
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 18.09.2026  Monaco vs Lens
     H2H Schnitt=3.6 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.

─────────────────────────────────────────────────────────────────
  🇩🇪 Bundesliga  (rl=31)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 18.09.2026  Bayern München vs Union Berlin
     Union Berlin: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 18.09.2026  Bayern München vs Union Berlin
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 18.09.2026  Bayern München vs Union Berlin
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 18.09.2026  Bayern München vs Union Berlin
     H2H Schnitt=3.3 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.

─────────────────────────────────────────────────────────────────
  🇭🇺 NB I  (rl=26)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 18.09.2026  Puskas Academy vs Budapest Honved
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 18.09.2026  Puskas Academy vs Budapest Honved
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.

─────────────────────────────────────────────────────────────────
  🇮🇹 Serie A  (rl=34)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 18.09.2026  Monza vs Sassuolo
     Monza: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 18.09.2026  Monza vs Sassuolo
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 18.09.2026  Monza vs Sassuolo
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.

─────────────────────────────────────────────────────────────────
  🇳🇱 Eredivisie  (rl=28)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 18.09.2026  Groningen vs PEC Zwolle
     PEC Zwolle: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 18.09.2026  Groningen vs PEC Zwolle
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 18.09.2026  Groningen vs PEC Zwolle
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 18.09.2026  Groningen vs PEC Zwolle
     Ø gpg=1.00, H2H Ø=2.4 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 18.09.2026  Groningen vs PEC Zwolle
     Ø gpg=1.00 (statischer Proxy) → Poisson FV für Over 3.5 = 2.0%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.

─────────────────────────────────────────────────────────────────
  🇵🇱 Ekstraklasa  (rl=26)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 18.09.2026  Widzew Łódź vs Wieczysta Kraków
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 18.09.2026  Widzew Łódź vs Wieczysta Kraków
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 18.09.2026  Widzew Łódź vs Wieczysta Kraków
     Ø gpg=1.30 — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 18.09.2026  Widzew Łódź vs Wieczysta Kraków
     Ø gpg=1.30 (statischer Proxy) → Poisson FV für Over 3.5 = 4.3%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 18.09.2026  Wisla Krakow vs Slask Wroclaw
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 18.09.2026  Wisla Krakow vs Slask Wroclaw
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 18.09.2026  Wisla Krakow vs Slask Wroclaw
     Slask Wroclaw expA≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇨🇭 Swiss SL  (rl=28)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 16.09.2026  FC Lugano vs FC ST. Gallen
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 16.09.2026  FC Lugano vs FC ST. Gallen
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 16.09.2026  FC Lugano vs FC ST. Gallen
     Ø gpg=1.80, H2H Ø=2.8 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 16.09.2026  FC Lugano vs FC ST. Gallen
     Ø gpg=1.80 (statischer Proxy) → Poisson FV für Over 3.5 = 10.9%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 16.09.2026  FC Thun vs Servette FC
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 16.09.2026  FC Thun vs Servette FC
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 16.09.2026  FC Thun vs Servette FC
     H2H Schnitt=3.6 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 16.09.2026  FC Thun vs Servette FC
     FC Thun expH≈1.05 (statischer Proxy) → FV über 1.5 = 28.3%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇹🇷 Süper Lig  (rl=33)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 18.09.2026  Kasımpaşa vs Konyaspor
     Konyaspor: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 18.09.2026  Kasımpaşa vs Konyaspor
     H2H Schnitt=3.2 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 18.09.2026  Kasımpaşa vs Konyaspor
     Konyaspor expA≈0.90 (statischer Proxy) → FV über 1.5 = 22.8%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

═════════════════════════════════════════════════════════════════
  Geprüft: 21 Spiele
  🟡 13 Warnungen — manuelle Prüfung empfohlen
  🔵 65 Hinweise — Pick-Richtung kontrollieren
═════════════════════════════════════════════════════════════════

```
