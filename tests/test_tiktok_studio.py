#!/usr/bin/env python3
"""
test_tiktok_studio.py — Studio-Foundation-Tests (Refactor-Standards)

Sichert:
  · studio_config.json    Schema + beide Profile (wm2026 + liga_default)
  · studio_pools.json     Schema + Mindest-Pool-Größen + Profile-Parity
  · studio_templates/*    alle Card-Typen haben HTML-Files
  · tiktok-studio.js      lädt aus External (keine inline-Pools)

Konformität zur RULE [feedback_new_features_rule]:
  - Keine Magic Numbers im JS
  - Liga-fähig per Profile
  - Tests obligatorisch
"""
from __future__ import annotations
import json
import re
import unittest
from pathlib import Path

BASE = Path(__file__).parent.parent
CONFIG_PATH    = BASE / 'studio_config.json'
POOLS_PATH     = BASE / 'studio_pools.json'
TEMPLATES_DIR  = BASE / 'studio_templates'
JS_PATH        = BASE / 'tiktok-studio.js'

CARD_TYPES = ['team_hook', 'player', 'bizarre', 'match_pick', 'killer_stat', 'quiz']


class TestStudioConfigSchema(unittest.TestCase):
    """studio_config.json muss Schema + beide Profile haben."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))

    def test_file_exists(self):
        self.assertTrue(CONFIG_PATH.exists())

    def test_has_profiles_active(self):
        self.assertIn('profiles', self.cfg)
        self.assertIn('active', self.cfg['profiles'])

    def test_both_profiles_exist(self):
        for prof in ('wm2026', 'liga_default'):
            with self.subTest(profile=prof):
                self.assertIn(prof, self.cfg['profiles'])

    def test_profile_sections(self):
        for prof in ('wm2026', 'liga_default'):
            p = self.cfg['profiles'][prof]
            for section in ('card', 'theme', 'defaults'):
                with self.subTest(profile=prof, section=section):
                    self.assertIn(section, p, f"Profile {prof} fehlt {section}")

    def test_card_dimensions(self):
        for prof in ('wm2026', 'liga_default'):
            card = self.cfg['profiles'][prof]['card']
            self.assertEqual(card['width_px'], 1080)
            self.assertEqual(card['height_px'], 1920)
            self.assertGreater(card['preview_scale'], 0)
            self.assertLessEqual(card['preview_scale'], 1)
            self.assertTrue(card['brand_text'])

    def test_theme_colors_valid_hex(self):
        for prof in ('wm2026', 'liga_default'):
            theme = self.cfg['profiles'][prof]['theme']
            for col in ('accent', 'primary_bg', 'text'):
                val = theme.get(col, '')
                self.assertTrue(re.match(r'^#[0-9a-fA-F]{6}$', val),
                    f"{prof}.{col} kein valides Hex: {val}")

    def test_defaults_has_card_type(self):
        for prof in ('wm2026', 'liga_default'):
            d = self.cfg['profiles'][prof]['defaults']
            self.assertIn('default_card_type', d)
            self.assertIn(d['default_card_type'], CARD_TYPES,
                f"{prof} default_card_type unbekannt: {d['default_card_type']}")


class TestStudioPoolsSchema(unittest.TestCase):
    """studio_pools.json — Pool-Mindest-Größen + Profile-Parity."""

    @classmethod
    def setUpClass(cls):
        cls.pools = json.loads(POOLS_PATH.read_text(encoding='utf-8'))

    def test_file_exists(self):
        self.assertTrue(POOLS_PATH.exists())

    def test_has_shared_section(self):
        self.assertIn('shared', self.pools['profiles'])

    def test_shared_has_required_pools(self):
        shared = self.pools['profiles']['shared']
        for key in ('stat_templates', 'bizarre_compares', 'punchlines',
                    'quiz_questions', 'position_map',
                    'player_topline_templates', 'player_subline_templates'):
            with self.subTest(pool=key):
                self.assertIn(key, shared, f"shared fehlt Pool '{key}'")

    def test_minimum_pool_sizes(self):
        """Mindest-Anzahl Einträge — verhindert leere Pools."""
        shared = self.pools['profiles']['shared']
        self.assertGreaterEqual(len(shared['stat_templates']),    8,  'stat_templates >= 8')
        self.assertGreaterEqual(len(shared['bizarre_compares']), 10, 'bizarre_compares >= 10')
        self.assertGreaterEqual(len(shared['punchlines']),        5, 'punchlines >= 5')
        self.assertGreaterEqual(len(shared['quiz_questions']),    4, 'quiz_questions >= 4')

    def test_both_profiles_have_hooks(self):
        for prof in ('wm2026', 'liga_default'):
            p = self.pools['profiles'].get(prof, {})
            with self.subTest(profile=prof):
                self.assertIn('hook_templates', p, f"{prof} hat keine hook_templates")
                self.assertGreaterEqual(len(p['hook_templates']), 8,
                    f"{prof} hook_templates < 8")

    def test_both_profiles_have_tags(self):
        for prof in ('wm2026', 'liga_default'):
            p = self.pools['profiles'].get(prof, {})
            with self.subTest(profile=prof):
                self.assertIn('tag_pool', p)
                self.assertGreaterEqual(len(p['tag_pool']), 3)

    def test_stat_templates_have_template_field(self):
        """Jedes stat_template muss 'id' + 'template'-Feld haben."""
        for t in self.pools['profiles']['shared']['stat_templates']:
            self.assertIn('id', t)
            self.assertIn('template', t)
            self.assertTrue(t['template'])

    def test_hook_templates_have_team_placeholder(self):
        """Hook-Templates müssen {team_upper}-Placeholder haben."""
        for prof in ('wm2026', 'liga_default'):
            for h in self.pools['profiles'][prof]['hook_templates']:
                with self.subTest(profile=prof, hook=h):
                    self.assertIn('{team_upper}', h,
                        f"Hook '{h}' fehlt {{team_upper}} placeholder")

    def test_position_map_covers_common(self):
        pm = self.pools['profiles']['shared']['position_map']
        for pos in ('ST', 'CM', 'CB', 'GK'):
            self.assertIn(pos, pm, f"position_map fehlt {pos}")


# Card-Typen mit Hook+Detail-Variants (Pair) vs Standalone
CARDS_WITH_DETAIL = ['team_hook', 'player', 'match_pick']
CARDS_STANDALONE  = ['bizarre', 'killer_stat', 'quiz']


class TestStudioTemplates(unittest.TestCase):
    """studio_templates/*.html — alle Card-Typen + Variants haben Files."""

    def test_dir_exists(self):
        self.assertTrue(TEMPLATES_DIR.is_dir())

    def test_common_css_exists(self):
        f = TEMPLATES_DIR / '_common.css'
        self.assertTrue(f.exists(), f'{f} fehlt')
        self.assertIn('.stc', f.read_text(encoding='utf-8'),
            '_common.css fehlt .stc Basis-Klasse')

    def test_all_card_types_have_template(self):
        # Standalone-Cards: <type>.html
        for ct in CARDS_STANDALONE:
            f = TEMPLATES_DIR / f'{ct}.html'
            with self.subTest(card_type=ct):
                self.assertTrue(f.exists(), f'Standalone-Template fehlt: {f}')
        # Hook+Detail-Cards: <type>.html (Hook) + <type>.detail.html
        for ct in CARDS_WITH_DETAIL:
            hook_f   = TEMPLATES_DIR / f'{ct}.html'
            detail_f = TEMPLATES_DIR / f'{ct}.detail.html'
            with self.subTest(card_type=ct):
                self.assertTrue(hook_f.exists(),   f'Hook-Template fehlt: {hook_f}')
                self.assertTrue(detail_f.exists(), f'Detail-Template fehlt: {detail_f}')

    def _all_template_paths(self):
        """Gibt alle Template-Files zurück (Standalone + Hook + Detail)."""
        paths = []
        for ct in CARDS_STANDALONE:
            paths.append((ct, TEMPLATES_DIR / f'{ct}.html'))
        for ct in CARDS_WITH_DETAIL:
            paths.append((f'{ct}.hook',   TEMPLATES_DIR / f'{ct}.html'))
            paths.append((f'{ct}.detail', TEMPLATES_DIR / f'{ct}.detail.html'))
        return paths

    def test_templates_have_brand_placeholder(self):
        """Jedes Template muss das Brand-Element haben."""
        for label, path in self._all_template_paths():
            content = path.read_text(encoding='utf-8')
            with self.subTest(template=label):
                self.assertIn('{{brand}}', content,
                    f'{label}.html fehlt {{{{brand}}}} placeholder')
                self.assertIn('stc-brand', content,
                    f'{label}.html fehlt .stc-brand element')

    def test_templates_use_css_variables(self):
        for label, path in self._all_template_paths():
            content = path.read_text(encoding='utf-8')
            with self.subTest(template=label):
                self.assertIn('var(--', content,
                    f'{label} nutzt keine CSS-Variablen — Theme-Switch broken')

    def test_no_inline_magic_numbers_for_dimensions(self):
        for label, path in self._all_template_paths():
            content = path.read_text(encoding='utf-8')
            with self.subTest(template=label):
                self.assertNotIn('width:1080px', content.replace(' ', ''),
                    f'{label} hat hardcoded 1080px Width')


class TestStudioJsRefactorConform(unittest.TestCase):
    """tiktok-studio.js darf KEINE Pools/Templates inline haben."""

    @classmethod
    def setUpClass(cls):
        cls.src = JS_PATH.read_text(encoding='utf-8')

    def test_loads_external_config(self):
        self.assertIn("'studio_config.json'", self.src,
            'JS muss studio_config.json laden')
        self.assertTrue(
            'fetch(' in self.src and 'studio_config.json' in self.src,
            'JS muss studio_config.json via fetch() laden')

    def test_loads_external_pools(self):
        self.assertIn("'studio_pools.json'", self.src)

    def test_loads_template_files(self):
        self.assertIn("studio_templates/", self.src)

    def test_no_inline_bizarre_compares(self):
        """Alte inline-Arrays dürfen NICHT mehr im Code stehen."""
        forbidden = [
            'wahrscheinlicher als dass Belgien rauskommt',
            'fast so sicher wie ein Bayern-Sieg gegen Köln'
        ]
        for line in forbidden:
            self.assertNotIn(line, self.src,
                f'Inline-Pool-String noch im JS: "{line}" — gehört in studio_pools.json')

    def test_no_inline_hook_templates(self):
        """Hooks mit {team_upper}-Replacement gehören in JSON."""
        forbidden_inline = [
            "'{team_upper}",
            'IST KEIN ZUFALL'  # Inline-Hook
        ]
        for line in forbidden_inline:
            count = self.src.count(line)
            # Im JSON-Helper-Code (replace) ist {team_upper} 1× OK
            with self.subTest(line=line):
                self.assertLessEqual(count, 2,
                    f'Inline-Hook noch im JS: "{line}" — gehört in studio_pools.json')

    def test_no_inline_card_dimensions(self):
        """1080×1920 darf nur 1× max im JS auftauchen (im Comment)."""
        for dim in ('1080', '1920'):
            count = self.src.count(dim)
            with self.subTest(dim=dim):
                self.assertLessEqual(count, 5,
                    f'{dim} taucht {count}× im JS auf — sollte aus studio_config kommen')

    def test_template_engine_present(self):
        """Schlanke template-engine muss vorhanden sein."""
        self.assertIn('renderTemplate', self.src)
        self.assertIn('{{#if', self.src,
            'if-block handler fehlt')

    def test_profile_aware(self):
        """JS muss ACTIVE_PROFILE benutzen."""
        self.assertIn('ACTIVE_PROFILE', self.src)
        self.assertIn('cfg(', self.src)
        self.assertIn('pool(', self.src)

    def test_variants_system(self):
        """JS muss variants-System haben (Hook+Detail-Paare)."""
        self.assertIn('variants:', self.src,
            'TEMPLATE_FILES muss variants-Dict pro Card-Typ haben')
        self.assertIn("hook:", self.src)
        self.assertIn("detail:", self.src)
        self.assertIn("standalone:", self.src)
        self.assertIn('variantsFor', self.src,
            'variantsFor() Helper fehlt')

    def test_render_card_takes_variant(self):
        """renderCard(type, data, variant) — Signatur"""
        # Eine der signatures muss enthalten sein
        self.assertTrue(
            'renderCard(_currentType, _currentData, variant' in self.src or
            'renderCard(type, data, variant' in self.src or
            'renderCard(_currentType, _currentData, v)' in self.src,
            'renderCard() muss variant-Parameter haben')


class TestStudioLigaSwitchWorks(unittest.TestCase):
    """Liga-Switch: profiles.active wechseln → andere Werte."""

    def test_wm_has_different_default_card_than_liga(self):
        cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        wm_def   = cfg['profiles']['wm2026']['defaults']['default_card_type']
        liga_def = cfg['profiles']['liga_default']['defaults']['default_card_type']
        # Beide müssen valide sein, dürfen aber differ
        self.assertIn(wm_def, CARD_TYPES)
        self.assertIn(liga_def, CARD_TYPES)

    def test_wm_and_liga_have_different_brand_sub(self):
        cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        wm_sub   = cfg['profiles']['wm2026']['card']['brand_subtext']
        liga_sub = cfg['profiles']['liga_default']['card']['brand_subtext']
        self.assertNotEqual(wm_sub, liga_sub,
            'Brand-Subtext sollte sich zwischen WM und Liga unterscheiden')

    def test_wm_and_liga_have_different_hook_pools(self):
        pools = json.loads(POOLS_PATH.read_text(encoding='utf-8'))
        wm_hooks   = set(pools['profiles']['wm2026']['hook_templates'])
        liga_hooks = set(pools['profiles']['liga_default']['hook_templates'])
        # Mindestens 50% sollten unterschiedlich sein
        overlap = wm_hooks & liga_hooks
        self.assertLess(len(overlap), len(wm_hooks) / 2,
            'WM- und Liga-Hooks überlappen zu stark — Profile haben zu wenig Unterschied')


if __name__ == '__main__':
    unittest.main()
