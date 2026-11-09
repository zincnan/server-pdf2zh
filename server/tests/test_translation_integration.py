"""Opt-in real next/BabelDOC translation against a local OpenAI-compatible API.

Run inside the built Docker image with RUN_TRANSLATION_INTEGRATION=1. No paid
service or external document is used; model/layout/font assets come from image.
"""
import io
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import fitz
from server import create_app


@unittest.skipUnless(os.environ.get('RUN_TRANSLATION_INTEGRATION') == '1', 'Opt-in real engine integration')
class RealTranslationTests(unittest.TestCase):
    def test_pdf_translation_download_restart_and_clear(self):
        calls = []
        class ModelHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                prompt = request['messages'][-1]['content']
                calls.append(prompt)
                # The engine uses JSON paragraph batches and plain-text fallbacks.
                content = 'Uebersetzt: ' + prompt.split('Input:\n\n')[-1].split('Now translate the following text:\n\n')[-1]
                for offset in reversed([i for i, char in enumerate(prompt) if char == '[']):
                    try:
                        values, _ = json.JSONDecoder().raw_decode(prompt[offset:])
                        if isinstance(values, list) and values and isinstance(values[0], dict) and 'input' in values[0]:
                            content = json.dumps([{'id': v['id'], 'output': 'Uebersetzt: ' + v['input']} for v in values])
                            break
                    except (ValueError, TypeError):
                        continue
                body = json.dumps({'id': 'mock', 'object': 'chat.completion', 'created': int(time.time()),
                    'model': request['model'], 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content}, 'finish_reason': 'stop'}],
                    'usage': {'prompt_tokens': 20, 'completion_tokens': 20, 'total_tokens': 40}}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        model = ThreadingHTTPServer(('127.0.0.1', 0), ModelHandler)
        thread = threading.Thread(target=model.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(model.server_close)
        self.addCleanup(model.shutdown)
        with tempfile.TemporaryDirectory() as temp:
            app = create_app({'TESTING': True, 'DATA_DIR': temp, 'AUTH_REQUIRED': False,
                              'ASSET_DIR': os.environ.get('ASSET_DIR', '/opt/pdf2zh-assets')})
            manager = app.extensions['tasks']
            client = app.test_client()
            headers = {'X-PDF2zh-Request': '1'}
            try:
                profile = client.post('/api/model-services', headers=headers, json={'name': 'Local mock',
                    'provider': 'openaicompatible', 'model': 'mock-translator', 'apiKey': 'integration-secret',
                    'apiUrl': f'http://127.0.0.1:{model.server_port}/v1'}).json
                client.put(f'/api/model-services/{profile["id"]}/active', headers=headers)
                with fitz.open() as doc:
                    page = doc.new_page()
                    page.insert_text((60, 60), 'Document Translation Integration', fontsize=18)
                    page.insert_textbox(fitz.Rect(60, 100, 530, 700),
                        'This document verifies the independent PDF translation service. '
                        'The service preserves the document layout and produces readable output. '
                        'It uses a local model server for deterministic testing without paid API calls.\n\n'
                        'Concurrent tasks keep their own input documents, settings, caches and results. '
                        'After translation the user can download both the translated and bilingual PDF. '
                        'Restarting the service must preserve completed results until manual cleanup.\n\n'
                        'The translation pipeline uses the original BabelDOC parser and layout engine. '
                        'No PDF parsing or typesetting algorithm is replaced by a mock in this test.', fontsize=12)
                    pdf = doc.tobytes()
                response = client.post('/api/tasks', headers=headers, data={'file': (io.BytesIO(pdf), 'integration.pdf'),
                    'options': json.dumps({'targetLang': 'de', 'disableGlossary': True, 'qps': 2, 'poolSize': 1,
                                           'skipReferences': True, 'tableMode': 'fixed'})})
                self.assertEqual(response.status_code, 202, response.json)
                task_id = response.json['taskId']
                deadline = time.monotonic() + 240
                while time.monotonic() < deadline:
                    task = manager.get(task_id)
                    if task['state'] in ('succeeded', 'failed', 'interrupted'):
                        break
                    time.sleep(.2)
                if task['state'] != 'succeeded':
                    log = Path(temp) / 'tasks' / task_id / 'task.log'
                    self.fail(f'{task}\n{log.read_text()[-16000:] if log.exists() else "no log"}')
                self.assertGreater(len(calls), 0, 'Translation must actually call the local model')
                self.assertEqual({f['type'] for f in task['files']}, {'mono', 'dual'})
                for item in task['files']:
                    with fitz.open(Path(temp) / 'tasks' / task_id / item['path']) as pdf_doc:
                        self.assertGreater(len(pdf_doc), 0)
                        self.assertIn('Uebersetzt', ''.join(page.get_text() for page in pdf_doc))
                    result = client.get(f'/api/tasks/{task_id}/files/{item["id"]}', buffered=True)
                    self.assertEqual(result.status_code, 200)
                    self.assertTrue(result.data.startswith(b'%PDF-'))
                    result.close()
                self.assertFalse((Path(temp) / 'tasks' / task_id / 'engine.toml').exists())
                self.assertNotIn('integration-secret', client.get('/api/tasks').get_data(as_text=True))
                manager.shutdown(3)
                restored = create_app({'TESTING': True, 'DATA_DIR': temp, 'AUTH_REQUIRED': False})
                try:
                    restored_client = restored.test_client()
                    self.assertEqual(restored_client.get(f'/api/tasks/{task_id}').json['state'], 'succeeded')
                    self.assertEqual(restored_client.delete(f'/api/tasks/{task_id}', headers=headers).status_code, 204)
                    self.assertFalse((Path(temp) / 'tasks' / task_id).exists())
                    self.assertEqual(len(restored_client.get('/api/model-services').json['services']), 1)
                finally:
                    restored.extensions['tasks'].shutdown(3)
            finally:
                manager.shutdown(3)


if __name__ == '__main__':
    unittest.main()
