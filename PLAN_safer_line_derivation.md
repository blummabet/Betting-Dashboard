# Plan: Safer-Line-Ableitung für Steam-Picks

**Ziel (Lucas):** Wenn ein Sharp-Drop + Signale auf einer Linie feuern (z.B. Über 3.5, Heimsieg),
soll das System die **nächst-sicherere Linie in derselben Richtung** ableiten und DIE als Wett-Pick
zeigen — der Drop ist das Signal, die sichere Linie ist die Wette.

- Über 3.5 → Über 3.25 / 3.0 (notch sicherer, „nur 3 Tore statt 4")
- Heimsieg → AH +0.25 / DNB / DC 1X (Remis wird Halb-Gewinn oder Refund statt Verlust)

---

## Ausgangslage (verifiziert 17.06.2026)

**Die Safer-Logik EXISTIERT** — `SUBSTITUTION_MAP` + synthetische Safer-Picks in
`generate_wm_picks.generate_picks_for_fixture` (Z.1288–1662). Sie kann eine sicherere Linie
ableiten, auch wenn die nicht eigenständig getriggert wurde (CASE 2, synthetischer Pick aus
der de-viggten Leiter).

**Das Problem:** Sie sitzt nur in der ALTEN Pick-Funktion. Die Steam-Picks (= seit der
Umstellung *alles*) laufen durch `generate_steam_picks_for_fixture` (Z.1837), eine SEPARATE
Funktion, die die Substitution **nie aufruft**. → Die Logik ist gestrandet, deshalb siehst du
die rohe riskante Linie.

**Daten-Realität:**
- Gespeichert: nur Halb-Linien — Tore 1.5/2.5/3.5, AH meist ±0.5/1.0.
- Asian-Quarter-Linien (Über 3.0/3.25, AH +0.25) werden zwar *gefetcht* (`alternate_totals`,
  `alternate_spreads`), aber **nicht gespeichert/de-viggt**.

---

## Phase 1 — Safer-Logik in den Steam-Pfad einhängen (Halb-Linien)

**Was:** Die bestehende Safer-Ableitung als eigenständige, getestete Funktion herauslösen und
aus dem Steam-Pfad aufrufen. Für jeden riskanten Steam-Pick wird die sichere Variante abgeleitet.

**Sofort lieferbar (nur Daten die wir haben):**
- Über 3.5 → **Über 2.5**
- Heimsieg → **DC 1X / DNB / AH −0.5**
- Auswärtssieg → **DC X2 / AH +0.5**
- AH-Favorit-Linien → flachere Linie / DC

**Darstellung:** Steam-Linie bleibt als THESE sichtbar („🔥 Move auf Über 3.5"), die sichere
Linie wird der empfohlene BET („✅ Wette: Über 2.5"). Genau dein „Signal vs Wette"-Gedanke.

**Dateien:** `generate_wm_picks.py` (Safer-Logik extrahieren + im Steam-Pfad aufrufen),
`wm2026-renderer.js` (These + abgeleitete Wette anzeigen), Tests.

**Aufwand:** mittel (~halber Tag). **Risiko:** mittel — berührt Kern-Pick-Logik.
Absicherung: Extraktion in getestete Funktion, bestehende Schwellen behalten
(Quote > 2.30, sichere Quote < 80% der Original-Quote), volle Test-Abdeckung, Guard.

**EHRLICHE EINSCHRÄNKUNG:** Über 2.5 ist oft ein GROSSER Sprung von 3.5 (von „4 Tore nötig"
auf „3 Tore nötig") → niedrige Quote, evtl. wenig Reiz. Den „nur eine Spur sicherer"-Effekt
(3.0/3.25), den du eigentlich willst, liefert erst Phase 2. Phase 1 beweist die Verdrahtung
und liefert sofort *eine* sicherere Option.

---

## Phase 2 — Asian-Quarter-Linien (Über 3.0/3.25, AH +0.25)

**Was:** Die feinen Linien freilegen, die du eigentlich meinst.

**1. Daten:** Quarter/Integer-Linien aus `alternate_totals`/`alternate_spreads` parsen +
speichern + de-viggen (wir fetchen sie schon, werfen sie nur weg).

**2. Modell-Wahrscheinlichkeit:** Über 3.0 = P(≥4 Tore) mit Push bei genau 3; AH +0.25 aus den
de-viggten 1X2-Probs. Machbar (Poisson + 1X2 haben wir).

**3. Settlement — DER knifflige Teil (neuer Ergebnis-Typ):**
- **Über 3.0** (Integer): 4+ = WIN, genau 3 = **PUSH/Refund**, ≤2 = LOSS.
- **Über 3.25** (Quarter): 4+ = WIN, genau 3 = **HALB-Verlust** (halb Push bei 3.0, halb Loss
  bei 3.5), ≤2 = LOSS.
- **AH +0.25 Heim**: Heimsieg = WIN, Remis = **HALB-Gewinn**, Heimniederlage = LOSS.

Das System kennt heute nur WIN/LOSS/VOID. Quarter-Linien brauchen **HALF_WIN/HALF_LOSS**
(Teil-Auszahlung) → betrifft `resolve_wm_results.py` (Settlement), P&L-Rechnung, Tracking,
Statistik, Conviction-Loop. Das ist der eigentliche Aufwand + das Risiko (echtes Geld + Lernen
hängen an korrektem Settlement).

**Dateien:** `fetch_wm_odds.py` (Quarter-Linien speichern), `generate_wm_picks.py` (Modell +
Linien-Auswahl), `resolve_wm_results.py` (Half-Win/Half-Loss-Settlement), `wm_results`-Pipeline
+ Frontend (Teil-Ergebnis anzeigen), viele Tests.

**Aufwand:** hoch (~1–2 Tage). **Risiko:** hoch — Settlement-Korrektheit mit Geld + Lern-Loop.

---

## Empfehlung

**Phase 1 zuerst.** Sie hängt die gestrandete Logik wieder ein und liefert für JEDEN riskanten
Steam-Pick sofort eine sichere Variante — mit den Daten, die wir haben, ohne Settlement-Risiko.
Damit ist das Grundprinzip („Drop = Signal, sichere Linie = Wette") wieder live und sichtbar.

**Phase 2 danach**, wenn sich zeigt, dass die Halb-Linien-Sprünge zu grob sind und du die feinen
3.0/3.25/+0.25 wirklich brauchst. Die kommt mit echtem Settlement-Aufwand — die sollten wir nur
mit voller Test-Abdeckung scharf schalten (wie beim Spread-/CLV-Fix).

**Liga-Bonus:** Phase 2 + das gelernte (Signal × Linie) aus deiner Linien-Auswahl-Vision greifen
ineinander — im Ligabetrieb lernt das System dann, *welche* sichere Linie bei welchem Muster
historisch am besten cashed. Dann wird aus „nimm die nächst-sichere Linie" ein „nimm die Linie,
die die Daten sagen".
