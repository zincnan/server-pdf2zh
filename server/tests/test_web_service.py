"""Lifecycle/API regressions using real PDFs and a controllable job runner."""
import io
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz
from server import create_app
from utils.config import Config, validate_options
from utils.execute import TaskLog, parse_progress
from utils.services import ServiceStore
from utils.storage import atomic_json
from utils.task_manager import BusyError, TaskManager

HEADERS = {'X-PDF-AI-Translator-Request': '1'}


def pdf_bytes(text='An example document with enough readable text for a PDF.'):
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), text)
        return doc.tobytes()


def completed_runner(directory, options, profile, update, register, stopping, assets):
    update(stage='translating', progress=50, message='translation')
    target = directory / 'output' / 'result.pdf'
    target.parent.mkdir(exist_ok=True)
    shutil.copyfile(directory / 'input.pdf', target)
    return {'mono': target}


def wait_for(manager, task_id, states=('succeeded', 'failed'), timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = manager.get(task_id)
        if task['state'] in states:
            return task
        time.sleep(0.01)
    raise AssertionError(f'Task did not reach {states}: {manager.get(task_id)}')


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATA_DIR': self.temp.name, 'AUTH_REQUIRED': False,
                               'TASK_RUNNER': completed_runner})
        self.manager = self.app.extensions['tasks']
        self.client = self.app.test_client()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: self.manager.shutdown(2))
        profile = self.client.post('/api/model-services', headers=HEADERS,
            json={'name': 'Local test', 'provider': 'openaicompatible', 'apiKey': 'secret-one', 'apiUrl': 'http://127.0.0.1:12345/v1', 'model': 'test'}).get_json()
        self.profile_id = profile['id']
        self.client.put(f'/api/model-services/{self.profile_id}/active', headers=HEADERS)

    def submit(self, filename='same.pdf', options=None, content=None):
        return self.client.post('/api/tasks', headers=HEADERS,
            data={'file': (io.BytesIO(content or pdf_bytes()), filename), 'options': json.dumps(options or {})})

    def test_upload_download_clear_and_keep_profiles(self):
        response = self.submit('中文.dual.pdf')
        self.assertEqual(response.status_code, 202, response.get_json())
        task = wait_for(self.manager, response.json['taskId'])
        self.assertEqual(task['state'], 'succeeded')
        url = f'/api/tasks/{task["id"]}/files/{task["files"][0]["id"]}'
        download = self.client.get(url, buffered=False)
        self.assertEqual(download.status_code, 200)
        self.assertIn('%PDF-', b''.join(download.response).decode('latin1'))
        # Reading bytes does not release the lease until response.close().
        self.assertEqual(self.client.delete(f'/api/tasks/{task["id"]}', headers=HEADERS).status_code, 409)
        download.close()
        self.assertEqual(self.client.delete(f'/api/tasks/{task["id"]}', headers=HEADERS).status_code, 204)
        self.assertFalse((Path(self.temp.name) / 'tasks' / task['id']).exists())
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(len(self.client.get('/api/model-services').json['services']), 1)

    def test_input_validation_releases_unaccepted_workspace(self):
        self.assertEqual(self.submit(content=b'%PDF-invalid').status_code, 422)
        self.assertEqual(self.submit(options={'qps': -1}).status_code, 400)
        self.assertEqual(self.submit(options={'engine': 'pdf2zh'}).status_code, 400)
        self.assertEqual(self.submit(options={'skipLastPages': 2}).status_code, 400)
        self.assertEqual(self.manager.list(), [])
        self.assertEqual(list((Path(self.temp.name) / 'tasks').iterdir()), [])
        with fitz.open() as doc:
            doc.new_page()
            encrypted = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw='private')
        self.assertEqual(self.submit(content=encrypted).status_code, 422)
        self.app.config['MAX_FILE_BYTES'] = 1
        self.assertEqual(self.submit().status_code, 413)

    def test_secret_never_returned_and_edit_preserves_it(self):
        self.assertNotIn('secret-one', self.client.get('/api/model-services').get_data(as_text=True))
        result = self.client.patch(f'/api/model-services/{self.profile_id}', headers=HEADERS, json={'name': 'Renamed'})
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json['hasApiKey'])
        self.assertEqual(self.app.extensions['model_services'].active()['apiKey'], 'secret-one')
        path = Path(self.temp.name) / 'config' / 'services.json'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(ServiceStore(path).active()['name'], 'Renamed')

    def test_profile_and_option_validation(self):
        for body in ({'provider': 'claudecode', 'name': 'No'},
                     {'provider': 'openaicompatible', 'name': 'Bad', 'apiUrl': 'file:///etc/passwd'},
                     {'provider': 'deepseek', 'name': 'Bad', 'extraData': {'arbitrary_key': 'x'}},
                     {'provider': 'openai', 'name': 'Bad', 'extraData': {'openai_enable_json_mode': 'maybe'}}):
            self.assertEqual(self.client.post('/api/model-services', headers=HEADERS, json=body).status_code, 400)
        for body in ({'qps': True}, {'tableMode': 'adaptive'}, {'dualMode': 'bad'}, {'sourceLang': '--help'},
                     {'pdf_offset_ratio': 0}, {'mono': False, 'dual': False}, {'poolSize': 129}):
            with self.assertRaises(ValueError):
                validate_options(body)

    def test_authentication_guards_every_data_endpoint(self):
        self.app.config['AUTH_REQUIRED'] = True
        for path in ('/api/model-services', '/api/preferences', '/api/tasks', '/api/capabilities', '/events', '/api/tasks/id/files/id'):
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.get('/health').status_code, 200)
        self.assertEqual(self.client.post('/api/session', json={'password': 'pdf2zh'}).status_code, 403)
        self.assertEqual(self.client.post('/api/session', headers=HEADERS, json={'password': 'wrong'}).status_code, 401)
        self.assertEqual(self.client.post('/api/session', headers={**HEADERS, 'Origin': 'http://evil.test'}, json={'password': 'pdf2zh'}).status_code, 403)
        self.assertEqual(self.client.post('/api/session', headers=HEADERS, json={'password': 'pdf2zh'}).status_code, 200)
        self.assertEqual(self.client.get('/api/model-services').status_code, 200)
        self.assertEqual(self.client.delete('/api/session', headers=HEADERS).status_code, 200)
        self.assertEqual(self.client.get('/api/tasks').status_code, 401)

    def test_unknown_old_routes_are_removed(self):
        for path in ('/translate', '/crop', '/compare', '/translatedInfo', '/translatedFile/input.pdf', '/api/history'):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_sse_snapshot_and_retry_copy(self):
        task_id = self.submit().json['taskId']
        task = wait_for(self.manager, task_id)
        response = self.client.get('/events', buffered=False)
        self.assertIn(task_id, next(response.response).decode())
        response.close()
        retried = self.client.post(f'/api/tasks/{task_id}/retry', headers=HEADERS)
        self.assertEqual(retried.status_code, 202)
        retry_id = retried.json['taskId']
        self.assertNotEqual(retry_id, task_id)
        self.manager.clear(task_id)
        self.assertEqual(wait_for(self.manager, retry_id)['state'], 'succeeded')

    def test_health_does_not_expose_server_paths(self):
        text = self.client.get('/health').get_data(as_text=True)
        self.assertNotIn(self.temp.name, text)
        self.assertNotIn('outputDir', text)

    def test_preferences_api_preserves_task_snapshot_and_survives_clear_and_restart(self):
        self.assertTrue(self.client.get('/api/preferences').json['translationOptions']['mono'])
        response = self.client.patch('/api/preferences', headers=HEADERS,
                                     json={'translationOptions': {'mono': False, 'dualMode': 'TB', 'targetLang': 'de'}})
        self.assertEqual(response.status_code, 200)
        options = response.json['translationOptions']
        task = wait_for(self.manager, self.submit(options=options).json['taskId'])
        self.client.patch('/api/preferences', headers=HEADERS, json={'translationOptions': {'targetLang': 'fr'}})
        self.assertEqual(self.manager.get(task['id'])['options']['targetLang'], 'de')
        self.assertEqual(self.client.delete('/api/tasks', headers=HEADERS).status_code, 200)
        self.assertEqual(self.client.get('/api/preferences').json['translationOptions']['targetLang'], 'fr')
        self.manager.shutdown(2)
        restarted = create_app({'TESTING': True, 'DATA_DIR': self.temp.name, 'AUTH_REQUIRED': False,
                                'TASK_RUNNER': completed_runner})
        self.addCleanup(lambda: restarted.extensions['tasks'].shutdown(2))
        restored = restarted.test_client().get('/api/preferences').json['translationOptions']
        self.assertFalse(restored['mono'])
        self.assertEqual(restored['dualMode'], 'TB')
        self.assertEqual(restored['targetLang'], 'fr')
        self.assertEqual(len(restarted.test_client().get('/api/model-services').json['services']), 1)

    def test_preferences_api_rejects_invalid_and_cross_origin_updates(self):
        before = self.client.get('/api/preferences').json
        body = {'translationOptions': {'mono': False}}
        self.assertEqual(self.client.patch('/api/preferences', json=body).status_code, 403)
        self.assertEqual(self.client.patch('/api/preferences', headers={**HEADERS, 'Origin': 'http://evil.test'},
                                          json=body).status_code, 403)
        self.assertEqual(self.client.patch('/api/preferences', headers=HEADERS,
                                          json={'translationOptions': {'apiKey': 'secret'}}).status_code, 400)
        self.assertEqual(self.client.get('/api/preferences').json, before)
        self.app.config['AUTH_REQUIRED'] = True
        self.assertEqual(self.client.patch('/api/preferences', headers=HEADERS, json=body).status_code, 401)

    def test_language_catalog_works_with_request_validation(self):
        response = self.client.get('/api/capabilities')
        self.assertEqual(response.status_code, 200)
        capabilities = response.get_json()
        languages = capabilities['languages']
        self.assertEqual(len(languages), 153)
        codes = [language['code'] for language in languages]
        self.assertEqual(len(set(codes)), len(codes))
        self.assertIn(capabilities['defaults']['sourceLang'], codes)
        self.assertIn(capabilities['defaults']['targetLang'], codes)
        for language in languages:
            with self.subTest(code=language['code']):
                self.assertTrue(language['label'])
                validate_options({'sourceLang': language['code'], 'targetLang': language['code']})
        names = {language['code']: language['label'] for language in languages}
        self.assertEqual(len({names['zh-CN'], names['zh-TW'], names['zh-HK']}), 3)
        self.assertNotEqual(names['pt'], names['pt-BR'])

    def test_multilingual_jobs_keep_language_codes_in_config_and_retry(self):
        profile = self.app.extensions['model_services'].active()
        # Preserve API compatibility for valid codes outside the UI catalog too.
        for source, target in [('fr', 'zh-CN'), ('ja', 'en'), ('zh-CN', 'de'), ('ar', 'he')]:
            with self.subTest(source=source, target=target):
                response = self.submit(options={'sourceLang': source, 'targetLang': target})
                self.assertEqual(response.status_code, 202)
                task = wait_for(self.manager, response.json['taskId'])
                self.assertEqual(task['state'], 'succeeded')
                options = task['options']
                path = Path(self.temp.name) / 'language-test.toml'
                config = Config(options).write(profile, path, Path(self.temp.name) / 'output')
                self.assertEqual(config['translation']['lang_in'], source)
                self.assertEqual(config['translation']['lang_out'], target)
                retried = self.client.post(f'/api/tasks/{task["id"]}/retry', headers=HEADERS)
                self.assertEqual(retried.status_code, 202)
                retry = wait_for(self.manager, retried.json['taskId'])
                self.assertEqual(retry['state'], 'succeeded')
                self.assertEqual(retry['options']['sourceLang'], source)
                self.assertEqual(retry['options']['targetLang'], target)

    def test_clear_failure_can_be_retried(self):
        task_id = self.submit().json['taskId']
        wait_for(self.manager, task_id)
        with patch('utils.task_manager.shutil.rmtree', side_effect=PermissionError('test')):
            self.assertEqual(self.client.delete(f'/api/tasks/{task_id}', headers=HEADERS).status_code, 500)
        self.assertEqual(self.manager.get(task_id)['state'], 'cleanup_failed')
        self.assertEqual(self.client.delete(f'/api/tasks/{task_id}', headers=HEADERS).status_code, 204)


class LifecycleTests(unittest.TestCase):
    def test_bounded_concurrency_and_frozen_model_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            release = threading.Event()
            running = []
            guard = threading.Lock()
            observed = []
            def gated(directory, options, profile, update, register, stopping, assets):
                with guard:
                    running.append(directory.name)
                    observed.append(profile['apiKey'])
                if not release.wait(5):
                    raise RuntimeError('test timeout')
                return completed_runner(directory, options, profile, update, register, stopping, assets)
            manager = TaskManager(temp, 2, gated)
            profile = {'id': 'x', 'revision': 1, 'name': 'A', 'provider': 'openai', 'model': 'x', 'apiKey': 'first'}
            try:
                ids = []
                for index in range(3):
                    ids.append(manager.submit(io.BytesIO(pdf_bytes(str(index))), 'same.pdf', {}, profile)['id'])
                    profile['apiKey'] = 'second'
                deadline = time.monotonic() + 3
                while len(running) < 2 and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertEqual(len(running), 2)
                self.assertEqual(manager.get(ids[2])['state'], 'queued')
                self.assertEqual(set(observed), {'first', 'second'})
                result = manager.clear_all()
                self.assertEqual(len(result['skipped']), 3)
                self.assertFalse(result['cleared'])
                release.set()
                for task_id in ids:
                    self.assertEqual(wait_for(manager, task_id)['state'], 'succeeded')
                self.assertEqual(len(manager.clear_all()['cleared']), 3)
            finally:
                release.set()
                manager.shutdown(5)

    def test_recovery_and_single_instance_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = TaskManager(temp, runner=completed_runner)
            profile = {'id': 'p', 'revision': 1, 'name': 'Saved', 'provider': 'openai', 'model': 'm', 'apiKey': 'key'}
            task = manager.submit(io.BytesIO(pdf_bytes()), 'kept.pdf', {}, profile)
            task = wait_for(manager, task['id'])
            with self.assertRaises(RuntimeError):
                TaskManager(temp)
            manager.shutdown(2)
            interrupted = dict(task, id='65bb2b7d-34a1-4a80-9bbd-2cba193d9c39', state='running', files=[])
            path = Path(temp) / 'tasks' / interrupted['id']
            path.mkdir()
            (path / 'input.pdf').write_bytes(pdf_bytes())
            atomic_json(path / 'task.json', interrupted)
            manager = TaskManager(temp, runner=completed_runner)
            try:
                self.assertEqual(manager.get(task['id'])['state'], 'succeeded')
                self.assertTrue((Path(temp) / 'tasks' / task['id'] / task['files'][0]['path']).exists())
                self.assertEqual(manager.get(interrupted['id'])['state'], 'interrupted')
                self.assertTrue(manager.get(interrupted['id'])['canRetry'])
            finally:
                manager.shutdown(2)

    def test_stop_interrupts_a_running_engine_process(self):
        import sys
        from utils.execute import execute_with_progress
        with tempfile.TemporaryDirectory() as temp:
            started = threading.Event()
            process_ref = []
            def runner(directory, options, profile, update, register, stopping, assets):
                def observed(process):
                    register(process)
                    if process:
                        process_ref.append(process)
                        started.set()
                execute_with_progress([sys.executable, '-u', '-c', 'import time; print("translate 1/100"); time.sleep(60)'],
                    directory, dict(os.environ), update, observed, TaskLog(directory / 'task.log', profile), stopping)
                return {}
            manager = TaskManager(temp, runner=runner)
            profile = {'id': 'p', 'revision': 1, 'name': 'Local', 'provider': 'openai', 'model': 'm', 'apiKey': 'key'}
            try:
                task = manager.submit(io.BytesIO(pdf_bytes()), 'stop.pdf', {}, profile)
                self.assertTrue(started.wait(3))
                manager.shutdown(.02)
                self.assertIsNotNone(process_ref[0].poll())
                self.assertEqual(manager.get(task['id'])['state'], 'interrupted')
            finally:
                manager.shutdown(3)

    def test_progress_and_log_redaction_are_per_task(self):
        self.assertEqual(parse_progress('translate 5/10')['progress'], 50)
        self.assertEqual(parse_progress('translate 10/10')['progress'], 99)
        with tempfile.TemporaryDirectory() as temp:
            first = TaskLog(Path(temp) / 'a.log', {'apiKey': 'secret-a'})
            second = TaskLog(Path(temp) / 'b.log', {'apiKey': 'secret-b'})
            first.write('Error first secret-a')
            second.write('Error second secret-b')
            self.assertNotIn('secret-a', first.tail())
            self.assertNotIn('second', first.tail())
            self.assertNotIn('first', second.tail())

    def test_request_config_writes_do_not_share_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = [Path(temp) / f'{index}.toml' for index in range(2)]
            for index, path in enumerate(paths):
                Config({}).write({'provider': 'openaicompatible', 'apiKey': f'key-{index}', 'apiUrl': 'http://localhost/v1', 'model': 'test'}, path, Path(temp))
            self.assertIn('key-0', paths[0].read_text())
            self.assertNotIn('key-1', paths[0].read_text())


if __name__ == '__main__':
    unittest.main()
