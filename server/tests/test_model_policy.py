"""Assert actual SDK HTTP payloads, not just generated TOML fields."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch

from utils.model_policy import EFFORTS, install_model_policy, model_family, request_fields


class ModelPolicyTests(unittest.TestCase):
    def test_model_recognition(self):
        for model, expected in [('deepseek-ai/DeepSeek-V4-Flash', 'deepseek'), ('deepseek-chat', 'deepseek'),
                                ('Qwen/Qwen3-32B', 'qwen'), ('vendor/QwQ-32B', 'qwen'),
                                ('o1', 'openai-reasoning'), ('o3-mini', 'openai-reasoning'),
                                ('o4-mini', 'openai-reasoning'), ('gpt-5.2', 'openai-reasoning'),
                                ('gpt-6', 'openai-reasoning'), ('gpt-4o-mini', 'openai'),
                                ('my-company-alias', 'openai')]:
            with self.subTest(model=model):
                self.assertEqual(model_family(model), expected)

    def test_off_omits_previous_effort_and_does_not_guess_unknown_aliases(self):
        for model, expected in [('deepseek-test', {'thinking': {'type': 'disabled'}}),
                                ('Qwen/test-Qwen', {}), ('Qwen3', {'enable_thinking': False}),
                                ('gpt-5', {'reasoning_effort': 'none'}), ('gpt-4o', {})]:
            with self.subTest(model=model):
                self.assertEqual(request_fields({'model': model, 'thinkingEnabled': False, 'reasoningEffort': 'max'}), expected)

    def test_real_sdk_payloads_and_restoration(self):
        from pdf2zh_next.translator.translator_impl.openai import OpenAITranslator
        from pdf2zh_next.translator.base_translator import BaseTranslator
        received = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                received.append(body)
                output = json.dumps({'id': 'test', 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'translated'}, 'finish_reason': 'stop'}]}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(output)))
                self.end_headers()
                self.wfile.write(output)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        original = OpenAITranslator.__init__

        def base_init(instance, *args, **kwargs):
            # Leave document caching to real-engine integration tests; the SDK
            # transport, translator implementation and JSON mode are real here.
            instance.lang_in, instance.lang_out = 'en', 'de'

        controls = [
            {'model': model, 'thinkingEnabled': enabled, 'reasoningEffort': effort, 'enableJsonMode': json_mode}
            for model in ('namespace/DeepSeek-Test', 'Qwen/Qwen3-test', 'gpt-5', 'custom-alias')
            for enabled in (False, True)
            for effort in EFFORTS
            for json_mode in (False, True)
            if not (enabled and not effort and model in ('gpt-5', 'custom-alias'))
        ]
        with patch.object(BaseTranslator, '__init__', base_init), patch.object(BaseTranslator, 'add_cache_impact_parameters'):
            for policy in controls:
                with self.subTest(policy=policy):
                    restore = install_model_policy(policy)
                    settings = SimpleNamespace(translate_engine_settings=SimpleNamespace(
                        openai_timeout='5', openai_base_url=f'http://127.0.0.1:{server.server_port}/v1',
                        openai_api_key='test-key', openai_temperature='0', openai_send_temprature=True,
                        openai_reasoning_effort='low', openai_send_reasoning_effort=True,
                        _openai_extra_body={'old': 'must not leak'}, openai_model=policy['model'], openai_enable_json_mode=False))
                    try:
                        translator = OpenAITranslator(settings, None)
                        try:
                            self.assertEqual(translator.do_translate('hello'), 'translated')
                            plain = received[-1]
                            self.assertNotIn('temperature', plain)
                            self.assertNotIn('response_format', plain)
                            self.assertNotIn('old', plain)
                            translator.do_llm_translate('structured prompt', {'request_json_mode': True})
                            body = received[-1]
                            for key in ('thinking', 'enable_thinking', 'reasoning_effort'):
                                self.assertEqual(body.get(key), request_fields(policy).get(key))
                            self.assertEqual(body.get('response_format'), {'type': 'json_object'} if policy['enableJsonMode'] else None)
                            self.assertNotIn('temperature', body)
                        finally:
                            translator.client.close()
                    finally:
                        restore()
                    self.assertIs(OpenAITranslator.__init__, original)


if __name__ == '__main__':
    unittest.main()
