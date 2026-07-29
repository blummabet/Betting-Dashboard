# Mac-Timer: Betfair-Fetcher verlässlich alle 15 Min auslösen

**Warum:** GitHubs Scheduler feuert den `*/15`-Cron nur sporadisch (Lücken bis 1–2 h) →
die Betwatch-Daten waren teils 50+ Min alt. Dein Mac läuft eh durch, also lässt der Mac
den Workflow alle 15 Min an. Der Workflow läuft weiter auf GitHub (deinem **Mac-Runner**,
Österreich-IP, mit dem `BETWATCH_KEY`-Secret) — nur der *Auslöser* kommt vom Mac statt von
GitHubs flakigem Scheduler. Exakt dasselbe Prinzip wie dein Poly-Timer.

## Der einfache Weg (empfohlen)

Doppelklick auf **`⏱️ Betfair-Timer einrichten.command`** im Projektordner. Das Skript
legt alles an, testet einmal und lädt den Timer. Fertig.

> Nutzt denselben Token wie der Poly-Timer (`~/.poly_gh_token`) — kein neuer Token nötig.
> Falls beim ersten Mal „macht nix auf": Rechtsklick → **Öffnen** (Gatekeeper einmalig bestätigen).

---

## Manuell (falls du es lieber Schritt für Schritt machst)

Alle Befehle als dein User (`lb`), **nicht** als root.

**1. Trigger-Script** (nutzt den vorhandenen Poly-Token):
```bash
cat > ~/betfair-trigger.sh <<'EOF'
#!/bin/bash
TOKEN=$(cat "$HOME/.poly_gh_token")
CODE=$(curl -s -o /tmp/betfairtrigger.out -w "%{http_code}" -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/blummabet/Betting-Dashboard/actions/workflows/betfair.yml/dispatches \
  -d '{"ref":"main"}')
echo "$(date '+%Y-%m-%d %H:%M') HTTP $CODE" >> /tmp/betfairtrigger.log
EOF
chmod +x ~/betfair-trigger.sh
~/betfair-trigger.sh ; tail -n1 /tmp/betfairtrigger.log   # erwartet: HTTP 204
```

**2. launchd-Timer (alle 15 Min):**
```bash
cat > ~/Library/LaunchAgents/com.blummabet.betfairtrigger.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.blummabet.betfairtrigger</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/lb/betfair-trigger.sh</string>
  </array>
  <key>StartInterval</key><integer>900</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>/tmp/betfairtrigger.log</string>
  <key>StandardErrorPath</key><string>/tmp/betfairtrigger.err</string>
</dict>
</plist>
EOF
launchctl unload ~/Library/LaunchAgents/com.blummabet.betfairtrigger.plist 2>/dev/null
launchctl load  ~/Library/LaunchAgents/com.blummabet.betfairtrigger.plist
launchctl list | grep betfairtrigger   # eine Zeile = läuft
```

---

## Was du jetzt erwartest
- In **Actions** kommt ab sofort alle 15 Min ein „🟡 Betfair Radar (Betwatch)"-Lauf,
  verlässlich, egal was GitHubs Scheduler macht.
- Der `*/15`-Cron im Workflow bleibt als Backup drin (Doppelläufe schaden nicht — der
  Mac-Runner serialisiert, Commit läuft mit Pull-Retry).
- Das „Daten sind X Min alt"-Banner im Radar sollte damit dauerhaft unter ~15 Min bleiben.

## Voraussetzungen (wie beim Poly-Timer)
- Mac am Strom, Deckel offen, eingeloggt (der Timer ist ein LaunchAgent → läuft, solange
  du eingeloggt bist; Auto-Login übersteht Neustarts). `SleepDisabled 1` hast du schon.

## Abschalten (falls je nötig)
```bash
launchctl unload ~/Library/LaunchAgents/com.blummabet.betfairtrigger.plist
```
