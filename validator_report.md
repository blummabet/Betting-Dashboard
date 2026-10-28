# 🟡 Picks Validator — 28.10.2026 22:50

**62 Spiele geprüft** · 🔴 0 Fehler · 🟡 43 Warnungen · 🔵 192 Hinweise

```
=================================================================
  🐕 CocoBet — Picks Logik-Check
  28.10.2026 22:50
  Filter: nächste 3 Tag(e)
=================================================================

─────────────────────────────────────────────────────────────────
  🇦🇹 Österreich BL  (rl=22)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 30.10.2026  Grazer AK vs TSV Hartberg
     Liga-Baserate=3.7 → Poisson FV für Über 3.5 Karten = 50.6% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+5.0%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 30.10.2026  Grazer AK vs TSV Hartberg
     Liga-Baserate=3.7 → Poisson FV für Über 4.5 Karten = 31.3%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 30.10.2026  Grazer AK vs TSV Hartberg
     Ø gpg=1.50, H2H Ø=1.6 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 30.10.2026  Grazer AK vs TSV Hartberg
     Ø gpg=1.50 (statischer Proxy) → Poisson FV für Over 3.5 = 6.6%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  SCR Altach vs Ried
     Liga-Baserate=3.7 → Poisson FV für Über 3.5 Karten = 50.6% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+5.0%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  SCR Altach vs Ried
     Liga-Baserate=3.7 → Poisson FV für Über 4.5 Karten = 31.3%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  Lask Linz vs WSG Wattens
     WSG Wattens: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Lask Linz vs WSG Wattens
     Liga-Baserate=3.7 → Poisson FV für Über 3.5 Karten = 50.6% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+5.0%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Lask Linz vs WSG Wattens
     Liga-Baserate=3.7 → Poisson FV für Über 4.5 Karten = 31.3%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 31.10.2026  Lask Linz vs WSG Wattens
     H2H Schnitt=3.4 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.

─────────────────────────────────────────────────────────────────
  🇧🇪 Jupiler Pro League  (rl=31)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 30.10.2026  Zulte Waregem vs Club Brugge KV
     Club Brugge KV dominiert H2H 16W/2X/2L in 20 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🔵 HINWEIS [H2H_DOM_GOLD_RED]
     📅 30.10.2026  Zulte Waregem vs Club Brugge KV
     Club Brugge KV dominiert H2H 16W/2X/2L in 20 Spielen. Gold vs Rot, aber H2H-Favorit klar — Angle sollte Pick-Richtung bestätigen, nicht dramatisieren.
  🟡 WARNUNG [HOME_POOR_FORM_HIGH_SCORE]
     📅 30.10.2026  Zulte Waregem vs Club Brugge KV
     Zulte Waregem: formScore=0.17 (sehr schwach) aber matchScore=7.5. Pick-Basis könnte überschätzt sein — Formeinbruch nicht ausreichend gewichtet.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 30.10.2026  Zulte Waregem vs Club Brugge KV
     Zulte Waregem: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 30.10.2026  Zulte Waregem vs Club Brugge KV
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 30.10.2026  Zulte Waregem vs Club Brugge KV
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 30.10.2026  Zulte Waregem vs Club Brugge KV
     H2H Schnitt=3.5 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 30.10.2026  Zulte Waregem vs Club Brugge KV
     Zulte Waregem expH≈0.85 (statischer Proxy) → FV über 1.5 = 20.9%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  KV Mechelen vs Genk
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  KV Mechelen vs Genk
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 31.10.2026  KV Mechelen vs Genk
     H2H Schnitt=3.2 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 31.10.2026  KV Mechelen vs Genk
     Ø gpg=1.80, H2H Ø=3.2 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 31.10.2026  KV Mechelen vs Genk
     Ø gpg=1.80 (statischer Proxy) → Poisson FV für Over 3.5 = 10.9%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Standard Liege vs Kortrijk
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Standard Liege vs Kortrijk
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 31.10.2026  Standard Liege vs Kortrijk
     Ø gpg=0.50, H2H Ø=2.6 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 31.10.2026  Standard Liege vs Kortrijk
     Ø gpg=0.50 (statischer Proxy) → Poisson FV für Over 3.5 = 2.0%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  SK Beveren vs Union St. Gilloise
     SK Beveren: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  SK Beveren vs Union St. Gilloise
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  SK Beveren vs Union St. Gilloise
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 31.10.2026  SK Beveren vs Union St. Gilloise
     H2H Schnitt=4.3 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.

─────────────────────────────────────────────────────────────────
  🇭🇷 HNL  (rl=25)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 30.10.2026  NK Slaven Belupo vs Istra 1961
     NK Slaven Belupo, Istra 1961: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 30.10.2026  NK Slaven Belupo vs Istra 1961
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 30.10.2026  NK Slaven Belupo vs Istra 1961
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 31.10.2026  HNK Hajduk Split vs HNK Gorica
     HNK Hajduk Split dominiert H2H 15W/2X/3L in 20 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🔵 HINWEIS [H2H_DOM_GOLD_RED]
     📅 31.10.2026  HNK Hajduk Split vs HNK Gorica
     HNK Hajduk Split dominiert H2H 15W/2X/3L in 20 Spielen. Gold vs Rot, aber H2H-Favorit klar — Angle sollte Pick-Richtung bestätigen, nicht dramatisieren.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  HNK Hajduk Split vs HNK Gorica
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  HNK Hajduk Split vs HNK Gorica
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 31.10.2026  HNK Hajduk Split vs HNK Gorica
     HNK Hajduk Split expH≈1.25 (statischer Proxy) → FV über 1.5 = 35.5%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 31.10.2026  HNK Hajduk Split vs HNK Gorica
     HNK Gorica expA≈1.20 (statischer Proxy) → FV über 1.5 = 33.7%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Rudes vs Dinamo Zagreb
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Rudes vs Dinamo Zagreb
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 31.10.2026  Rudes vs Dinamo Zagreb
     H2H Schnitt=3.4 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.

─────────────────────────────────────────────────────────────────
  🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League  (rl=30)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  Chelsea vs Manchester United
     Manchester United: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Chelsea vs Manchester United
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 31.10.2026  Chelsea vs Manchester United
     Manchester United expA≈1.10 (statischer Proxy) → FV über 1.5 = 30.1%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Bournemouth vs Leeds
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 31.10.2026  Bournemouth vs Leeds
     H2H Schnitt=4.1 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 31.10.2026  Bournemouth vs Leeds
     Leeds expA≈1.15 (statischer Proxy) → FV über 1.5 = 31.9%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Manchester City vs Brighton
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 31.10.2026  Manchester City vs Brighton
     H2H Schnitt=3.3 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Brentford vs Nottingham Forest
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 31.10.2026  Brentford vs Nottingham Forest
     Nottingham Forest expA≈1.10 (statischer Proxy) → FV über 1.5 = 30.1%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Hull City vs Ipswich
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Coventry vs Sunderland
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 31.10.2026  Coventry vs Sunderland
     Ø gpg=2.20 (statischer Proxy) → Poisson FV für Over 3.5 = 18.1%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 31.10.2026  Coventry vs Sunderland
     Coventry expH≈1.25 (statischer Proxy) → FV über 1.5 = 35.5%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  Tottenham vs Crystal Palace
     Crystal Palace: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Tottenham vs Crystal Palace
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 31.10.2026  Tottenham vs Crystal Palace
     Crystal Palace expA≈1.30 (statischer Proxy) → FV über 1.5 = 37.3%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  Aston Villa vs Fulham
     Fulham: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Aston Villa vs Fulham
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 31.10.2026  Aston Villa vs Fulham
     Fulham expA≈1.20 (statischer Proxy) → FV über 1.5 = 33.7%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇪🇸 La Liga  (rl=28)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [ASYMMETRIC_STAKE_SCORES]
     📅 30.10.2026  Villarreal vs Espanyol
     Score-Differenz 4.1 Punkte: Espanyol (8.6) vs Villarreal (4.5). Pick-Richtung sehr klar — Favoritenpflicht prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 30.10.2026  Villarreal vs Espanyol
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 30.10.2026  Villarreal vs Espanyol
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 30.10.2026  Villarreal vs Espanyol
     Espanyol expA≈1.20 (statischer Proxy) → FV über 1.5 = 33.7%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Levante vs Atletico Madrid
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Levante vs Atletico Madrid
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 31.10.2026  Levante vs Atletico Madrid
     Levante expH≈1.15 (statischer Proxy) → FV über 1.5 = 31.9%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  Rayo Vallecano vs Celta Vigo
     Rayo Vallecano: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Rayo Vallecano vs Celta Vigo
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Rayo Vallecano vs Celta Vigo
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 31.10.2026  Rayo Vallecano vs Celta Vigo
     Rayo Vallecano expH≈1.00 (statischer Proxy) → FV über 1.5 = 26.4%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Real Betis vs Malaga
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Real Betis vs Malaga
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 31.10.2026  Barcelona vs Alaves
     Barcelona dominiert H2H 14W/2X/2L in 18 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🔵 HINWEIS [ASYMMETRIC_STAKE_SCORES]
     📅 31.10.2026  Barcelona vs Alaves
     Score-Differenz 4.5 Punkte: Barcelona (9.0) vs Alaves (4.5). Pick-Richtung sehr klar — Favoritenpflicht prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Barcelona vs Alaves
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Barcelona vs Alaves
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 31.10.2026  Barcelona vs Alaves
     H2H Schnitt=3.1 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 31.10.2026  Barcelona vs Alaves
     Alaves expA≈1.20 (statischer Proxy) → FV über 1.5 = 33.7%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇫🇷 Ligue 1  (rl=26)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 30.10.2026  Nice vs Rennes
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 30.10.2026  Nice vs Rennes
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 30.10.2026  Le Havre vs Paris Saint Germain
     Paris Saint Germain dominiert H2H 7W/1X/0L in 8 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🔵 HINWEIS [H2H_DOM_GOLD_RED]
     📅 30.10.2026  Le Havre vs Paris Saint Germain
     Paris Saint Germain dominiert H2H 7W/1X/0L in 8 Spielen. Gold vs Rot, aber H2H-Favorit klar — Angle sollte Pick-Richtung bestätigen, nicht dramatisieren.
  🟡 WARNUNG [HOME_POOR_FORM_HIGH_SCORE]
     📅 30.10.2026  Le Havre vs Paris Saint Germain
     Le Havre: formScore=0.22 (sehr schwach) aber matchScore=7.5. Pick-Basis könnte überschätzt sein — Formeinbruch nicht ausreichend gewichtet.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 30.10.2026  Le Havre vs Paris Saint Germain
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 30.10.2026  Le Havre vs Paris Saint Germain
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 30.10.2026  Le Havre vs Paris Saint Germain
     H2H Schnitt=3.9 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 30.10.2026  Lille vs Lens
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 30.10.2026  Lille vs Lens
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 30.10.2026  Lille vs Lens
     Lille expH≈1.25 (statischer Proxy) → FV über 1.5 = 35.5%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  Lyon vs Angers
     Angers: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Lyon vs Angers
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Lyon vs Angers
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 31.10.2026  Lyon vs Angers
     H2H Schnitt=3.0 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 31.10.2026  Lyon vs Angers
     Angers expA≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  Lorient vs Stade Brestois 29
     Stade Brestois 29: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Lorient vs Stade Brestois 29
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Lorient vs Stade Brestois 29
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 31.10.2026  Lorient vs Stade Brestois 29
     Lorient expH≈1.25 (statischer Proxy) → FV über 1.5 = 35.5%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 31.10.2026  Lorient vs Stade Brestois 29
     Stade Brestois 29 expA≈1.20 (statischer Proxy) → FV über 1.5 = 33.7%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🟡 WARNUNG [HOME_POOR_FORM_HIGH_SCORE]
     📅 31.10.2026  Estac Troyes vs Le Mans
     Estac Troyes: formScore=0.11 (sehr schwach) aber matchScore=7.5. Pick-Basis könnte überschätzt sein — Formeinbruch nicht ausreichend gewichtet.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  Estac Troyes vs Le Mans
     Le Mans: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Estac Troyes vs Le Mans
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Estac Troyes vs Le Mans
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 31.10.2026  Estac Troyes vs Le Mans
     Ø gpg=1.70, H2H Ø=2.3 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 31.10.2026  Estac Troyes vs Le Mans
     Ø gpg=1.70 (statischer Proxy) → Poisson FV für Over 3.5 = 9.3%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 31.10.2026  Estac Troyes vs Le Mans
     Estac Troyes expH≈1.25 (statischer Proxy) → FV über 1.5 = 35.5%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🇩🇪 Bundesliga  (rl=27)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [HOME_POOR_FORM_HIGH_SCORE]
     📅 30.10.2026  SV Elversberg vs FSV Mainz 05
     SV Elversberg: formScore=0.22 (sehr schwach) aber matchScore=7.5. Pick-Basis könnte überschätzt sein — Formeinbruch nicht ausreichend gewichtet.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 30.10.2026  SV Elversberg vs FSV Mainz 05
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 30.10.2026  SV Elversberg vs FSV Mainz 05
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Werder Bremen vs 1899 Hoffenheim
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Werder Bremen vs 1899 Hoffenheim
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 31.10.2026  Werder Bremen vs 1899 Hoffenheim
     H2H Schnitt=3.0 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 31.10.2026  Borussia Mönchengladbach vs SC Paderborn 07
     Borussia Mönchengladbach dominiert H2H 6W/0X/1L in 7 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🟡 WARNUNG [BOTRED_ASYMMETRIC_PRESSURE]
     📅 31.10.2026  Borussia Mönchengladbach vs SC Paderborn 07
     Kellerduell-Narrativ aber asymmetrischer Druck: Borussia Mönchengladbach pressureRatio=0.33 vs SC Paderborn 07 pressureRatio=0.27. Nur eine Mannschaft kämpft wirklich — Angle zu vereinfacht.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  Borussia Mönchengladbach vs SC Paderborn 07
     SC Paderborn 07: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Borussia Mönchengladbach vs SC Paderborn 07
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Borussia Mönchengladbach vs SC Paderborn 07
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 31.10.2026  Borussia Mönchengladbach vs SC Paderborn 07
     SC Paderborn 07 expA≈1.20 (statischer Proxy) → FV über 1.5 = 33.7%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  Bayer Leverkusen vs VfB Stuttgart
     VfB Stuttgart: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Bayer Leverkusen vs VfB Stuttgart
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Bayer Leverkusen vs VfB Stuttgart
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 31.10.2026  Bayer Leverkusen vs VfB Stuttgart
     H2H Schnitt=3.2 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  FC Augsburg vs SC Freiburg
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  FC Augsburg vs SC Freiburg
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 31.10.2026  FC Augsburg vs SC Freiburg
     H2H Schnitt=3.1 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  FC Schalke 04 vs RB Leipzig
     FC Schalke 04: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  FC Schalke 04 vs RB Leipzig
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  FC Schalke 04 vs RB Leipzig
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 31.10.2026  FC Schalke 04 vs RB Leipzig
     H2H Schnitt=3.4 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Bayern München vs Borussia Dortmund
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Bayern München vs Borussia Dortmund
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 31.10.2026  Bayern München vs Borussia Dortmund
     H2H Schnitt=4.0 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.

─────────────────────────────────────────────────────────────────
  🇭🇺 NB I  (rl=22)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  Budapest Honved vs Kisvarda FC
     Kisvarda FC: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Budapest Honved vs Kisvarda FC
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Budapest Honved vs Kisvarda FC
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  Zalaegerszegi TE vs MTK Budapest
     MTK Budapest: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Zalaegerszegi TE vs MTK Budapest
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Zalaegerszegi TE vs MTK Budapest
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [ASYMMETRIC_STAKE_SCORES]
     📅 31.10.2026  Gyori ETO FC vs Vasas
     Score-Differenz 4.3 Punkte: Gyori ETO FC (8.8) vs Vasas (4.5). Pick-Richtung sehr klar — Favoritenpflicht prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Gyori ETO FC vs Vasas
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Gyori ETO FC vs Vasas
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 31.10.2026  Gyori ETO FC vs Vasas
     H2H Schnitt=3.7 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.

─────────────────────────────────────────────────────────────────
  🇮🇹 Serie A  (rl=29)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 29.10.2026  Frosinone vs Lecce
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 29.10.2026  Frosinone vs Lecce
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 29.10.2026  Frosinone vs Lecce
     Ø gpg=2.20 (statischer Proxy) → Poisson FV für Over 3.5 = 18.1%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 29.10.2026  Fiorentina vs Atalanta
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 29.10.2026  Fiorentina vs Atalanta
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 29.10.2026  Fiorentina vs Atalanta
     H2H Schnitt=3.1 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 29.10.2026  Fiorentina vs Atalanta
     Ø gpg=1.80, H2H Ø=3.1 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 29.10.2026  Fiorentina vs Atalanta
     Ø gpg=1.80 (statischer Proxy) → Poisson FV für Over 3.5 = 10.9%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  Bologna vs Monza
     Monza: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Bologna vs Monza
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Bologna vs Monza
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 31.10.2026  Udinese vs AS Roma
     AS Roma dominiert H2H 15W/1X/4L in 20 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🔵 HINWEIS [H2H_DOM_GOLD_RED]
     📅 31.10.2026  Udinese vs AS Roma
     AS Roma dominiert H2H 15W/1X/4L in 20 Spielen. Gold vs Rot, aber H2H-Favorit klar — Angle sollte Pick-Richtung bestätigen, nicht dramatisieren.
  🟡 WARNUNG [HOME_POOR_FORM_HIGH_SCORE]
     📅 31.10.2026  Udinese vs AS Roma
     Udinese: formScore=0.11 (sehr schwach) aber matchScore=7.5. Pick-Basis könnte überschätzt sein — Formeinbruch nicht ausreichend gewichtet.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  Udinese vs AS Roma
     Udinese: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Udinese vs AS Roma
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Udinese vs AS Roma
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 31.10.2026  Udinese vs AS Roma
     Udinese expH≈0.90 (statischer Proxy) → FV über 1.5 = 22.8%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  AC Milan vs Inter
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  AC Milan vs Inter
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.

─────────────────────────────────────────────────────────────────
  🇳🇱 Eredivisie  (rl=24)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Feyenoord vs Fortuna Sittard
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Feyenoord vs Fortuna Sittard
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 31.10.2026  Feyenoord vs Fortuna Sittard
     H2H Schnitt=3.2 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 31.10.2026  Feyenoord vs Fortuna Sittard
     Fortuna Sittard expA≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  PSV Eindhoven vs Willem II
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  PSV Eindhoven vs Willem II
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 31.10.2026  PSV Eindhoven vs Willem II
     H2H Schnitt=3.4 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 31.10.2026  PSV Eindhoven vs Willem II
     Willem II expA≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Ajax vs AZ Alkmaar
     Liga-Baserate=3.5 → Poisson FV für Über 3.5 Karten = 46.3% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+9.3%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Ajax vs AZ Alkmaar
     Liga-Baserate=3.5 → Poisson FV für Über 4.5 Karten = 27.5%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.

─────────────────────────────────────────────────────────────────
  🇵🇱 Ekstraklasa  (rl=22)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [HOME_POOR_FORM_HIGH_SCORE]
     📅 30.10.2026  Cracovia Krakow vs Motor Lublin
     Cracovia Krakow: formScore=0.22 (sehr schwach) aber matchScore=7.5. Pick-Basis könnte überschätzt sein — Formeinbruch nicht ausreichend gewichtet.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 30.10.2026  Cracovia Krakow vs Motor Lublin
     Cracovia Krakow, Motor Lublin: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 30.10.2026  Cracovia Krakow vs Motor Lublin
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 30.10.2026  Cracovia Krakow vs Motor Lublin
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 30.10.2026  Cracovia Krakow vs Motor Lublin
     H2H Schnitt=4.5 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 30.10.2026  Gornik Zabrze vs Legia Warszawa
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 30.10.2026  Gornik Zabrze vs Legia Warszawa
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 30.10.2026  Gornik Zabrze vs Legia Warszawa
     H2H Schnitt=3.6 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 30.10.2026  Gornik Zabrze vs Legia Warszawa
     Gornik Zabrze expH≈1.00 (statischer Proxy) → FV über 1.5 = 26.4%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Wieczysta Kraków vs Jagiellonia
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Wieczysta Kraków vs Jagiellonia
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 31.10.2026  Wieczysta Kraków vs Jagiellonia
     Ø gpg=1.80 — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 31.10.2026  Wieczysta Kraków vs Jagiellonia
     Ø gpg=1.80 (statischer Proxy) → Poisson FV für Over 3.5 = 10.9%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [ASYMMETRIC_STAKE_SCORES]
     📅 31.10.2026  Lech Poznan vs Wisla Krakow
     Score-Differenz 4.7 Punkte: Lech Poznan (9.2) vs Wisla Krakow (4.5). Pick-Richtung sehr klar — Favoritenpflicht prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Lech Poznan vs Wisla Krakow
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Lech Poznan vs Wisla Krakow
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 31.10.2026  Lech Poznan vs Wisla Krakow
     H2H Schnitt=3.1 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  GKS Katowice vs Widzew Łódź
     Liga-Baserate=3.6 → Poisson FV für Über 3.5 Karten = 48.5% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+7.1%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  GKS Katowice vs Widzew Łódź
     Liga-Baserate=3.6 → Poisson FV für Über 4.5 Karten = 29.4%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 31.10.2026  GKS Katowice vs Widzew Łódź
     Ø gpg=1.20, H2H Ø=2.5 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 31.10.2026  GKS Katowice vs Widzew Łódź
     Ø gpg=1.20 (statischer Proxy) → Poisson FV für Over 3.5 = 3.4%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.

─────────────────────────────────────────────────────────────────
  🇵🇹 Primeira Liga  (rl=25)
─────────────────────────────────────────────────────────────────
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 30.10.2026  Casa Pia vs Sporting CP
     Sporting CP dominiert H2H 9W/0X/0L in 9 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 30.10.2026  Casa Pia vs Sporting CP
     Casa Pia: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 30.10.2026  Casa Pia vs Sporting CP
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 30.10.2026  Casa Pia vs Sporting CP
     H2H Schnitt=4.0 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 30.10.2026  Casa Pia vs Sporting CP
     Casa Pia expH≈1.25 (statischer Proxy) → FV über 1.5 = 35.5%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🟡 WARNUNG [H2H_DOMINATED_HIGH_SCORE]
     📅 31.10.2026  FC Porto vs Estoril
     FC Porto dominiert H2H 15W/2X/3L in 20 Spielen. matchScore=7.5 — Pick-Richtung sollte klar sein, Angle-Text darf den Underdog nicht überbewerten.
  🔵 HINWEIS [H2H_DOM_GOLD_RED]
     📅 31.10.2026  FC Porto vs Estoril
     FC Porto dominiert H2H 15W/2X/3L in 20 Spielen. Gold vs Rot, aber H2H-Favorit klar — Angle sollte Pick-Richtung bestätigen, nicht dramatisieren.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  FC Porto vs Estoril
     Liga-Baserate=3.8 → Poisson FV für Über 4.5 Karten = 33.2%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 31.10.2026  FC Porto vs Estoril
     H2H Schnitt=3.1 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [TEAM_OVER_AWAY_LOW_FV]
     📅 31.10.2026  FC Porto vs Estoril
     Estoril expA≈0.95 (statischer Proxy) → FV über 1.5 = 24.6%. JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.

─────────────────────────────────────────────────────────────────
  🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scottish Prem  (rl=27)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  Kilmarnock vs ST Johnstone
     ST Johnstone: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Kilmarnock vs ST Johnstone
     Liga-Baserate=4.0 → Poisson FV für Über 4.5 Karten = 37.1%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 31.10.2026  Kilmarnock vs ST Johnstone
     Ø gpg=2.00, H2H Ø=2.4 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 31.10.2026  Kilmarnock vs ST Johnstone
     Ø gpg=2.00 (statischer Proxy) → Poisson FV für Over 3.5 = 14.3%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 31.10.2026  Kilmarnock vs ST Johnstone
     Kilmarnock expH≈1.35 (statischer Proxy) → FV über 1.5 = 39.1%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🟡 WARNUNG [HOME_POOR_FORM_HIGH_SCORE]
     📅 31.10.2026  Motherwell vs ST Mirren
     Motherwell: formScore=0.06 (sehr schwach) aber matchScore=7.5. Pick-Basis könnte überschätzt sein — Formeinbruch nicht ausreichend gewichtet.
  🟡 WARNUNG [BOTH_DEFENSIVE_OVER_RISK]
     📅 31.10.2026  Motherwell vs ST Mirren
     Motherwell (0.8 Tore/Sp) + ST Mirren (0.7 Tore/Sp): kombiniert nur ~1.3 erwartete Tore. Over 2.5 Pick wäre kontraindiziert — Modell prüfen.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  Motherwell vs ST Mirren
     Motherwell: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Motherwell vs ST Mirren
     Liga-Baserate=4.0 → Poisson FV für Über 4.5 Karten = 37.1%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 31.10.2026  Motherwell vs ST Mirren
     Ø gpg=1.50, H2H Ø=2.4 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 31.10.2026  Motherwell vs ST Mirren
     Ø gpg=1.50 (statischer Proxy) → Poisson FV für Over 3.5 = 6.6%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.

─────────────────────────────────────────────────────────────────
  🇨🇭 Swiss SL  (rl=25)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  FC ST. Gallen vs Servette FC
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  FC ST. Gallen vs Servette FC
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 31.10.2026  FC ST. Gallen vs Servette FC
     Ø gpg=1.70, H2H Ø=2.8 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 31.10.2026  FC ST. Gallen vs Servette FC
     Ø gpg=1.70 (statischer Proxy) → Poisson FV für Over 3.5 = 9.3%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  Grasshoppers vs FC Vaduz
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  Grasshoppers vs FC Vaduz
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.
  🟡 WARNUNG [U25_H2H_HARD_BLOCK_MISS]
     📅 31.10.2026  Grasshoppers vs FC Vaduz
     H2H Schnitt=4.4 Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 31.10.2026  FC Luzern vs FC Sion
     FC Luzern: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [CARDS35_LOW_FV]
     📅 31.10.2026  FC Luzern vs FC Sion
     Liga-Baserate=3.4 → Poisson FV für Über 3.5 Karten = 44.2% (typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~+11.4%). FV-Gate (GOALS_REAL=0.05 → flaggt unter 50.6%) sollte Karten-3.5-Pick blocken. Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.
  🔵 HINWEIS [CARDS45_LOW_FV]
     📅 31.10.2026  FC Luzern vs FC Sion
     Liga-Baserate=3.4 → Poisson FV für Über 4.5 Karten = 25.6%. JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.

─────────────────────────────────────────────────────────────────
  🇹🇷 Süper Lig  (rl=29)
─────────────────────────────────────────────────────────────────
  🔵 HINWEIS [LOW_MOTIV_CARDS_CHECK]
     📅 30.10.2026  Konyaspor vs Galatasaray
     Konyaspor: motivationLevel='low' (fast gerettet) — Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.
  🔵 HINWEIS [TEAM_OVER_HOME_LOW_FV]
     📅 30.10.2026  Konyaspor vs Galatasaray
     Konyaspor expH≈1.30 (statischer Proxy) → FV über 1.5 = 37.3%. JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.
  🟡 WARNUNG [H2H_HIGH_AVG_UNDER_RISK]
     📅 31.10.2026  Kocaelispor vs Rizespor
     H2H Schnitt=3.0 Tore (3.0–3.5). Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 31.10.2026  Kocaelispor vs Rizespor
     Ø gpg=1.50, H2H Ø=3.0 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 31.10.2026  Kocaelispor vs Rizespor
     Ø gpg=1.50 (statischer Proxy) → Poisson FV für Over 3.5 = 6.6%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.
  🔵 HINWEIS [LOW_SCORING_PROFILE]
     📅 31.10.2026  Fenerbahçe vs Göztepe
     Ø gpg=1.80, H2H Ø=2.8 Tore — Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt
  🔵 HINWEIS [OVER35_LOW_FV]
     📅 31.10.2026  Fenerbahçe vs Göztepe
     Ø gpg=1.80 (statischer Proxy) → Poisson FV für Over 3.5 = 10.9%. JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.

═════════════════════════════════════════════════════════════════
  Geprüft: 62 Spiele
  🟡 43 Warnungen — manuelle Prüfung empfohlen
  🔵 192 Hinweise — Pick-Richtung kontrollieren
═════════════════════════════════════════════════════════════════

```
