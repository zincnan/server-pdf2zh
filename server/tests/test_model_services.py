"""Profile validation and durable, credential-preserving migration."""
import json
import tempfile
import unittest
from pathlib import Path

import toml
from utils.config import Config
from utils.services import ServiceStore, provider_catalog
from utils.storage import atomic_json, read_json


def profile(**overrides):
    return {'name': 'Model', 'provider': 'openaicompatible', 'apiUrl': 'http://localhost:8000/v1',
            'apiKey': 'test-secret', 'model': 'namespace/Qwen3-32B', **overrides}


class ModelServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'services.json'
        self.store = ServiceStore(self.path)

    def test_only_three_types_and_explicit_options(self):
        self.assertEqual([p['id'] for p in provider_catalog()], ['openaicompatible', 'google', 'bing'])
        self.assertNotIn('extraFields', json.dumps(provider_catalog()))
        for provider in ('google', 'bing'):
            saved = self.store.put({'name': provider, 'provider': provider})
            self.store.activate(saved['id'])
            self.assertFalse(saved['hasApiKey'])
            self.assertFalse(saved['needsConversion'])
        for changes in ({'apiUrl': ''}, {'apiKey': ''}, {'model': ''}, {'extraData': {}},
                        {'enableJsonMode': 'true'}, {'thinkingEnabled': 'false'}, {'reasoningEffort': 'extreme'},
                        {'apiUrl': 'http://localhost:bad/v1'}, {'provider': 'deepseek'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.store.put(profile(**changes))
        with self.assertRaises(ValueError):
            self.store.put({'name': 'Bing', 'provider': 'bing', 'thinkingEnabled': True})

    def test_required_effort_for_standard_openai_only(self):
        with self.assertRaisesRegex(ValueError, '推理强度'):
            self.store.put(profile(model='gpt-5', thinkingEnabled=True))
        self.assertTrue(self.store.put(profile(model='Qwen/Qwen3-32B', thinkingEnabled=True))['thinkingEnabled'])
        saved = self.store.put(profile(apiUrl='http://localhost/v1/chat/completions/'))
        self.assertEqual(saved['apiUrl'], 'http://localhost/v1')

    def test_model_options_survive_edits_without_returning_keys(self):
        saved = self.store.put(profile(enableJsonMode=True, thinkingEnabled=True, reasoningEffort='xhigh'))
        self.store.activate(saved['id'])
        self.store.put({'name': 'Renamed'}, saved['id'])
        active = self.store.active()
        self.assertEqual(active['apiKey'], 'test-secret')
        self.assertTrue(active['enableJsonMode'])
        self.assertEqual(active['reasoningEffort'], 'xhigh')
        self.assertNotIn('test-secret', json.dumps(self.store.list()))
        self.assertEqual(ServiceStore(self.path).active(), active)

    def test_task_config_disables_temperature_even_without_policy(self):
        destination = Path(self.temp.name) / 'engine.toml'
        Config({}).write(profile(enableJsonMode=True), destination, Path(self.temp.name))
        detail = toml.load(destination)['openaicompatible_detail']
        self.assertIs(detail['openai_compatible_send_temperature'], False)
        self.assertIs(detail['openai_compatible_enable_json_mode'], True)
        self.assertIs(detail['openai_compatible_send_reasoning_effort'], False)

    def seed_v1(self, profiles, active):
        data = {'schemaVersion': 1, 'services': profiles, 'activeId': active}
        atomic_json(self.path, data)
        return data

    def test_openai_migration_preserves_defaults_key_and_active(self):
        original = self.seed_v1([{'id': 'old', 'revision': 3, 'name': 'OpenAI', 'provider': 'openai',
            'apiKey': 'old-secret', 'apiUrl': '', 'model': '', 'extraData': {
                'openai_enable_json_mode': 'true', 'openai_send_reasoning_effort': True,
                'openai_reasoning_effort': 'high', 'openai_send_temprature': True, 'openai_temperature': '0'}}], 'old')
        store = ServiceStore(self.path)
        active = store.active()
        self.assertEqual(active['provider'], 'openaicompatible')
        self.assertEqual(active['apiUrl'], 'https://api.openai.com/v1')
        self.assertEqual(active['model'], 'gpt-4o-mini')
        self.assertEqual(active['apiKey'], 'old-secret')
        self.assertTrue(active['enableJsonMode'])
        self.assertTrue(active['thinkingEnabled'])
        self.assertNotIn('extraData', active)
        backup = self.path.with_name('services.v1.backup.json')
        self.assertEqual(read_json(backup), original)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        before = backup.read_bytes()
        ServiceStore(self.path)
        self.assertEqual(before, backup.read_bytes())
        self.assertEqual(read_json(self.path)['schemaVersion'], 2)

    def test_compatible_custom_url_and_pending_legacy_profiles(self):
        original = self.seed_v1([
            {'id': 'compat', 'revision': 1, **profile(apiUrl='http://my-gateway/custom',
                extraData={'openai_compatible_enable_json_mode': True})},
            {'id': 'legacy', 'revision': 2, 'name': 'Old DeepSeek', 'provider': 'deepseek',
             'apiKey': 'keep-this-key', 'apiUrl': 'http://custom/v1', 'model': 'deepseek-test',
             'extraData': {'some_secret_token': 'private-extra'}},
        ], 'legacy')
        store = ServiceStore(self.path)
        public = store.list()
        self.assertIsNone(public['activeId'])
        self.assertTrue(public['services'][1]['needsConversion'])
        self.assertNotIn('private-extra', json.dumps(public))
        self.assertNotIn('keep-this-key', json.dumps(public))
        with self.assertRaises(ValueError):
            store.activate('legacy')
        store.activate('compat')
        self.assertEqual(store.active()['apiUrl'], 'http://my-gateway/custom')
        self.assertTrue(store.active()['enableJsonMode'])
        converted = store.put({'provider': 'openaicompatible'}, 'legacy')
        self.assertFalse(converted['needsConversion'])
        store.activate('legacy')
        self.assertEqual(store.active()['apiKey'], 'keep-this-key')
        self.assertEqual(read_json(self.path.with_name('services.v1.backup.json')), original)

    def test_incomplete_legacy_profile_is_not_silently_activated(self):
        self.seed_v1([{'id': 'empty', 'revision': 0, **profile(apiUrl='')}], 'empty')
        store = ServiceStore(self.path)
        self.assertIsNone(store.list()['activeId'])
        self.assertTrue(store.list()['services'][0]['needsConversion'])
        with self.assertRaises(ValueError):
            store.activate('empty')


if __name__ == '__main__':
    unittest.main()
