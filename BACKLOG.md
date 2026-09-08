# CocoBet Backlog (Liga + WM)

Stand 07.09.2026 (oberster Block); Liga/WM-Teil darunter Stand 26.06.2026. Lebendige Liste aller offenen Punkte — Liga UND noch nicht umgesetzte WM-Sachen —
damit wir alles abarbeiten können. ✅ = erledigt (Referenz), ⏳ = offen, 🔒 = blockiert.

## 🤝 08.09.2026 — Remis-Pushs: Lucas' Skepsis ist gemessen richtig

Lucas: *„Ich hab wieder eine Push bekommen bei einem portugiesischen U23-Match … das Match war bei
0:0, dann 0:2, dann 2:2 und dann haben sie doch noch 4:2 gewonnen. Ich bin da sehr skeptisch bei
diesen Unentschieden-Pushes prinzipiell. Jetzt hat es übrigens auch noch im Trades-Channel eine
Push gegeben beim Jugend-Champions-League-Spiel, Manchester City, die sind 2:0 hinten."*

### Was das eigene Buch sagt

Aus `betfair_track_results` (16.614 abgerechnete Zeilen), Preis = `entryOdd`, also der Preis beim
ersten Sehen des Signals — dieselbe Rechnung wie für jedes andere Signal im Repo:

| Geld liegt auf … | n | Treffer | Ø Quote | break-even | ROI | Intervall |
|---|---|---|---|---|---|---|
| Heim | 1.482 | 53,3 % | @2,10 | 47,7 % | **+3,9 %** | −0,7 … |
| Auswärts | 868 | 49,0 % | @2,57 | 39,0 % | **+1,4 %** | −5,0 … |
| **Unentschieden** | 296 | **25,0 %** | @3,68 | 27,2 % | **−14,1 %** | −28,8 … +0,6 % |

Das Remis ist die einzige Seite ohne Kante. Und die Teilmengen, die eine **Push-Bedingung**
beschreiben, verlieren **belegt** (einseitige 95-%-Obergrenze unter null):

| Teilmenge | n | Treffer | ROI | Obergrenze |
|---|---|---|---|---|
| konzentriertes Geld (`conc`) | 135 | 21,5 % | −29,3 % | **−10,0 %** |
| Quote zieht rein (`dir=in`) | 79 | 20,3 % | −31,3 % | **−4,9 %** |
| konzentriert **und** Quote ≥ 3,4 | 57 | 12,3 % | −54,7 % | **−28,0 %** |

Das eigene Public-Buch sagt dasselbe: **10 Remis-Pushs, 3 Treffer, ROI −32 %** (mit dem
Estoril-4:2). Drei davon liefen im Spiel (@2,22 / @2,46 / @2,50) — davon 1 Treffer.

**Halbzeit-Remis ist ausdrücklich nicht betroffen**: n=804, Treffer 44,7 %, break-even 42,2 %,
ROI +4,1 %. Bei Anpfiff steht 0:0, das ist der Normalzustand und ein anderes Ereignis.

### 🔴 Der eigentliche Fund: der Geld-Anteil ist Altbestand

Beide Spiele, über die Lucas gestolpert ist, standen zum selben Zeitpunkt so im Feed:

| Spiel | Minute | Stand | Geld-Führer | Anteil | Quote | implizit |
|---|---|---|---|---|---|---|
| Estoril U23 v Famalicao U23 | 87 | 3:2 | The Draw | **86 %** | @6,60 | 15 % |
| Porto U19 v Man City U19 | 45 | 2:0 | The Draw | **48 %** | @14,00 | 7 % |

⭐ **Der Anteil ist kumulierter Umsatz über die ganze Marktlaufzeit, der Preis ist von jetzt.**
Bei 2:2 in der 70. Minute wird auf das Remis gehandelt; fällt danach das 3:2, bleibt das Geld in
der Statistik stehen und die Quote springt auf 6,6. „86 % des Geldes liegen auf dem Remis"
beschreibt dann nichts Gegenwärtiges mehr — niemand backt ein 15-%-Ereignis mit 86 % des Marktes.

Gemessen am Feed dieses Laufs: von **6 laufenden Spielen** tragen **genau diese zwei** einen
Geld-Führer mit ≥ 40 % Anteil auf einer Quote ≥ 5,0.

- ✅ `geld_ist_altbestand()` — nur in-play (vor Anpfiff kann der Anteil nicht veralten), ≥ 40 %
  Anteil auf ≥ 5,0 Quote, **in beiden Kanälen**. Es gab schon `_pub_incoherent` (≥70 % auf ≥3,0),
  aber Man City hatte nur 48 % **und** der Filter läuft nur auf dem Public-Pfad — der Push kam in
  Trades. Der neue Guard schließt genau diese Lücke.
- ✅ **Match-Odds-Remis geht nicht mehr in den Public-Kanal.** Trades behält es (dort entscheidet
  Lucas selbst) samt Warnzeile. Halbzeit-Remis bleibt überall.

### 🔴 Und: die Begründung der alten Remis-Sperre war selbst falsch gerechnet

Die Zahl „−31…−79 % ROI", mit der `DRAW_INPLAY_CHASE_MAX_ODD` seit dem 13.08. begründet ist, kommt
aus `betfair_draw_tracker`. Dessen In-Play-Eimer rechnen gegen `lastDrawOddInplay` — die **letzte**
gesehene In-Play-Quote, also die vom Schlusspfiff. Im Eimer `inplayOddTightened` sind das
Median @7,80, **Mittel @96,80, P90 @250, Max @1.000**. Bei einem 4:2 steht das X eben bei 1.000.

Dieselben 869 Spiele, dasselbe Ergebnis, entgegengesetztes Vorzeichen:

| Preisbasis | ROI |
|---|---|
| `lastDrawOddInplay` (Schlusspfiff) | **−36,9 %** |
| `firstLevelOdd` (Gleichstand, vor dem Geld) | **+24,2 %** |

Der Kommentar im Code verlangt sogar ausdrücklich `firstLevelOdd` — übergeben wurde
`lastDrawOddInplay`. Der echte Einstiegspreis (die X-Quote in dem Moment, in dem das Geld
reinläuft) wird gar nicht mitgeschrieben; er liegt irgendwo zwischen den beiden Rändern
(Median 3,50 gegen 1,90).

- ✅ Der Tracker weist beide Ränder aus (`roiFrueh` / `roiSpaet`) und setzt `backRoi: None` — ein
  ROI, dessen Vorzeichen an der Wahl des Preises hängt, ist keine Zahl, sondern eine Einstellung.
- ✅ Die Warnzeilen in `betfair_alerts.py` zitieren nicht mehr die widerlegte Zahl, sondern das
  Signal-Buch (n=135, −29,3 %, OG −10,0 %).
- ⏳ Offen: den Einstiegspreis beim Geldzufluss tatsächlich mitschreiben. Erst dann ist über den
  In-Play-Remis-Nachlauf überhaupt etwas belegbar — bisher war es das nie.

## 🐋 08.09.2026 — Polymarket-Menü: Whales, Lernen, Pushes (Durchsicht mit zwei Agenten)

Lucas vor der Heimfahrt: *„schaut ihr bitte noch im Menü die ganzen Whales an, ob wir da eh
überall die richtige Logik haben, ob die Whales eh neue dazukommen … und ob die Push, die im
Public gehen oder auch in Trades, ob das alles reibungslos funktioniert … vor allem Tennis und
E-Sports."*

### Die gute Nachricht zuerst: es lernt, und es lernt bei Tennis und E-Sport besser als bei Fußball

Es gibt **keine gepflegte Wallet-Liste** — die Menge wird bei jedem Lauf neu aus
`poly_wallet_track.json` gerechnet, und jede neue Großposition legt automatisch eine Wallet an.
Aus der Commit-Historie der Datei:

| Zeitraum | Wallets neu | „bewiesen" neu | „bewiesen" raus |
|---|---|---|---|
| 30 Tage | 2.429 | **185** | 18 |
| 14 Tage | 924 | 91 | 20 |
| 7 Tage | 483 | 59 | 11 |

185 der 233 „bewiesenen" sind in 30 Tagen dazugekommen. Und der Vorwärtstest sagt, wo die
Kante liegt: **E-Sport ROI −1,1 %, Tennis −3,0 %, Fußball −14,6 %** (n=207/141/149, alle
`belegt: false`). Von den 19 Wallets, die das strenge Gate bestehen, sind 9 E-Sport, 5 Tennis,
3 Fußball. Die Volumenschwellen ($7.500) schließen die kleinen Sportarten **nicht** aus —
Median-Volumen Tennis $30.354, E-Sport $32.830.

### 🔴 „Bewiesen" hieß: 91 bestätigte Verlierer, einer mit −$7,78 Mio

`killer.py` hatte eine **eigene, dritte** Sharp-Definition: `n >= 8 und Ø CLV > 0`. Kein Wilson,
keine Untergrenze, kein Ausschluss bestätigter Verlierer.

| Regel | Wallets |
|---|---|
| die alte Regel in `killer.py` | **233** |
| `sharp_gate.sharp_grade > 0` | 51 |
| `sharp_gate.is_sharp` (Schalter) | 19 |

**91 der 233 sind bestätigte Verlierer** — die größte mit n=186 und **P&L −$7.775.708**, die
zweite −$4.105.669. Sie trugen den Tiefen-Punkt im Bücher-Score. Das eigene Statusfile meldete
es die ganze Zeit (`proven_wallets_profitable`: „101/238 sind netto-NEGATIV"), nur las es dort
niemand.

- ✅ `_bewiesene_wallets` delegiert an `sharp_gate` — die eine Definition, die Dashboard,
  Shortlist, Whale-Watch und Live-Watch schon benutzen. Genommen wird die **lockere** Kante der
  Rampe (`grade > 0`, 51 Wallets), nicht der Schalter: am 01.09. wurde gemessen, dass die
  strengste Einstellung die schlechteste Vorwärtsleistung liefert.

### 🔴 Eine arme Regex gatete beide Kanäle — und druckte dabei keine Zeile

In **derselben Datei** standen zwei Liga→Sport-Zuordnungen: `sport_category()` (volle Regex) und
`_sport()` (`SOCCER…/LIGA/MLS/EPL/UCL`). Gegatet hat die arme: `_pub_ok()` wirft alles raus, was
bei ihr auf dem 🎯-Default landet — und `_pub_ok` filtert **beide** Kanäle, nicht nur Public.

Von 617 offenen Positionen landeten **75 auf 🎯, davon 55 echter Fußball**: EFL Championship 14,
Ligue 1 13, Eliteserien 8, Ligue 2 7, Brazil Serie A 5, Allsvenskan 4, Scottish Premiership 4.
Der Fingerabdruck steht in den Push-Zahlen: `epl` 54 Pushes, `lal` 33 — aber `fl1` **2**,
`elc` 5, `nor` 1, `bra`/`sco`/`all`/`fl2` **0**. Jeder andere Public-Filter druckt eine
Unterdrückungszeile (🚫 💭 🤝 ⚔️); dieser nicht, deshalb war der Verlust unsichtbar.

- ✅ `_sport()` fragt jetzt `sport_category()` und hängt nur noch das Emoji dran; der gestempelte
  `sport` aus dem Capture hat Vorrang (601 der 617 Positionen tragen ihn). **59 von 75 Positionen
  freigeschaltet**, 0 falsche dazu. Übrig bleiben CFB und SACHSEN.
- ✅ Zwei Regex-Lücken im geteilten Spiegel (Python + JS gleichzeitig): `\bcfb\b` ergänzt,
  `pro-?league` → `pro(?:fessional)?-?league` (traf „SAUDI-PROFESSIONAL-LEAGUE" nicht).

### 🔴 Das größte Push-Buch im Repo war das einzige ohne Untergrenze

`betfair_public_record.json`: n=190, Treffer 58,4 %, ROI −2,6 % — **kein `roiUg`, kein `hitUg`,
nirgends**, und `renderPushBoard()` zeigte beides als nackte Punktschätzer. Das *kleinste* Buch
(Poly Public, n=9) schreibt seit dem 03.09. sauber „UG — (n<30)".

Gerechnet steht da jetzt: Treffer 58,4 % (**UG 52,5 %**), ROI −2,6 % (**UG −12,9 %**), und der
Satz, der die Quote erst zu einer Zahl macht: bei Ø 1,83 liegt der **Break-even bei 54,6 %** —
die Untergrenze liegt darunter. Dazu fielen **17 von 210** Ledger-Zeilen still aus dem Nenner
(`expired`, nie aufgelöst) — das Board zeigte nur „offen: 2".

- ✅ `hitUg` (Wilson aus `sharp_gate`), `roiUg` + `belegt` (aus `freigabe.untergrenze`, n≥30)
  im Artefakt und je Szenario; `verfallen`/`ungueltig` gezählt und auf dem Board benannt.

### 🟠 Die Puls-Kachel zeigte nur das obere Ende ihres Bereichs

Nachfolge-Fund zum 04.09.: die Kachel heißt seither richtig („Poly-Kandidaten · Vorschau, sendet
nicht"), trug ihre Zahl aber weiter ohne Fehlerbalken. `poly_shortlist_track.agg.public` liefert
`roiUg: −0,0283` und `belegt: false` **gleich mit** — sie kamen im Puls nur nie an. Angezeigt
wurde +6,3 %; der wahre Bereich läuft von −2,8 % bis +6,3 %.

- ✅ `roiUgPct` + `belegt` durchgereicht und auf der Kachel gezeigt.

### 🟠 Ein leerer Abschnitt und ein nie gebauter Abschnitt sahen gleich aus

- **🏆 WM 2026** — `wm_poly_wallets.json` trägt den Stempel 19.07.2026, **50 Tage alt** (das
  Finale war an dem Tag). Der Tab rendert diese Zahlen wie frische.
- **🎮 E-Sport** — der Tab lädt `esports_poly_settlement.json`, `esports_poly_wallet_ledger.json`
  und `esports_poly_money_accuracy.json`. **Alle drei existieren nicht**: `fetch_poly_esports.py`
  schreibt nur prices/wallets/smartmoney/coherence, und `build_poly_wallet_ledger.py` läuft in
  fünf Workflows, alle Fußball. Bug-Klasse „verdrahtet, aber hinten kommt nichts an".

- ✅ Banner an den Datensatz-Reitern: Alter des Datensatzes (ab 12 h, ab 48 h rot) und welche
  seiner Dateien **gar nicht gebaut** werden.

### 🟠 Cross-Sport pushte 84 von 84 Alerts in eine gesperrte Kategorie

Alle 84 Cross-Sport-Alerts der letzten 30 Tage waren MLB — die Kategorie, die
`PW_BLOCKED_BET_CATS` sperrt und die der Whale-Watch mit einer 🚫-Zeile abweist.

Die Sperre wird **bewusst nicht übernommen**: sie wurde am Whale-Papierdepot gemessen
(MLB n=72, ROI −28 %), also an „einer Wallet folgen". Cross-Sport ist Poly-Preis gegen die
de-viggte Pinnacle — eine andere Mechanik, und ein Messwert der einen auf die andere anzuwenden
wäre ein Kurzschluss.

- ✅ Die Karte trägt jetzt den Hinweis, dass diese Kategorie für Einsätze gesperrt ist und dass
  es für diese Mechanik noch kein eigenes Buch gibt.

### ⏳ Offen — bewusst nicht in dieser Runde

- **1.850 Pushes in 30 Tagen ohne Buch.** `poly_whale_watch` (Trades, 981), `poly_live_watch`
  (785) und `poly_cross_sport_watch` (84) speichern nur `{usd, ts}` bzw. `{gap, ts}` — kein Preis
  zum Sendezeitpunkt, kein Ergebnis, keine Bilanz. Das Muster existiert bereits (`killer_push`
  und Public schreiben `pushPreis`/`pushPrice` + Settlement); für diese drei wurde es nie gebaut.
  **Der lauteste Kanal ist der unbelegte.**
- **Dedup je Sender statt je Kanal.** 186 Extra-Sendungen in 30 Tagen (gleicher Markt + gleiche
  Seite, verschiedene Wallets), 106 davon binnen 2 h; 16 von 26 Shortlist-Pushes decken sich
  exakt mit einem Whale-Push (Median 141 min, einer bei 0 min); ein kanalübergreifendes
  Public-Doppel (LASK–Celtic, 25.08., 9 min Abstand, Betfair + Poly).
- **`_dedup_by_wallet` läuft nur auf den Trades-Kandidaten**, nicht auf `pub_cand` — im
  öffentlichen Kanal darf eine Wallet pro Lauf beliebig viele Karten füllen. Tatsächlich kommen
  **24 der 42 Public-Pushes von einer einzigen CS2-Wallet**.
- **Tennis erreicht den Public-Kanal nicht.** Letzter Tennis-Public-Push: 12.08., vor 27 Tagen —
  bei 161 Tennis-Pushes in Trades im selben Zeitraum. Es scheitert nicht am Top-10-Gate
  (69 Tennis-Pushes kamen von Top-10-Wallets), sondern an Größe ($25.000-Boden, Median-Einsatz
  Tennis $7.000) und Mindestquote. Das ist eine Entscheidung, keine Reparatur.
- **Tennis hat gar keinen Menüpunkt** — 285 Wallets mit Tennis-Historie, 989 gewertete
  Auflösungen, 5 der 19 strengen Wallets, und über die Oberfläche nicht als Sportart adressierbar.
- **53 % der offenen Whale-Positionen sind per Konstruktion unbewertbar.** 327 von 613 sind
  `-more-markets`-Bündel mit generischer Seite; `poly_money_broad.py:1670` löscht sie beim
  Auflösen ganz, inklusive CLV. Im Close-Store: 1.188 bereits still verworfene Positionen, alle
  Fußball. Die Fußball-Stichprobe wird an einer nicht-zufälligen Stelle beschnitten.
- **`poly_whale_watch._pub_keep()` und `PUB_MIN_USD_NOREC` sind toter Code**, der wie ein aktives
  Tor aussieht — die nächste Änderung wird sonst an der falschen Stelle gemacht.
- **`betfair_alerts.py:850` hat eine hartkodierte Public-Chat-ID als Rückfall, Poly nicht.** Fällt
  `TELEGRAM_CHAT_ID` weg, verstummt Poly still und Betfair sendet weiter.

## 🧭 08.09.2026 — Ebene 0: die Spielzentrale

Lucas: *„alle sources zu sehen aber auch Empfehlungen was deckt sich, was sinnvoll zu wetten ohne
da jede source extra zu checken. Also quasi hybrid."* Und danach, zu Recht: *„schau dir mal die
Elemente oben an, die gehen ja schon in die Richtung."*

Sie gehen in die Richtung — und beantworten trotzdem eine andere Frage. Gemessen an diesem Tag:

| Ebene | Frage | Stand 09:33 UTC | warum |
|---|---|---|---|
| 1 Register | darf ich blind spielen? | 0 freigegeben | 2 von 64 reifen Schubladen über ROI-UG 0, beide an CLV gescheitert |
| 2 Punktestand | wie viele Bücher sind sich einig? | 0/0 | **`inflow` 0 von 192** — das Tor verlangt ≥ 2.000 € Zufluss zwischen zwei Snapshots im Abstand von 15 Min; größter Wert im ganzen Feld 1.178 € |
| 3 Rangliste | was ist das stärkste Einzelsignal? | 0 | Money-Map-Eingang ist `verdict !== 'uneinig'` → die einzige „einig"-Zeile fällt genau deshalb raus |

Ebene 2 misst **Bewegung**, nicht Übereinstimmung: im Ledger tauchten **76 % aller Zeilen erst
< 3 h vor Anpfiff** auf (Median 0,7 h, nur 17 % ≥ 6 h vorher). Morgens ist sie leer — und schreibt
dann „Gerade deckt sich nichts", was sich wie ein Befund liest. Real Madrid v Inter stand im selben
Moment mit `conc: true`, 88 % Geldanteil, 102.861 € und **7 von 10 Bücherpunkten** in
`alleBewertet`, unsichtbar wegen `inflow: false, dir: flat`.

**Ebene 0** beantwortet die dritte Frage — *auf welche Spiele schauen heute überhaupt mehrere
Quellen, und liegen sie auf derselben Seite* — und braucht dafür keine Bewegung.

- ✅ `spielzentrale.py` (rein/testbar) + `spielzentrale_basis.json`: `money_map_row` für **jedes**
  Spiel im Feed statt nur für die Radar-Liste. Dieselbe Rechnung wie die Money Map, andere Frage.
- ✅ Das Urteil entsteht im Produzenten (`urteil`, `dafuer`, `gegen`, `text`); das Frontend liest
  und rechnet nichts nach.
- ✅ **Pinnacle stiftet keine Einigkeit.** Das Geld liegt fast immer auf dem Favoriten — wäre der
  Anker eine Stimme, wäre fast jede Zeile „einig". Er kann nur bestätigen oder widersprechen.
  Ebenso stimmt ein reiner Poly-**Preis** nicht mit ab (`polyGeld`), bleibt aber sichtbar.
- ✅ Stake wird dritte Geldquelle — Einzelwetten, Seite nur aus dem 1X2-Markt. Die angezeigte
  Summe hat **keinen** Boden (sie gibt es nur einmal); der Boden entscheidet nur, ob Stake mitstimmt.
- ✅ Namens-Joins (Stake, Cards) laufen über `gleiche_elf` — dieselbe Regel wie beim Poly-Join.
- ✅ Die Restmenge steht als Zahl da: heute **23 Zeilen, 77 Spiele mit nur einer Geldquelle**,
  14 später als 24 h, 9 angepfiffen. Ohne sie liest sich eine kurze Liste wie ein Ausfall.
- ✅ Guard `check_spielzentrale_urteil`: „einig" braucht zwei Stimmen ohne Gegenstimme, Pinnacle
  steht nie in `dafuer`, ein Poly-Preis auch nicht — und Money Map und Zentrale dürfen zum selben
  Spiel nicht zwei verschiedene Antworten geben.

Ergebnis heute an echten Daten: **19 einig, 4 uneinig**, obenan Real Madrid v Inter mit
Betfair 88 % / 102.861 € + Polymarket 60 % / $294.571 + Stake $21.362, alle auf Heim.

⏳ Offen, bewusst nicht miterledigt:
- Ebene 2 sagt weiter „Gerade deckt sich nichts", ohne zu sagen, dass ihr Tor Bewegung verlangt.
  Der Satz gehört an die Messung angepasst (76 % der Zeilen < 3 h vor Anpfiff).
- Ebene 3 nimmt die Money Map weiter nur bei `uneinig`. Mit Ebene 0 darüber ist das jetzt
  verteidigbar (die Rangliste sucht Einzelsignale), sollte aber dranstehen.
- `_mdFetch` hat sein eigenes `jf` statt `rawJson` — funktional identisch, aber ein Duplikat der
  Stelle, die genau dafür gebaut wurde.

## 🔴 08.09.2026 — der Nachwuchs bekam das Geld der ersten Mannschaft

Beim Übersichts-Check aufgefallen: `betfair_anker.json` führte für **Real Madrid U19 v Inter U19**
(UEFA Youth League) den Poly-Markt `ucl-rma-int-2026-09-08` mit **$294.571** — das ist das Geld des
Senioren-Spiels am selben Abend. Fünf Fälle in einer Datei:

| Betfair-Spiel | fälschlich verbundener Poly-Markt | Geld |
|---|---|---|
| Goztepe U19 v Gazisehir U19 | `tur-goz-gfk-2026-09-07` | $339.991 |
| Real Madrid U19 v Inter U19 | `ucl-rma-int-2026-09-08` | $294.571 |
| Caykur Rizespor U19 v Alanyaspor U19 | `tur-riz-ala-2026-09-07` | $120.566 |
| Porto U19 v Man City U19 | `ucl-por-mnc-2026-09-08` | $47.300 |
| Club Brugge U19 v Aston Villa U19 | `ucl-bru-ast-2026-09-08` | $34.981 |

`ucl-por-mnc-2026-09-08` hing damit **gleichzeitig an zwei Betfair-Spielen** (Porto U19 und Man City).

Der Namens-Score kann das grundsätzlich nicht trennen: „Real Madrid U19" gegen „Real Madrid CF"
ergibt 2/3 (das „CF" fällt als Rausch-Token weg, das „U19" bleibt stehen), „Inter U19" gegen
„Inter Milan" 1/2 — Summe 1,17 über der Schwelle 0,99. Ein Altersmarker ist keine Namensvariante.

- ✅ **`elf_marker()` / `gleiche_elf()` in `betfair_consensus.py`**: U15–U23, II/III, B, W/Frauen,
  Reserve, Youth, Jong sind Teil der Identität; fehlende Angabe = erste Mannschaft. Der Join
  vergleicht die Ebene **vor** dem Score — auch im Abkürzungs-Rückfall.
- ✅ Gegenprobe an den echten Pools (1.983 close + 239 upcoming + 61 live gegen 125 Betfair-Spiele):
  **genau 5 Joins fallen weg, alle fünf die falschen; 0 richtige verloren, 0 neue dazu.**
  Real Madrid v Inter behält seinen Markt.
- ✅ Guard `check_poly_markt_gehoert_zur_selben_mannschaft` (uebersicht_integrity.py) prüft am
  fertigen Artefakt zwei Sätze: gleiche Mannschaftsebene, und **ein Poly-Markt hängt an höchstens
  einem Spiel**. Gegen den heutigen Stand meldet er alle 6 Befunde. Der ältere Guard
  `check_money_map_poly_gehoert_zum_spiel` sah davon nichts — „Real Madrid U19" und „Real Madrid CF"
  teilen ja Tokens, das ist gerade der Punkt.

## 🟠 08.09.2026 — die Feuer-Schwelle wurde an der falschen Stelle gesucht

Die Signal-Bilanz filterte dünne Zeilen mit `d.signals && d.signals.minFire || 0`.
`pulse.signals` gibt es nicht (null) — das Feld heißt `minFire` und liegt in `pulse.signalBoard`,
also in genau dem Objekt, aus dem zwei Zeilen weiter oben die Zeilen kommen. Ergebnis: Schwelle 0,
keine Zeile gilt als dünn, **alle 25 Signale standen gleichwertig ausgeklappt** — darunter fünf mit
n ≤ 2 („reverse_line_move n2 · 100 %·2 dafür") direkt neben n = 130.

Der Produzent hatte `minFire: 6` die ganze Zeit mitgeliefert. Dieselbe Klasse wie am 04.09.:
**fehlende Information rendert als harmloser Default.**

- ✅ Schwelle kommt aus `b.minFire`. Fehlt sie wirklich, sagt die Tafel das (`⚠ keine
  Feuer-Schwelle im Artefakt`), statt still auf 0 zu fallen.

## 🟠 08.09.2026 — die Stake-Geld-Kachel war zuverlässig Rückblick

„Stake · größtes Geld" sortierte über 24 h nach Geld und zeigte damit vier Spiele, die seit 11 bis
15 Stunden angepfiffen waren. Nicht falsch, aber nutzlos: eine prominente Kachel, die jeden Blick
kostet und nie eine Handlung zurückgibt.

- ✅ Erst die Spiele vor Anpfiff; nur wenn keins da ist, der Rückblick — dann ausdrücklich als
  solcher beschriftet. Ohne Anpfiff gilt ein Spiel **nicht** als offen.
- ✅ Guard `tests/frontend/uebersicht-stake-geld.test.mjs`; mit dem alten Verhalten fallen alle drei
  Tests (geprüft).

## 🔴 08.09.2026 — der Detail-Deckel schnitt das teuerste Spiel des Tages weg

Lucas: *„vorher war Real Madrid drin, heute Champions League mit dem meisten Geld … nun sind
beide Spiele verschwunden."* Es war kein Anzeigefilter — die Spiele waren **nicht mehr im Feed**.

`select_ids` (fetch_betfair_betwatch.py) vergibt die teuren Detail-Calls in der Reihenfolge
live → Prioritäts-Ligen (72 h) → Rest im 26-h-Fenster **nach Anpfiff sortiert**, gedeckelt bei
`BETWATCH_MAX_DETAIL` = 150. Gemessen an den beiden Läufen dieses Morgens:

| Lauf | Spiele | Folge |
|---|---|---|
| 04:57 UTC | 125 (unter dem Deckel) | Real Madrid v Inter mit **102.861 €** drin |
| 07:57 UTC | **150 (= Deckel)** | **alle vier CL-Spiele weg** (Real Madrid, Dortmund, Porto–City, Lille–Betis), dazu Boca und Fluminense |

Nachgerückt sind 19 Scottish Challenge Cup, 13 English National League Cup, 6 Portuguese U23.
Das Spiel mit dem meisten Geld des Tages fiel raus, weil vierzig Pokalspiele früher anpfeifen —
und der Public-Push zeigte da schon auf eine Fläche, die leer war.

Zwei Ursachen, beide behoben:

- ✅ **Die Prioritäts-Definition wich von der des Verbrauchers ab.** `betfair-radar.js` stuft mit
  `tierOf()` in top5 / UEFA+International / Rest und gibt den ersten beiden dieselbe Schwelle;
  der Fetcher hatte eine zweite, kürzere Liste ohne UEFA. Jetzt dieselbe Einstufung
  (`ist_prioritaet`).
- ✅ **Der Rest-Topf sortierte nach Anpfiff** — die einzige Achse, die nichts darüber sagt, ob uns
  ein Spiel interessiert. Jetzt zuerst nach dem Geld, das wir vom letzten Lauf schon **kennen**
  (`bekanntes_volumen` aus `betfair_prices.json`, kostet keinen API-Call), dann Anpfiff. Das
  greift auch für Wettbewerbe, die auf keiner Liste stehen (Libertadores, Sudamericana).

Gegenprobe an den echten Daten beider Läufe: mit der alten Logik fallen alle drei geprüften
CL-Spiele bei Cap 150 raus, mit der neuen sind alle drei drin. Guard dazu:
`check_grosses_geld_faellt_nicht_aus_dem_feed` — ein Spiel, das zuletzt ≥ 20.000 € trug und noch
nicht angepfiffen ist, darf nicht kommentarlos aus dem Feed verschwinden. Gegen den 07:57-Stand
meldet er zwei Spiele (125.638 € und 21.226 €, Anpfiff in 10,8 h). Zusätzlich sagt der Fetcher
beim Lauf, wenn der Deckel greift und dabei ein bekanntes Geld-Spiel fällt.

⏳ **Offen:** `MAX_DETAIL = 150` bleibt, wie es ist. Der Deckel ist jetzt nach der richtigen Achse
sortiert, aber er greift täglich — wenn du mehr Abdeckung willst, ist die Frage, was ein höherer
Deckel an Laufzeit und API-Budget kostet. Das habe ich nicht gemessen.

---

## 🔴 Übersicht-Checkup 07.09.2026 abends — vier Funde, alle behoben

1. **Money Map: fremdes Geld in einer Konsens-Zeile.** „Al-Ahed v Al Ahli Akhaa Aley"
   (Lebanese FA Cup) zeigte Poly **$267.964** und „Konsens 3/3". Das Geld gehörte zu
   `spl-hil-ahl-2026-09-01` — Al Hilal v Al Ahli, Saudi Pro League, **sechs Tage vorher
   abgerechnet** und im selben Board zwei Kacheln weiter mit $257K sichtbar. Zwei Ursachen:
   der Kandidaten-Pool enthielt jeden abgerechneten Snapshot (2.494 von 2.557 — der Close-Feed
   hält sie 30 Tage für die Auswertung), und der Abkürzungs-Rückfall ließ „al" als gemeinsames
   Token gelten. → Abgerechnete Märkte, die **vor dem Anpfiff** abgerechnet wurden, fallen aus
   dem Pool; der Rückfall braucht ein Token, das ein Name sein kann. Guard:
   `check_money_map_poly_gehoert_zum_spiel`.
2. **„verliert" war kein Verlustbeleg.** `betfair_track_record` fällte das Urteil an der
   UNTERgrenze (≤ −10 %) — für „trägt" richtig (UG > 0), für „verliert" falsch. Gemessen:
   **40 Buckets mit „verliert", 37 davon mit Obergrenze über null, 18 mit positivem
   Punktschätzer** — bis **+32,6 %** (Argentinian Primera Nacional · Ü/U 3.5, n=36, UG −14,3 %,
   OG +79,5 %). Das Urteil hat Zähne: es nahm Zeilen aus der Rangliste und mutete
   Terminal-Zeilen. → `roiOg` wird mitgeschrieben, „verliert" verlangt die Obergrenze unter
   null; die alte Schwelle lebt als **Risiko-Marke `fade`** weiter, an der alle Gates hängen
   (Verhalten unverändert). `killer.py` baute die Schwelle zum vierten Mal nach — liest jetzt.
3. **Die Rangliste filterte still.** Unter „Was ist gerade das Stärkste?" steht „nicht geprüft,
   nur sortiert" — und darüber lief der Track-Filter. Deshalb fehlte die stärkste
   Betfair-Bewegung des Tages (Nueva Chicago v Quilmes, **+6,2 pp**), während die Steam-Kachel
   sie als Nummer 2 führte. → Filter bleibt, wird gezählt und benannt.
4. **Drei Zahlen, die etwas anderes hießen als sie sind.** Die Signal-Bilanz zeigt `n` =
   Feuerungen neben zwei Quoten, deren Basis kleiner ist (**66 Feuerungen über 8 Signale ohne
   Richtung**, bei Kader-Abgängen 21 von 67) → „o. R." steht jetzt dran. Stake zeigte
   „● 125. Min" für ein Serie-A-Spiel — gemessen ist die **Wanduhr seit Anpfiff**, inklusive
   Halbzeitpause (9 Fußball-Wetten über der 100.) → heißt jetzt so. Und „Am nächsten dran"
   listete Schubladen mit n=16–25, während der Satz davor von reifen Schubladen sprach →
   „Am nächsten an der Mindestzahl (30 Plays) — nicht an einem Beleg".

⚠️ **Rollout:** Fund 1 und 2 wirken erst, wenn `betfair_consensus.py` und
`betfair_track_record.py` auf dem Runner neu gelaufen sind. Bis dahin melden beide Guards rot —
das ist der gewünschte Zustand, nicht ein zweiter Fehler.

---

## ⏳ Offen aus der Session vom 07.09.2026

Reihenfolge ist Absicht: oben, was ohne neue Entscheidung gebaut werden kann.

### Stake
- ⏳ **Die beiden vorregistrierten Schubladen abwarten.** `randliga_hoher_einsatz` (Ziel n=150,
  ~12 Kandidaten/Tag → ca. zwei Wochen) und `topliga_hoher_einsatz` (Ziel n=200). Bis dahin ist
  die Spielklasse-Ansicht **Anzeige, keine Empfehlung** — der Rückblick ist der Fund, nicht der
  Beleg. Details: CAPABILITIES §„07.09.2026 — die Spielklasse einer Liga".
- ✅ **Die „🚩 Auffällig"-Ansicht ehrlich beschriftet** (07.09. abends): heißt jetzt
  **„📏 Über der Norm"**, und das Urteil über die eigene Prämisse wird **gerechnet**
  (`stake_analyse.norm_phase` → `normPhase.urteil.praemisse`), nicht getippt. Nachgemessen mit
  der Faktor-Definition des Erzeugers: `>15×` gepoolt **−22,1 %, OG −2,5 %, n=71** → belegt
  gegen die Prämisse. Ein Frontend-Test verbietet feste Prozentzahlen im Urteilstext.
- ✅ **Achse umgestellt** auf live × Einsatzgröße (`STUFEN_FEIN`, neuer Schnitt bei 15×). Vor
  Anpfiff verliert belegt (`<1.5×` −11,5 %, OG −7,6 %, n=987), live nicht — das ist die Achse,
  die trennt.
- ✅ **Sortierung im Spielklasse-Reiter** nach Betrag (07.09. abends). Kein reines Sortierthema:
  die Auswahl ist jetzt die **Vereinigung** der besten 30 nach Faktor und nach Betrag, jede Zeile
  mit `warumDrin`. Sonst zeigte „nach Betrag" die größten Beträge einer nach Faktor
  abgeschnittenen Liste.
- 🔒 **Verknüpfung zu den anderen Büchern** — bewusst zurückgestellt (Lucas 06.09.: *„lass mal
  aus, das kommt erst wenn wir Stake als einzelne Quelle vernünftig verwenden"*).
- ℹ️ **Kein Track-Record je Konto möglich.** `user` ist im Feed dauerhaft `null`; Stake
  anonymisiert die Highroller-Liste vollständig. Nicht erneut versuchen.

### Frontend-Hygiene
- ✅ **raw-first ist jetzt eine Funktion** (07.09. abends): `raw-json.js` (`rawJson`,
  `rawFirstUrls`) als erstes Skript im Dashboard; die fünf offenen Dateien rufen sie auf statt
  die Reihenfolge abzuschreiben. `AUSNAHMEN` ist leer. Der breiter gefasste Guard fand dabei
  **zwei weitere** Fälle (`money-map.js`, `tiktok-studio.js`) — die alte Erkennung sah nur
  Literale direkt im `fetch()`. Neuer Guard: kein jsdom-Harness testet eine Umgebung ohne
  `raw-json.js`.

### Ops
- ✅ **Pages-Artefakt: 160,3 → 126,3 MB** (07.09. abends). Ursache war kein Wachstum, sondern ein
  Leck in der Ballast-Regel: ihr Sicherheitsnetz für dynamisch gebaute Namen liess jedes
  generische Endstück gelten (`ledger.json`, `_results.json`, `_cache.json`), und damit fuhren
  **34,1 MB** mit, die keine Zeile Frontend-Code anfasst — allen voran `stake_bet_ledger.json`
  (15,4 MB), das nur blieb, weil irgendwo `liga_signal_ledger.json` steht. Endstücke zählen jetzt
  nur an einer echten Verkettungsgrenze (`'`, `"`, `` ` ``, `}`). Budget 160 → **140**, damit der
  gewonnene Platz nicht stillschweigend zuwächst.
  *Woher der Deckel kommt:* nicht von GitHub (1 GB veröffentlichte Seite), sondern von der
  **10-Minuten-Grenze für einen Deploy** — bei 198 MB dauerte der Upload 10–18 Min und wurde vom
  nächsten Trigger überholt.
- ⏳ **Was ohne Entscheidung nicht rauszuholen ist:** `matches/` 49 MB (1.018 Einzel-JSONs à
  ~150 KB) und ~76 MB referenzierte Wurzel-JSONs. Letztere liegen im Deploy nur noch als
  **Rückfall** — geholt wird seit heute überall raw-zuerst. Wer den Rückfall aufgibt, spart den
  grössten Teil davon, hat bei einer raw-Störung aber eine leere Seite statt einer alten.

### Nachtarbeit — gemessen, wann wirklich tote Zeit ist
- ℹ️ **02–06 Uhr ist NICHT tot: das ist MLS-Primetime.** 419 von 510 MLS-Anpfiffen (82 %) liegen
  zwischen 01 und 05 Uhr Wien. Genau dann laufen Live-Scan, Steam-Erkennung, Wallet-Beobachtung.
- 📌 **Das echte Loch liegt 06–09 Uhr Wien** (Stake-Fluss 393–430 Wetten/Std gegen 486–631 in
  02–06 und ~800 abends; Top-5-Anpfiffe beginnen erst ab 12 Uhr). Kandidaten für dieses Fenster:
  Kompaktierung/Archivierung der grossen JSONs, Backtests und Lernläufe — damit der geteilte
  Mac-Runner tagsüber frei bleibt (gemessen: Live-Scan lief sechs Tage bei 8–29 %).

### Angeboten, nicht begonnen
- ⏳ **Draw-No-Bet als Alternative auf gerichteten Cards** + eigene vorregistrierte Schublade.
  Gemessen halbieren DNB/DC die Varianz: Beleg bräuchte ~176 statt ~950 Picks.
- ⏳ **Vor-Einstiegs-Momentum als Vorfilter** verdrahten (`movePreEntryPP` wird seit 06.09.
  gestempelt, aber nirgends als Filter benutzt).

### Zurückgezogene Befunde — nicht wieder aufgreifen ohne neue Daten
- ❌ **Leader-Following** (n=52, ROI +27,8 %): nicht reproduzierbar. Das volle Public-Ledger
  steht bei −2,6 %, das HT-Szenario bei −22,8 %.
- ❌ **Soft-Bookies als Quotenempfehlung**: verworfen (Lucas 06.09.). Der Soft-Median liegt
  6,2–6,7 % unter fair; wir geben weiter Pinnacle bzw. den Median an.

---

## Liga (auf WM-Stack, ~6 Wochen bis Saisonstart)

### ✅ Erledigt (Referenz)
Daten/Odds/Picks-Engine/Renderer/Tracking/CLV/Resolve/eigener Workflow · Guards + Lern-Loop
dataset-bewusst · LeaguePressureSignal · Post-Match-xG-Re-Learning · Backtest (5 Ligen + Value-Filter
+ CLV) · Backtest-als-Prior (liga_signal_priors) · LIGA_SIGNALS.md · Club-Elo (Baseline).

### ⏳ Daten / Pipeline
- ⏳ Odds-Takt nahe Spieltage hochdrehen (~2 Wochen vor Saisonstart) — sonst werden Intraday-Steam-Drops verpasst (= genau die Picks). Jetzt sinnlos (keine Bewegung).
- ✅ ESP/GER verifiziert: live leer (La Liga/Bundesliga-Spielplan noch nicht bei API-Football,
  upstream-Timing — kein Bug). Guard `check_liga_leagues_populated` (warn) macht's sichtbar; füllt
  sich auto, wenn die Spielpläne kommen. Falls kurz vor Saisonstart noch leer → nachgehen.
- ⏳ ClubElo-Fetch im GitHub-Workflow verifizieren — Sandbox gab 403; in Actions prüfen, sonst UA/Quelle anpassen.

### ⏳ Frontend / Cards
- ✅ Matchday-Subnav „1 dann 20"-Bug behoben (Daten-Fix pick_event_for_fixture + Frontend-Cap + Guard).
- ✅ Sharp Radar: aktuelle Linien auch OHNE Bewegung (Tabelle Pinnacle/Soft, bis Moves da sind).
- ⏳ Heart-Tab Liga-Integration (Top-Conviction-Ansicht + Liga-Signale; aktuell WM-verdrahtet).
- ✅ Pick→Card-Pfad bewiesen (simulierter Drop → 2 Cards) — Cards füllen sich automatisch bei Linienbewegung.

### ⏳ Signale (laut LIGA_SIGNALS.md, modular dazubauen)
- ✅ `injury` Liga-Fetch (Fetcher dataset-bewusst; InjurySignal liest wm[injuries]).
- ✅ `apif_predictions` Liga-Fetch (Fetcher dataset-bewusst → liga_apif_predictions.json).
- ✅ `fixture_congestion` / Erschöpfung (Ruhetage aus Spielplan; registriert, context-Familie).
- ✅ Spieler-Layer Spine: `squads` (Schlüsselspieler → lineup_signal) + `player_form`-Ledger
  (aus gespielten Spielen via fetch_liga_match_stats → liga_player_form.json, skaliert lineup_signal).
- ✅ `topscorer_momentum` (/players/topscorers → liga-data.json[topScorers]; form-Familie, Boost Sieg/Über).
- ⏳ Spieler-Layer Rest: `squad_strength` (überlappt injury/lineup, niedrige Prio).
- ✅ `coach_change` (Neue-Trainer-Bounce, /coachs) + `transfer_shift` (Schlüsselspieler-Abgang, /transfers).
- ⛔ `referee_tendency` — KEIN Quick-Signal: braucht zuerst den **Karten-Markt** (Schiri wird nicht
  geholt — kein referee-Feld; kein fetch_wm_cards; kein Karten-Markt in der Engine). Eigener Block:
  Schiri-Daten + Karten-Quoten + Pick/Resolve, DANN das Signal. Scope-Disziplin: ohne Markt = Lärm.
- ❌ News-Signal — VERWORFEN (27.06.2026). Probe (fetch_liga_news_probe.py) ergab: API-Football hat
  KEINEN /news-Endpoint ("The News endpoint does not exist.", results=0 bei allen Varianten). Über
  diese API nicht machbar. Probe + news-probe.yml entfernt; Evidenz in liga_news_probe.json + LIGA_SIGNALS.md C8.

### ⏳ Märkte
- ⏳ Player-Props + Corner-Markt + Engine-Hooks (`corner_rate`-Signal).
- 🔒 Poly Trading / Wallets Liga — blockiert, bis Polymarket Ligen listet.

### Lern-Loop / Guards
- ✅ Guard-Batterie Liga auditiert (26.06.): 42/48 laufen auf Liga, 5 zurecht N/A (WM-Venue/time, Poly-Book/Steam-Lag-Dedup), 1 Lücke gefixt (`soft_opening_captured` las WM-History → `IntegrityCtx.history` dataset-bewusst). + `liga_leagues_populated` + `liga_odds_round_sane`.
- ⏳ Lern-Loop end-to-end: Plumbing verifiziert (Trockenlauf grün, Prior greift) — volle Aussage erst mit aufgelösten Liga-Picks (datenblockiert bis Saisonstart).
- ⏳ Forward-CLV-Tracking: Mechanik da (`resolve_steam_clv` schreibt `clvPP` auf Liga-Picks); Dashboard-Aggregat bauen, sobald erste Picks existieren (datenblockiert).

### ⏳ Liga-Switch-Ideen
- ⏳ Halbzeit-Märkte + Signale anpassen.
- ⏳ Liga-Historie als eigenes lernbares Signal (Backtest-als-Signal: gelernter Prior je Markt/Liga).

## WM — noch nicht umgesetzt / offen
- ⏳ KO-Bracket: `best_third` + W-Referenzen auflösen (TBD bis FIFA-Tabelle / KO-Ergebnisse).
- ⏳ Trade-Post-Mortem: Closing-Capture bei Anpfiff (CLV-Abdeckungslücke).
- ⏳ Poly Pre-Match-Close: hängt am `AUTO_SELL_ENABLED`-Secret.
- ⏳ smart_money: Holders-Endpoint am 1. echten Live-Lauf justieren.
- ⏳ Poly-Handicap-Trading: `ah_trade_enabled` gated AUS bis Token-Platzierung verifiziert.
- ✅ Pick-Kalibrierung ausgewertet (27.06.): 75 Picks, Baseline 0.585, steam Δ=+0.0 → kein Nudge nötig (kalibriert). High-Conviction 0.79 (n=5, zu klein). Nach mehr Runden erneut.
- ⏳ Freshness-Reverser: Phase 2 (reinforcing-market).
- ⏳ Safer-Line: Phase 2 (Quarter-Linien 3.0 / 3.25 / +0.25).
- ⏳ Player-Props: deaktiviert (kein Engine-Hook) → aktivieren, wenn Markt + Hook stehen.
- ⏳ Signal-Engine-Roadmap: restliche geplante Signale der 5 Tiers.
- ⏳ Post-Match-Move-These: Dense-Capture-Daten auswerten, dann entscheiden.
- ✅ Daten-Lücken geprüft (27.06.): apif liefert jetzt 59 Spiele (WC2026 gelistet, Turnier live) — keine Lücke. weather dünn (nur 4 Einträge) → Wetter-Workflow prüfen (kleinere Sache).
- ✅ R32-Cards ohne Pick GEFIXT (27.06.): fetch_wm_poly_prices.real_keys enthielt koFixtures nicht → KO-Odds bei jedem Lauf als Phantom geprunt. real_keys |= koFixtures + Guard check_ko_odds_present.
