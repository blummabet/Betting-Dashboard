import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
const w = dom.window; w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
try { w.eval(readFileSync(process.cwd()+'/poly-wallets.js','utf8')); } catch(e){ console.log('load err', e.message); }
console.log(typeof w._pwPlayLabel);
try { console.log(w._pwPlayLabel('epl-ars-lee-2026-10-10-more-markets',[{s:'Over'},{s:'Under'}])); } catch(e){console.log('err',e.message)}
try { console.log(w._pwPrettyKey('epl-ars-lee-2026-10-10-more-markets')); } catch(e){console.log('err',e.message)}
