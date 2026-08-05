// scripts/emit_shortlist.mjs — 02.08.2026 (Lucas): Snapshot der „Heute spielenswert"-Shortlist
// für das Paper-Track-Record. Lädt die ECHTE Frontend-Engine (poly-wallets.js) in jsdom gegen die
// lokalen JSON-Dateien und gibt exakt die Plays aus, die der Nutzer sieht — kein Python-Port, kein
// Drift. Ausgabe: JSON auf stdout { generatedAt, plays:[...], public:[ "key|side", ... ] }.
// Datenverzeichnis: $SHORTLIST_DATA_DIR (Default: Repo-Wurzel neben dieser Datei).
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, dirname } from 'node:path';
import { JSDOM } from 'jsdom';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, '..');
const DATA_DIR = process.env.SHORTLIST_DATA_DIR || REPO;
const PW = join(REPO, 'poly-wallets.js');

function mockFetch() {
  return (url) => {
    const name = String(url).split('?')[0].split('/').pop();
    try {
      const body = JSON.parse(readFileSync(join(DATA_DIR, name), 'utf8'));
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
    } catch {
      return Promise.resolve({ ok: false, json: () => Promise.resolve(null) });
    }
  };
}

const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
  { url: 'https://cocobet.local/', runScripts: 'outside-only', pretendToBeVisual: true });
const w = dom.window;
w.fetch = mockFetch();
w.eval(readFileSync(PW, 'utf8'));

await new Promise((res) => w._pwEnsurePlaysData(res));

let plays = [], pub = [];
try { plays = w._pwTopPlays(0, false, false) || []; } catch { plays = []; }
try { pub = w._pwPublicTopPlays() || []; } catch { pub = []; }

const publicKeys = pub.map(p => p.key + '|' + p.side);
const out = {
  generatedAt: new Date().toISOString(),
  plays: plays.map(p => ({
    key: p.key, side: p.side, verdict: p.verdict, conv: p.conv,
    league: p.league || null, htk: (p.htk == null ? null : p.htk),
    moneyPct: (p.moneyPct == null ? null : p.moneyPct),
    price: (typeof p.price === 'number' ? p.price : null),
    reasons: p.reasons || [],
    signals: p.signals || [],
    sharpN: (p.sharp && p.sharp.n) || 0,
    sharpHit: (p.sharp && typeof p.sharp.hit === 'number') ? p.sharp.hit : null,
    public: publicKeys.includes(p.key + '|' + p.side),
  })),
  public: publicKeys,
};
process.stdout.write(JSON.stringify(out));
