# 🟡 Picks Validator — 08.11.2026 16:54

**19 Spiele geprüft** · 🔴 0 Fehler · 🟡 11 Warnungen · 🔵 65 Hinweise

```
=================================================================
  🐕 CocoBet — Picks Logik-Check
  08.11.2026 16:54
  Filter: nächste 3 Tag(e)
=================================================================

─────────────────────────────────────────────────────────────────
  🇧🇪 Jupiler Pro League  (rl=29)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 08.11.2026  Union St. Gilloise vs Genk
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  Union St. Gilloise vs Genk
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 08.11.2026  St. Truiden vs Zulte Waregem
     Zulte Waregem: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 08.11.2026  St. Truiden vs Zulte Waregem
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  St. Truiden vs Zulte Waregem
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 08.11.2026  St. Truiden vs Zulte Waregem
     Zulte Waregem expA≈1.10 (statischer Proxy) → FV über 1.5 = 30.1%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇭🇷 HNL  (rl=23)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [MUSTWIN_LOW_GPG]
     📅 08.11.2026  NK Varazdin vs Dinamo Zagreb
     NK Varazdin: mustWin=True aber nur 0.7 Tore/Spiel — Pick 'muss gewinnen' bei Teams die kaum treffen ist unrealistisch.
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 08.11.2026  NK Varazdin vs Dinamo Zagreb
     Dinamo Zagreb dominiert H2H 15W/5X/0L in 20 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 08.11.2026  NK Varazdin vs Dinamo Zagreb
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  NK Varazdin vs Dinamo Zagreb
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 08.11.2026  NK Varazdin vs Dinamo Zagreb
     H2H Schnitt=3.0 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 08.11.2026  NK Varazdin vs Dinamo Zagreb
     NK Varazdin expH≈0.95 (statischer Proxy) → FV über 1.5 = 24.6%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League  (rl=28)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [HOME_POOR_FORM_HIGH_SCORE]
     📅 08.11.2026  Manchester United vs Aston Villa
     Manchester United: formScore=0.22 (sehr schwach) aber matchScore=7.5. Pick-Basis könnte überschätzt sein — Formeinbruch nicht ausreichend gewichtet.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  Manchester United vs Aston Villa
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 08.11.2026  Manchester United vs Aston Villa
     Ø gpg=2.00, H2H Ø=2.9 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 08.11.2026  Manchester United vs Aston Villa
     Ø gpg=2.00 (statischer Proxy) → Poisson FV für Over 3.5 = 14.3%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 08.11.2026  Manchester United vs Aston Villa
     Manchester United expH≈1.15 (statischer Proxy) → FV über 1.5 = 31.9%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇪🇸 La Liga  (rl=26)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 08.11.2026  Villarreal vs Getafe
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  Villarreal vs Getafe
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 08.11.2026  Villarreal vs Getafe
     Ø gpg=1.50, H2H Ø=2.2 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 08.11.2026  Villarreal vs Getafe
     Ø gpg=1.50 (statischer Proxy) → Poisson FV für Over 3.5 = 6.6%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 08.11.2026  Celta Vigo vs Levante
     Levante: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 08.11.2026  Celta Vigo vs Levante
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  Celta Vigo vs Levante
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 08.11.2026  Celta Vigo vs Levante
     Ø gpg=1.50, H2H Ø=3.0 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 08.11.2026  Celta Vigo vs Levante
     Ø gpg=1.50 (statischer Proxy) → Poisson FV für Over 3.5 = 6.6%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 08.11.2026  Atletico Madrid vs Barcelona
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  Atletico Madrid vs Barcelona
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 08.11.2026  Atletico Madrid vs Barcelona
     H2H Schnitt=3.0 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.

─────────────────────────────────────────────────────────────────
  🇫🇷 Ligue 1  (rl=24)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 08.11.2026  Lens vs Marseille
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  Lens vs Marseille
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 08.11.2026  Lens vs Marseille
     Lens expH≈1.10 (statischer Proxy) → FV über 1.5 = 30.1%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇩🇪 Bundesliga  (rl=25)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 08.11.2026  SC Freiburg vs Union Berlin
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  SC Freiburg vs Union Berlin
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 08.11.2026  SC Freiburg vs Union Berlin
     Ø gpg=2.00, H2H Ø=2.5 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 08.11.2026  SC Freiburg vs Union Berlin
     Ø gpg=2.00 (statischer Proxy) → Poisson FV für Over 3.5 = 14.3%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 08.11.2026  SC Freiburg vs Union Berlin
     SC Freiburg expH≈1.25 (statischer Proxy) → FV über 1.5 = 35.5%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 08.11.2026  SC Freiburg vs Union Berlin
     Union Berlin expA≈1.25 (statischer Proxy) → FV über 1.5 = 35.5%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 08.11.2026  1899 Hoffenheim vs FC Schalke 04
     1899 Hoffenheim: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 08.11.2026  1899 Hoffenheim vs FC Schalke 04
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  1899 Hoffenheim vs FC Schalke 04
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 08.11.2026  1899 Hoffenheim vs FC Schalke 04
     H2H Schnitt=3.5 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 08.11.2026  1899 Hoffenheim vs FC Schalke 04
     Ø gpg=2.00, H2H Ø=3.5 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 08.11.2026  1899 Hoffenheim vs FC Schalke 04
     Ø gpg=2.00 (statischer Proxy) → Poisson FV für Over 3.5 = 14.3%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 08.11.2026  1899 Hoffenheim vs FC Schalke 04
     FC Schalke 04 expA≈0.55 (statischer Proxy) → FV über 1.5 = 10.6%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇭🇺 NB I  (rl=20)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 08.11.2026  Vasas vs Ferencvarosi TC
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  Vasas vs Ferencvarosi TC
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.

─────────────────────────────────────────────────────────────────
  🇮🇹 Serie A  (rl=27)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 08.11.2026  Inter vs Como
     Inter dominiert H2H 5W/1X/0L in 6 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 08.11.2026  Inter vs Como
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  Inter vs Como
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 08.11.2026  Inter vs Como
     H2H Schnitt=3.3 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 08.11.2026  Inter vs Como
     Inter expH≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 08.11.2026  Fiorentina vs Juventus
     Fiorentina: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 08.11.2026  Fiorentina vs Juventus
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  Fiorentina vs Juventus
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.

─────────────────────────────────────────────────────────────────
  🇳🇱 Eredivisie  (rl=22)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 08.11.2026  Utrecht vs NEC Nijmegen
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  Utrecht vs NEC Nijmegen
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 08.11.2026  Utrecht vs NEC Nijmegen
     Ø gpg=2.00, H2H Ø=2.3 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 08.11.2026  Utrecht vs NEC Nijmegen
     Ø gpg=2.00 (statischer Proxy) → Poisson FV für Over 3.5 = 14.3%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.

─────────────────────────────────────────────────────────────────
  🇵🇱 Ekstraklasa  (rl=20)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [ASYMMETRIC_STAKE_SCORES]
     📅 08.11.2026  Lech Poznan vs Zaglebie Lubin
     Score-Differenz 4.6 Punkte: Lech Poznan (9.1) vs Zaglebie Lubin (4.5). Pick-Richtung sehr klar — Favoritenpflicht prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 08.11.2026  Lech Poznan vs Zaglebie Lubin
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  Lech Poznan vs Zaglebie Lubin
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 08.11.2026  Lech Poznan vs Zaglebie Lubin
     Zaglebie Lubin expA≈1.15 (statischer Proxy) → FV über 1.5 = 31.9%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇵🇹 Primeira Liga  (rl=23)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 08.11.2026  Vitória SC vs FC Porto
     FC Porto dominiert H2H 16W/2X/2L in 20 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🔵 HINWEIS [H2H_DOM_GOLD_RED]
     📅 08.11.2026  Vitória SC vs FC Porto
     FC Porto dominiert H2H 16W/2X/2L in 20 Spielen. Gold vs Rot, aber H2H-Favorit klar — Angle sollte Pick-Richtung bestätigen, nicht dramatisieren.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 08.11.2026  Vitória SC vs FC Porto
     Vitória SC: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  Vitória SC vs FC Porto
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 08.11.2026  Vitória SC vs FC Porto
     Vitória SC expH≈1.05 (statischer Proxy) → FV über 1.5 = 28.3%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 08.11.2026  Vitória SC vs FC Porto
     FC Porto expA≈1.25 (statischer Proxy) → FV über 1.5 = 35.5%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  Rio Ave vs SC Braga
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 08.11.2026  Rio Ave vs SC Braga
     Ø gpg=1.30, H2H Ø=2.8 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 08.11.2026  Rio Ave vs SC Braga
     Ø gpg=1.30 (statischer Proxy) → Poisson FV für Over 3.5 = 4.3%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 08.11.2026  Estrela vs Benfica
     Benfica dominiert H2H 9W/0X/0L in 9 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 08.11.2026  Estrela vs Benfica
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 08.11.2026  Estrela vs Benfica
     H2H Schnitt=3.8 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.

─────────────────────────────────────────────────────────────────
  🇹🇷 Süper Lig  (rl=27)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 08.11.2026  Beşiktaş vs Gençlerbirliği S.K.
     Gençlerbirliği S.K.: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.

═════════════════════════════════════════════════════════════════
  Geprüft: 19 Spiele
  🟡 11 Warnungen — manuelle Prüfung empfohlen
  🔵 65 Hinweise — Pick-Richtung kontrollieren
═════════════════════════════════════════════════════════════════

```
