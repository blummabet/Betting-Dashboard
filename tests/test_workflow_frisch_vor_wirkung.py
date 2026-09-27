"""🔴 27.09.2026 — Marsborne (CS2), 26.09. 23:41 und 23:45 UTC: zweimal $5 auf denselben Play,
zwei Order-IDs. Der Waechter `check_ein_play_eine_order` hat es gefunden, ein Mensch nicht.

Hergang: Lauf A setzt um 23:41 und sichert seinen Dedup-Stand sofort (ci_sichern.sh). Lauf B
war um ~23:30 ausgeloest worden und wartete hinter A in der `concurrency`-Schlange. Ein
geplanter Lauf checkt aber den Commit seines AUSLOESE-Zeitpunkts aus, nicht den neuesten —
Lauf B las also ein Buch, in dem A's Wette noch nicht stand, und setzte ein zweites Mal. Die
zweite Schranke (Wallet-Positionen) griff nicht: die Positions-API zeigte die 3,5 Minuten alte
Position noch nicht.

Fehlerklasse: *ein Gedaechtnis, das erst am Ende des Laufs geholt wird, hilft den Schritten
davor nicht.* Die Regel ist deshalb eine ueber ALLE Workflows, nicht ueber diesen einen: in
jedem Job, der etwas sendet oder setzt (TELEGRAM_TOKEN / POLY_PRIVATE_KEY), steht der Pull auf
den neuesten Stand VOR dem ersten solchen Schritt.
"""
import glob
import re
import unittest
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parents[1]
WIRKUNG = re.compile(r"\b(TELEGRAM_TOKEN|POLY_PRIVATE_KEY)\b")
PULL = re.compile(r"ci_pull\.sh|git pull")


class TestFrischVorWirkung(unittest.TestCase):
    def test_jeder_wirkende_job_holt_zuerst_den_neuesten_stand(self):
        fehler = []
        for f in sorted(glob.glob(str(BASE / ".github" / "workflows" / "*.yml"))):
            d = yaml.safe_load(Path(f).read_text(encoding="utf-8")) or {}
            for jn, job in (d.get("jobs") or {}).items():
                gepullt = False
                for s in job.get("steps") or []:
                    roh = yaml.safe_dump(s, allow_unicode=True)
                    if PULL.search(str(s.get("run") or "")):
                        gepullt = True
                    if WIRKUNG.search(roh) and not gepullt:
                        fehler.append("%s/%s: „%s“ wirkt vor dem ersten Pull"
                                      % (Path(f).name, jn, s.get("name") or "?"))
                        break
        self.assertEqual(fehler, [], "\n".join(fehler))


if __name__ == "__main__":
    unittest.main()
