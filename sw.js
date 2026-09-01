/* CocoBet Service Worker (28.06.2026) — installierbare PWA + Offline.
 *
 * Strategie (wichtig: KEINE veralteten Picks/Code):
 *   - Daten (*.json)        → network-first, Cache nur als Offline-Fallback.
 *   - Navigation (HTML)     → network-first, Cache-Fallback (season-finish-v2.html).
 *   - App-Code (JS/CSS)     → network-first (29.06.2026 Fix: SWR lieferte dauerhaft die ALTE
 *                             Version → „seit gestern keine Änderungen". Jetzt frisch online,
 *                             Cache nur offline). Bilder bleiben stale-while-revalidate.
 *   - Fremd-Origin (CDN)    → unangetastet durchlassen.
 *
 * Cache-Version bei jedem Hüllen-Update hochzählen → alte Caches werden beim activate gelöscht.
 */
const VERSION = 'cocobet-v199';   // 01.09.2026: Uebersicht — Lesebreite gedeckelt, Spiele ab 1040px zweispaltig; Money-Map-Rendite.

// App-Hülle (entspricht dem Script-Loader in season-finish-v2.html). Relative Pfade,
// weil die App in einem GitHub-Pages-Unterpfad (/Betting-Dashboard/) liegt.
const SHELL = [
  './season-finish-v2.html',
  './pick-engine.js', './pick-verdict.js', './_pick_helpers.js', './validator.js',
  './renderer.js', './share.js', './ui.js', './status-checks.js', './polymarket-tab.js',
  './poly-wallets.js', './betfair-radar.js', './pinnacle-poly.js', './main-dashboard.js', './results-v2.js', './wm2026-renderer.js', './wm2026-tracking.js',
  './tiktok-studio.js', './tiktok-studio.css',
  './cocobet-logo.png',
  './icons/icon-180.png', './icons/icon-192.png', './icons/icon-512.png', './icons/icon-512-maskable.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(VERSION)
      .then((c) => Promise.allSettled(SHELL.map((u) => c.add(u))))  // einzelne Fehler nicht fatal
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // CDN etc. normal lassen

  // Daten: network-first (frische Picks online), Cache-Fallback offline.
  if (url.pathname.endsWith('.json')) {
    e.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copy));
          return res;
        })
        .catch(() => caches.match(req, { ignoreSearch: true }))
    );
    return;
  }

  // Navigation: frische Seite online, Hülle offline.
  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req, { cache: 'reload' })
        .then((res) => {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put('./season-finish-v2.html', copy));
          return res;
        })
        .catch(() => caches.match('./season-finish-v2.html', { ignoreSearch: true }))
    );
    return;
  }

  // App-Code (JS/CSS): network-first → online IMMER der frische Code, Cache nur als Offline-Fallback.
  if (url.pathname.endsWith('.js') || url.pathname.endsWith('.css')) {
    e.respondWith(
      fetch(req, { cache: 'reload' })
        .then((res) => {
          if (res && res.status === 200) {
            const copy = res.clone();
            caches.open(VERSION).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req, { ignoreSearch: true }))
    );
    return;
  }

  // Bilder/sonstige Hülle: stale-while-revalidate (ändern sich selten, dürfen schnell sein).
  e.respondWith(
    caches.match(req, { ignoreSearch: true }).then((cached) => {
      const fromNet = fetch(req)
        .then((res) => {
          if (res && res.status === 200) {
            const copy = res.clone();
            caches.open(VERSION).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => cached);
      return cached || fromNet;
    })
  );
});
