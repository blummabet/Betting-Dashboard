// ═══════════════════════════════════════════════════════
//  poly-wallets.js — „Polymarket Wallets"-Tab (21.06.2026, Lucas)
//
//  Zeigt die fetten Einzel-Einsätze auf den WM-Märkten:
//    1. Größte Einzel-Positionen (Leaderboard, aus /holders)
//    2. Letzte große Trades (Feed, aus /trades)
//
//  Datenquelle: wm_poly_wallets.json (von fetch_wm_poly_smartmoney.py auf dem
//  Mac-Runner geschrieben — Polymarket ist geoblockt, läuft nur dort).
//  WM-Märkte only. Wallets sind on-chain öffentlich → Link aufs Polymarket-Profil.
// ═══════════════════════════════════════════════════════

let _polyWalletsLoaded = false;

function initPolyWallets() {
  const panel = document.getElementById('polyWalletsPanel');
  if (!panel) return;
  if (_polyWalletsLoaded) return;          // einmal laden reicht (Tab-Wechsel)
  _polyWalletsLoaded = true;
  panel.innerHTML = '<p style="color:#76819c;text-align:center;padding:40px">🐋 Lade Wallet-Daten…</p>';
  fetch('wm_poly_wallets.json?t=' + Date.now(), { cache: 'no-store' })
    .then(r => r.ok ? r.json() : null)
    .catch(() => null)
    .then(d => renderPolyWallets(panel, d));
}

function _pwUsd(v) {
  const n = Number(v) || 0;
  if (n >= 1e6) return '$' + (n / 1e6).toFixed(2) + 'M';
  if (n >= 1e3) return '$' + (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + 'K';
  return '$' + Math.round(n);
}
function _pwWallet(w) {
  if (!w) return '—';
  const s = String(w);
  return s.length > 12 ? s.slice(0, 6) + '…' + s.slice(-4) : s;
}
function _pwSideColor(side) {
  return side === 'home' ? '#4cc2ff' : side === 'away' ? '#ff5d5d' : '#f5c518';
}
function _pwLink(w) { return 'https://polymarket.com/profile/' + encodeURIComponent(w); }

function renderPolyWallets(panel, data) {
  const positions = (data && data.topPositionsAll) || [];
  const trades    = (data && data.bigTradesAll) || [];
  const upd = data && data.updatedAt ? (typeof _timeAgo === 'function' ? _timeAgo(data.updatedAt) : data.updatedAt) : '—';

  if (!data || (!positions.length && !trades.length)) {
    panel.innerHTML =
      '<div style="max-width:680px;margin:40px auto;text-align:center;color:#76819c;line-height:1.7">'
      + '<div style="font-size:40px;margin-bottom:12px">🐋</div>'
      + '<h2 style="color:#e6ebf5;font-weight:700;margin:0 0 8px">Polymarket Wallets</h2>'
      + '<p>Noch keine Wallet-Daten verfügbar. Der Runner befüllt <code>wm_poly_wallets.json</code> '
      + 'stündlich aus der Polymarket-API (geoblockt → läuft nur auf dem Mac-Runner). '
      + 'Sobald Daten da sind, erscheinen hier die fettesten Einsätze auf die WM-Märkte.</p></div>';
    return;
  }

  const header =
    '<div style="display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:6px">'
    + '<h2 style="color:#e6ebf5;font-weight:800;margin:0;font-size:22px">🐋 Polymarket Wallets</h2>'
    + '<span style="color:#76819c;font-size:12px">WM-Märkte · Stand ' + upd + '</span></div>'
    + '<p style="color:#76819c;font-size:13px;margin:0 0 22px;line-height:1.6">Wo das große Geld liegt: '
    + 'die größten Einzel-Positionen und die jüngsten fetten Trades. Klick auf ein Wallet → Polymarket-Profil. '
    + 'Beträge sind geschätzt (Anteile × aktueller Preis).</p>';

  // ── 1. Größte Einzel-Positionen ──
  let posHTML =
    '<div style="margin-bottom:34px"><div style="font-size:11px;font-weight:800;letter-spacing:1.2px;'
    + 'text-transform:uppercase;color:#5eead4;margin-bottom:12px">Größte Einzel-Positionen</div>';
  if (!positions.length) {
    posHTML += '<p style="color:#76819c;font-size:13px">Keine Positionen erfasst.</p>';
  } else {
    posHTML += '<div style="display:flex;flex-direction:column;gap:7px">';
    positions.forEach((p, i) => {
      const c = _pwSideColor(p.side);
      posHTML +=
        '<div style="display:grid;grid-template-columns:28px 1fr auto;gap:12px;align-items:center;'
        + 'background:#0f1626;border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:11px 14px">'
        + '<span style="font-family:monospace;font-weight:800;color:' + (i < 3 ? '#5eead4' : '#414c66') + ';font-size:13px">' + (i + 1) + '</span>'
        + '<div style="min-width:0">'
        +   '<a href="' + _pwLink(p.wallet) + '" target="_blank" rel="noopener" style="font-family:monospace;font-size:13px;color:#e6ebf5;text-decoration:none;border-bottom:1px dashed #414c66">' + _pwWallet(p.wallet) + '</a>'
        +   '<div style="font-size:11px;color:#76819c;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
        +     '<span style="color:' + c + ';font-weight:700">' + (p.pick || p.side) + '</span> · ' + (p.match || p.key || '') + '</div>'
        + '</div>'
        + '<span style="font-family:monospace;font-weight:800;font-size:16px;color:#e6ebf5;white-space:nowrap">' + _pwUsd(p.usd) + '</span>'
        + '</div>';
    });
    posHTML += '</div>';
  }
  posHTML += '</div>';

  // ── 2. Letzte große Trades ──
  let trHTML =
    '<div><div style="font-size:11px;font-weight:800;letter-spacing:1.2px;text-transform:uppercase;'
    + 'color:#5eead4;margin-bottom:12px">Letzte große Trades</div>';
  if (!trades.length) {
    trHTML += '<p style="color:#76819c;font-size:13px">Keine großen Trades im Fenster.</p>';
  } else {
    trHTML += '<div style="display:flex;flex-direction:column;gap:7px">';
    trades.forEach(t => {
      const c = _pwSideColor(t.side);
      const isBuy = (t.action || '').toUpperCase() === 'BUY';
      const ago = t.ts && typeof _timeAgo === 'function' ? _timeAgo(t.ts) : '';
      trHTML +=
        '<div style="display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:center;'
        + 'background:#0f1626;border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:11px 14px">'
        + '<span style="font-size:10px;font-weight:800;padding:3px 8px;border-radius:6px;white-space:nowrap;'
        +   'background:' + (isBuy ? 'rgba(45,212,126,.14)' : 'rgba(255,93,93,.14)') + ';color:' + (isBuy ? '#2dd47e' : '#ff5d5d') + '">'
        +   (isBuy ? 'KAUF' : (t.action === 'SELL' ? 'VERKAUF' : (t.action || '—'))) + '</span>'
        + '<div style="min-width:0">'
        +   '<a href="' + _pwLink(t.wallet) + '" target="_blank" rel="noopener" style="font-family:monospace;font-size:13px;color:#e6ebf5;text-decoration:none;border-bottom:1px dashed #414c66">' + _pwWallet(t.wallet) + '</a>'
        +   '<div style="font-size:11px;color:#76819c;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
        +     '<span style="color:' + c + ';font-weight:700">' + (t.pick || t.side) + '</span> · ' + (t.match || t.key || '') + (ago ? ' · ' + ago : '') + '</div>'
        + '</div>'
        + '<span style="font-family:monospace;font-weight:800;font-size:15px;color:#e6ebf5;white-space:nowrap">' + _pwUsd(t.usd) + '</span>'
        + '</div>';
    });
    trHTML += '</div>';
  }
  trHTML += '</div>';

  panel.innerHTML = header + posHTML + trHTML;
}
