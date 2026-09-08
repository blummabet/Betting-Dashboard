# CocoBet Backlog (Liga + WM)

Stand 07.09.2026 (oberster Block); Liga/WM-Teil darunter Stand 26.06.2026. Lebendige Liste aller offenen Punkte — Liga UND noch nicht umgesetzte WM-Sachen —
damit wir alles abarbeiten können. ✅ = erledigt (Referenz), ⏳ = offen, 🔒 = blockiert.

## 🎯 08.09.2026 (nachts) — welche SPIELE fallen unter eine freigegebene Schublade

Lucas, nachdem er die erste Push-Vorschau gesehen hat: *„also es wird nur das geschickt, aber
nicht welche Spiele — na dann brauch ich das eher nicht. Interessant wäre ja, welche Spiele für
die freigegebenen Schubladen in Frage kämen. Das müsste man im Board sehen und halt ne Push
dafür."*

Er hat recht, und der Einwand trifft eine echte Lücke: **„Liga · ABWÄGEN ist freigegeben" ist
eine Aussage über 91 abgerechnete Plays von gestern.** Was man damit TUT, steht erst in den
offenen Picks, die heute unter dieselbe Definition fallen. Genau dort hörte das Register auf.

- ✅ **`freigabe.offene_plays` / `freigabe.spiele`** — je freigegebener Schublade die offenen
  Plays, die unter ihren Schnitt fallen. Der Schnitt wird **nicht nachgebaut**: jede Schublade
  trägt ihre Definition schon als `meta` (`art` + `wert` + `datensatz`), weil `bewerte` sie beim
  Zählen dorthin geschrieben hat. Dieselbe Definition wird auf die offenen Plays angewandt —
  sonst hätten wir zwei Wahrheiten über eine Schublade, und die Liste könnte Spiele zeigen, die
  in der Messung nie gezählt hätten. Dieselben Ausschlüsse gelten (`trackingExcluded`, `boldAlt`).
  Stand heute: **31 offene Picks** aus Liga · ABWÄGEN (Venezia–Fiorentina, Rennes–Marseille,
  Genoa–Frosinone, Real Madrid–Rayo …), **0** aus Public-Kandidaten.
- ⭐ **Drei verschiedene Arten von „nichts", die als leere Liste alle gleich aussehen** — und
  drei völlig verschiedene Auskünfte:
  1. **nicht auflösbar** — für die Betfair-Aggregat-Schubladen gibt es gar keine Liste offener
     Zeilen (sie rechnen auf Eimern). Eine „0" wäre dort eine Aussage über den Spielplan, die
     wir nicht haben — dieselbe Lüge wie ein fehlender CLV, den man als „nein" liest.
  2. **leer, aber alles läuft schon** — heißt zu spät. Genau der Fall bei Public-Kandidaten:
     alle 4 Kandidaten sind angepfiffen. Sie werden **gezählt**, nicht bloß verworfen.
  3. **leer und nichts läuft** — heißt warten.
- ✅ **Der Poly-Anpfiff kommt aus `firstTs` + `htkAtEntry`.** Keine Schätzung: beide Werte stehen
  in der Zeile, ihre Summe IST der Anpfiff. Fehlt einer, gibt es keinen — und dann bleibt die
  Zeile drin (unbekannt ist kein „vorbei"), trägt aber auch kein Datum.
- ✅ **Der Poly-Spielname wird nachgeschlagen, nicht geraten.** Der Shortlist-Eintrag trägt nur
  „sea-fro-ven-2026-09-06-more-markets"; die beiden Seitennamen stehen im Markt selbst. Aus dem
  Schlüssel ließe sich kein Vereinsname rekonstruieren, nur einer erfinden.
- ✅ **Board:** unter den freigegebenen Schubladen steht ihre Spielliste (Spiel · Auswahl · Quote
  · Anpfiff), gedeckelt auf 10 mit gezähltem Rest.
- ✅ **Push:** eine ZWEITE Art Nachricht („🆕 NEUE SPIELE AUS FREIGEGEBENEN SCHUBLADEN") mit
  eigenem Zustand **je Play**. Gemeldet wird, was NEU dazugekommen ist — eine tägliche Liste mit
  31 Zeilen wäre nach drei Tagen Tapete. Abgelaufene Plays verschwinden still; ein „Spiel
  angepfiffen"-Push wäre Rauschen über etwas, das man ohnehin nicht mehr tun kann. Erstlauf
  meldet nichts (sonst fluteten 31 Picks den Channel), nicht auflösbare Schubladen bekommen
  weder Meldung noch Zustand. Die **CLV-Warnung reist mit**: sie gehört an jede Nachricht, die
  auf dieser Schublade beruht, nicht nur an die eine, in der sie freigegeben wurde.
- ✅ **Der Zustand hat jetzt zwei Ebenen** (`schubladen` + `plays`) in EINER Datei, damit ein
  Sendefehler nicht die eine Hälfte fortschreibt und die andere nicht. Die alte flache Form wird
  weiter gelesen — würde sie es nicht, gälte der nächste Lauf als Erstlauf, und der meldet
  nichts: genau die Freigabe, auf die seit Wochen gewartet wird, ginge still verloren.

**So sieht die Spiele-Nachricht aus:**

    🆕 NEUE SPIELE AUS FREIGEGEBENEN SCHUBLADEN
    Diese offenen Plays fallen unter einen Schnitt, dessen Rendite-Untergrenze
    über null liegt. Es sind Kandidaten aus einer belegten Schublade — keine
    Einzelprüfung.

    🎯 Liga · ABWÄGEN
    freigegeben · Rendite-Untergrenze +0.8%
    ⚠️ CLV spricht gegen diese Schublade — freigegeben auf die Rendite.

    ▸ Venezia v Fiorentina — Doppelte Chance — X2 @1.40
       🕐 Fr 11.09. 20:45
    ▸ Rennes v Marseille — Doppelte Chance — 1X @1.38
       🕐 Fr 11.09. 20:45
    …
    … und 19 weitere.

**Gegenbeweis** (sieben Regeln, jede provoziert): ausgeschlossene Picks zugelassen → Test fällt;
angepfiffene Spiele als Kandidaten → Test fällt; Betfair meldet leere Liste statt „nicht
auflösbar" → Test fällt; Poly-Name aus dem Schlüssel geraten → Test fällt; Erstlauf meldet alle
Plays → Test fällt; nicht auflösbare Schublade bekommt Zustand → Test fällt; „alle laufen schon"
wie „nichts dabei" gerendert → Frontend-Test fällt.

**Offen:** ob 31 Picks auf einmal zu viel für eine Nachricht sind — gedeckelt ist bei 12 je
Schublade, der Rest wird gezählt. Nach dem ersten echten Lauf sieht man, wie viele je Tag
wirklich neu dazukommen.

## 📣 08.09.2026 (spät) — die Freigabe geht in den Trades-Channel

Lucas: *„ja zum Testen mal in Trades-Channel."*

Der Weg dahin existierte schon: `freigabe_push.py` läuft seit dem 01.09. in `betfair.yml` und
meldet Zustands-WECHSEL (Freigabe rauf **und** Rücknahme, letztere zuerst — sie ist die
Nachricht, die Geld spart). Der Zustand kennt beide Schubladen bereits mit `false`, der nächste
CI-Lauf schickt sie also von selbst raus. Was nachgezogen werden musste, ist die **Ehrlichkeit
der Nachricht** unter dem gelockerten Tor:

- ✅ **Das CLV-Urteil steht im Push, nicht nur im Frontend.** Wer den Push liest, spielt danach —
  er darf die einzige Warnung, die es zu dieser Freigabe noch gibt, nicht nur auf dem Board
  finden. Drei Zeilen für drei Zustände, und „nicht erhoben" ist ausdrücklich **keine** Warnung:
  gegen eine Schublade ohne CLV-Erhebung ist nichts gemessen.
- ✅ **Die Kopfzeile sagt, WELCHE Untergrenze.** „Ab jetzt blind spielbar — die Untergrenze liegt
  über null" war eindeutig, solange beide stimmen mussten. Jetzt steht **Rendite**-Untergrenze da,
  sonst liest sich die Zeile als Zusicherung, die sie nicht mehr ist.
- ✅ **Prozente mit einer Nachkommastelle.** Die beiden Schubladen liegen bei +2,3 % und +0,8 %
  Untergrenze; auf ganze Prozent gerundet wurde daraus „+2%" und „+1%". Dieselbe Korrektur wie
  auf dem Board — genau in diesem Bereich entscheidet die Nachkommastelle, ob die Zahl etwas sagt.
- ✅ **Der `grund` steht nur noch an der Rücknahme.** Bei einer Freigabe sagte er inzwischen
  dasselbe wie die Zeilen darüber; zweimal dieselbe Warnung liest sich beim dritten Push wie
  Formelsprache. An der Rücknahme ist er die einzige Auskunft darüber, welche Bedingung kippte.

**So sieht die erste Nachricht aus** (aus den echten Zahlen gerendert, nicht gesendet):

    ✅ FREIGEGEBEN
    Ab jetzt blind spielbar — die Rendite-Untergrenze liegt über null.
    Was der CLV dazu sagt, steht je Schublade darunter.

    🔓 Public-Kandidaten
    📊 n=35 · ROI +20.8% · Untergrenze +2.3%
    📈 CLV -0.8pp  (UG -2.53)
    ❔ CLV gemessen, aber weder über noch unter null belegt.

    🔓 Liga · ABWÄGEN
    📊 n=91 · ROI +15.2% · Untergrenze +0.8%
    📈 CLV -1.5pp  (UG -2.01)
    ⚠️ CLV spricht dagegen — Obergrenze unter null. In unseren Daten liefen
       Schubladen mit negativem CLV im Schnitt −6,8 %. Freigegeben auf die
       Rendite, nicht auf eine gemessene Kante.

**Gegenbeweis:** CLV-Urteil aus der Nachricht entfernt → 3 Tests fallen; ganze Prozente →
Test fällt; „nicht erhoben" als ⚠️ gemeldet → Test fällt; `grund` auch an der Freigabe →
die Warnung steht zweimal, Test fällt.

**Offen:** ob eine Rücknahme dieser zwei Schubladen anders aussehen soll als eine reguläre —
sie wurden auf die Rendite allein freigegeben und können deshalb schneller kippen.

## 🔓 08.09.2026 (spät) — Freigabe locker, Stake in Ebene 3

Lucas, zwei Sätze: *„ja Freigabe locker"* und *„Stake in Ebene 3, aber genauso dargestellt wie
diese anderen Indikatoren mit dem Balken."*

### Das Freigabe-Tor

- ✅ **Das Tor ist ab jetzt die ROI-Untergrenze** (plus Mindestzahl und Lebendigkeit). Der CLV
  blockiert nicht mehr, er **beschreibt** — als `clvUrteil` auf jeder Zeile.
  `FREIGABE_CLV_BLOCKT=1` stellt das alte, strenge Tor ohne Code-Änderung wieder her (und ein
  Test beweist, dass der Schalter wirklich feuert — s. x-Norm-Badge).
- **Was das heute bewirkt:** 74 reife Schubladen, 2 mit belegter ROI-Untergrenze → freigegeben
  werden genau diese zwei: **Public-Kandidaten** (n=35, ROI-UG +2,3 %) und **Liga · ABWÄGEN**
  (n=91, ROI-UG +0,8 %). Vorher: null, seit Wochen jeden Tag.
- ⚠️ **Der Einwand steht auf der Zeile, nicht in einer Fußnote.** In unseren Daten ist der CLV
  monoton prädiktiv (n=2.651: CLV>0 → ROI +7,5 %, UG +1,9 %; CLV<0 → −6,8 %). Liga · ABWÄGEN ist
  genau der Fall, vor dem er warnt, und trägt deshalb „⚠ CLV dagegen".
- ⭐ **Und die Umstellung hat einen alten Etikettenfehler freigelegt.** Solange der CLV das TOR
  war, wurden zwei Fälle gleich behandelt: „nachweislich schlechter CLV" und „CLV um null, breit
  gestreut". Als Auskunft AUF der Zeile sind das nicht dieselben Dinge. „Negativ belegt" heißt
  ab jetzt, was es heißen muss: die **Obergrenze** liegt unter null (neu: `freigabe.obergrenze`,
  das Spiegelbild von `untergrenze`). Real: Public-Kandidaten hat CLV −0,80 pp mit Untergrenze
  −2,53 — nach der alten Lesart „negativ belegt". Die Obergrenze liegt bei **+0,93**: gegen
  diese Schublade ist gar nichts bewiesen. Vier Zustände statt zwei, und „nicht erhoben" ist
  eine Datenlücke, kein Messergebnis.

### Stake als vierter Indikator in Ebene 3

- ✅ **`spielzentrale.stake_je_polykey`** — derselbe Namens-Join, aber über den Poly-Marktschlüssel
  adressiert. Ebene 3 kennt keinen anderen Schlüssel; ein Namensvergleich im Renderer wäre
  Produzenten-Logik an der falschen Stelle (die Klasse, an der schon `elf_marker` und `polyKey`
  hingen). Gerechnet wird er einmal je Lauf in `killer.py`, das Ergebnis steht als `stakePoly`
  im Artefakt, und das Frontend **schlägt nur nach**.
- ✅ **Die Zelle ist eine normale `_mdSigCell`** — gleicher Balken wie Geld, Wallets, Liga-Track.
  Gleiche Seite grün, andere Seite als **Warnung** (Stake-Geld auf der Gegenseite ist kein
  Rückenwind), „Geld ohne vergleichbare Seite" wenn nur Satzsieger-Wetten dalagen. Und
  „nicht erhoben" ≠ „kein Highroller-Geld auf diesem Spiel".
- 🔴 **Zwei Fehler, die der Bau sichtbar gemacht hat — beide gemessen, beide behoben:**
  1. **`paart` ließ EINEN Namen den ganzen Join tragen.** Poly „Cincinnati Reds / Los Angeles
     Dodgers" wurde mit Stake „Boston Red Sox − Los Angeles Angels" gepaart: 0,67 für die STADT,
     0,00 für den anderen Namen, Summe über der Hürde. Jetzt muss jeder Name seinen eigenen
     Beleg mitbringen (`NAME_JE_MIN = 0.34`). Gegenprobe: der Fußball-Join behält alle 7 Treffer
     (schwächster Einzelname dort 0,50), der Poly-Join verliert genau die 3 falschen.
     ⚠️ Was das **nicht** löst: „Manchester United" gegen „Manchester City" bringt 0,50 auf
     beiden Seiten. Zwei Vereine derselben Stadt sind über Namen allein nicht trennbar — dagegen
     hilft nur ein Schlüssel. Steht als Kommentar im Code, damit niemand die Hürde für mehr hält.
  2. **`_STAKE_1X2` kannte nur Fußball.** Bei Tennis und E-Sport heißt derselbe Markt „Winner"
     oder „Match Winner - Twoway" — deshalb hatte **0 von 9** Treffern eine Stake-Seite, obwohl
     Geld dalag. Jetzt zählen die Ganzspiel-Sieger-Märkte aller Sportarten; „1st Set - Winner"
     und „Map 2 Winner" ausdrücklich **nicht** (sie tragen Geld, aber keine Spielseite — genau
     wie „Over 1.5").
  Ergebnis: 6 Treffer, alle korrekt, alle mit Seite. Heute u. a. Tiafoe–Michelsen ($7.427 auf
  Tiafoe), Shelton–Alcaraz, Gill–Ofner, ein CS2- und zwei UFC-Kämpfe.

**Gegenbeweis:** Hürde je Name entfernt → der MLB-Fehlpaarungs-Test fällt; Satzsieger als
Spielseite → Test fällt; Drei-Wege-Markt zugelassen → Test fällt; „nicht erhoben" wie „kein
Geld" gerendert → Frontend-Test fällt; andere Seite als gleiche gemeldet → Frontend-Test fällt;
`CLV_BLOCKT=True` → das alte Tor greift wieder.

**Offen:** ob die zwei freigegebenen Schubladen auch gepusht werden sollen — bisher ist
„freigegeben" eine Anzeige, kein Auslöser.

## 📊 08.09.2026 (nachts) — Ebene 1 ist eine Leistungstafel, keine Freigabe-Frage mehr

Lucas: *„mein Ansatz wäre: ich seh dort die Schubladen die Sinn machen, mit etwas Stats — ROI,
P/L, CLV. Und dann weiß ich für mich auch was ich besser folgen kann: eher Poly, eher Betfair,
eher Konsens, eher Cards."* Und direkt danach vier Nachfragen, die alle dasselbe Muster haben:
die Zahl war da, nur nie an der Stelle, wo sie die Frage beantwortet.

- ✅ **Je Strom eine Kachel** (ROI, P/L, Plays, CLV) aus `freigabe.stroeme()`. Gerechnet über
  **eine überschneidungsfreie Zerlegung** je Strom (cards→Verdikt, poly→Conviction,
  betfair→Markt) und mit deren Namen beschriftet: die Schubladen eines Stroms sind Schnitte
  durch dieselben Plays, aufsummiert ergäben sie 580 „Plays" aus 200. Ruhende Schubladen
  (die WM trägt 158 der 314 Card-Plays) bleiben draußen.
  Stand: **cards +9,5 % (n=156) · betfair −0,2 % (n=16.657) · poly −7,3 % (n=234)**.
- ✅ **Jede Kachel nennt ihre stärkste BELEGTE Schublade.** Lucas: *„bei Poly wäre gut wenn wir
  den Public-Kandidaten auch anzeigen, weil der gut ist — also nicht über alle Poly."* Genau der
  Fall: „Polymarket −7,3 %" ist wahr und verschweigt, dass **Public-Kandidaten** darin +20,8 %
  bei einer Untergrenze von +2,3 % tragen (n=35). Ist keine Schublade belegt, steht *das* da —
  nicht die beste unbelegte. Ein ROI von +77 % ohne Untergrenze über null ist kein Beleg.
- ✅ **P/L je Schublade.** Der ROI sagt, wie gut eine Schublade ist; das P/L, wie viel sie
  getragen hat. „Half Time" bringt +5,0 % aus 1.936 Plays (+96 Einheiten), eine 30er-Schublade
  mit +36 % ROI ganze +12. Aggregat-Schubladen ohne Einzelrenditen rechnen `roi × n` — dieselbe
  Zahl aus der anderen Richtung, statt `null`.
- ✅ **Die Betfair-Public-Pushes sind endlich eine Schublade.** Lucas: *„kann man bei Betfair
  anzeigen z. B. die Public-Push? die sind relativ solide."* Sie standen in **keiner**:
  `betfair_schubladen` liest `betfair_track_record.json`, der Public-Kanal führt sein eigenes
  Register. Der einzige Kanal, der von selbst sendet, war der einzige ohne Zeile.
  🔴 **Und der Eindruck kippt beim Nachrechnen:** 191 Pushes, **58,1 % Treffer** — bei der
  Ø-Quote 1,84 wären das +6,9 % ROI, gemessen sind es **−3,1 %** (UG −13,4 %). Die Treffer
  liegen bei kleineren Quoten als die Fehlschüsse. *Eine Trefferquote ohne die Quoten ist keine
  Zahl.* Der Satz steht jetzt als `grund` an der Zeile, nicht in einer Notiz.
  Zerlegung: frisches Signal n=167 ROI −0,3 % · Halbzeit n=24 ROI −22,8 %.
- ✅ **Liga-Tafel** (`freigabe.betfair_ligen`). Lucas: *„geht aus dem Tracking eventuell auch
  anzeigen welche Ligen gut performen? die Daten haben wir."* Sie lagen da und waren nie
  zusammengefasst: das Record führt `byMarket` und `byLeagueMarket`, aber **kein `byLeague`** —
  eine Liga stand in bis zu sieben Zeilen mit je n≈30 und in keiner mit ihrem Gesamtbild.
  178 Ligen mit n≥30, davon **7 mit Untergrenze über null**:
  Ukrainian Premier League +37,9 % (UG +13,5 %, n=80) · Bolivian Cup +37,5 % (UG +11,3 %) ·
  Romanian Liga II +24,0 % (UG +5,3 %, n=120) · Uruguayan Segunda · South African Premier ·
  Peruvian Primera · French Ligue 2. Das teure Ende steht daneben (Slovakian Cup −49,9 %) —
  ohne das liest sich die Tafel als Empfehlungsliste.
  ⚠️ Das ist eine **zweite** überschneidungsfreie Zerlegung derselben Plays (jeder Play hat eine
  Liga UND einen Markt). Sie steht deshalb als eigene Tabelle in `ligen`, nicht in `alle`, und
  darf nie zur Markt-Tafel addiert werden. Der Satz steht auch im Frontend.
- ✅ **Wallet-Tafel** (`freigabe.poly_wallets`). Lucas: *„wäre eventuell auch gut wenn man
  anzeigt z. B. top 10 Poly Wallets — dann weiß ich, die Pushs die ich krieg von denen sind
  gut."* `sharp_gate` entschied das je Push seit jeher still; **welche** Wallets das sind, stand
  nirgends. Filter ist `sharp_gate.sharp_grade` — dieselbe Definition, die auch sendet, keine
  zweite Liste mit eigener Regel. 52 Wallets über der Schwelle, sortiert nach der
  Wilson-**Untergrenze** der Trefferquote. Die Lebensbilanz einer Wallet steht bewusst **nicht**
  als Rang: sie enthält Wahlen und Krypto und sagt über Tennis nichts (s. `sharp_gate.py`).
- ✅ **Reserveligen in jeder Sprache** (CI-Wachhund, `campeonato-de-reserva-de-primera-division-c`).
  Die Regel las nur die englische Schreibweise `reserve`; in Südamerika heißt dieselbe Sache
  `reserva`, in Italien `riserve`. Ein Muster, das eine Sprache kennt, ist kein Muster, sondern
  ein Einzelfall mit Platzhalter. Gegenprobe an den 171 Fußball-Slugs: beantwortet genau den
  einen offenen, stuft keinen bereits eingestuften um.

**Gegenbeweis** (jede Regel provoziert): Sortierung nach dem Punktschätzer statt der Untergrenze
→ Liga- und Wallet-Test fallen; `belegt = ROI positiv` → Test fällt (+35,5 % Schnitt bei −9,4 %
Untergrenze); Public-Zeile mit `art="markt"` → doppelte Zählung fällt auf; Wallet-Gate umgangen
→ der bestätigte Verlierer (n=186, −$7,78 Mio) steht wieder in der Liste; Kachel-Beste ohne
n-Boden und ohne Untergrenze → 2 Frontend-Tests fallen.

**Offen:** ob Ebene 1 die Ligen und Wallets ausgeklappt oder eingeklappt zeigen soll — beide
stehen als `<details>`, damit die Ebene nicht 180 Zeilen lang wird.

## 🔁 08.09.2026 (abends) — Ebene 0 wieder raus, Ebene 2 kann jetzt, was sie konnte

Lucas nach einem Tag mit der Spielzentrale: *„Ebene 0 hast du heute dazugebaut, da seh ich aber
eben nicht den Mehrwert zu Ebene 2, außer dass bei paar Spielen Stake dabei steht."*

Nachgemessen hatte er recht: **24 von 25** Zeilen der Zentrale standen ohnehin in
`killer.alleBewertet`. Dieselbe Frage, zweimal gestellt, mit zwei verschiedenen Maßstäben.

Und der Grund, warum Ebene 2 trotzdem immer leer wirkte, war ein anderer als gedacht:
**sie bewertet 145 Spiele und zeigte davon 6** — nur die, bei denen zusätzlich Geld in Bewegung
war. Die anderen 139 standen in der Datei und wurden vom Frontend **nie gelesen** (grep über alle
`.js`: null Treffer auf `alleBewertet`). Die Skala, die Lucas als „stimmiger eingestellt" empfand,
war da; sichtbar war sie nicht.

- ✅ **Stake ist das vierte Buch.** Ebene 2 kannte Betfair, Polymarket, Pinnacle. Der
  Stake-Highroller ist die einzige der vier Quellen, die kein Buchmacher-Preis ist, sondern
  fremdes Geld auf einer Seite. Der Namens-Join (inkl. `gleiche_elf`) kommt aus `spielzentrale`
  und wird benutzt, nicht nachgebaut. Nenner wächst auf 13, wo Stake erhoben ist.
- ✅ **`teile` wandert in die Datei.** `alleBewertet` trug `punkte`/`moeglich` und sonst nichts —
  deshalb konnte die Tafel gar nicht gebaut werden, sie hätte Zahlen ohne Begründung gezeigt.
- ✅ **Die Tafel steht immer**, auch wenn das Bewegungs-Tor leer ist. Sie zeigt die Spitze
  (ab 6 Punkten, höchstens 12 Zeilen), darunter die gezählte Restmenge und ein Register mit allen.
- ✅ **„—" heißt nicht erhoben, „0" heißt gefragt und stimmt nicht zu.** Ohne den Unterschied
  sehen die beiden gleich aus — und genau dafür wird der Nenner mitgeschrieben.
- ✅ **Ebene 0 ist raus**, `spielzentrale.json`/`_basis.json` werden nicht mehr erzeugt, der
  Workflow-Schritt ist weg. `spielzentrale.py` bleibt als Stake-Join-Helfer (der Teil, der stimmt).
- ✅ Guard `check_buecher_punktestand` löst `check_spielzentrale_urteil` ab: Punkte = Summe der
  Teile, Nenner = Summe der Nenner, ein nicht erhobenes Buch steht nicht im Nenner, Tiefe zählt
  nur bei Zustimmung, jede Zeile trägt ihre Aufschlüsselung.

Ergebnis an den echten Daten: 139 bewertete Spiele vor Anpfiff, **12 ab 6 Punkten**. Oben
AEK Athens, Real Madrid und Porto mit **10/13** — alle vier Bücher auf derselben Seite. Lille
steht bei 8/13 mit **Betfair 0** (kein konzentriertes Geld), aber Poly, Pinnacle und Stake
zustimmend — eine Zeile, die vorher nirgends sichtbar war.

## 📉 08.09.2026 — CLV: die Messung gegen Lucas' Vermutung, das Tor trotzdem in seinem Sinn

Lucas: *„Ich bin kein Fan von CLV … bei Cards und beim Paper Trading auf Poly ist der CLV negativ,
bei beiden aber Profit da und der ROI positiv."*

**Die Vermutung hält der Nachrechnung nicht stand.** Betfair-Track, Match Odds, n=2.651, nach CLV
gegen den Betfair-Close geschichtet:

| CLV | n | Treffer | ROI |
|---|---|---|---|
| < −5 pp | 173 | 51,4 % | −8,6 % |
| −5…−1 | 567 | 48,0 % | −5,6 % |
| −1…+1 | 1.080 | 43,2 % | −1,7 % |
| +1…+5 | 608 | 53,3 % | +4,8 % |
| > +5 pp | 223 | 61,9 % | **+27,0 %** (UG +13,6 %) |

Grob: CLV>0 → **ROI +7,5 % mit Untergrenze +1,9 %** — die einzige Aggregation im Repo mit einer
Untergrenze über null. CLV<0 → −6,8 %. Monoton über fünf Bänder.

Und die beiden Belege: **Cards** n=1.184 abgerechnet → **ROI −11,4 %** (UG −16,1 %), CLV −1,8 pp —
beide negativ, kein Widerspruch. **Poly-Paper** ganzes Buch n=638 → **ROI −3,6 %**, CLV −0,50.
Positiv ist nur die Teilmenge `public` (n=173, +6,3 %), deren Untergrenze bei −2,8 % liegt.
Nebenbefund aus den Cards: **50,2 % Treffer bei Ø 1,89** — 2,6 Punkte unter dem Break-even von
52,8 %, und das sind exakt die −11,4 %.

**Beim Tor hat er trotzdem recht, aus zwei anderen Gründen:**

- **62 von 73 reifen Schubladen tragen gar keinen CLV-Wert.** Für die ist die Bedingung nicht
  *nicht erfüllt*, sondern *unbekannt* — und wird wie ein Nein behandelt.
- Liegt die **Rendite-Untergrenze über null, ist der Profit belegt.** Ein Nebenindikator kann das
  nicht widerlegen. Heute betrifft das zwei Schubladen (Public-Kandidaten, Liga·ABWÄGEN), beide
  scheitern ausschließlich an CLV.

⏳ Vorschlag steht, noch nicht gebaut: **Rendite-Untergrenze ist das Tor, CLV beschreibt und
blockiert nicht mehr.** Fehlender CLV heißt „unbekannt", nicht „nein".

## ✅ 08.09.2026 — der CI-Wachhund hat zugeschlagen (Liga-Ebenen)

`test_alle_ligen_im_echten_ledger_haben_eine_ebene` fiel im CI mit zwei Slugs:
**`veikkausliiga`** und **`uefa-youth-league`**. Genau dafür ist der Guard gebaut — beide Ligen
sind heute neu im Ledger aufgetaucht (das Youth-League-Spiel Porto U19 v Man City U19 und die
finnische Runde, beide aus demselben Feed, über den wir vorher gesprochen haben).

- ✅ **`veikkausliiga` → Ebene 1.** Ein reines Tabellen-Loch: `ykkonen` (2) und `kolmonen` (3)
  standen seit dem ersten Tag drin, die oberste Klasse desselben Landes fehlte. Eine Tabelle mit
  einem Loch in der Mitte fällt ohne Wachhund nie auf.
- ✅ **`uefa-youth-league` → `jugend`**, und zwar über das Muster, nicht von Hand. Die Regel las
  bisher nur die **ersten drei Zeichen** (`s[:3] in ("u17","u19",…)`) und fing damit „u19-…",
  aber keinen Wettbewerb, der seine Jugend ausschreibt. Jetzt `u17`–`u23` an beliebiger Stelle
  plus `youth|jugend|junior|academy|primavera`.

  Man könnte die UEFA Youth League auch „kontinental" nennen — nicht falsch, aber die schwächere
  Auskunft: für die Frage, die diese Tabelle beantwortet (wie verhält sich ein großer Einsatz),
  verhält sich ein U19-Spiel wie Nachwuchs und nicht wie ein Champions-League-Abend. Dieselbe
  Unterscheidung wie bei `elf_marker` in `betfair_consensus` vom selben Tag.

- ✅ Gegenprobe an allen **170 Fußball-Slugs des echten Ledgers**: die breitere Regel stuft
  **keinen** bereits eingestuften Slug um — sie beantwortet genau den einen, der vorher `None` war.
- ✅ Guard gegen die Wiederholung: fünf Tests, die mit dem alten Stand fallen (geprüft).

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
