# 🟡 Picks Validator — 24.11.2026 20:55

**15 Spiele geprüft** · 🔴 0 Fehler · 🟡 9 Warnungen · 🔵 59 Hinweise

```
=================================================================
  🐕 CocoBet — Picks Logik-Check
  24.11.2026 20:55
  Filter: nächste 3 Tag(e)
=================================================================

─────────────────────────────────────────────────────────────────
  🇦🇹 Österreich BL  (rl=19)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [HOME_POOR_FORM_HIGH_SCORE]
     📅 27.11.2026  Grazer AK vs SCR Altach
     Grazer AK: formScore=0.06 (sehr schwach) aber matchScore=7.5. Pick-Basis könnte überschätzt sein — Formeinbruch nicht ausreichend gewichtet.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 27.11.2026  Grazer AK vs SCR Altach
     SCR Altach: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 27.11.2026  Grazer AK vs SCR Altach
     Liga-Baserate=3.7 → Poisson FV für Über 3.5 Karten = 50.6% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+5.0%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 27.11.2026  Grazer AK vs SCR Altach
     Liga-Baserate=3.7 → Poisson FV für Über 4.5 Karten = 31.3%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 27.11.2026  Grazer AK vs SCR Altach
     Grazer AK expH≈0.75 (statischer Proxy) → FV über 1.5 = 17.3%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇧🇪 Jupiler Pro League  (rl=28)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 27.11.2026  OH Leuven vs Kortrijk
     OH Leuven: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 27.11.2026  OH Leuven vs Kortrijk
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 27.11.2026  OH Leuven vs Kortrijk
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 27.11.2026  OH Leuven vs Kortrijk
     Ø gpg=2.00, H2H Ø=2.0 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 27.11.2026  OH Leuven vs Kortrijk
     Ø gpg=2.00 (statischer Proxy) → Poisson FV für Over 3.5 = 14.3%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 27.11.2026  OH Leuven vs Kortrijk
     Kortrijk expA≈0.75 (statischer Proxy) → FV über 1.5 = 17.3%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇭🇷 HNL  (rl=22)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 27.11.2026  Istra 1961 vs NK Varazdin
     Istra 1961: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 27.11.2026  Istra 1961 vs NK Varazdin
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 27.11.2026  Istra 1961 vs NK Varazdin
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.

─────────────────────────────────────────────────────────────────
  🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League  (rl=27)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [HOME_POOR_FORM_HIGH_SCORE]
     📅 27.11.2026  Nottingham Forest vs Chelsea
     Nottingham Forest: formScore=0.22 (sehr schwach) aber matchScore=7.5. Pick-Basis könnte überschätzt sein — Formeinbruch nicht ausreichend gewichtet.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 27.11.2026  Nottingham Forest vs Chelsea
     Nottingham Forest: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 27.11.2026  Nottingham Forest vs Chelsea
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 27.11.2026  Nottingham Forest vs Chelsea
     Ø gpg=1.80, H2H Ø=2.9 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 27.11.2026  Nottingham Forest vs Chelsea
     Ø gpg=1.80 (statischer Proxy) → Poisson FV für Over 3.5 = 10.9%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 27.11.2026  Nottingham Forest vs Chelsea
     Nottingham Forest expH≈1.05 (statischer Proxy) → FV über 1.5 = 28.3%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 27.11.2026  Nottingham Forest vs Chelsea
     Chelsea expA≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇪🇸 La Liga  (rl=25)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 27.11.2026  Levante vs Racing Santander
     Levante: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 27.11.2026  Levante vs Racing Santander
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 27.11.2026  Levante vs Racing Santander
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 27.11.2026  Levante vs Racing Santander
     Levante expH≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 27.11.2026  Levante vs Racing Santander
     Racing Santander expA≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇫🇷 Ligue 1  (rl=23)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 27.11.2026  Stade Brestois 29 vs Paris FC
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 27.11.2026  Stade Brestois 29 vs Paris FC
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.

─────────────────────────────────────────────────────────────────
  🇩🇪 Bundesliga  (rl=24)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 27.11.2026  Werder Bremen vs Borussia Mönchengladbach
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 27.11.2026  Werder Bremen vs Borussia Mönchengladbach
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 27.11.2026  Werder Bremen vs Borussia Mönchengladbach
     H2H Schnitt=3.5 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 27.11.2026  Werder Bremen vs Borussia Mönchengladbach
     Borussia Mönchengladbach expA≈1.25 (statischer Proxy) → FV über 1.5 = 35.5%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇭🇺 NB I  (rl=19)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 27.11.2026  Gyori ETO FC vs Debreceni VSC
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 27.11.2026  Gyori ETO FC vs Debreceni VSC
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 27.11.2026  Gyori ETO FC vs Debreceni VSC
     Gyori ETO FC expH≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇮🇹 Serie A  (rl=26)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 27.11.2026  Venezia vs Bologna
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 27.11.2026  Venezia vs Bologna
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 27.11.2026  Venezia vs Bologna
     H2H Schnitt=3.0 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 27.11.2026  Venezia vs Bologna
     Venezia expH≈0.90 (statischer Proxy) → FV über 1.5 = 22.8%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇳🇱 Eredivisie  (rl=21)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 27.11.2026  Groningen vs Willem II
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 27.11.2026  Groningen vs Willem II
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 27.11.2026  Groningen vs Willem II
     Ø gpg=1.50, H2H Ø=2.5 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 27.11.2026  Groningen vs Willem II
     Ø gpg=1.50 (statischer Proxy) → Poisson FV für Over 3.5 = 6.6%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.

─────────────────────────────────────────────────────────────────
  🇵🇱 Ekstraklasa  (rl=19)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 27.11.2026  Raków Częstochowa vs Piast Gliwice
     Raków Częstochowa: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 27.11.2026  Raków Częstochowa vs Piast Gliwice
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 27.11.2026  Raków Częstochowa vs Piast Gliwice
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 27.11.2026  Raków Częstochowa vs Piast Gliwice
     Raków Częstochowa expH≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 27.11.2026  Raków Częstochowa vs Piast Gliwice
     Piast Gliwice expA≈1.25 (statischer Proxy) → FV über 1.5 = 35.5%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 27.11.2026  Gornik Zabrze vs Wisla Plock
     Wisla Plock: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 27.11.2026  Gornik Zabrze vs Wisla Plock
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 27.11.2026  Gornik Zabrze vs Wisla Plock
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 27.11.2026  Gornik Zabrze vs Wisla Plock
     Wisla Plock expA≈0.95 (statischer Proxy) → FV über 1.5 = 24.6%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇵🇹 Primeira Liga  (rl=23)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [HOME_POOR_FORM_HIGH_SCORE]
     📅 27.11.2026  Maritimo vs Nacional
     Maritimo: formScore=0.22 (sehr schwach) aber matchScore=7.5. Pick-Basis könnte überschätzt sein — Formeinbruch nicht ausreichend gewichtet.
  🟡 WARNUNG [BOTH_DEFENSIVE_OVER_RISK]
     📅 27.11.2026  Maritimo vs Nacional
     Maritimo (0.7 Tore/Sp) + Nacional (0.7 Tore/Sp): kombiniert nur ~1.2 erwartete Tore. Over 2.5 Pick wäre kontraindiziert — Modell prüfen.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 27.11.2026  Maritimo vs Nacional
     Maritimo, Nacional: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 27.11.2026  Maritimo vs Nacional
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 27.11.2026  Maritimo vs Nacional
     Ø gpg=1.40, H2H Ø=2.4 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 27.11.2026  Maritimo vs Nacional
     Ø gpg=1.40 (statischer Proxy) → Poisson FV für Over 3.5 = 5.4%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 27.11.2026  Maritimo vs Nacional
     Maritimo expH≈1.10 (statischer Proxy) → FV über 1.5 = 30.1%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 27.11.2026  Maritimo vs Nacional
     Nacional expA≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CORNER_LOW_ATTACK_PROFILE]
     📅 27.11.2026  Maritimo vs Nacional
     Maritimo (0.7 T/Sp) + Nacional (0.7 T/Sp): Beide Teams sehr angriffsschwach — Corner-Over-Pick hat schwaches Fundament. FV-Gate (CORN_EST=0.10 bei geschätzten Quoten) sollte Corner-Pick blocken.

─────────────────────────────────────────────────────────────────
  🇹🇷 Süper Lig  (rl=26)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [HOME_POOR_FORM_HIGH_SCORE]
     📅 27.11.2026  Alanyaspor vs Konyaspor
     Alanyaspor: formScore=0.17 (sehr schwach) aber matchScore=7.5. Pick-Basis könnte überschätzt sein — Formeinbruch nicht ausreichend gewichtet.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 27.11.2026  Alanyaspor vs Konyaspor
     Alanyaspor, Konyaspor: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 27.11.2026  Alanyaspor vs Konyaspor
     H2H Schnitt=3.2 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 27.11.2026  Alanyaspor vs Konyaspor
     Ø gpg=1.70, H2H Ø=3.2 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 27.11.2026  Alanyaspor vs Konyaspor
     Ø gpg=1.70 (statischer Proxy) → Poisson FV für Over 3.5 = 9.3%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 27.11.2026  Alanyaspor vs Konyaspor
     Alanyaspor expH≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 27.11.2026  Rizespor vs Kasımpaşa
     H2H Schnitt=3.1 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.

═════════════════════════════════════════════════════════════════
  Geprüft: 15 Spiele
  🟡 9 Warnungen — manuelle Prüfung empfohlen
  🔵 59 Hinweise — Pick-Richtung kontrollieren
═════════════════════════════════════════════════════════════════

```
