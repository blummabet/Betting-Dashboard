# CocoBet Backlog (Liga + WM)

Stand 10.09.2026 (oberster Block); Liga/WM-Teil darunter Stand 26.06.2026. Lebendige Liste aller offenen Punkte — Liga UND noch nicht umgesetzte WM-Sachen —
damit wir alles abarbeiten können. ✅ = erledigt (Referenz), ⏳ = offen, 🔒 = blockiert.

## 🔬 11.09.2026 (spät) — der eigentliche Logikfehler: wir haben gar nicht hingeschaut

Lucas: *„wir müssen da an Logik Fehler haben, weil ich will ja herausfinden, Spiele bei Poly, die
kleine Märkte sind und wo ein eventuelles Sharp Wallet höher sitzt … wenn der auf ein Tennis-Match
viertausend setzt und es sind maximal fünftausend drin, dann könnte das schon sein, dass derjenige
sich sehr sicher ist, vor allem weil's ein kleiner Markt ist. … Dann müssten's hohe Vielspieler am
Tag geben, vor allem E-Sport und Tennis."*

Er hatte recht, und der Fehler lag **nicht** bei den Schwellen des Bands.

### Der Befund

`poly_money_broad.py`, Zeile ~1252: `if vol < min_vol: continue` — mit `MIN_VOL_USD = 7500`.
Dieser Boden entscheidet nicht nur, was in die Close-Datei kommt, sondern **welcher Markt
überhaupt einen Holder-Call bekommt**, also wo wir erfahren, *wer wie viel hält*. Unter $7.500
wurde nie gefragt.

Gemessen: **der kleinste Markt mit Wal-Daten in der gesamten Close-Datei hatte $7.504, und in
2.928 Zeilen lag keine einzige darunter.** Lucas' Fall — $4.000 in einem $5.000-Markt — konnte das
Band nicht finden, weil der Sammler dort nie hinschaut. Ein Band, das kleine Märkte finden soll,
suchte in einem Bestand, aus dem kleine Märkte per Konstruktion entfernt waren.

Und es war **genau verkehrt herum**: die höchsten Anteile sitzen in den kleinsten Märkten. In der
`upcoming`-Datei (die kleine Märkte sieht, aber nur 30 von 566 mit Wal-Daten, weil auch dort das
Budget nach Volumen vergeben wird) standen oben:

| Markt | Volumen | größter Wal | Anteil |
|---|---|---|---|
| den-kob-hor (Fußball) | $4.107 | $2.249 | **55 %** |
| elc-whu-wre-total-corners | $4.671 | $2.360 | **51 %** |
| atp-zverev-khachan | $585.805 | $280.666 | 48 % |

Das Budget war übrigens **nicht** der Engpass — `vorStats` meldet 22 von 22 Calls genutzt, nur 3
über Budget. Es war der Volumenboden.

**Lucas' Tipp stimmte auch:** von den 5 Positionen, die das Band aktuell findet, sind **4 Tennis
und 1 E-Sport**.

### Was gebaut wurde — und was ausdrücklich nicht

⚠️ **`MIN_VOL_USD` wurde NICHT gesenkt.** Es speist Close-Freeze, Historie,
Trefferquoten-Auswertung und das bestehende Whale-Buch. Ein niedrigerer Boden hätte jede dieser
Zahlen umgedeutet und alte gegen neue Messungen unvergleichbar gemacht — dieselbe Fehlerklasse
wie das Zusammenwerfen von Liga- und MLS-Conviction am 10.09., nur größer.

Stattdessen eine **eigene Spur**, dieselbe Bauart wie die „vor"-Spur vom 01.09.:

```
KLEIN_MIN_VOL            1500     eigener Boden
MAX_HOLDER_CALLS_KLEIN     18     eigenes Budget (kann den Close-Freeze nicht aushungern)
poly_money_klein.json             eigene Datei — liest NUR poly_whale_watch.py
```

Im Band werden beide Spuren zu **einer Marktsicht** zusammengeführt (bei Kollision gewinnt die
Close-Zeile — sie ist die belastbarere). Die Wallet-Bewertung kommt **immer** aus `scores` des
Haupt-Tracks; eine Kleinmarkt-Zeile bringt keine eigene Reputation mit und darf auch keine
vortäuschen.

Was die Kleinmarkt-Spur **nicht** weiß und worüber sie nicht lügt: den **Einstiegspreis** des
Wals. Wir wissen nur, dass die Wallet jetzt da ist. Die Karte zeigt bei diesen Zeilen deshalb
keinen „Einstieg @x" — eine Zahl, die wie ein Einstieg aussieht und der Jetzt-Preis ist, wäre an
genau der Stelle erfunden, an der Lucas die Bewegung abliest. Jede Zeile trägt `quelle`, damit
sich die beiden Spuren später trennen lassen.

### Der Gegenbeweis, den nichts gefangen hat

Von zwölf provozierten Regelbrüchen liefen elf rot. Einer lief **grün durch die gesamte Suite**:

```python
fetch_markets.klein = klein
markets.extend(klein.values())      # ← niemand merkt es
```

Das wäre der teuerste Fehler der ganzen Änderung gewesen. `markets` speist
`update_wallet_track` — und `scores` ist das **Reputations-Buch über 3.650 Wallets**, CLV und
Trefferquote, gemessen ausschließlich in Märkten ab $7.500. Märkte ab $1.500 hätten rückwirkend
die Bedeutung jeder dieser Zahlen geändert, **und zwar unbemerkt: die Datei sähe danach genauso
aus.**

Behoben nicht durch eine Konvention („bitte nur `pre` übergeben"), sondern durch eine Regel beim
**Verbraucher**: die Zeilen der Spur tragen `spur: "klein"`, und `update_wallet_track` weist sie
ab. Close-Freeze und Historie filtern ohnehin über den Volumenboden. Ein Test prüft alle drei
zugleich — einzeln geprüft ließe jeder von ihnen die Lücke offen.

### Lucas' Fall, wörtlich nachgebaut

$4.000 auf ein Tennis-Match, maximal $5.000 im Markt, Anpfiff in 40 Minuten, Wallet 53/63:

```
🎯 MARKT-DOMINANZ · 80 % des Marktes
████████░░  80 %
💰 $4K auf Spieler A  ·  📦 Markt gesamt $5K
🕒 Anpfiff 17:05 — in 40 Min
⏱️ gemessen 40 Min vor Anpfiff — Markt steht
📈 @1.61
Wallet 0xabc · ✅ bewiesene Wallet (53/63 richtig, 84% · +0.7pp CLV)
```

Feuert. Vorher war diese Karte unmöglich — nicht wegen einer Schwelle, sondern weil die Daten
dafür nie geholt wurden.

### Der Quotenboden bleibt bei 1,35 — Lucas' Entscheidung, mit offener Rechnung

Die Daten sprechen dagegen: Dominanz in einem kleinen Markt **drückt den Preis**, je sicherer sich
einer ist, desto kürzer die Quote. Gemessen: 5 Kandidaten → 3 bei ≥1,20 → **1** bei ≥1,35. Der
Boden schneidet also die stärksten Ausprägungen genau des Effekts weg, um den es geht.

Lucas hat sich trotzdem für 1,35 entschieden, und das ist vertretbar: es ist die einzige
Preisecke, in der das Projekt überhaupt Vergleichszahlen hat (Public-Whale-Buch, 27 abgerechnete
Pushs, keine Zeile darunter), und bei @1,14 braucht man 88 % Trefferquote zum Nullpunkt.
Festgehalten, damit die Rechnung offen liegt, falls das Band in vier Wochen zu dünn besetzt ist:
**der Quotenboden ist der bindende Schnitt, nicht die Datenlage.** Die Kleinmarkt-Spur hebt die
Grundgesamtheit (124 kleine Märkte im Fenster statt 0) — ob das reicht, sagt das Buch.

## 🎯 11.09.2026 (abends) — was die erste echte Dominanz-Karte aufgedeckt hat

Lucas hat die erste gepushte Karte zurückgeschickt:

```
🎯 MARKT-DOMINANZ · 40 % des Marktes
💰 $5K auf Jaume Munar  ·  📦 Markt gesamt $12.4K
Einstieg @1.21
```

Drei Befunde daraus — und **einer davon war nur an einer echten Karte zu sehen**, nicht an
Testdaten.

### 1. Der Quotenboden fehlte, und zwar systematisch

Lucas: *„bitte mindest odd auch einbauen, ab 1,35 erst wieder."*

Nachgemessen: von den **fünf** Positionen, die das Band an dem Tag gefunden hätte, lagen **vier
unter 1,35** — @1,14 · @1,18 · @1,21 · @1,25. Nur eine (@1,75) darüber.

Das ist keine Pechsträhne, das ist **Bauart**. Die $25.000-Schwelle des Whale-Pushs landet in
großen, ausgeglichenen Märkten; die $3.000-Schwelle dieses Bands landet zwangsläufig in kleinen
Favoritenmärkten — nur dort kann ein einzelner Einsatz überhaupt 40 % erreichen. Das Band hätte
also mehrheitlich in einer Preisecke gemessen, in der das Projekt noch nie etwas gemessen hat:
**im Public-Whale-Buch steht über 27 abgerechnete Pushs mit Preis keine einzige Zeile unter
1,35.** Und bei @1,14 braucht man 88 % Trefferquote zum Nullpunkt — da ist keine Beobachtung
mehr drin, nur noch Marge.

`DOM_MIN_QUOTE = 1.35`, dieselbe Zahl, die im Projekt schon gilt (pick-engine, stake-radar).
Gerechnet wird auf dem **Push-Preis**, nicht auf dem Einstieg des Wals: sonst könnte eine Zeile
mit @1,50 ins Buch gehen und mit @1,15 abgerechnet werden. Die Karte zeigt jetzt beide Preise,
wenn sie sich unterscheiden.

### 2. 🔴 Die Karte ging 26 Minuten NACH Anpfiff raus

Das stand nicht in Lucas' Nachricht — es fiel beim Nachbauen der Karte auf. `htk` ist der
**Mess**zeitpunkt der Close-Zeile, nicht die Gegenwart; zwischen Messung und Versand liegt der
Runner. Eine Zeile, die 20 Minuten vor Anpfiff gemessen wurde, wurde 26 Minuten danach gepusht.

Für die **Messung** ist ein Markt nach Anpfiff maximal reif — für den **Push** ist er wertlos:
Lucas wollte „aktiv mitbeobachten", und die genannte Quote wäre nicht mehr zu bekommen. Es
entscheidet jetzt die echte Uhr gegen den Anpfiff, nicht der Messzeitpunkt.

Fehlerklasse: **zwei Zeitpunkte mit demselben Namen.** Genau derselbe Fehler wie „Min" im Stake
Radar (Spielminute vs. Wanduhr) und wie `n_observations` vs. Glättungs-n bei den Signalgewichten.

### 3. „Sollt ich sehen wann das Spiel ist / seh ich ned"

Die Karte nannte Anteil, Betrag, Wallet, Markt — aber nicht, **wann**. Der Markt speichert keinen
Anpfiff, sondern `capturedAt + hoursToKickoff`; die Summe steht jetzt als `🕒 Anpfiff 21:30 — in
1 h 05` auf der Karte (Wiener Zeit). Ist er nicht bestimmbar, wird **nicht** gepusht — dieselbe
Regel wie bei fehlendem Volumen: in diesem Band ist der Zeitpunkt keine Zusatzinfo, sondern die
Voraussetzung.

### Und die Antwort auf „hast du Idee wie wir das Zeitproblem lösen?"

Das Reifefenster löste das **Mess**problem und schuf ein **Anzeige**problem: eine Position von
2,8 h vor Anpfiff stand erst 1,8 h später im Kanal.

Beides zugleich geht, wenn man den Anteil nicht schätzt, sondern **die Schätzung gegen sich
selbst laufen lässt**: `anteil × füllgrad(htk)` ist der Anteil, der übrig bliebe, wenn sich der
Markt bis zum Anpfiff noch wie üblich auffüllt.

| Anteil jetzt | bei 2,8 h (Füllgrad 0,54) | Folge |
|---|---|---|
| 80 % | → 43 % | **sofort raus** — trägt auch nach Nachfüllung |
| 50 % | → 27 % | wartet auf den echten Nenner |

Deutliche Dominanz kommt also sofort und mit voller Vorlaufzeit; knappe wartet. **Verworfen wird
nichts** — die wartende Zeile kommt einen Lauf später auf dem normalen Weg.

⚠️ Ehrlich bleiben, was das ist: der Füllgrad ist ein **Median**. In der Hälfte der Fälle füllt
sich der Markt stärker und der Anteil fällt doch unter die Schwelle. Deshalb steht es auf der
Karte (*„Markt füllt sich noch (~54 % voll), der Anteil kann noch fallen"*) und im Buch
(`fruehFreigabe`, `fuellgrad`, `anteilKons`). Ungetrennt ließe sich später nicht sagen, ob eine
Trefferquote von den früh oder den reif gemeldeten Zeilen kommt.

### Was das Band jetzt kostet — der Trichter am 11.09.

| Stufe | fällt hier raus |
|---|---|
| 421 offene Positionen, unter $3.000 | 381 |
| kein oder zu kleiner Markt | 13 |
| Anteil < 40 % | 50 |
| Zeit (unreif **oder** schon angepfiffen) | 3 |
| **Quote < 1,35** | **2** |
| durch | 0 |

Das ist sehr eng, und der **Quotenboden ist der bindende Schnitt**. Bei dieser Rate braucht das
Buch Monate für eine Aussage. Das ist Lucas' Abwägung, nicht meine — er hat 1,35 ausdrücklich
gesetzt, und die Alternative wäre, in einer Preisecke zu messen, in der ohnehin nichts zu holen
ist. Festgehalten, damit in vier Wochen nicht „das Band feuert ja nie" als Überraschung kommt.

### Gegenbeweise

| entfernte Regel | Test bricht |
|---|---|
| Quotenboden ganz weg | ✅ |
| Quote auf dem Einstieg statt dem Push-Preis | ✅ |
| Quotenboden auf 1,0 gesenkt | ✅ |
| fehlender Preis gilt als in Ordnung | ✅ |
| Anpfiff-Sperre weg | ✅ |
| unbekannter Anpfiff lässt durch | ✅ |
| Anpfiff aus `htk` statt `capturedAt + htk` | ✅ |
| frühe Freigabe ohne Füllgrad-Abschlag | ✅ |
| Füllgrad auf 1,0 gesetzt | ✅ |
| Karte verschweigt die frühe Freigabe | ✅ |
| Anpfiffzeile weg | ✅ |

## 📻 11.09.2026 — Stake Radar: drei Anzeigefehler und eine Idee, die nicht trägt

Lucas, vier Fragen an einem Stück. Drei davon waren Fragen an eine **Anzeige** — und eine
Anzeige, bei der der Leser raten muss, ist der Befund.

### 1. „Was heisst der rote Punkt und die min daneben? Ist das vergangen?"

Da stand `🔴 380. Min`. Zwei Fehler in einer Zeile:

- **„380. Min" liest sich als Spielminute.** Gemessen ist die **Wanduhr seit Anpfiff** — die
  Halbzeitpause zählt mit, und bei Cricket oder Tennis hat „Minute" gar keine Bedeutung. Genau
  diese Verwechslung war am **07.09. schon einmal aufgefallen** und in den Auswertungs-Schubladen
  korrigiert worden. Hier nicht — obwohl es dieselbe Zahl aus derselben Quelle ist. Eine
  Korrektur an der Instanz statt an der Klasse.
- **Der rote Punkt hiess „läuft".** Ein Spiel, das vor sechs Stunden angepfiffen wurde, läuft
  nicht mehr. Lucas' Frage *„ist das vergangen?"* ist nicht das Missverständnis, sie ist das
  Ergebnis des Entwurfs.

Jetzt: `⏱ in 1 h 35 min` · `🔴 läuft · seit 1 h 03 min` · `⏹ angepfiffen vor 6 h 20 min` (grau).
Der Feed meldet **kein Spielende** (`phase` kennt nur `vor`/`live`, `spielminute` läuft bis 3012
weiter), deshalb steht dort ausdrücklich **nicht** „beendet" — nur nicht mehr „läuft".

> 🔴 **Beim Schreiben des Tests dazu ein echter Fehler gefunden:** `new Date(null)` ist nicht
> Invalid Date, sondern der **01.01.1970**. Eine Zeile ohne Anpfiff bestand deshalb jede
> null-Prüfung und kam als *„angepfiffen vor 496.981 h"* heraus — vorher als
> *„🔴 29818860. Min"*, also derselbe Fehler, nur besser getarnt. Fehlerklasse: fehlende
> Information rendert als harmloser Default — und Epoch 0 ist alles andere als harmlos, weil es
> ein **gültiges** Datum ist. `_srMs` gibt jetzt für `null`/`''` auch `null`.

### 2. „Da is vieles alt" — und der Regler stand falsch herum

Gemessen am Stand vom 11.09.: von **47 Gruppen auf dem Board lagen 37 über 30 Minuten im Spiel,
17 davon über sechs Stunden.** Nur **10** waren überhaupt noch nicht angepfiffen.

Der Filter dafür existierte seit Tag eins (`SR_NUR_SPIELBAR`) — er stand auf `false`. Ein Board,
dessen Standardansicht zu **79 % aus gelaufenen Spielen** besteht, ist kein Radar, sondern ein
Archiv. Steht jetzt auf `true`; der Regler bleibt, er geht jederzeit wieder auf.

Das ist nicht nur Kosmetik: die Standardansicht versteckte damit ausgerechnet die **einzige
Schublade, die im eigenen Buch etwas trägt** (siehe 3.).

**Geld und Anteil** stehen jetzt je Seite auf der Karte. ⚠️ Aber **nicht als Marktanteil** —
Lucas hatte nach „% vom Markt" gefragt, und den gibt es bei Stake nicht: der Feed ist eine Liste
einzelner Highroller-Wetten, kein Orderbuch. Was dort steht, ist der Anteil am **beobachteten
Großgeld** dieses Spiels, also an einer Stichprobe mit Auswahl (nur über der Schwelle, nur
öffentliche Konten). Die Spalte heißt deshalb, was sie misst; ein Prozentwert, der „Marktanteil"
suggeriert, wäre eine erfundene Zahl.

### 3. „Sagen uns die anderen Auswertungen etwas aus?" — ja, und zwar etwas Unbequemes

Über 24.679 gewertete Beine tragen **2 von 18 Schubladen** ein Urteil (einseitige 95 %-Untergrenze
der Rendite je Bein über null):

| Schublade | n (Beine) | Rendite/Bein | Untergrenze | |
|---|---|---|---|---|
| **vor Anpfiff** | 11.632 | **+2,6 %** | **+1,5 %** | ✅ trägt |
| **Quote ab 3,50** | 7.101 | **+3,4 %** | **+1,5 %** | ✅ trägt |
| gesamt | 24.679 | −1,1 % | −1,9 % | — |
| live | 13.047 | −4,3 % | −5,7 % | — |
| live, ≤ 30 min | 3.792 | −2,9 % | −5,3 % | — |
| live, > 60 min | 6.679 | −6,5 % | −8,4 % | — |
| ab $10k Einsatz | 2.612 | −1,0 % | −4,0 % | — |
| über Liga-Norm | 198 | −0,2 % | −12,2 % | — |
| Ebene 2/3, ab 3× Norm | 81 | −7,4 % | −22,5 % | — |

Drei Dinge stehen da, die dem Tab widersprechen, in dem sie stehen:

- **Größe allein sagt nichts.** `ab $10k` liegt bei −1,0 %. Das war die Vorregistrierung
  („Trägt Größe allein etwas? Die Vorlage behauptet ja, ohne Beleg") — die Antwort ist nein.
- **„Auffällig ist relativ" trägt auch nicht.** `über Liga-Norm`: −0,2 % bei n=198. Das ist die
  Kernthese des Tabs „Über der Norm", und sie ist unbelegt.
- **Die Live-Hypothese ist gefallen.** Vorregistriert war *„wenn Live etwas taugt, dann früh"* —
  früh liegt bei −2,9 %, spät bei −6,5 %. Früh ist nur **weniger schlecht**, nicht gut. Und der
  Feed besteht zu 83 % aus Live.

Die Bilanz-Ansicht sagt das jetzt **oben in einem Satz**, gezählt aus dem Artefakt statt
hineingeschrieben: eine feste Zahl im Text wäre in einer Woche falsch, und ausgerechnet die
Zeile, die das Urteil zusammenfasst, darf nicht als erste veralten. Wichtig in der Formulierung:
die übrigen sind **nicht widerlegt, sondern unbelegt** — ihre Untergrenze liegt unter null, das
ist kein Gegenbeweis.

### 4. „Sollten wirs bei Stake auch so machen wie bei Poly?" — nein, und zwar aus zwei Gründen

**Der strukturelle Grund: es gibt keinen Nenner.** Die Poly-Dominanz misst Einsatz gegen
*Marktvolumen*. Stake liefert kein Marktvolumen — kein `totalUsd`, keine Orderbuch-Tiefe,
nichts. Übertragbar wäre nur „Anteil am beobachteten Großgeld", und das ist ein Anteil an
**unserer Stichprobe**, nicht am Markt. Zwei verschiedene Dinge mit demselben Prozentzeichen.

**Der gemessene Grund: selbst dieser Ersatz trägt nichts.** Über 1.536 abgerechnete Wetten,
geschnitten nach Anteil am beobachteten Großgeld ihres Spiels:

| Anteil | n | Treffer | Wilson-UG | ROI |
|---|---|---|---|---|
| ≥ 60 % | 61 | 70,5 % | 60,2 % | +7,7 % |
| 40 – 60 % | 78 | 71,8 % | 62,8 % | +10,3 % |
| 20 – 40 % | 141 | 73,0 % | 66,5 % | +2,1 % |
| < 20 % | 948 | 69,8 % | 67,3 % | +6,9 % |

Keine Richtung. Die Trefferquoten liegen zwischen 69,8 % und 73,0 %, die Konfidenzbänder
überlappen vollständig, und der ROI springt ohne Ordnung (7,7 / 10,3 / 2,1 / 6,9). Bei Poly war
die Anteils-Richtung wenigstens sichtbar (15–30 %: 81,8 %) — hier ist sie es nicht.

**Nicht gebaut.** Ein Band, dessen Nenner eine andere Bedeutung hat als das Vorbild und dessen
Vorab-Messung nichts zeigt, wäre eine Fläche, die aussieht wie das Poly-Band und nicht dasselbe
misst. Das ist teurer als gar nichts.

## 🎯 11.09.2026 — Markt-Dominanz: ein eigenes Beobachtungsband im Trades-Kanal

Lucas: *„wenn irgendwelche Wallets vielleicht auch nur so fünftausend, aber das sind nachher dann
bei dem Turnier vielleicht achtzig Prozent. Mich würd nur interessieren, ob das vielleicht Treffer
sind viele."* Und zum Aufbau: *„mach's bitte vom Template her so, dass ich's wirklich gleich auch
seh, weil das geht sonst unter in den Nachrichten."*

### Was gemessen war, bevor gebaut wurde

Über die bisherigen Public-Whale-Pushs, nach Marktanteil geschnitten:

| Anteil am Markt | n | Treffer |
|---|---|---|
| < 15 % | 21 | 57,1 % |
| 15 – 30 % | 11 | **81,8 %** |
| > 30 % | 4 | 75,0 % |

Die Richtung ist da, aber **n = 11 und n = 4 sind kein Beleg** — das ist der Grund, warum das Band
*Beobachtungsband* heißt und nicht Signal. Entscheidend ist die zweite Zahl: **Lucas' eigentlicher
Fall kam in 36 Pushs 0 Mal vor.** Pushs in Märkten ≤ $60.000: **0 von 36.** Die $25.000-Schwelle
des Whale-Pushs und ein hoher Anteil schließen sich fast aus — wer $25.000 setzt, tut das im großen
Markt. Deshalb ein **eigenes Band mit eigenen Schwellen**, kein Umbau am Whale-Push: der bestehende
Kanal hätte diesen Fall nie gezeigt, egal wie man an ihm dreht.

### Die Schwellen (Lucas: „ab dreitausend Dollar, ja, klingt okay und mindestens Anteil größer vierzig Prozent")

```
DOM_MIN_USD    = 3000    Einsatz der Wallet
DOM_MIN_SHARE  = 0.40    Anteil am Marktvolumen
DOM_MIN_MARKET = 6000    Marktboden  ← steht NICHT in Lucas' Ansage, s. u.
DOM_MAX_ALERTS = 5
```

Der **Marktboden** ist meine Ergänzung, und zwar wegen Lucas' eigener Einschränkung: *„natürlich
jetzt nicht auf der Spielwohnung dreihundert Euro und ich hab hundert Prozent, das will ich nicht
finden."* Der Boden steht am **Markt**, nicht am Einsatz, weil genau dort der Unsinn entsteht.

> 🔴 **Korrektur am selben Tag: der Boden stand auf $6.000 und konnte nie greifen.** Ich habe ihn
> oben als die Verteidigung gegen „100 % von $4.000" beschrieben — er hat nie eine einzige Zeile
> abgelehnt. `poly_money_broad.py` nimmt mit `MIN_VOL_USD = 7500` ohnehin keinen kleineren Markt in
> die Close-Datei auf: **0 von 2.928 Zeilen liegen unter $6.000, der kleinste Markt überhaupt hat
> $7.504.** Der Boden stand im Code, im Backlog und in einem grünen Test — und war Deko.
>
> Die Fehlerklasse: eine Schwelle gegen einen Fall setzen, den eine *andere* Datei schon
> ausschließt, und die eigene Schwelle dann für den Grund halten. Der Test dazu war grün, weil er
> die Schwelle direkt aufrief statt gegen echte Daten zu prüfen. Jetzt steht der Boden auf **7500**
> — dem Wert, der tatsächlich gilt — und seine Aufgabe hat sich geändert: er ist eine
> **Stolperschwelle**. Ein Test verankert ihn gegen `MIN_VOL_USD`, damit ein Absenken dort nicht
> still dazu führt, dass das Band $2.000-Märkte als Dominanz meldet.

`markt_anteil` gibt **None**, wo der Einsatz das Marktvolumen übersteigt: der Nenner widerspricht
dann dem Zähler, und die teuerste Fehlannahme wäre, das als 100 % zu lesen. Fehlende Information
rendert als nichts — die Position fällt raus, sie wird nicht geschätzt.

### ⏱️ Das Reifefenster — und warum Lucas recht hatte

Lucas: *„wie können wir sicherstellen, dass nicht quasi zu jedem Markt bei Poly dann ein Push
kommt? Weil prinzipiell beginnt jeder Markt bei 0 … ein Markt in 2 Wochen wo jetzt 5K gespielt
werden die 60 % sind, interessiert mich ja 0. Wir müssens quasi zeitlich wie die Whale-Alerts
eingrenzen, oder?"*

Erste Antwort auf den Wortlaut: der Zwei-Wochen-Fall **kann heute nicht auftreten.**
`_capture_class` lässt nur Märkte innerhalb `CAPTURE_WINDOW_H = 3h` in den `pre`-Pfad, und der
Wallet-Track wird ausschließlich daraus gespeist — gemessen liegt `htkFirst` über alle 421 offenen
Positionen zwischen 0,1 h und 3,0 h. Eine Position zwei Wochen vor Anpfiff existiert in diesen
Daten nicht.

**Aber die Frage war trotzdem richtig, nur eine Größenordnung zu grob.** Das Problem passiert
*innerhalb* der drei Stunden. Gemessen an 424 Märkten mit Verlauf bis zum Anpfiff, Volumen im
Verhältnis zum Endstand:

| Stunden vor Anpfiff | Median | unteres Viertel |
|---|---|---|
| 2,5 – 3 h | **54 %** | 28 % |
| 2 – 2,5 h | 69 % | 45 % |
| 1,5 – 2 h | 75 % | 49 % |
| 1 – 1,5 h | 82 % | 60 % |
| 0,5 – 1 h | **92 %** | 73 % |
| 0 – 0,5 h | 100 % | 100 % |

Ein Anteil, der 2,8 h vor Anpfiff gemessen wird, hat einen **halb leeren Nenner** und ist
systematisch zu hoch — grob doppelt. Das ist exakt Lucas' „jeder Markt beginnt bei 0", nur passiert
es nicht zwei Wochen vorher, sondern in dem Fenster, das wir ohnehin erfassen. Und es traf die
gebauten Kandidaten direkt: von den vier Positionen, die das Band am 11.09. gefunden hätte, waren
**drei bei htk = 2,83 gemessen** — im leersten Band der Tabelle.

**`DOM_MAX_HTK = 1.0`**: der Anteil wird erst gelesen, wenn die Close-Zeile innerhalb einer Stunde
vor Anpfiff steht. Dort hat der Nenner im Median 92 % seines Endstands, und 94 % aller Close-Zeilen
(2.756 von 2.928) erreichen diesen Punkt überhaupt — enger bringt kaum Genauigkeit und kostet
Abdeckung.

Die Stunde kommt aus der **Close-Zeile** (`hoursToKickoff`), nicht aus `htkFirst` der Position: die
Frage ist, wie voll der *Markt* beim Messen war, nicht wie früh die *Wallet* drin war. Zwei
verschiedene Dinge — beide werden gestempelt (`htkMess`, `htkFirst`), damit sich später getrennt
fragen lässt, ob ein früher Einstieg bei reifem Markt etwas anderes ist als ein später.

⚠️ **Das ist ein Tausch, kein freies Mittagessen.** Die Karte kommt später: eine Position, die
2,8 h vor Anpfiff aufgemacht wird, steht erst rund 1,8 h später im Kanal. Gefiltert wird sie
dadurch **nicht** — sie wird zurückgehalten und kommt einen Pipeline-Lauf später durch. Für ein
Beobachtungsband ist das richtig herum: ein zu früh gemessener Anteil verdirbt genau die Zahl, um
die es in diesem Band geht. Der Effekt am 11.09.: aus 4 sofortigen Kandidaten wird **1** — die
anderen drei folgen, wenn ihr Markt steht.

Der Messzeitpunkt steht auf der **Karte**, nicht nur im Buch (*„⏱️ gemessen 50 Min vor Anpfiff"*).
Ein Anteil ohne Zeitstempel lädt dazu ein, 2,8-h- und 0,3-h-Anteile für dasselbe Maß zu halten.

### Läuft über alles

Lucas: *„läuft hier über alles drüber, oder?"* — ja. Die Sperrliste für US-Sport/Kampfsport, die im
Public-Whale-Push gilt, gilt hier **nicht**: das Band ist nichts, dem jemand folgen soll, und eine
Sportart wegzuschneiden, bevor eine einzige Zahl da ist, macht die spätere Auswertung unmöglich.
Die Kategorie wird **gestempelt**, damit sie sich in ein paar Wochen trennen lässt.

### Eigener Bereich in der Tracking-Info

Lucas: *„wenn Du so was baust, mach das bitte zumindest in der Tracking Info auch als eigenen
Bereich."*

```
poly_dominanz_ledger.json   jeder Push mit Anteil, Marktvolumen, Einstiegspreis, Wallet-Stand
poly_public_eval.py         zweiter settle()/report()-Durchlauf über dieses Buch
poly_dominanz_record.json   die ausgewertete Bilanz
poly-wallets.js → _pwDominanz(rec)   eigener Block auf der Seite, getrennt von den Whale-Zahlen
```

Getrennt zu buchen ist keine Ordnungsfrage: zusammengelegt wäre in drei Monaten nicht mehr
trennbar, ob eine Trefferquote vom Whale-Push oder vom Band kommt. **Wer pusht, misst den Push** —
und zwar den, den er gepusht hat.

### Was die Gegenbeweise gezeigt haben

Jede Regel einzeln entfernt, geprüft ob ein Test bricht:

| entfernte Regel | Test bricht |
|---|---|
| Marktboden | ✅ |
| Anteilsschwelle | ✅ |
| „kein Anteil" → 100 % angenommen | ✅ |
| Einsatzschwelle | ❌ → **nachgebessert** |
| Dedup gegen die Whale-Stände | ✅ |
| Reifefenster ganz entfernt | ✅ |
| fehlender Messzeitpunkt gilt als reif | ✅ |
| Vorzeichen gedreht (nach Anpfiff ausgesperrt) | ✅ |
| Fenster auf 3 h aufgebohrt | ✅ |
| `htkFirst` statt Markt-Reife gemessen | ✅ |
| Marktboden zurück auf den toten Wert | ✅ |
| Messzeitpunkt nicht mehr gestempelt | ✅ |

Die **Einsatzschwelle war ungedeckt**. Der Test dazu gab es, er benutzte nur $2.500 in einem
$4.000-Markt — den fing der *Marktboden* weg, bevor `min_usd` je geprüft wurde. Ein Test, der grün
bleibt, während die Regel weg ist, prüft nichts. Neu zugeschnitten auf $2.500 in einem
$6.000-Markt (41,7 % Anteil, Markt über dem Boden), plus Gegenprobe mit $3.100.

Beim Provozieren fiel außerdem auf, dass die **Dedup-Sperre nur in `main()` stand** und dort nicht
prüfbar war. Sie ist jetzt `dom_sperre(dom_seen, trades_seen, pub_seen)` — eine reine Funktion, die
alle drei Stände zusammenlegt, damit eine Position, die schon als Whale im Trades- **oder**
Public-Kanal stand, nicht Minuten später ein zweites Mal kommt. Lucas liest beide Kanäle; die
Doppelung wäre seine.

### Das Urteil steht in der Karte

Letzte Zeile jeder Dominanz-Karte: *„🔬 Beobachtungsband — läuft mit, ist noch kein Beleg."* Bei
n = 11 hinter der Idee gehört das dorthin, wo die Zahl gelesen wird, nicht in eine Fußnote im
Backlog.

## ✂️ 11.09.2026 — die Signatur-Zeile ist aus dem Cards-Push raus

Lucas: *„bitte die letzte Zeile weg mit dem datengetrieben Pick Modell."*

```
🤖 CocoBet · datengetriebenes Pick-Modell mit 19 Signalen     ← weg
```

Sie stand unter **jeder** Morning-Card und sagte nichts, was die Karte nicht schon zeigt. Die
Zahl „19 Signale" war obendrein hartkodiert und seit dem Registry-Umbau falsch: das Registry
führt **33** Signale, davon sechs im Profil abgeschaltet.

⭐ Weggenommen ist der **Aufruf**, nicht der Text. `L["de"]["footer"]` und `L["en"]["footer"]`
bleiben in `telegram_i18n.py` stehen — die Recap-Karte hat ihren eigenen Fuß (`recap_footer`) und
wird nicht angefasst; ein gelöschter Übersetzungs-Baustein wäre schwerer zurückzuholen als eine
Zeile.

Die **Bilanz-Zeile bleibt**: sie trägt eine gemessene Zahl, keine Selbstbeschreibung. Ein Test
hält beides fest — Signatur weg, Bilanz da.

## 🎯 11.09.2026 — warum die Liga nie ein BET hatte, und warum ich es trotzdem nicht gesenkt habe

Lucas: *„dass wir selten 7 erreichen ist halt weil wir glaub ich relativ hart gegated haben."*
Gemessen ist es anders: **die Liga hat in 326 Picks noch nie ein BET erzeugt.** Alles war ABWÄGEN
oder NOBET.

### Die Ursache steht in einer Config-Zeile

```
cocobet_config.json → profiles.<x>.conviction_score.steam_bet_threshold
   wm2026         6          Decke 8   →  BETs
   liga_default   8          Decke 6   →  null
   mls_default    8          Decke 8   →  3
```

Alle 326 Liga-Picks sind `source: "steam"`, die Schwelle gilt also für jeden. Der Code-Kommentar
sagt die Absicht: *„WM-Schwelle niedriger als Liga (weniger Spiele)"* — übersehen wurde, dass die
Liga gleichzeitig eine **kürzere Skala** hat. Die Kontext-Säule feuert dort in **7 von 326** Picks
(2,2 %), weil ihre Mitglieder Turnierdruck, Reise und Hitze messen und im Herbst einer 34er-Liga
per Konstruktion schweigen. Strengere Schwelle auf kürzerer Skala ergibt mathematisch null.

**Dass die Schwelle falsch sitzt, ist damit belegt.** Welcher Wert richtig wäre, nicht.

### 🔴 Und der naheliegende Fix wäre der falsche gewesen

Ich hatte Lucas „Conviction 6: n=25, Treffer 68,0 %, ROI +13,1 %" gemeldet und auf dieser Basis
die Absenkung auf 6 vorgeschlagen. Er hat zugestimmt, ich habe die Config geändert — und beim
Verdrahten der Vorregistrierung fiel auf, dass **diese Zahl Liga und MLS poolt**. Getrennt:

| | Liga | | MLS | |
|---|---|---|---|---|
| Conv 4 | n=50 · 68,0 % · **+18,0 %** | UG −3,0 % | n=24 · 50,0 % · −17,1 % | |
| Conv 5 | n=34 · 76,5 % · **+37,2 %** | **UG +12,9 %** | n=23 · 52,2 % · −15,2 % | |
| Conv 6 | n=11 · 45,5 % · **−28,6 %** | UG −69,8 % | n=14 · 85,7 % · +45,9 % | UG +16,7 % |

**Die 6 — genau das Band, das eine Absenkung auf 6 neu zugelassen hätte — ist in der Liga das
schlechteste.** Die +45,9 % stammen vollständig aus der MLS. Die Config-Änderung wurde
zurückgenommen, `liga_default` steht wieder auf 8.

Dieselbe Fehlerklasse, die einen Tag vorher die Picks-Blöcke der Stats-Seite betraf: eine Zahl,
die zwei Mengen mischt und deren Name nur eine nennt. Diesmal war ich es selbst.

### Was stattdessen läuft

Neuer vorangemeldeter Zuschnitt **`liga_conv_ab_5`** (`vorregistrierung.py`, zielN=80), gespeist
aus `freigabe._liga_conv5_plays()`. Der Rückblick (+21,1 % über 45 Plays) steht ausdrücklich als
Anlass drin, nicht als Beleg — die 5 ist genauso rückwärts geschnitten wie die 6, sie sieht nur
besser aus.

⚠️ Der Fallstrick beim Verdrahten, gegen den jetzt ein Test steht: das Lern-Ledger nennt die
Felder `odds`, `result` und `resolvedAt`, während `_rendite` `odd`/`win` erwartet und `teilen()`
nach `settledTs`/`settledAt`/`resolvedTs` sucht. Ohne Übersetzung hätte die Schublade **still leer
gemessen** und ewig „0 von 80" gemeldet — der Defekt, den `_rendite` im eigenen Docstring als
„Geduld-Tarnung" beschreibt. Drei Gegenproben provoziert: Zeitstempel nicht übersetzt, Quote nicht
übersetzt, Schnitt auf 6 zurückgedreht — jede fällt.

### ⏳ Offen

* **Die Schwelle bleibt auf 8 und damit unerreichbar.** Das ist bewusst: lieber eine Schwelle, die
  sichtbar nie greift, als eine gesenkte auf einem Band, das im Rückblick verloren hat. Entschieden
  wird, wenn `liga_conv_ab_5` seine 80 Plays hat.
* Die `market`-Säule ist in allen drei Datensätzen praktisch tot (Ø 0,02–0,04). `public_static_bias`
  feuert nur, wenn Pinnacle und der 29–49-Bücher-Konsens 2–15pp auseinanderliegen — das ist in
  **90 %** der Liga-Spiele nicht der Fall, weil die Softbooks dem Move bereits gefolgt sind.

## 🇩🇪 10.09.2026 — der Public-Channel ist einsprachig

Lucas: *„bei den Cards-Picks haben wir immer Deutsch und Englisch. Bitte deaktivier mal
Englisch."*

`TG_LANGS` stand seit dem 04.07. auf `"de,en"` — jede Morning-Card und jeder Recap ging
**zweimal** in denselben Channel. Default jetzt `"de"`.

⭐ **Weggenommen ist der Versand, nicht die Übersetzung.** `telegram_i18n` bleibt vollständig,
`build_morning_card(..., "en")` baut die englische Karte weiter, und ein Test hält fest, dass sie
gebaut wird. `TG_LANGS="de,en"` holt sie in einem Schritt zurück — eine gelöschte Übersetzung
wäre nicht rückgängig zu machen, ein Default ist es.

Betroffen ist nur dieser eine Sender: `telegram_i18n` hat außer `telegram_wm` keinen Aufrufer,
die anderen Kanäle waren nie zweisprachig.

## 🔗 10.09.2026 — der Markt-Link ist zurück in der Poly-Public-Karte

Lucas: *„bitte wieder den Markt rein, das hab ich vergessen … ist userfreundlicher."*

Beim Kürzen der Karte heute früh flog `Markt ansehen ↗` mit raus. Er gehört zurück, und der
Grund überlebt die Kürzung: **alles andere auf der Karte ist eine Behauptung von uns** — der
Rang, der Marktanteil, die Quote. Der Link ist das Einzige, womit ein fremder Leser sie
nachprüfen kann. Eine Karte, die Zahlen nennt und den Weg zur Quelle weglässt, verlangt
Vertrauen, statt es zu verdienen.

Er steht am Ende, nicht oben — die Karte führt mit dem Spiel. Ohne `key` steht dort **nichts**;
ein Link auf `polymarket.com/event/None` wäre schlechter als kein Link.

## 📊 10.09.2026 — die Stats-Seite: drei Fragen, zwei Bugs, eine Kopfzeile

### 1. Die WM ist raus

Lucas: *„WM kann raus, wertlos in Wahrheit."* Am 09.09. bekam sie einen eigenen Block, damit sie
die Gesamtzahl nicht zur Hälfte füllt — das war die halbe Lösung. Getrennt stand sie richtig da,
beantwortet aber keine Frage, die heute noch jemand stellt.

⭐ **Die Daten bleiben.** `cards_plays("WM")` liefert die Picks weiter, `freigabe._card_plays()`
kennt sie unverändert. Weggenommen wurde der Platz auf der Seite, nicht die Auskunft aus dem
System — dieselbe Trennung wie bei der ✦-Prosa im Cards-Digest.

### 2. 🔴 Die Picks-Blöcke zählten Picks, die nie gepusht wurden

`pick_push_ledger.json` ist ein **Schattenbuch** und soll es sein: es hält jeden announce-fähigen
Pick, den gesendeten **und** den vom Gegensignal-Filter aussortierten, damit der Filter sich nicht
selbst bestätigen kann. Genau das macht es als Quelle für einen Push-Kanal untauglich:

```
Liga   131 Zeilen  →   42 gepusht,   89 nie
MLS     44 Zeilen  →    6 gepusht,   38 nie
```

127 Picks standen in der Gruppe „Push-Kanäle", die nie in einem Push waren. Dieselbe Fehlerklasse
wie beim Public-Block eine Stunde vorher: der Name verspricht eine Menge, die Zahl enthält eine
andere. Ein Kanal-Block zählt, was den Kanal verlassen hat — sonst misst er die Engine und nennt
es Kanal.

| | vorher | jetzt |
|---|---|---|
| Liga-Picks · Trades | n=125, ROI +12,6 % | **n=42, ROI +17,0 %** |
| MLS-Picks · Trades | n=29, ROI −11,8 % | **n=6, ROI −11,6 %** |

Die Aussortierten verschwinden nicht: der Block nennt ihre Zahl, die Gegenprobe steht als eigene
Schublade im Freigabe-Register.

### 3. 🔴 „Heute spielenswert" wurde nicht seit kurzem getrackt — es hat vergessen

Lucas: *„wird das erst seit kurzem getrackt? weil nur 23 in KW 37 und sonst nichts."*

Die Quelle war `shortlist_push_seen.json` — kein Ledger, sondern ein **Dedup-Buch mit 3 Tagen
TTL** (`SEEN_TTL_DAYS = 3`), das sich bei jedem Lauf selbst aufräumt:

```
n=24   von 2026-09-08 bis 2026-09-10
```

Mehr kann dort nie stehen. KW 36 war nicht leer, weil nichts gepusht wurde, sondern weil die
Datei es weggeworfen hatte. Ein Ergebnis trug sie auch nicht — der Block hatte deshalb weder
Trefferquote noch ROI.

„Heute spielenswert" war als **einziger der fünf Push-Kanäle ohne eigenes Buch**. Der Satz dazu
steht seit dem 01.09. in `killer_push.py`: **wer pusht, misst den Push.**

Neu: `shortlist_push_ledger.json`, geschrieben von `push_shortlist_trades.py`. Es hält, was beim
Senden galt — Zeitpunkt, **Push-Preis** (nicht den älteren Scan-Preis) und Conviction.

⭐ **Es rechnet nicht selbst ab.** Der Ausgang kommt aus `poly_shortlist_track.json`, das seit
heute früh weiß, wann ein Bündel-Markt überhaupt entscheiden darf. Zwei Bücher mit zwei Regeln
waren in diesem Repo schon einmal der Fehler. Gebucht wird nur, was wirklich gesendet wurde —
ein Vorschau-Lauf schreibt keine Zeile.

⚠️ Das Buch beginnt am 10.09.2026. Die früheren Pushes sind nicht rekonstruierbar; der Block
erscheint erst, wenn die erste Zeile drinsteht (`_add` überspringt leere Blöcke — leer ist ein
Ergebnis, aber eine leere Tabelle ist keine Auskunft).

### 4. Die Kopfzeile

Lucas: *„kannst du mir ganz oben ne Zusammenfassung von Cards / Betfair aus dem Public-Push /
Poly aus den Public-Kandidaten — und das wechselt mit, wenn ich Monat/Woche umstell."*

Eine **KPI-Zeile aus drei Stat-Kacheln**, kein Diagramm: drei Kennzahlen nebeneinander sind genau
der Fall, für den es Kacheln gibt — drei Balken wären mehr Tinte für weniger Auskunft. Keine
Hero-Zahl: eine Seite trägt genau eine, und drei gleichrangige Zahlen sind keine.

Je Kachel: Periode · Rendite · Stichprobe + Trefferquote · Differenz zur Vorperiode **in
Prozentpunkten**, mit deren Namen.

Drei Stellen, an denen so eine Kopfzeile lügt — alle drei sind als Test provoziert:

* **Sie zeigt die laufende Periode.** Am Montag ist die Woche ein Spiel groß; als Schlagzeile
  wäre das eine Behauptung über nichts. Gezeigt wird die letzte **abgeschlossene** Periode; die
  laufende steht weiter in der Tabelle darunter, dort als unvollständig markiert.
* **Sie zeigt eine Rendite auf n=8, ohne dass man es sieht.** Die Stichprobe steht immer daneben,
  und unter `ugMinN` sagt die Kachel ausdrücklich „Punktschätzer, keine Untergrenze". Ohne das
  wäre die Kopfzeile die Klasse *ein Punktschätzer entscheidet*, gegen die der Rest der Seite
  gebaut ist.
* **Sie geht beim Umschalten nicht mit.** Ein Test schaltet auf Monate und prüft, dass danach
  keine Kalenderwoche mehr dasteht.

Fehlt ein Bereich, steht dort ein Wort statt einer Null; fehlt die Vorperiode, steht „keine
Vorperiode zum Vergleich" statt „+0,0 pp".

## 🔴 10.09.2026 — der Bündel-Markt, zweiter Teil: die Erfassung

Lucas: *„vor allem die 2 Fußball sind mmn schon alle erledigt, nur schaffst du es nicht, sie
aufzulösen. Das UCL war jedenfalls win mit dem Under."* — Stimmt beides. Die Auflösungen lagen
seit Tagen da:

```
ucl-aek1-lin2-2026-09-08-more-markets  →  winner: "Under"   08.09. 19:08
sea-fro-ven-2026-09-06-more-markets    →  winner: "Over"    06.09. 15:33
```

### Warum sie trotzdem nicht abrechneten — und warum das richtig war

`poly_slug_urteil.aufloesbar()` blockt seit dem 04.09. (Leeds-Brentford: wir hatten einen Gewinn
erfunden). Bei einem `-more-markets`-Bündel kann „Under" **Under 1,5 oder Under 3,5** heißen, und
beide liegen im selben Event. Die Regel ist richtig: lieber offen als geraten.

Die Regel hat einen Ausweg — `aufloesbar(key, seite, sieger, cond=…)`, die conditionId nagelt
einen Markt fest. **Dieses Argument wurde an keiner einzigen Stelle im Repo übergeben.** Der
Ausweg war gebaut und nie angeschlossen.

### Und beim Nachsehen kippt der Befund

Die Historie von `ucl-aek1-lin2-2026-09-08-more-markets`, sechs Snapshots eines Nachmittags:

| Zeit | Over | Under | Volumen |
|---|---|---|---|
| 14:07 | 0,415 | 0,585 | 13.926 |
| 14:36 | 0,425 | 0,575 | 18.880 |
| **15:07** | **0,855** | **0,145** | 25.479 |
| 16:07 | 0,865 | 0,135 | 25.702 |
| **16:37** | **0,395** | **0,605** | **124.818** |

Under 0,145 und Under 0,605 sind **keine Preisbewegung**. Ein Vorspiel-Totals-Markt läuft nicht
44 Punkte weg und zurück; das sind zwei verschiedene Linien (Under 1,5 gegen Under 3,5). Die
Erfassung hat den Markt gewechselt, weil `_outcomes()` bei einem Bündel den Markt mit dem
**meisten Volumen** nimmt — **in jedem Lauf neu**.

Der 04.09.-Fix hat die **Abrechnung** festgenagelt. Die **Erfassung** blieb Volumen-Roulette.
Damit konnten `entryPrice`, `lastPrice` und das daraus gerechnete CLV eines Bündel-Plays aus
**drei verschiedenen Märkten** stammen. Der Play, um den es Lucas ging, stieg zu Under **0,705**
ein — ein Preis, der in keinem einzigen Snapshot vorkommt.

Rate im Bestand: **7 % der Bündel-Keys** zeigen einen Sprung >25 pp gegen **1 %** der
Einzelmärkte.

### Die Kette, die jetzt geschlossen ist

| Stelle | vorher | jetzt |
|---|---|---|
| `poly_money_broad.outcomes_gepinnt` | jeder Lauf wählt neu nach Volumen | ein erfasstes Bündel behält seine conditionId |
| `resolutions_mit_markt` / `update_resolutions` | `{winner, ts}` | `+ cond, frage` („AEK vs. LASK Linz: O/U 3.5") |
| `poly_shortlist_track` Eintrag | Key + Seite | `+ cond, frage` |
| `poly_shortlist_track` `lastPrice` | Preis aus dem aktuellen Close-Stand | nur aus **demselben** Markt — sonst bleibt der alte stehen |
| `poly_shortlist_track` Abrechnung | Bündel + „Under" → nie | rechnet ab, **wenn beide Seiten dieselbe conditionId tragen** |

Findet sich der gepinnte Markt nicht mehr, gibt es **keine** Ausgänge — der Lauf überspringt ihn.
Eine alte Auskunft schlägt eine falsche.

⚠️ **Die 15 offenen Plays vom 04.–09.09. rechnen dadurch NICHT rückwirkend ab.** Der Altbestand
in `poly_resolutions.json` trägt keine conditionId, und die Historie zeigt ja gerade, dass der
Markt in der Zwischenzeit gewechselt haben kann. Sie nachträglich zu buchen hieße genau das zu
tun, wogegen der Riegel gebaut wurde. Sie laufen sichtbar in `unaufloesbar` — und ab jetzt
entsteht die Lücke nicht mehr.

### Verfallen ist ein Ergebnis, also muss es dastehen

`expired` war ein Zähler **je Lauf**: was gestern verfiel, stand nirgends. Am 10.09. waren **15
von 23** offenen Plays Bündel-Märkte, die nie abrechnen konnten — am **18.09.** wären sie auf
einen Schlag weg gewesen (`STALE_TTL_D = 14`), ohne dass eine Zahl im Board sich bewegt hätte.

Neu: `unaufloesbar` als fortgeschriebenes Buch (500 Zeilen rollierend) mit `unaufloesbarAgg`
**samt Grund** — „nicht getrackt", „nie aufgelöst", „Bündel ohne Marktkennung", „Bündel:
Auflösung nennt einen anderen Markt". Die Zahl allein wäre die schwächere Auskunft: ein Grund
nennt eine Ursache, die man beheben kann. Der Whale-Ledger macht das seit dem 02.09. genauso;
dieses Buch war das letzte, das es nicht tat.

## 📐 10.09.2026 — „+11 P/L" gegen „+$105": zweimal dieselbe Zahl, zweimal falsch beschriftet

Lucas' Frage. Antwort: **ja, dasselbe Geld** — `stats_perioden.kennzahlen()` summiert
`rendite = pnl/stake`, also **Einheiten**. 10,98 × $10 = $109,80.

Aber die Blöcke meinten auch **nicht dieselbe Menge**:

```
Board  n=188   $105,28
Stats  n=183   $109,85
       ─────   ───────
         5      $4,57     ← genau die gesperrten US-Sport-Plays
```

`aggregate()` baute `public` aus **allen** settled-Zeilen, während `bettable`/`blocked` zwei
Zeilen tiefer korrekt nach `blockedCats` trennen. Der Public-Block zeigte also einen ROI, in dem
5 Plays stecken, **auf die nie gesetzt wird** — und sie zogen ihn nach unten (+5,6 % statt
+6,0 %), mit Geld, das nie geflossen ist.

`public` heißt jetzt dasselbe wie `bettable`. Die Gesperrten stehen als `publicBlocked` daneben.
Die **Kontrollgruppe** (`publicOhneWallet`) wird genauso getrennt — sonst stünden auf den beiden
Seiten des Wallet-Vergleichs zwei verschieden zusammengesetzte Mengen, und der Unterschied wäre
teils Sportart statt Wallet-Tor.

| | n | Treffer | ROI | UG | P&L |
|---|---|---|---|---|---|
| ◆ Public-Kandidaten | 183 | 71,0 % | +6,0 % | −2,8 % | +$109,85 |
| 🚫 davon gesperrt | 5 | 60,0 % | −9,1 % | — | −$4,57 |
| 🧪 Kontrollgruppe | 40 | 77,5 % | +20,1 % | **+1,9 %** | +$80,20 |

Auf der Stats-Seite heißt die Spalte jetzt „P/L *Einh.*" und die Kachel nennt die Umrechnung.

## 🏷️ 10.09.2026 — zwei Board-Texte, die ihrem Code zwei Wochen hinterher waren

Lucas: *„ich bin grad etwas verwirrt."* Zu Recht — der Untertitel des Public-Blocks log in
**beiden** Angaben:

* **„sendet nichts"** — `push_shortlist_trades.py` schickt genau diese Menge seit dem 07.09. in
  den **Trades**-Channel, gegated auf `public`.
* **„Conv≥7"** — `PW_PUBLIC_MIN_CONV` steht seit dem 29.08. auf **6**.

Derselbe Fehler in `_pwPushInfo`: „der Push feuert ab Conviction ≥6, ein Public-Kandidat verlangt
≥7 … zwei verschiedene Tore". Seit dem 07.09. hängt `push_shortlist_trades.select()` am
Public-Tor **selbst** (`_tor(p) = bool(p.public)`) — die Mengen sind nicht mehr verschieden, der
Push ist eine **Teilmenge**. Ein „kein Push" heißt jetzt Deckel (max. 6), Preis >92¢ oder Dedup
(3 Tage), **nicht** „nicht gut genug".

Beide Texte lesen die Konstanten jetzt aus dem Code, statt sie zu behaupten.

### ⏳ Offen

* **Die Push-Frage selbst** (Public-Kandidaten in den Public-Channel?) ist bewusst **nicht**
  entschieden — Lucas wollte erst die korrigierten Zahlen sehen. Sachstand: Whale-Public bringt
  0 Tennis (Dollar-Schwelle gegen Marktgröße: größte Tennis-Position $2.850 gegen $25K nötig),
  die Public-Kandidaten bringen 43 Tennis-Plays mit 76,7 % / +5,8 %. Dagegen steht, dass die
  Kontrollgruppe **ohne** Wallet-Tor besser läuft als die Menge **mit** — bei n=40.

## ✂️ 10.09.2026 — die Public-Templates entschlackt

Lucas hat drei Templates neu geschnitten und eines abgeschaltet. Die Klammer über allem:
**der Public-Kanal ist nicht der Trades-Kanal.** Im Trades-Kanal entscheidet Lucas selbst und
will alles sehen; im Public-Kanal liest jemand mit, der die Vorgeschichte nicht kennt.

### 1. Poly-Whale · Public — kürzer, mit Quote statt Cent

Vorher sieben Zeilen (Ticket-Median des Kontos, Preisbewegung mit Pfeil, Außenseiter-Hinweis,
volle Wallet-Bilanz, Markt-Link). Jetzt vier Angaben: Sportart, Spiel, wer, wie viel, zu
welchem Preis.

```
🐋 <b>Polymarket Whale</b>

<i>Fußball</i>
⚽ <b>Flamengo v Palmeiras</b>
🥇 <b>Rang #1 Sharp Bettor</b> hat gewettet

💰 <b>$150K</b> auf <b>Flamengo</b>

📊 <b>18 %</b> des Marktvolumens
Einstieg @1.41
```

* **Quote statt Cent** (`_quote`): 71¢ ist Polymarket-Sprache, @1.41 ist Wett-Sprache. Ein
  Preis außerhalb (0,1) gibt **None**, nicht „@∞" — ein quasi-abgerechneter Markt hat keine
  Einstiegsquote, und eine erfundene wäre schlimmer als keine.
* **Betrag fett**, Sportart **vor** dem Spiel: die Sportart ist der Filter, mit dem ein
  fremder Leser entscheidet, ob ihn die Zeile angeht.
* ⚠️ **Was rausfiel, fiel GANZ raus.** Die Wallet-Bilanz halb zu zeigen („15/20") wäre
  schlechter als sie wegzulassen — ohne CLV und ohne Lifetime ist sie kein Urteil, sondern
  eine Zahl, die nach einem klingt.

### 2. Poly-Whale · Trades — unverändert, plus die Lifetime-Bilanz

Lucas: *„Trades-Channel lassen wir alles wie es ist, da will ich die ganze Info haben, die
sonst noch da steht."* Wörtlich genommen: die Lifetime-P&L stand bis heute **nur** in der
Public-Karte. Mit deren Kürzung wäre sie ersatzlos verschwunden — also wandert sie in
`_wallet_line` (neu: `_lifetime`) statt weg.

```
Wallet 0xA1b2…5678 · ✅ <b>bewiesene Wallet</b> (15/20 richtig, 75% · +3.2pp CLV) · +$412K lifetime
```

* Fehlt `pnl`, steht **nichts** dort — kein „$0", das eine ausgeglichene Bilanz behauptet, wo
  gar keine gemessen wurde. Der Guard dazu ist provoziert: mit `pnl = 0` als Default fällt er.
* Ein **negativer** Lifetime erreicht `_lifetime` nie: `_is_confirmed_loser` schließt beide
  Zweige von `_wallet_line` aus, eine Verlierer-Wallet bekommt „Track-Record noch im Aufbau"
  auch bei 10/12 Treffern. Die Minus-Formatierung bleibt trotzdem drin — als Absicherung für
  künftige Aufrufer, und ein Test hält fest, dass sie ein echtes „−" schreibt und kein „+".

### 3. Cards-Digest — drei Streichungen

| Vorher | Jetzt | Warum |
|---|---|---|
| `━━ Gruppe A · Spieltag 1 ━━` über **jedem** Spiel | nur beim **Wechsel** | Bei drei Spielen desselben Spieltags trennte der Trenner nichts, weil links und rechts dasselbe stand |
| `✦ Das Modell sieht Treffer auf beiden Seiten — Value auf Beide Teams treffen — Nein` | *(weg)* | Stand eine Zeile über `🟡 Abwägen: Beide Teams treffen — Nein @2.18` — eine Übersetzung der Pick-Zeile, kein zusätzlicher Inhalt |
| Einsatz in der **Kopfzeile**, Signale und Signalnamen je auf eigener Zeile | Einsatz am **Ende der Begründungszeile**, alles in einer | Die Kopfzeile beantwortet „was und zu welcher Quote", der Einsatz gehört zu „warum so viel" |

⚠️ `aiSnippet` und `_pick_intro` werden **weiter erzeugt** und stehen unverändert im Dashboard
und in den Vorschau-Seiten. Weggenommen wurde der Platz im Push, nicht die Information aus dem
System.

**Die Tests dazu waren im ersten Entwurf wertlos** und wurden ersetzt: einer las mit
`inspect.getsource` nach, ob die ✦-Zeile noch im Quelltext steht (misst Code, nicht Ausgabe),
der andere suchte den Trenner-Fall in Daten, die im Arbeitsverzeichnis gar nicht liegen — er
lief als stiller No-Op durch. Jetzt wird der Fall **gebaut**: ein Spiel wird samt seinem Pick
auf den nächsten Spieltag umgehängt (`pick_key` trägt den Spieltag im Namen — ohne Mitziehen
fällt das Spiel aus der Karte und der Test misst die falsche Sache). Beide Richtungen sind
provoziert: Trenner immer → fällt, Trenner nie → fällt die Gegenprobe.

### 4. „Serie der Woche" ist aus dem Public-Kanal raus

`.github/workflows/telegram-streaks.yml`: der Cron ist auskommentiert (mit Datum),
`workflow_dispatch` bleibt. Der Workflow wird **nicht gelöscht** — ein gelöschter Workflow
nimmt seine Historie mit und mit ihr die Frage, warum es ihn mal gab.

### 5. 🔴 Der Flag-Fix — derselbe Bug, gegen den es seit dem 25.07. `tg_safe` gibt

`notify_new_picks.py` schrieb `u['homeFlag']` roh in die Nachricht. Bei den Klub-Datensätzen
ist das kein Emoji, sondern ein komplettes `<img src="https://media.api-sports.io/…">`-Tag
(fürs Dashboard gedacht). Telegram erlaubt im HTML-Modus **kein `<img>`** und antwortet mit
HTTP 400 „Unsupported start tag" — die Nachricht scheitert **lautlos**.

`telegram_wm`, `detect_wm_sharp_moves` und `telegram_streak_watch` benutzen `safe_flag`
seitdem; dieser Sender nie. **Folge: der Cards-Public-Push hat für liga/mls vermutlich noch
nie zugestellt** — nur für die WM mit echten Länderflaggen, und die ist seit dem 19.07. vorbei.

### 6. Der CI-Wachhund, vierter und fünfter Slug

`superettan` (Schwedens **zweite** Klasse, trotz „super" im Namen) und `v-league` (Vietnams
oberste). Beide in die **Tabelle**, nicht in eine Regel: ein Muster auf „super" würde
`super-lig`, `super-league`, `super-league-1` und `chinese-super-league` umstürzen, um einen
Nachtrag zu sparen. `v-league` heißt in Korea und Japan die **Volleyball**-Liga — dass hier
trotzdem eine „1" stehen darf, hält allein `stufe()` fest, das außerhalb `sport == "soccer"`
grundsätzlich `None` gibt.

Der Wachhund wird bei jedem neuen Land wieder feuern. Das ist kein Mangel: ein Ligaslug bringt
seine Spielklasse nicht mit, und eine geratene Ebene wäre schlechter als eine gemeldete Lücke.

### ⏳ Offen / beobachten

* `_sport(league, sport)` gibt für `("SOCCER", "soccer")` das Fallback-🎯 zurück und **`_pub_ok`
  sperrt 🎯** — ein Fußball-Push würde damit gar nicht erst rausgehen. Aktuell harmlos, weil die
  echten Positionen `sport = None` tragen und `("SOCCER", None)` sauber zu ⚽ Fußball auflöst;
  die Konvention im Repo sind deutsche Kategorienamen (`"Fußball"`). Wer dort je englische
  Kleinschreibung einträgt, schaltet den Fußball im Public-Kanal still ab.
* `1 Signale dafür` — Singular/Plural in der Cards-Karte. Kosmetisch, vorbestehend.

## 📊 09.09.2026 — die Stats-Seite (Mehr → Stats)

Lucas: *„schaffen wir eine eigene Stats-Seite? Im Mehr-Menü einfach Stats, und dort alles rein was
geht — Cards, Betfair, Poly, Push-Channels usw. Alles auf Monatsbasis und Wochenbasis auch. Schön
modern dargestellt, weil brauch das um es zu posten."*

Neu: `stats_perioden.py` (rechnet) → `stats_perioden.json` → `stats.js` (zeichnet). **12 Blöcke**
in drei Gruppen, je mit Wochen, Monaten und Gesamt.

| Block | n | Treffer | ROI |
|---|---|---|---|
| Cards · laufender Betrieb (Liga+MLS) | 151 | 64,9 % | **+9,4 %** |
| Cards · Liga | 91 | 68,1 % | **+15,2 %** |
| Cards · MLS | 60 | 60,0 % | +0,7 % |
| Betfair · alle Signale | 17.678 | 52,4 % | −0,5 % |
| Polymarket · Shortlist | 615 | 64,1 % | +1,1 % |
| Polymarket · Public-Kandidaten | 174 | 70,7 % | **+6,0 %** |
| Betfair · Public-Channel | 215 | 58,9 % | −1,5 % |
| Poly-Whales · Public-Channel | 53 | 73,9 % | **+39,4 %** |
| Konjunktion · Trades | 34 | 62,5 % | +11,9 % |
| Liga-Picks · Trades | 125 | 68,8 % | +12,6 % |
| MLS-Picks · Trades | 29 | 58,3 % | −11,8 % |
| Heute spielenswert · Trades | 24 | — | — |

### Die zwei Sätze, an denen so eine Seite sonst scheitert

1. ⭐ **Eine Periode ohne Abdeckung ist keine Periode.** Der Betfair-Ledger hält ein rollierendes
   Fenster und reicht am 09.09. nur bis zum **26.08.** zurück. Ein Balken „August" wäre dort seine
   letzte Woche und sähe neben dem September aus wie ein schwacher Monat statt wie ein halber.
   Jede Zeile trägt `vollstaendig` und, wenn nicht, den Grund („läuft noch" / „die Datenquelle
   reicht nur bis … zurück"); die Balken sind dann schraffiert. Perioden ganz vor der Abdeckung
   bekommen **gar keine Zeile** statt einer Null.
2. **Eine fehlende Kennzahl ist keine Null.** „Heute spielenswert" führt ein Dedup-Buch, kein
   Ledger — dort steht die Zahl der Pushes und **kein ROI**, mit dem Satz warum. `mitQuote: 0`
   macht das maschinenlesbar.

### Gestaltung

- **Eine Serie je Sparkline** — damit braucht es keine kategoriale Palette und keine Legende. (Die
  fünf Marken-Farben nebeneinander fallen im Palette-Validator durch das Helligkeitsband; die
  Frage stellt sich so gar nicht.) **Balken statt Linie:** die Perioden sind diskret und teils
  unvollständig — eine Linie würde dazwischen interpolieren und Werte behaupten, die nie gemessen
  wurden.
- **Farbe trägt nur Status**, und nie allein: Grün↔Rot hat für Rot-Grün-Blinde **ΔE 2,2**. Jede
  Rendite trägt ihr Vorzeichen, jede unvollständige Periode ihr Wort und ihre Schraffur.
- **Post-Modus** (Lucas' Screenshots): blendet P/L und Beträge aus, lässt Trefferquote, Rendite in
  Prozent, Stichprobe und Untergrenzen stehen. Ein Test hält fest, dass er **genau eine Spalte und
  genau eine Kachel** entfernt — mehr wäre ärmer als nötig, weniger nicht postbar.
- **Cards „gesamt" ist Liga + MLS, nicht alles.** Die WM trägt 160 der 314 abgerechneten Picks und
  ist seit 19.07. vorbei; sie steht als eigener, ausdrücklich als beendet beschrifteter Block.
  Dieselbe Entscheidung wie bei den ruhenden Schubladen im Freigabe-Register.

### Zwei Guards haben beim ersten Lauf zugeschlagen

- 🔴 **`stats_perioden.py` las das rohe `cat`-Feld.** Der Wächter aus `test_shortlist_kategorie.py`
  fand es sofort: nicht jede Zeile trägt einen Stempel, und eine ungestempelte UFC-Zeile wäre in
  der bespielbaren Bilanz gelandet. Jetzt über `poly_shortlist_track._row_cat`.
- 🔴 **`mizoram-premier-league`** — dritter CI-Treffer des Tages. Eine indische *Staats*liga:
  trotz „Premier" im Namen nicht die oberste Klasse. Deshalb Tabelle statt Regel — ein Muster
  würde aus dem Wort das Gegenteil lesen.
- Und der Navi-Guard verlangte den Eintrag auf **beiden** Flächen (Desktop-Dropdown + mobiles
  Sheet), sonst wäre die Seite mobil unerreichbar gewesen.

🔴 **Und ein vierter Wachhund-Treffer, diesmal einer anderen Klasse:** `ballon-dor`. Die drei
davor („reserva", „efl-trophy", „mizoram-premier-league") waren Wettbewerbe, deren Ebene nur
fehlte. Der Ballon d'Or ist **gar kein Wettbewerb**: „Ballon dor 2026 · Winner · Harry Kane" ist
eine Auszeichnung mit einem Sieger, kein Spiel mit einer Spielklasse. Eine Zahl dafür wäre
erfunden — es gibt keine Liga, in der Harry Kane den Ballon d'Or gewinnt. Deshalb eine eigene
Marke `auszeichnung` statt einer Ebene: die Zeile fällt nicht mehr aus der Ansicht (der Grund für
den Wächter), behauptet aber auch keine Spielklasse. Das Muster deckt Golden Boy, Golden Boot,
Puskás und Player-of-the-Year gleich mit ab.

**Gegenbeweis** (sechs Regeln): Vollständigkeit ignorieren → 2 Tests fallen; fehlende Quote als
0 → fällt; Untergrenze ohne Mindestzahl → fällt; WM zurück in „gesamt" → fällt; Sparkline ohne
Schraffur → fällt; Post-Modus nimmt eine Kachel zu viel → fällt.

**Rollout:** `stats_perioden.py` läuft in `betfair.yml` **nach** freigabe/killer (es liest deren
Artefakte) und wird committet. Bis zum ersten CI-Lauf ist die Seite leer und sagt das auch.

## 🔍 09.09.2026 — ein Guard, der die Daten mass · und die Spiele hinter den Public-Kandidaten

### Der Guard, der bei gutem Marktzustand rot wurde

`test_schlechte_fits_werden_ueberhaupt_aussortiert` verlangte, dass im **LIVE**-Snapshot
mindestens ein Poisson-Fit an der RMSE-Schranke scheitert. Am 09.09.: 49 Leitern, schlechtester
Fit 0,0154, Schranke 0,02 — **keiner scheitert**, also rot. Die Absicht war richtig (eine
Schranke, die nie greift, könnte man versehentlich löschen), die Umsetzung nicht: der Test wurde
rot, weil die **Daten gut waren**. Ein Guard, der bei gutem Marktzustand anschlägt, erzieht dazu,
ihn zu ignorieren — und dann fängt er auch den echten Fall nicht mehr.

Ersetzt durch zwei Sätze, die beide vom Tagesbestand unabhängig sind:

- ✅ **Die Schranke greift im Entscheidungspfad** — geprüft mit einer *konstruierten* verbogenen
  Leiter, plus der Nachweis, dass der Code sie überhaupt liest (`rmse > MAX_RMSE`).
- ✅ **Sie ist an diesen Daten kalibriert** — sie muss in der Größenordnung der real vorkommenden
  Fits liegen. `MAX_RMSE = 0,5` wäre formal da und praktisch tot; `MAX_RMSE = 0,0001` würde jede
  Leiter aussortieren und das Signal still abschalten. **Beide Richtungen** werden geprüft.
- ✅ Dazu ein **Protokoll ohne Urteil**: der Testlauf druckt „49 Leitern, 0 über MAX_RMSE,
  schlechtester Fit 0,0154". Eine Verschiebung fällt auf, ohne dass ein guter Markttag rot wird.

Gegenbeweis: Schranke auf 0,5 → fällt; auf 0,0001 → fällt; Aussortieren entfernt → fällt.

### ◆ Public-Kandidaten: welche Spiele sind das eigentlich?

Lucas: *„was mir fehlt vor allem beim Public-Kandidaten ist, welche Spiele da überhaupt dabei
sind. … und ich will auch immer kontrollieren, ob für die ‚Heute spielenswert' auch wirklich in
Trades-Channel eine Push kommt."*

Der Block zeigte seit Wochen n, Trefferquote, ROI und CLV — also wie **gut** die Auswahl war, aber
nie **was** drin war. Eine Kennzahl ohne ihre Zeilen kann man nicht nachprüfen.

- ✅ Ausklappbare Liste unter den Public-KPIs: offene und zuletzt abgerechnete Kandidaten mit
  Markt, Seite, Conviction, Einstiegspreis, Ergebnis — **und einer Push-Spalte**.
- ⭐ **Die Push-Spalte ist der eigentliche Punkt.** `push_shortlist_trades.py` führt sein
  Dedup-Buch unter `key|side` — demselben Schlüssel wie der Paper-Track. Damit ist die Frage
  ohne jede Rekonstruktion beantwortbar: nachschlagen statt vermuten.
- ⚠️ **Sie ist absichtlich nicht überall ✅.** Der Trades-Push feuert ab **Conviction ≥6**, ein
  Public-Kandidat verlangt **≥7 plus bewiesene Wallet plus Mehrheit**. Zwei verschiedene Tore,
  zwei verschiedene Mengen — und genau die Differenz ist das, was kontrolliert werden soll. Der
  Satz steht über der Tabelle, damit ein fehlendes ✅ nicht als Fehler gelesen wird.
- ⭐ **„Unbekannt" ≠ „nicht gepusht".** Ohne geladenes Push-Buch steht „—" und nie „kein Push" —
  das wäre eine Behauptung über etwas, das gar nicht nachgesehen wurde. (Der Test hat mir dabei
  meine eigene Formulierung um die Ohren gehauen: der Tooltip enthielt die Zeichenfolge „kein
  Push" und ließ die Zusicherung anschlagen. Umformuliert statt Test aufgeweicht.)

Gegenbeweis: fehlendes Buch als „kein Push" rendern → fällt; nicht-öffentliche Plays mit
aufnehmen → fällt; laufendes Spiel bekommt ein Ergebnis → fällt.

## 📒 09.09.2026 — das Serien-Buch: wurde die Serie erfüllt, ja oder nein

Lucas: *„naja der Preis is da egal um ehrlich zu sein. Die Frage ist einfach: wurde Serie erfüllt
ja oder nein. Das dann etwas simpler, aber das braucht es oder?"*

Ja — und es ist die **bessere erste Frage**. Ob Serien Geld bringen, kann man erst sinnvoll
fragen, wenn sie überhaupt Information tragen; und das entscheidet sich an der Trefferquote gegen
die Erwartung, nicht am Preis.

🔴 **Der Fund: die Antwort wurde seit August täglich berechnet und weggeworfen.**
`telegram_streak_watch.build_recap` rechnet `streak_held()` aus, postet „Serie hält" bzw.
„gerissen" — und `main` löscht den Eintrag danach aus dem Watch. Stand 08.09.: **50 bewachte
Serien, 0 Ergebnisse.** Nicht „noch nicht gebaut", sondern gebaut, gerechnet, und in den Müll.

- ✅ **`streak_record.json`** — eine Zeile je abgerechneter Serie, angehängt, nie neu geschrieben.
  Getrennt vom Watch-Zustand: der ist flüchtig (Einträge fallen nach dem Spiel raus), das Buch
  dauerhaft.
- ⭐ **Die Erwartung wird VOR dem Spiel festgeschrieben** (`erwartetPct` aus der neuen
  `seltenheit`, beim Setzen des Watch). Ohne sie ist die Trefferquote hinterher nur eine Zahl:
  „71 % erfüllt" ist gut oder schlecht, je nachdem, was ohne jede Serie zu erwarten war. Sie
  später nachzuschlagen wäre kein Vergleich, sondern ein Rückblick auf einen Wert, den dasselbe
  Spiel schon verändert hat — dieselbe Regel wie in `vorregistrierung.py`.
- ✅ **`bilanz()`** vergleicht die **Untergrenze** der beobachteten Quote mit der Erwartung:
  · Untergrenze > Erwartung → *trägt sich selbst* (Hot Hand)
  · Obergrenze < Erwartung → *kehrt um* (das wäre ein Fade-Signal, die nützlichere Auskunft)
  · sonst → *kein Unterschied*
  Ein Punktschätzer entscheidet nichts: 25 von 35 sind 71 % gegen 60 % Erwartung, aber die
  Untergrenze liegt bei 58 % — voll vereinbar mit „die Serie sagt gar nichts".
- ✅ **Sieg- und Ungeschlagen-Serien sind jetzt abrechenbar.** Sie stehen im Endstand genauso
  drin wie die Tor-Märkte und fehlten in `streak_held` nur — und fielen deshalb still aus jeder
  Abrechnung.
- ✅ **Ecken und Karten bleiben im Nenner sichtbar.** Sie stehen nicht im Endstand, werden aber
  als `erfuellt: null` gebucht statt still verworfen: ein Markt, den wir nicht abrechnen können,
  muss zählbar bleiben, sonst sieht das Buch vollständiger aus, als es ist.
- ✅ Die Kachel zeigt das Urteil des **Produzenten**; das Frontend vergleicht nichts selbst.
  Ohne Buch-Datei erscheint gar nichts, mit leerem Buch steht „es beginnt mit dem nächsten
  Spieltag" — nicht „nichts gemessen".

**Ehrlich dazugesagt:** diese Bilanz beantwortet **nicht**, ob Serien Geld bringen — dafür fehlen
die Quoten, und *eine Trefferquote ohne die Quoten ist keine Zahl*. Sie beantwortet, ob Serien
überhaupt Information tragen. Ohne dieses Ja ist die Geldfrage sinnlos; mit dem Ja ist sie die
nächste. Und sie liefert erst ab n=30 ein Urteil, also in einigen Wochen.

**Nebenbefund, vom Guard sofort eingefordert:** eine neu geladene Quelle muss in die
Frische-Rechnung. Beim Serien-Buch mit einer Besonderheit — es wächst nur, wenn eine Serie
abgerechnet wird, also alle paar Tage. Deshalb setzt jeder Recap-Lauf `updatedAt`, auch ohne neue
Zeile: „nichts passiert" und „läuft nicht mehr" dürfen nicht gleich aussehen.

**Gegenbeweis** (fünf Regeln): Ergebnis wieder wegwerfen → 3 Tests fallen; unauflösbare Zeilen
still verschwinden lassen → Test fällt; Punktschätzer statt Untergrenze → Test fällt; Erwartung
nicht mitbuchen → Test fällt; ohne Erwartung trotzdem urteilen → Test fällt.

**Nicht von mir, aber gefunden:** `test_betfair_coherence_fit.py::test_schlechte_fits_werden_
ueberhaupt_aussortiert` ist rot. Er verlangt, dass im LIVE-Bestand mindestens ein Fit an der
RMSE-Schranke scheitert — heute scheitert keiner. Ein Guard, der rot wird, wenn die Daten gut
sind, misst die Daten und nicht den Code. Gehört umgebaut (etwa gegen eine synthetische
Schlecht-Leiter), ist aber ein eigener Vorgang.

## 🎲 08.09.2026 (nachts) — die Serien-Seltenheit rechnete mit dem falschen Nenner

Externes Feedback zur Serien-Seite, an den echten Artefakten nachgerechnet: **es stimmt in jedem
Punkt.** 714 Serien aus Liga + MLS geprüft.

    Parma · Unter 2,5, 10er-Serie
        angezeigt   „1 von 11.990 (Liga-Basis 39 %)"
        daneben     „Eigenrate vor der Serie 80 %"
        richtig     0,8^10 = 1 von 9          →  Faktor 1.290

    Colorado · Beide treffen — Nein, 8er
        angezeigt   1 von 4.554 (Liga-Basis 35 %)
        Eigenrate   57 %  →  1 von 90         →  Faktor 50

Die Liga-Grundrate ist der Nenner für ein **Durchschnittsteam**. Sobald das Team selbst eine
andere Rate hat — und die steht auf derselben Karte —, beantwortet die Zahl eine Frage, die
niemand gestellt hat. Betroffen: **207 von 556** Serien allein in der Liga-Datei.

🔴 **Am 05.09. wurde derselbe Widerspruch schon einmal gesehen** — der Kommentar in
`main-dashboard.js` rechnet „0,83^9 wäre 1 von 5" sogar vor — und damals nur **beschriftet**
statt behoben. Schlimmer: der Test von damals hielt fest, dass die Seltenheit „Liga-Basis" als
Nenner *nennt*, und zementierte damit die falsche Zahl. Genau die Klasse, vor der sein eigener
Kommentar warnte. Und `check_serie_seltenheit_nennt_ihren_nenner` war die ganze Zeit **grün**:
er prüft, dass `zufallPct` sauber aus der Liga-Basis folgt, und das tat sie. *Ein Guard, der die
Arithmetik einer Zahl bewacht, die die falsche Frage beantwortet, meldet nichts.*

### Zwei weitere Funde beim Nachrechnen

1. **Der Punktschätzer trägt nichts.** Parmas 80 % sind **4 von 5 Spielen**. Das 95-%-Band ist
   44 %..95 %, und daraus wird „1 von 2" bis „1 von 4.097" — drei Größenordnungen. Dieselbe
   Klasse wie ein ROI ohne Untergrenze, nur an einer anderen Stelle.
2. **Das Suchfeld.** Gesucht wird über 125 Teams × 11 Märkte × 3 Ansichten = **4.125
   Kombinationen**. Ein „1 von 4.554" ist darin 0,9-mal zu erwarten, ein „1 von 24"
   (Rennes · Team trifft 15×) **175-mal**. Ohne diese Zahl daneben liest man jede Seltenheit als
   Befund. *(Der Einwand „selbst 1-zu-12.000 ist der Erwartungswert" geht mir allerdings zu weit:
   bei 4.125 Kombinationen ist das 0,34-mal zu erwarten, also weiterhin bemerkenswert — wenn der
   Nenner stimmt.)*

### Was jetzt gerechnet wird — `compute_streaks.seltenheit`

- **Nenner ist die eigene Vor-Serien-Rate**, wenn es sie gibt; sonst die Liga-Rate, und dann
  heißt das Urteil **„nicht belegbar"**. Ohne eigene Vorgeschichte gilt der Liga-Schnitt für ein
  Durchschnittsteam — ob dieses Team eines ist, wissen wir gerade nicht. Das ist „nicht
  gemessen", nicht „unauffällig". (Zwei der fünf Serien auf Lucas' Board hatten gar keine
  Eigenrate; die Liga-Basis rutschte still als Default durch.)
- **Band statt Punkt:** `einsZuBand` aus zwei einseitigen Wilson-Grenzen der eigenen Rate.
- **`erwartet`:** wie viele solcher Läufe im getesteten Feld ohnehin zu erwarten sind.
- **Beweislast beim Befund:** „auffällig" nur, wenn selbst mit der *günstigsten* Rate des Bandes
  weniger als ein solcher Lauf im Feld zu erwarten wäre.
- Das Urteil entsteht im **Produzenten**; das Frontend vergleicht nichts mehr selbst.

### Das Ergebnis, und es ist unbequem

    436  keine eigene Vorgeschichte  → nicht belegbar
    278  im Feld erwartbar
      0  auffällig

**Keine einzige der 714 Serien hält einer ehrlichen Prüfung stand.** Das ist die Antwort auf
„machen die Serien Sinn": als *Seltenheits*-Befund nein — und das war nie ihr nützlicher Teil.
`zufallPct` bleibt, aber nur wofür es gebaut war: Märkte untereinander sortierbar machen.

🔴 **Und der eigentliche Grund, warum die Frage bisher unbeantwortbar ist:** `liga_streak_watch.json`
führt **50 beobachtete Serien und 0 Ergebnisse**. Der Streak-Watch postet, bucht aber nie ab. Es
gibt bis heute keine einzige Messung, ob das Folgen einer Serie je Geld gebracht hat.

- ✅ Neuer Guard `check_serie_seltenheit_rechnet_mit_der_eigenen_rate` in der Batterie — er prüft
  den **Nenner**, nicht die Rechnung. Gegenbeweis: fünf verschiedene Manipulationen, jede wird
  gefangen. Der erste Entwurf meldete prompt 8 gesunde Serien (Arsenal „Sieg-Serie 3×": 0,67³ =
  1 von 3,3 → gerundet 3), weil Rate **und** Ergebnis gerundet sind — geprüft wird jetzt gegen
  das Intervall, das die Rundung zulässt.

**Rollout-Lücke:** der Guard steht lokal auf Rot, bis die Pipeline neu gelaufen ist — die
Artefakte auf der Platte stammen von vor der Änderung. Gegen frisch gerechnete Serien: 0 Fehler.

**Offen (braucht eine Entscheidung):** ob der Streak-Watch abrechnen soll und was „der Serie
folgen" heißt — die Fortsetzung zu welchem Preis, bei welchem Buch. Ohne diese Festlegung bleibt
die Frage „machen die Serien Sinn" unbeantwortbar.

## 💶 08.09.2026 (nachts) — Geld ins Kästchen, und warum Poly zwei Zahlen hatte

### Die Bücher-Kästchen zeigen Beträge, nicht Mini-Prozente

Lucas: *„könnte man das optisch nicht ins Kästchen schreiben, wieviel Kohle oben liegt? Bei
Betfair, Poly und Stake. Nur +2 und ganz mini so ein %, das sieht man ja nicht gut — unten in
Ebene 3 ist das mit den Balken optisch besser gelöst."*

- ✅ **Derselbe Aufbau wie die Signal-Zellen in Ebene 3:** Betrag als große Zahl, Anteil als
  Balken, Punkte klein in die Ecke. Die Punkte sind die *Mechanik* des Scores; das Geld ist das,
  wonach man schaut.
- ✅ **Die Zahlen kommen aus dem Produzenten** (`killer._geld` je Buch), nicht aus dem
  Begründungstext. „Geld 88% auf der Seite" wäre als Quelle beim nächsten Satzbau kaputt — und
  der Betrag steht dort ohnehin nie drin.
- 🔴 **`totVol` fehlte im Anker.** Betfair konnte den Anteil zeigen, aber für **48 von 54**
  Zeilen keinen Betrag: Spiele unter der €15.000-Radar-Schwelle laufen über
  `betfair_anker.json`, und dessen Feld-Whitelist enthielt das Volumen nicht — obwohl es längst
  gerechnet war und nur nicht mitkam. Ein Feld ergänzt, kein zusätzlicher API-Call.
- ⭐ **Der teure Teil war nicht der Balken, sondern wann es KEINEN Betrag gibt:**
  · **Poly-Preis:** bei `shareSrc == "preis"` sind die 68 % eine Wahrscheinlichkeit, kein
    Geldanteil. Ein Betrag daraus wäre eine erfundene Zahl an genau der Stelle, auf die Lucas ab
    jetzt schaut. Der Balken stimmt trotzdem (der Anteil ist gemessen), daneben steht „Preis,
    kein Geldanteil" und das Marktvolumen.
  · **Pinnacle** bekommt gar keinen Balken — ein Preisbuch hat kein Geld auf einer Seite, und
    ein leerer Balken sähe aus wie „null Geld".
  · **Anteil ohne Betrag** wird benannt, nie als 0 gerendert.

### Warum die Poly-Kachel und die Track-Record-Seite verschiedene Zahlen zeigten

Lucas: *„aja, und was ist das in Polymarket — im Tracking vom Polymarket-Wallet stehen da andere
Sachen."* Standen da wirklich: **−6,6 %** auf der Kachel, **+0,1 %** auf der Track-Seite. Beide
richtig, beide über eine andere Menge, und keine der beiden sagte welche.

- **Grund 1 — der Engine-Filter (kein Fehler, aber ungesagt):** die Freigabe rechnet nur auf der
  aktuellen Engine-Version — **240 von 644** abgerechneten Plays (320 tragen gar keinen Stempel,
  84 einen älteren). Die Track-Seite zeigt alle. Bei den Public-Kandidaten macht das den ganzen
  Unterschied: **+21,1 % (UG +3,6 %, n=37)** auf der aktuellen Engine gegen **+6,5 % (UG −2,5 %,
  n=175)** über alle — die neue Engine ist dort messbar besser.
- 🔴 **Grund 2 — die gesperrten Kategorien (echter Fehler):** die Track-Seite trennt „bespielbar"
  von „nicht bespielbar" (US-Sport, Kampfsport) und sagt dazu ausdrücklich *„nur Beobachtung,
  kein Geld"*. Die Freigabe zählte sie mit. **Ein Strom-ROI, der Wetten enthält, die gar nicht
  gespielt werden dürfen, beantwortet eine Frage, die niemand hat.** Heute sind es nur 4 der 240
  Plays (Kachel −6,6 % → **−5,6 %**), aber die gesperrten Kategorien laufen bei **−43,2 %**
  (n=53 über alle Engines) — sobald mehr davon in die aktuelle Engine fällt, verzerrt es ernsthaft.
  Gefiltert wird über `poly_shortlist_track._row_cat`, nicht über das rohe Feld: nicht jede Zeile
  trägt einen Stempel, und eine ungestempelte UFC-Zeile landete sonst im bespielbaren Topf. Der
  Wächter in `test_shortlist_kategorie.py` hat genau das beim ersten Versuch gefunden.
- ✅ **Die Kachel sagt ihre Basis jetzt selbst:** *„236 von 644 abgerechneten Plays · nur Engine
  2026-09-01 · ohne Kampfsport, US-Sport"*. Das ist derselbe Satz wie „nach Conviction", nur eine
  Ebene tiefer: worüber wurde gerechnet.

### Zweiter CI-Wachhund des Tages

- ✅ **`efl-trophy`** — dieselbe Klasse wie „reserva" zwei Stunden vorher: die Pokal-Regel kannte
  drei Wörter (Cup, Copa, Pokal). Trophy, Shield, Coupe, Taça sind derselbe Wettbewerbstyp und
  fielen durch. Gegenprobe am Ledger: beantwortet den einen offenen Slug, stuft keinen um.

**Gegenbeweis:** Poly-Preis bekommt einen Betrag → Test fällt; Pinnacle bekommt einen Geldblock
→ Test fällt; fehlender Betrag rendert als 0 → Test fällt; Balken auch ohne Anteil → 9 Tests
fallen; gesperrte Kategorien zählen mit → Test fällt; `basis` auch für Cards → Test fällt.

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
