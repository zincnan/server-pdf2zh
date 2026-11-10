"""PDF AI Translator Web service. Start through Docker Compose."""
import json
import os
import secrets
import signal
import threading
import time
from urllib.parse import urlsplit
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file, session
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from utils.config import DEFAULTS, validate_options
from utils.services import ServiceStore, provider_catalog
from utils.model_policy import EFFORTS, MODEL_RULES
from utils.storage import atomic_json, read_json
from utils.task_manager import BusyError, InvalidPDF, TaskManager

__version__ = '1.0.0'
PRODUCT_NAME = 'PDF AI Translator'
PROJECT_ID = 'pdf-ai-translator'
SERVICE_NAME = 'pdf-ai-translator-server'
ROOT = Path(__file__).resolve().parent


def create_app(config=None):
    app = Flask(__name__, static_folder=str(ROOT / 'static'))
    published = os.environ.get('PUBLISHED_BIND_ADDRESS', '0.0.0.0')
    app.config.update(
        DATA_DIR=os.environ.get('DATA_DIR', '/data'),
        ASSET_DIR=os.environ.get('ASSET_DIR', '/opt/pdf2zh-assets'),
        MAX_WORKERS=int(os.environ.get('MAX_CONCURRENT_TASKS', '2')),
        MAX_CONTENT_LENGTH=(int(os.environ.get('MAX_UPLOAD_MB', '100')) + 1) * 1024 * 1024,
        MAX_FILE_BYTES=int(os.environ.get('MAX_UPLOAD_MB', '100')) * 1024 * 1024,
        AUTH_REQUIRED=published not in ('127.0.0.1', '::1', 'localhost'),
        ACCESS_PASSWORD=os.environ.get('ACCESS_PASSWORD', 'pdf2zh'),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
        SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', 'false').lower() == 'true',
    )
    if config:
        app.config.update(config)
    if not 1 <= app.config['MAX_WORKERS'] <= 32:
        raise ValueError('MAX_CONCURRENT_TASKS 必须在 1–32 之间')
    if app.config['AUTH_REQUIRED'] and not app.config['ACCESS_PASSWORD']:
        raise ValueError('公开绑定必须配置访问密码')
    data = Path(app.config['DATA_DIR'])
    manager = TaskManager(data, app.config['MAX_WORKERS'], assets=app.config['ASSET_DIR'],
                          **({'runner': app.config['TASK_RUNNER']} if 'TASK_RUNNER' in app.config else {}))
    try:
        config_dir = data / 'config'
        config_dir.mkdir(mode=0o700, exist_ok=True)
        secret_path = config_dir / 'session.json'
        if not secret_path.exists():
            atomic_json(secret_path, {'secret': secrets.token_hex(32)})
        app.secret_key = read_json(secret_path)['secret']
        services = ServiceStore(config_dir / 'services.json')
    except Exception:
        manager.shutdown(0)
        raise
    app.extensions.update(tasks=manager, model_services=services)
    login_failures = {}
    login_lock = threading.Lock()

    @app.before_request
    def protect():
        # A custom header blocks cross-origin form submissions, including in
        # local passwordless mode. No CORS permission is granted.
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            if request.headers.get('X-PDF-AI-Translator-Request') != '1':
                return jsonify(error='请求来源无效'), 403
            origin = request.headers.get('Origin')
            if origin and (urlsplit(origin).scheme not in ('http', 'https') or urlsplit(origin).netloc.lower() != request.host.lower()):
                return jsonify(error='不允许跨站请求'), 403
        public = request.path in ('/', '/health', '/api/session') or request.path.startswith('/static/')
        if not public and app.config['AUTH_REQUIRED'] and not session.get('authenticated'):
            return jsonify(error='请先输入访问密码'), 401

    @app.after_request
    def response_headers(response):
        if request.path.startswith('/api/') or request.path == '/events':
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        return response

    @app.errorhandler(Exception)
    def errors(exc):
        if isinstance(exc, InvalidPDF):
            return jsonify(error=str(exc)), 422
        if isinstance(exc, BusyError):
            return jsonify(error=str(exc)), 409
        if isinstance(exc, KeyError):
            return jsonify(error='记录或文件不存在'), 404
        if isinstance(exc, RequestEntityTooLarge):
            return jsonify(error='PDF 超过上传大小限制'), 413
        if isinstance(exc, ValueError):
            return jsonify(error=str(exc)), 400
        if isinstance(exc, HTTPException):
            return jsonify(error=exc.name), exc.code
        # Do not print request bodies, credentials or task contents into the
        # container's permanent logging stream.
        return jsonify(error='操作失败，请检查磁盘空间和目录权限'), 500

    def json_body():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ValueError('请提交 JSON 对象')
        return body

    @app.get('/')
    def index():
        return send_file(ROOT / 'index.html')

    @app.get('/health')
    def health():
        return jsonify(status='ok' if manager.accepting else 'stopping', version=__version__,
                       product=PRODUCT_NAME, project=PROJECT_ID, service=SERVICE_NAME), 200 if manager.accepting else 503

    @app.route('/api/session', methods=['GET', 'POST', 'DELETE'])
    def access_session():
        if request.method == 'POST':
            with login_lock:
                ip = request.remote_addr or ''
                stamp, count = login_failures.get(ip, (0, 0))
                if time.monotonic() - stamp > 60:
                    stamp, count = time.monotonic(), 0
                if count >= 10:
                    return jsonify(error='尝试过于频繁，请一分钟后重试'), 429
                password = json_body().get('password', '')
                if not isinstance(password, str) or not secrets.compare_digest(password.encode(), app.config['ACCESS_PASSWORD'].encode()):
                    login_failures[ip] = (stamp, count + 1)
                    return jsonify(error='密码不正确'), 401
                login_failures.pop(ip, None)
            session.clear()
            session['authenticated'] = True
        elif request.method == 'DELETE':
            session.clear()
        return jsonify(required=app.config['AUTH_REQUIRED'], authenticated=not app.config['AUTH_REQUIRED'] or bool(session.get('authenticated')))

    @app.get('/api/capabilities')
    def capabilities():
        return jsonify(version=__version__, product=PRODUCT_NAME, project=PROJECT_ID, service=SERVICE_NAME,
                       engine='pdf2zh_next', providers=provider_catalog(), defaults=DEFAULTS,
                       modelRules=MODEL_RULES, reasoningEfforts=EFFORTS,
                       maxUploadBytes=app.config['MAX_FILE_BYTES'], concurrency=app.config['MAX_WORKERS'])

    @app.route('/api/model-services', methods=['GET', 'POST'])
    def model_services():
        if request.method == 'GET':
            return jsonify(services.list())
        return jsonify(services.put(json_body())), 201

    @app.route('/api/model-services/<profile_id>', methods=['PATCH', 'DELETE'])
    def model_service(profile_id):
        if request.method == 'PATCH':
            return jsonify(services.put(json_body(), profile_id))
        services.delete(profile_id)
        return '', 204

    @app.put('/api/model-services/<profile_id>/active')
    def activate_service(profile_id):
        services.activate(profile_id)
        return jsonify(services.list())

    @app.route('/api/tasks', methods=['GET', 'POST', 'DELETE'])
    def tasks():
        if request.method == 'GET':
            return jsonify(tasks=manager.list())
        if request.method == 'DELETE':
            return jsonify(manager.clear_all())
        uploaded = request.files.get('file')
        if not uploaded or not uploaded.filename:
            raise ValueError('请选择 PDF 文件')
        raw_name = uploaded.filename.replace('\\', '/').split('/')[-1]
        if not raw_name.lower().endswith('.pdf') or len(raw_name) > 240 or any(ord(c) < 32 for c in raw_name):
            raise ValueError('请输入有效的 PDF 文件名')
        uploaded.stream.seek(0, 2)
        size = uploaded.stream.tell()
        uploaded.stream.seek(0)
        if size > app.config['MAX_FILE_BYTES']:
            raise RequestEntityTooLarge()
        try:
            options = validate_options(json.loads(request.form.get('options', '{}')))
        except json.JSONDecodeError as exc:
            raise ValueError('翻译参数不是有效的 JSON') from exc
        task = manager.submit(uploaded.stream, raw_name, options, services.active())
        return jsonify(taskId=task['id'], task=task), 202

    @app.route('/api/tasks/<task_id>', methods=['GET', 'DELETE'])
    def task(task_id):
        if request.method == 'GET':
            return jsonify(manager.get(task_id))
        manager.clear(task_id)
        return '', 204

    @app.post('/api/tasks/<task_id>/retry')
    def retry(task_id):
        task = manager.retry(task_id, services.active())
        return jsonify(taskId=task['id'], task=task), 202

    @app.get('/api/tasks/<task_id>/files/<file_id>')
    def download(task_id, file_id):
        lease = manager.download(task_id, file_id)
        path, item = lease.__enter__()
        try:
            stream = path.open('rb')
            response = send_file(stream, as_attachment=request.args.get('preview') != 'true',
                                 download_name=item['name'], mimetype='application/pdf' if path.suffix == '.pdf' else 'text/csv',
                                 conditional=False)
            response.direct_passthrough = False
            response.call_on_close(lambda: lease.__exit__(None, None, None))
            return response
        except BaseException:
            lease.__exit__(None, None, None)
            raise

    @app.get('/events')
    def events():
        def generate():
            # A snapshot protocol makes reconnects and missed deletions safe.
            while manager.accepting:
                yield 'data: ' + json.dumps({'type': 'tasks', 'data': manager.list()}, ensure_ascii=False) + '\n\n'
                time.sleep(1)
        return Response(generate(), mimetype='text/event-stream', headers={'X-Accel-Buffering': 'no'})

    return app


def main():
    from waitress import create_server
    app = create_app()
    port = int(os.environ.get('PORT', '7000'))
    server = create_server(app, host='0.0.0.0', port=port,
                           threads=16, max_request_body_size=app.config['MAX_CONTENT_LENGTH'],
                           channel_timeout=60, expose_tracebacks=False)
    stopping = threading.Event()

    def stop(signum, frame):
        stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    thread = threading.Thread(target=server.run, name='http', daemon=True)
    thread.start()
    print(f'{PRODUCT_NAME} listening on :{port}', flush=True)
    while thread.is_alive() and not stopping.wait(0.5):
        pass
    clean = app.extensions['tasks'].shutdown(int(os.environ.get('SHUTDOWN_GRACE_SECONDS', '600')))
    server.close()
    if not clean:
        # Do not let a stuck native postprocessing thread defeat the stop grace.
        os._exit(0)


if __name__ == '__main__':
    main()
