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

let plays = [], pub = [], blockedCats = [], whales = [];
try { plays = w._pwTopPlays(0, false, false) || []; } catch { plays = []; }
try { pub = w._pwPublicTopPlays() || []; } catch { pub = []; }
// 06.09.2026: die Schatten-Gruppe — alles am Public-Gate ausser der Wallet-Bedingung.
// Wird NICHT gesendet und nicht angezeigt, nur mitgeschrieben (s. _pwTermIsPublicOhneWallet).
let pubOhneWallet = [];
try { pubOhneWallet = w._pwPublicOhneWalletPlays() || []; } catch { pubOhneWallet = []; }

try { blockedCats = w.PW_BLOCKED_BET_CATS || []; } catch { blockedCats = []; }
// 24.08.2026 (Lucas, Whales-Tab): die noch spielbaren offenen Positionen der Top-20-Wallets —
// dieselbe Funktion, die auch der Betting-Tab rendert. Fürs Nachspiel-Papier-Depot.
try { whales = (w._pwWhalePlays ? w._pwWhalePlays() : []) || []; } catch { whales = []; }
for (const p of plays) {
  try { p.cat = w._pwSportCategory(p.league, p.sport); } catch { p.cat = null; }
}

const publicKeys = pub.map(p => p.key + '|' + p.side);
const ohneWalletKeys = pubOhneWallet.map(p => p.key + '|' + p.side);
const out = {
  generatedAt: new Date().toISOString(),
  blockedCats,                       // eine Quelle: kommt aus poly-wallets.js
  whales: whales.map(r => ({
    key: r.key, side: r.side,
    price: (typeof r.price === 'number' ? r.price : null),
    n: r.n, bestRank: r.bestRank,
    conflict: !!r.conflict,
    againstRank: (r.conflict && r.against && r.against[0]) ? r.against[0].bestRank : null,
    league: r.league || null, sport: r.sport || null,
    cat: (() => { try { return w._pwSportCategory(r.league, r.sport); } catch { return null; } })(),
    usd: Math.round(r.usd || 0),
    entryAvg: (r.entryAvg != null ? Math.round(r.entryAvg * 1e4) / 1e4 : null),
    htk: (r.htk == null ? null : Math.round(r.htk * 100) / 100),
  })),
  plays: plays.map(p => ({
    key: p.key, side: p.side, verdict: p.verdict, conv: p.conv,
    match: p.match || null,
    league: p.league || null, sport: p.sport || null,
    // 24.08.2026: Sport-KATEGORIE gleich mitgeben. Das Papier-Depot kann dann nach Sportart
    // aufschluesseln (bespielbar vs. nur beobachtet), ohne _pwSportCategory nach Python zu portieren.
    cat: p.cat || null, htk: (p.htk == null ? null : p.htk),
    moneyPct: (p.moneyPct == null ? null : p.moneyPct),
    price: (typeof p.price === 'number' ? p.price : null),
    // 03.09.2026: woher der Preis stammt. Ein live gepushter Play, dessen Zahlen aus dem
    // Close-Satz kamen, war genau der Fehler vom Hapoel-Push — jetzt faehrt die Basis mit.
    preisQuelle: p.preisQuelle || null,
    reasons: p.reasons || [],
    signals: p.signals || [],
    // 29.08.2026: Engine-Stempel mitgeben. Ohne ihn kann das Papier-Depot spaeter nicht sagen,
    // unter welchen Gewichten ein Play bewertet wurde — und der Kalibrierer lernt quer ueber
    // Engine-Wechsel hinweg (genau das, was der Cards-Lernloop seit dem 04.07. verhindert).
    ev: p.ev || null,
    sharpN: (p.sharp && p.sharp.n) || 0,
    sharpHit: (p.sharp && typeof p.sharp.hit === 'number') ? p.sharp.hit : null,
    public: publicKeys.includes(p.key + '|' + p.side),
    ohneWallet: ohneWalletKeys.includes(p.key + '|' + p.side),
  })),
  public: publicKeys,
  publicOhneWallet: ohneWalletKeys,
};
process.stdout.write(JSON.stringify(out));
