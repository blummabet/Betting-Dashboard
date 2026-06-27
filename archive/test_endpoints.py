import urllib.request, json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.sofascore.com/",
    "Origin": "https://www.sofascore.com",
}

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode()), r.status
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception as e:
        return None, str(e)

team_id = 36  # Spurs — bekannt aus euren Daten

print("=== Team Events Endpoints ===")
for ep in ["last", "previous", "lastevents"]:
    data, status = fetch(f"https://api.sofascore.com/api/v1/team/{team_id}/events/{ep}/0")
    n = len(data.get("events", [])) if data else 0
    print(f"  /{ep}/0 → HTTP {status}  ({n} events)")

# Spurs vs Liverpool event aus euren Daten → eventId brauchen wir
# Hole erst die Premier League Season
print("\n=== H2H Endpoint Test ===")
tid = 17  # EPL
seasons, _ = fetch(f"https://api.sofascore.com/api/v1/unique-tournament/{tid}/seasons")
sid = seasons["seasons"][0]["id"] if seasons else None
print(f"  EPL Season ID: {sid}")

if sid:
    events_data, _ = fetch(f"https://api.sofascore.com/api/v1/unique-tournament/{tid}/season/{sid}/events/next/0")
    if events_data and events_data.get("events"):
        ev = events_data["events"][0]
        eid = ev["id"]
        home = ev["homeTeam"]["name"]
        away = ev["awayTeam"]["name"]
        print(f"  Testing H2H for event {eid}: {home} vs {away}")
        h2h_data, h2h_status = fetch(f"https://api.sofascore.com/api/v1/event/{eid}/h2h")
        print(f"  H2H endpoint → HTTP {h2h_status}")
        if h2h_data:
            for k in h2h_data.keys():
                n = len(h2h_data[k]) if isinstance(h2h_data[k], list) else '?'
                print(f"    key '{k}': {n} items")

