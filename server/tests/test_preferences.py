"""Durable translation drafts, partial updates and preservation on failure."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from utils.config import DEFAULTS, validate_options
from utils.preferences import PreferenceStore
from utils.storage import atomic_json, read_json


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'preferences.json'
        self.store = PreferenceStore(self.path)

    def test_defaults_missing_fields_and_copy_isolation(self):
        defaults = self.store.get()['translationOptions']
        self.assertEqual(defaults, {key: value for key, value in DEFAULTS.items() if key != 'compare'})
        self.assertFalse(self.path.exists(), 'Loading defaults must not create a settings file')
        defaults['mono'] = False
        self.assertTrue(self.store.get()['translationOptions']['mono'])
        atomic_json(self.path, {'translationOptions': {'mono': False, 'targetLang': 'de'}})
        loaded = PreferenceStore(self.path).get()['translationOptions']
        self.assertFalse(loaded['mono'])
        self.assertEqual(loaded['targetLang'], 'de')
        self.assertEqual(loaded['qps'], DEFAULTS['qps'])

    def test_partial_updates_survive_restart_and_keep_file_private(self):
        self.store.patch({'translationOptions': {'mono': False, 'dualMode': 'TB', 'qps': 7}})
        self.store.patch({'translationOptions': {'sourceLang': 'ja', 'targetLang': 'en', 'autoOcr': False}})
        restored = PreferenceStore(self.path).get()['translationOptions']
        self.assertFalse(restored['mono'])
        self.assertFalse(restored['autoOcr'])
        self.assertEqual((restored['dualMode'], restored['qps'], restored['sourceLang'], restored['targetLang']),
                         ('TB', 7, 'ja', 'en'))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_draft_may_have_no_outputs_but_jobs_still_require_one(self):
        outputs = {key: False for key in ('mono', 'dual', 'mono_cut', 'dual_cut', 'crop_compare')}
        options = self.store.patch({'translationOptions': outputs})['translationOptions']
        self.assertEqual(PreferenceStore(self.path).get()['translationOptions'], options)
        with self.assertRaisesRegex(ValueError, 'PDF 输出'):
            validate_options(options)

    def test_invalid_updates_do_not_overwrite_saved_settings(self):
        self.store.patch({'translationOptions': {'mono': False}})
        before = self.path.read_bytes()
        invalid = [None, {}, {'apiKey': 'secret'}, {'translationOptions': None},
                   {'translationOptions': {'compare': True}}, {'translationOptions': {'qps': 0}},
                   {'translationOptions': {'qps': True}}, {'translationOptions': {'poolSize': 1.5}},
                   {'translationOptions': {'mono': 'false'}}, {'translationOptions': {'sourceLang': 'xx'}},
                   {'translationOptions': {'dualMode': 'other'}}, {'translationOptions': {'qps': float('nan')}}]
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.store.patch(data)
            self.assertEqual(self.path.read_bytes(), before)

    def test_write_failure_preserves_disk_and_memory(self):
        before = self.store.patch({'translationOptions': {'qps': 6}})
        with patch('utils.preferences.atomic_json', side_effect=PermissionError('disk unavailable')):
            with self.assertRaises(PermissionError):
                self.store.patch({'translationOptions': {'qps': 9}})
        self.assertEqual(self.store.get(), before)
        self.assertEqual(read_json(self.path), before)

    def test_delayed_old_request_cannot_revert_newer_edits(self):
        self.store.patch({'translationOptions': {'targetLang': 'ja'}, 'writerId': 'page-one', 'sequence': 2})
        # Older fields not superseded by a newer edit still need to be saved.
        self.store.patch({'translationOptions': {'targetLang': 'de', 'qps': 9}, 'writerId': 'page-one', 'sequence': 1})
        self.assertEqual(self.store.get()['translationOptions']['targetLang'], 'ja')
        self.assertEqual(self.store.get()['translationOptions']['qps'], 9)
        # API clients without ordering metadata retain ordinary PATCH behavior.
        self.store.patch({'translationOptions': {'qps': 7}})
        self.assertEqual(self.store.get()['translationOptions']['qps'], 7)

    def test_failed_write_does_not_consume_sequence(self):
        data = {'translationOptions': {'qps': 12}, 'writerId': 'page-one', 'sequence': 1}
        with patch('utils.preferences.atomic_json', side_effect=PermissionError('disk unavailable')):
            with self.assertRaises(PermissionError):
                self.store.patch(data)
        self.store.patch(data)
        self.assertEqual(self.store.get()['translationOptions']['qps'], 12)

    def test_invalid_delivery_metadata_does_not_save(self):
        for metadata in ({'writerId': 'page-one'}, {'sequence': 1}, {'writerId': '', 'sequence': 1},
                         {'writerId': 'page-one', 'sequence': True}, {'writerId': 'page-one', 'sequence': 0}):
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                self.store.patch({'translationOptions': {'qps': 12}, **metadata})
        self.assertFalse(self.path.exists())

    def test_concurrent_partial_updates_do_not_lose_other_fields(self):
        updates = [{'qps': 8}, {'mono': False}, {'targetLang': 'fr'}, {'dualMode': 'TB'}, {'autoOcr': False}]
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(lambda change: self.store.patch({'translationOptions': change}), updates))
        restored = PreferenceStore(self.path).get()['translationOptions']
        for update in updates:
            for key, value in update.items():
                self.assertEqual(restored[key], value)

    def test_corrupt_or_invalid_file_is_not_replaced(self):
        for contents in ('{broken', '[]', '{"translationOptions":{"qps":-2}}', '{"unexpected":true}'):
            with self.subTest(contents=contents):
                self.path.write_text(contents)
                with self.assertRaisesRegex(ValueError, '翻译设置文件无效'):
                    PreferenceStore(self.path)
                self.assertEqual(self.path.read_text(), contents)
