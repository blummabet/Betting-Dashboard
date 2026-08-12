# Live-Signal — bessere Kriterien & nachspielbar machen

*Vorschlag, 12.08.2026. Ziel: aus „viel Live-Geld" akkurate, reproduzierbare Signale machen.*

---

## Das Kernproblem (warum Größe allein nicht reicht)

Live-Geld auf Poly ist zum größten Teil **reaktiv**: Tor fällt → Preis springt → Geld flutet auf die Seite, die gerade gestiegen ist. Das ist **schon eingepreist** und trägt null Information. Größe trennt das nicht — ein $50K-Nachlauf-Bet nach dem 1:0 sieht genauso „groß" aus wie ein $50K-Bet, der den Move *vorwegnimmt*. Deshalb „kommt viel rein" und wenig davon ist nachspielbar.

**Die eine Unterscheidung, die zählt:** Führt das Geld den Preis — oder folgt es ihm?

- **Folgt (reaktiv)** → wertlos. Geld auf eine Seite, deren Preis gerade in ihre Richtung gesprungen ist.
- **Führt (proaktiv / scharf)** → Signal. Geld, das *vor* der Bewegung kommt, *gegen* den aktuellen Move (Fade), oder von einer bewiesen scharfen Wallet.

Das ist **messbar**, weil wir die Live-Preis-Zeitreihe je Markt haben (`poly_money_broad_live_history.json`: `{ts, p:{Seite:Preis}, v}`).

---

## Bessere Kriterien — Mehr-Faktor-Gate statt einer Zahl

Ein Live-Einstieg zählt als Signal, wenn mehrere Achsen zusammenkommen (Vorschlagswerte — final aus den Tracking-Daten, s.u.):

**1. Wer + wie viel (Größe, schärfe-skaliert)** — haben wir teils
- bewiesen scharfe Wallet: ab **$5K** · anonymes Geld: ab **$25K**.
- *Warum:* eine scharfe Wallet trägt Info auch klein; anonymes Geld braucht echtes Konvikt.

**2. Value-Zone (Preis der bespielten Seite)** — enger als jetzt
- Seitenpreis in **0.25–0.75** (statt aktuell 0.10–0.90).
- *Warum:* unter 25¢/über 75¢ lehnt das Spiel schon stark → Live-Geld dort ist meist Abwicklung. Der informative Bereich ist die umkämpfte Mitte.

**3. Markt-Reife (Gesamtvolumen)** — neu
- totalUsd ≥ **$50K**.
- *Warum:* dünne Märkte haben verrauschte Preise, ein einzelner Whale verzerrt sie → nicht reproduzierbar. Reife Märkte sind effizient, ein Signal bedeutet dort mehr.

**4. Nicht-Chasing — der neue Kern** (aus der Preis-Zeitreihe)
- Preis-Move der bespielten Seite über die letzten ~2 Scans (~30 Min):
  - Seite gerade **≥ CHASE_PP (z.B. 8pp) gestiegen** UND das Geld geht auf dieselbe Seite → **reaktiv → raus.**
  - Preis flach, oder Geld geht auf die Seite, die *gedippt* ist (Fade), oder *bevor* der Preis zieht → **proaktiv → behalten.**
- *Warum:* das killt den „1:0, Geld flutet den Führenden"-Fall — genau das Rauschen, das gerade reinkommt.

**5. Konzentration (ein Whale, kein Schwarm)** — für den Zufluss
- größter Einzel-Whale ≥ **30%** des Zuflusses.
- *Warum:* ein Konvikt-Bet ist ein Signal, 40 Kleinstwetten sind Crowd-Rauschen.

Statt hartem An/Aus lieber ein **Signal-Score** (Punkte je erfüllter Achse) → erlaubt „starkes" vs „schwaches" Signal und macht die Schwellen tunebar.

---

## Nachspielbar machen: Forward-CLV (das eigentliche Genie)

Ohne Messung bleibt jede Schwelle Bauchgefühl. Der Schlüssel: **jedes Signal loggen und seine Vorwärts-Preisbewegung tracken.**

- Bei jedem Signal loggen: `{Markt, Seite, Einstiegspreis (= Seitenpreis beim Scan), Zeit, Größe, scharf?, Kriterien-Flags}`.
- Bei jedem folgenden Scan den aktuellen Seitenpreis nachziehen.
- **Forward-CLV = Preis(jetzt) − Einstiegspreis** bei +15 / +30 / +60 Min und bei Spielende.
- Bewertung: Signal „trug", wenn Forward-CLV **> 0** — der Markt zog in unsere Richtung, das Geld hat den Preis **geführt**.
- Aggregat: Trefferquote / Ø Forward-CLV **je Kriterien-Bucket** (scharf vs nicht · Value-Zone · Chasing-Flag · Größenband · Markt-Reife).

→ Wir sehen **empirisch**, welche Kriterien positives CLV vorhersagen — und tunen das Gate aus echten Daten statt aus dem Bauch.

### Warum Forward-CLV statt „hat das Spiel gewonnen"
- **Schnell:** Feedback in Minuten statt erst bei Spielende → viele Datenpunkte, schnell nachspielbar.
- **Geringe Varianz:** kontinuierliche Preisbewegung statt eines 0/1-Ausgangs pro Spiel.
- **Misst genau das Richtige:** „hat das Geld den Preis geführt?" — das *ist* die Definition von scharf.
- **Konsistent:** CLV ist schon unser Nordstern bei Betfair und Poly-Pre.

---

## Stufenplan (erst messen, dann gaten)

1. **Tracking zuerst — misst, gatet noch nicht.** Jedes Live-Whale/Zufluss-Ereignis mit den Kriterien-Flags loggen + Forward-CLV über die Live-History nachziehen. Läuft im bestehenden Live-Scan mit, kostet **nichts** (Preis-Zeitreihe liegt schon vor). Nach ein paar Tagen haben wir echte CLV-Zahlen je Kriterium.
2. **Kriterien aus Daten schärfen.** Welche Buckets tragen (positives Ø CLV), welche nicht → Schwellen entsprechend setzen (z.B. „Chasing-Flag" bestätigt sich als CLV-negativ → hart raus).
3. **Gate + Anzeige.** Die validierten Kriterien als Filter in Live-Whales / Zufluss / Alerts, plus ein **„Live-Signal Track-Record"-Tab** (wie das Money-Map-Tracking): Trefferquote/CLV je Kriterium, offene & abgerechnete Signale.

**Empfehlung:** mit Stufe 1 (Tracking) starten. Ohne die Messung raten wir bei den Schwellen weiter; mit ihr wird jede Schwelle beweisbar — genau dein „akkurater + nachspielbar".
