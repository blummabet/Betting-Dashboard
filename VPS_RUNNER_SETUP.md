> ⛔️ **VERALTET / FUNKTIONIERT NICHT (07.07.2026).** Der EU-VPS wurde ausprobiert und von
> **Polymarket trotz DE/EU-Standort GEBLOCKT** (Region-Restriction) — hat Geld für nichts gekostet.
> Die Annahme unten („EU = erlaubte Region ✅") ist in der Praxis FALSCH. **Diesen Weg NICHT gehen.**
> Der einzige tragfähige Poly-Trading-Runner ist Lucas' **Mac** (erlaubte Region). Für Neustarts:
> Runner als Service installieren (`actions-runner/svc.sh install` + `start`) + Mac wachhalten.

# EU-VPS Self-Hosted Runner — Setup für manage-wm-poly

**Warum:** Der Auto-Trader (`manage-wm-poly`) braucht einen Runner, der **immer an** UND **in einer erlaubten Region** ist:
- GitHub-Cloud-Runner (ubuntu-latest) → von Polymarket **geoblockt** (403 „Trading restricted in your region", US-Region).
- Dein Mac → erlaubte Region, aber **schläft** → geplante Läufe feuern nicht.
- **EU-VPS** → immer an + erlaubte Region + Mac-unabhängig. ✅

Der Workflow zielt jetzt auf `runs-on: [self-hosted, linux]` — das trifft **nur den Linux-VPS**, nicht deinen Mac (macOS-Label). `poly-bets.yml` (manuelles Wetten) bleibt auf dem Mac.

---

## 1. VPS mieten (~4 €/Monat)

**Hetzner Cloud** (empfohlen): https://console.hetzner.cloud
- Server-Typ: **CX22** (2 vCPU, 4 GB RAM) reicht locker — ~4 €/Monat.
- Image: **Ubuntu 24.04**.
- Standort: **Nürnberg oder Falkenstein (Deutschland)** — geografisch bei dir, gleiche erlaubte Region wie dein Mac in Österreich. (Falls Polymarket bei einem Standort zickt: anderen DE-Standort nehmen.)
- SSH-Key hinterlegen (oder Passwort-Login).

Alternativen: Netcup (Wien/DE), Contabo, IONOS — Hauptsache **EU-Standort**.

---

## 2. Auf den VPS einloggen + Grundpakete

```bash
ssh root@DEINE_VPS_IP

# System + Python 3.11 + Git + Build-Tools
apt update && apt -y upgrade
apt -y install git curl python3.11 python3.11-venv python3-pip build-essential

# Eigenen User für den Runner (nicht als root laufen lassen)
adduser --disabled-password --gecos "" runner
usermod -aG sudo runner
su - runner
```

---

## 3. GitHub Actions Runner installieren

1. Im Browser: **Repo → Settings → Actions → Runners → New self-hosted runner → Linux**.
2. GitHub zeigt dir die exakten Befehle mit einem **Token** (gültig ~1h). Auf dem VPS als User `runner` ausführen — ungefähr so:

```bash
mkdir actions-runner && cd actions-runner
curl -o actions-runner-linux-x64.tar.gz -L https://github.com/actions/runner/releases/download/vX.Y.Z/actions-runner-linux-x64-X.Y.Z.tar.gz
tar xzf actions-runner-linux-x64.tar.gz

# Konfigurieren — Token + URL aus der GitHub-Seite einsetzen:
./config.sh --url https://github.com/blummabet/Betting-Dashboard --token DEIN_TOKEN
```

Bei `config.sh` die Fragen so beantworten:
- **Runner group:** Enter (Default)
- **Runner name:** z.B. `poly-vps`
- **Additional labels:** Enter (das automatische `linux`-Label reicht — der Workflow nutzt `[self-hosted, linux]`)
- **Work folder:** Enter (Default `_work`)

---

## 4. Als Dienst installieren (immer an + Auto-Restart)

```bash
sudo ./svc.sh install runner
sudo ./svc.sh start
sudo ./svc.sh status      # sollte "active (running)" zeigen
```

Damit läuft der Runner als systemd-Service — startet beim Boot automatisch, übersteht Neustarts, läuft 24/7.

---

## 5. Prüfen + Testen

1. **Repo → Settings → Actions → Runners** — `poly-vps` muss **🟢 Idle** (online) zeigen.
2. **Actions → „💹 WM Poly Positionen überwachen" → Run workflow** (manuell auslösen).
3. Im Log checken:
   - `✅ py-clob-client-v2 ok` (Setup klappt)
   - Auto-Trigger: **KEIN 403-Geoblock mehr** — Orders gehen durch (oder „0 Kandidaten", wenn grad kein Edge da ist)
   - Am Ende ein `💹 WM Poly Update`-Commit

Wenn Schritt 2 sauber durchläuft + kein 403 kommt → **fertig**. Ab dann feuern die geplanten 0,30-Läufe zuverlässig auf dem VPS, rund um die Uhr, in erlaubter Region.

---

## Hinweise

- **Mac-Runner:** kannst du parallel laufen lassen (für `poly-bets.yml`) oder abdrehen — `manage-wm-poly` geht durch das `linux`-Label eh nur auf den VPS.
- **Kosten:** ~4 €/Monat VPS. Die TheOddsAPI-Quota (5M) läuft davon unabhängig weiter.
- **Sicherheit:** Die Secrets (`POLY_PRIVATE_KEY` etc.) kommen wie gehabt von GitHub und werden nur zur Laufzeit in den Job injiziert — sie liegen nicht dauerhaft auf dem VPS.
- **Updates:** Der Runner aktualisiert sich selbst. Python-Deps werden pro Lauf frisch in `.venv` installiert (~30s).
- **Falls Geoblock trotz EU-VPS:** anderen EU-Standort wählen (Polymarket sperrt einzelne Länder regulatorisch, z.B. zeitweise FR) — DE/AT sind erfahrungsgemäß ok, da dein Mac dort auch funktioniert.
