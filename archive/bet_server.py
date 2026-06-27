#!/usr/bin/env python3
"""
bet_server.py — Lokaler HTTP Server für Polymarket Bet Placement
================================================================
Läuft auf localhost:7777 und empfängt Orders vom Dashboard.
Kein GitHub Actions Runner nötig — läuft direkt auf dem Mac.

Start: python3 bet_server.py
  oder: Doppelklick auf start-bet-server.command
"""

import json
import os
import sys
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT = 7777
BASE_DIR = Path(__file__).parent

class BetHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Kompakteres Logging
        print(f"  [{self.command}] {self.path} — {args[0]}")

    def do_OPTIONS(self):
        """CORS preflight"""
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path != '/place-bets':
            self.send_error(404)
            return

        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)

        try:
            payload = json.loads(body)
            orders = payload.get('orders', [])
        except Exception as e:
            self.send_error(400, f"Invalid JSON: {e}")
            return

        if not orders:
            self._respond(200, {"status": "ok", "message": "Keine Orders"})
            return

        print(f"\n🟣 {len(orders)} Order(s) empfangen:")
        for o in orders:
            print(f"   {o.get('home')} vs {o.get('away')} — {o.get('market')}")

        # POLY_PRIVATE_KEY aus Umgebung lesen (in .env Datei oder direkt gesetzt)
        private_key = os.environ.get('POLY_PRIVATE_KEY', '').strip()
        if not private_key:
            env_file = BASE_DIR / '.env.local'
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith('POLY_PRIVATE_KEY='):
                        private_key = line.split('=', 1)[1].strip().strip('"').strip("'")
                        break

        if not private_key:
            msg = "POLY_PRIVATE_KEY nicht gesetzt — bitte in .env.local eintragen"
            print(f"❌ {msg}")
            self._respond(500, {"status": "error", "message": msg})
            return

        env = {**os.environ,
               'POLY_PRIVATE_KEY': private_key,
               'ORDERS_JSON': json.dumps(orders)}

        result = subprocess.run(
            [sys.executable, str(BASE_DIR / 'polymarket_bet.py')],
            env=env,
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR),
        )

        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        if result.returncode == 0:
            self._respond(200, {"status": "ok", "output": result.stdout})
        else:
            self._respond(500, {"status": "error", "output": result.stdout, "stderr": result.stderr})

    def do_GET(self):
        if self.path == '/health':
            self._respond(200, {"status": "running", "port": PORT})
        else:
            self.send_error(404)

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _respond(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self._cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    print(f"\n🟣 BetEdge Bet Server")
    print(f"   Port: {PORT}")
    print(f"   Verzeichnis: {BASE_DIR}")

    env_file = BASE_DIR / '.env.local'
    if not env_file.exists():
        print(f"\n⚠️  Kein .env.local gefunden!")
        print(f"   Erstelle {env_file}")
        print(f"   und trage ein: POLY_PRIVATE_KEY=0x...")
    else:
        print(f"   ✅ .env.local gefunden")

    print(f"\n✅ Server läuft auf http://localhost:{PORT}")
    print(f"   Warte auf Orders vom Dashboard...\n")

    try:
        server = HTTPServer(('localhost', PORT), BetHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹  Server gestoppt.")
