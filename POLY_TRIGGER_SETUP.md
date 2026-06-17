# Mac-Timer: manage-wm-poly verlässlich alle 15min auslösen

**Warum:** GitHubs Scheduler feuert den 0,30-Cron nur sporadisch (Lücken 1-3h). Dein Mac
läuft jetzt eh durch (SleepDisabled 1) — also lassen wir den **Mac** den Workflow alle
15min anstoßen. Der Workflow läuft weiter auf GitHub (auf deinem Mac-Runner), nur der
*Auslöser* kommt vom Mac statt von GitHubs flakigem Scheduler. Bombenfest.

Alle Befehle als dein normaler User (`lb`), **nicht** als root.

---

## 1. Fine-grained Token erstellen (1×)

GitHub → oben rechts dein Profilbild → **Settings → Developer settings → Personal access
tokens → Fine-grained tokens → Generate new token**.

- **Token name:** `poly-trigger`
- **Expiration:** 1 year (oder „No expiration")
- **Repository access:** „Only select repositories" → **blummabet/Betting-Dashboard**
- **Permissions → Repository permissions → Actions:** auf **Read and write** stellen
- **Generate token** → den Token (beginnt mit `github_pat_…`) **kopieren** (siehst du nur 1×)

Token auf dem Mac sicher ablegen (Terminal):
```bash
echo 'HIER_DEN_TOKEN_EINFÜGEN' > ~/.poly_gh_token
chmod 600 ~/.poly_gh_token
```

---

## 2. Trigger-Script anlegen

```bash
cat > ~/poly-trigger.sh <<'EOF'
#!/bin/bash
TOKEN=$(cat "$HOME/.poly_gh_token")
curl -s -o /tmp/polytrigger.out -w "%{http_code}" -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/blummabet/Betting-Dashboard/actions/workflows/manage-wm-poly.yml/dispatches \
  -d '{"ref":"main"}'
echo " [$(date '+%H:%M')]" >> /tmp/polytrigger.log
EOF
chmod +x ~/poly-trigger.sh
```

**Sofort testen:**
```bash
~/poly-trigger.sh ; cat /tmp/polytrigger.out
```
- Gibt es **kein** sichtbares Fehler-JSON aus (leere `/tmp/polytrigger.out` + HTTP 204) →
  passt. In GitHub → Actions sollte gleich ein neuer „WM Poly Positionen überwachen"-Lauf
  („Manually run / API") auftauchen.
- Kommt ein JSON mit „Bad credentials" / „Not Found" → Token/Permission stimmt nicht
  (Schritt 1 prüfen: richtiges Repo + Actions: Read and write).

---

## 3. launchd-Timer (alle 15min, auto-Start)

```bash
cat > ~/Library/LaunchAgents/com.blummabet.polytrigger.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.blummabet.polytrigger</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/lb/poly-trigger.sh</string>
  </array>
  <key>StartInterval</key><integer>900</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>/tmp/polytrigger.log</string>
  <key>StandardErrorPath</key><string>/tmp/polytrigger.err</string>
</dict>
</plist>
EOF

launchctl unload ~/Library/LaunchAgents/com.blummabet.polytrigger.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.blummabet.polytrigger.plist
```

`StartInterval 900` = alle 900 Sekunden = 15min. `RunAtLoad` = startet sofort einmal.

**Prüfen, dass er geladen ist:**
```bash
launchctl list | grep polytrigger
```
Eine Zeile mit `com.blummabet.polytrigger` = läuft. Ab jetzt feuert er alle 15min.

---

## Fertig — was du jetzt erwartest

- In **Actions** kommt ab sofort **alle 15min** ein „WM Poly Positionen überwachen"-Lauf,
  verlässlich, egal was GitHubs Scheduler macht.
- Der 0,30-Cron im Workflow bleibt als Backup drin (doppelte Läufe schaden nicht — der
  Mac-Runner serialisiert eh, und Trades sind dedupliziert).
- Damit feuert dein **40min-Close** zuverlässig, und der Auto-Trader handelt rund um die Uhr.

## Voraussetzungen (gelten weiter)
- Mac am Strom, **Deckel offen**, eingeloggt (der Timer ist wie der Runner ein LaunchAgent
  → läuft, solange du eingeloggt bist). Auto-Login an = übersteht Neustarts.
- `SleepDisabled 1` (hast du) → kein System-Sleep.

## Abschalten (falls je nötig)
```bash
launchctl unload ~/Library/LaunchAgents/com.blummabet.polytrigger.plist
```
