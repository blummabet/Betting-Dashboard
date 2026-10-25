# 🟡 Picks Validator — 25.10.2026 21:06

**22 Spiele geprüft** · 🔴 0 Fehler · 🟡 14 Warnungen · 🔵 61 Hinweise

```
=================================================================
  🐕 CocoBet — Picks Logik-Check
  25.10.2026 21:06
  Filter: nächste 3 Tag(e)
=================================================================

─────────────────────────────────────────────────────────────────
  🇭🇷 HNL  (rl=25)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 26.10.2026  Istra 1961 vs HNK Hajduk Split
     Istra 1961: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 26.10.2026  Istra 1961 vs HNK Hajduk Split
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 26.10.2026  Istra 1961 vs HNK Hajduk Split
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 26.10.2026  Istra 1961 vs HNK Hajduk Split
     Istra 1961 expH≈1.30 (statischer Proxy) → FV über 1.5 = 37.3%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 26.10.2026  Istra 1961 vs HNK Hajduk Split
     HNK Hajduk Split expA≈1.10 (statischer Proxy) → FV über 1.5 = 30.1%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 27.10.2026  Dinamo Zagreb vs HNK Rijeka
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 27.10.2026  Dinamo Zagreb vs HNK Rijeka
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.

─────────────────────────────────────────────────────────────────
  🇪🇸 La Liga  (rl=28)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 26.10.2026  Sevilla vs Osasuna
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 26.10.2026  Sevilla vs Osasuna
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.

─────────────────────────────────────────────────────────────────
  🇫🇷 Ligue 1  (rl=26)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 26.10.2026  Paris Saint Germain vs Lyon
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 26.10.2026  Paris Saint Germain vs Lyon
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 26.10.2026  Paris Saint Germain vs Lyon
     H2H Schnitt=3.4 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.

─────────────────────────────────────────────────────────────────
  🇮🇹 Serie A  (rl=30)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 27.10.2026  Sassuolo vs Lazio
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 27.10.2026  Sassuolo vs Lazio
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 27.10.2026  AS Roma vs Cagliari
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 27.10.2026  AS Roma vs Cagliari
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 27.10.2026  AS Roma vs Cagliari
     Cagliari expA≈1.15 (statischer Proxy) → FV über 1.5 = 31.9%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 27.10.2026  Torino vs Como
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 27.10.2026  Torino vs Como
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 27.10.2026  Torino vs Como
     H2H Schnitt=3.5 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 28.10.2026  AC Milan vs Bologna
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 28.10.2026  AC Milan vs Bologna
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 28.10.2026  AC Milan vs Bologna
     Ø gpg=1.80, H2H Ø=2.8 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 28.10.2026  AC Milan vs Bologna
     Ø gpg=1.80 (statischer Proxy) → Poisson FV für Over 3.5 = 10.9%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 28.10.2026  Venezia vs Inter
     Inter dominiert H2H 5W/0X/0L in 5 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🔵 HINWEIS [H2H_DOM_GOLD_RED]
     📅 28.10.2026  Venezia vs Inter
     Inter dominiert H2H 5W/0X/0L in 5 Spielen. Gold vs Rot, aber H2H-Favorit klar — Angle sollte Pick-Richtung bestätigen, nicht dramatisieren.
  🟡 WARNUNG [HOME_POOR_FORM_HIGH_SCORE]
     📅 28.10.2026  Venezia vs Inter
     Venezia: formScore=0.17 (sehr schwach) aber matchScore=7.5. Pick-Basis könnte überschätzt sein — Formeinbruch nicht ausreichend gewichtet.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 28.10.2026  Venezia vs Inter
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 28.10.2026  Venezia vs Inter
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 28.10.2026  Venezia vs Inter
     Venezia expH≈1.00 (statischer Proxy) → FV über 1.5 = 26.4%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🟡 WARNUNG [HOME_POOR_FORM_HIGH_SCORE]
     📅 28.10.2026  Parma vs Udinese
     Parma: formScore=0.22 (sehr schwach) aber matchScore=7.5. Pick-Basis könnte überschätzt sein — Formeinbruch nicht ausreichend gewichtet.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 28.10.2026  Parma vs Udinese
     Parma, Udinese: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 28.10.2026  Parma vs Udinese
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 28.10.2026  Parma vs Udinese
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 28.10.2026  Parma vs Udinese
     H2H Schnitt=3.0 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 28.10.2026  Parma vs Udinese
     Ø gpg=1.80, H2H Ø=3.0 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 28.10.2026  Parma vs Udinese
     Ø gpg=1.80 (statischer Proxy) → Poisson FV für Over 3.5 = 10.9%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 28.10.2026  Genoa vs Juventus
     Genoa: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 28.10.2026  Genoa vs Juventus
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 28.10.2026  Genoa vs Juventus
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 28.10.2026  Genoa vs Juventus
     Ø gpg=2.00, H2H Ø=2.8 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 28.10.2026  Genoa vs Juventus
     Ø gpg=2.00 (statischer Proxy) → Poisson FV für Over 3.5 = 14.3%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 28.10.2026  Genoa vs Juventus
     Genoa expH≈1.05 (statischer Proxy) → FV über 1.5 = 28.3%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 28.10.2026  Genoa vs Juventus
     Juventus expA≈1.20 (statischer Proxy) → FV über 1.5 = 33.7%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 28.10.2026  Monza vs Napoli
     Monza: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 28.10.2026  Monza vs Napoli
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 28.10.2026  Monza vs Napoli
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.

─────────────────────────────────────────────────────────────────
  🇵🇹 Primeira Liga  (rl=25)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 26.10.2026  Santa Clara vs Benfica
     Benfica dominiert H2H 12W/2X/1L in 15 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 26.10.2026  Santa Clara vs Benfica
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 26.10.2026  Santa Clara vs Benfica
     H2H Schnitt=3.3 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 26.10.2026  Santa Clara vs Benfica
     Santa Clara expH≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scottish Prem  (rl=28)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 28.10.2026  Celtic vs Dundee Utd
     Liga-Baserate=4.0 → Poisson FV für Über 4.5 Karten = 37.1%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 28.10.2026  Celtic vs Dundee Utd
     H2H Schnitt=3.0 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🟡 WARNUNG [HOME_POOR_FORM_HIGH_SCORE]
     📅 28.10.2026  ST Mirren vs Hibernian
     ST Mirren: formScore=0.17 (sehr schwach) aber matchScore=7.5. Pick-Basis könnte überschätzt sein — Formeinbruch nicht ausreichend gewichtet.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 28.10.2026  ST Mirren vs Hibernian
     Liga-Baserate=4.0 → Poisson FV für Über 4.5 Karten = 37.1%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 28.10.2026  ST Mirren vs Hibernian
     Ø gpg=1.70, H2H Ø=2.7 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 28.10.2026  ST Mirren vs Hibernian
     Ø gpg=1.70 (statischer Proxy) → Poisson FV für Over 3.5 = 9.3%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 28.10.2026  ST Mirren vs Hibernian
     ST Mirren expH≈0.95 (statischer Proxy) → FV über 1.5 = 24.6%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 28.10.2026  Aberdeen vs Falkirk
     Aberdeen: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 28.10.2026  Aberdeen vs Falkirk
     Liga-Baserate=4.0 → Poisson FV für Über 4.5 Karten = 37.1%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 28.10.2026  Dundee vs Kilmarnock
     Kilmarnock: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 28.10.2026  Dundee vs Kilmarnock
     Liga-Baserate=4.0 → Poisson FV für Über 4.5 Karten = 37.1%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 28.10.2026  Dundee vs Kilmarnock
     H2H Schnitt=3.5 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 28.10.2026  Dundee vs Kilmarnock
     Kilmarnock expA≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 28.10.2026  Heart Of Midlothian vs Rangers
     Liga-Baserate=4.0 → Poisson FV für Über 4.5 Karten = 37.1%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 28.10.2026  Heart Of Midlothian vs Rangers
     H2H Schnitt=3.1 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 28.10.2026  Heart Of Midlothian vs Rangers
     Heart Of Midlothian expH≈1.10 (statischer Proxy) → FV über 1.5 = 30.1%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🟡 WARNUNG [BOTH_DEFENSIVE_OVER_RISK]
     📅 28.10.2026  ST Johnstone vs Motherwell
     ST Johnstone (0.8 Tore/Sp) + Motherwell (0.5 Tore/Sp): kombiniert nur ~1.1 erwartete Tore. Over 2.5 Pick wäre kontraindiziert — Modell prüfen.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 28.10.2026  ST Johnstone vs Motherwell
     ST Johnstone, Motherwell: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 28.10.2026  ST Johnstone vs Motherwell
     Liga-Baserate=4.0 → Poisson FV für Über 4.5 Karten = 37.1%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 28.10.2026  ST Johnstone vs Motherwell
     Ø gpg=1.30, H2H Ø=2.5 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 28.10.2026  ST Johnstone vs Motherwell
     Ø gpg=1.30 (statischer Proxy) → Poisson FV für Over 3.5 = 4.3%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 28.10.2026  ST Johnstone vs Motherwell
     Motherwell expA≈0.90 (statischer Proxy) → FV über 1.5 = 22.8%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇹🇷 Süper Lig  (rl=29)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 26.10.2026  Beşiktaş vs Başakşehir
     Ø gpg=2.20 (statischer Proxy) → Poisson FV für Over 3.5 = 18.1%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 26.10.2026  Rizespor vs Trabzonspor
     H2H Schnitt=3.5 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.

═════════════════════════════════════════════════════════════════
  Geprüft: 22 Spiele
  🟡 14 Warnungen — manuelle Prüfung empfohlen
  🔵 61 Hinweise — Pick-Richtung kontrollieren
═════════════════════════════════════════════════════════════════

```
