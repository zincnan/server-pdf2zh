"""Single-process, persistent job lifecycle with bounded background execution."""
import copy
import fcntl
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import fitz
from utils.config import validate_options
from utils.execute import TaskLog, terminate_process
from utils.pipeline import run_pipeline
from utils.services import ServiceStore
from utils.storage import atomic_json, read_json

TERMINAL = {'succeeded', 'failed', 'interrupted', 'cleanup_failed'}


def now():
    return datetime.now(timezone.utc).isoformat()


class BusyError(Exception):
    pass


class InvalidPDF(ValueError):
    pass


def validate_pdf(path):
    try:
        with path.open('rb') as stream:
            if b'%PDF-' not in stream.read(1024):
                raise InvalidPDF('文件不是有效的 PDF')
        with fitz.open(path) as doc:
            if doc.needs_pass or not doc.is_pdf or not len(doc):
                raise InvalidPDF('PDF 已加密、没有页面或无法读取')
            return len(doc)
    except InvalidPDF:
        raise
    except Exception as exc:
        raise InvalidPDF('无法读取此 PDF，请检查文件是否损坏') from exc


class TaskManager:
    def __init__(self, root, workers=2, runner=run_pipeline, assets=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lockfile = (self.root / '.instance.lock').open('a')
        try:
            fcntl.flock(self.lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.lockfile.close()
            raise RuntimeError('此数据卷已被另一个服务进程使用') from exc
        self.tasks_dir, self.trash = self.root / 'tasks', self.root / '.trash'
        self.tasks_dir.mkdir(exist_ok=True, mode=0o700)
        self.trash.mkdir(exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.tasks, self.downloads, self.processes = {}, {}, {}
        self.stopping = threading.Event()
        self.accepting = True
        self.runner, self.assets = runner, assets
        self._last_persist = {}
        self.futures = set()
        try:
            self._recover()
        except BaseException:
            self.lockfile.close()
            raise
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='pdf-task')

    def directory(self, task_id):
        # IDs come from internal records, never from a user-supplied path.
        if task_id not in self.tasks:
            raise KeyError(task_id)
        return self.tasks_dir / task_id

    def _recover(self):
        for item in self.trash.iterdir():
            if item.is_dir() and not item.is_symlink():
                try:
                    shutil.rmtree(item)
                except OSError:
                    pass  # Listed as cleanup_failed below if still present.
        for directory in self.tasks_dir.iterdir():
            if not directory.is_dir() or directory.is_symlink():
                continue
            try:
                if str(uuid.UUID(directory.name)) != directory.name:
                    continue
                task = read_json(directory / 'task.json')
                if task.get('schemaVersion') != 1 or task.get('id') != directory.name:
                    raise RuntimeError('任务清单版本或 ID 无效，拒绝启动以保护数据')
            except (ValueError, OSError):
                task = {'schemaVersion': 1, 'id': directory.name, 'fileName': '未完成的上传',
                        'state': 'interrupted', 'stage': 'interrupted', 'progress': 0,
                        'createdAt': now(), 'files': [], 'options': {}, 'message': '上传或保存被中断，可清理此任务'}
            if task['state'] not in TERMINAL:
                task.update(state='interrupted', stage='interrupted', endedAt=now(), message='服务重启导致中断，请手动重试')
            task['canRetry'] = (directory / 'input.pdf').is_file()
            (directory / 'engine.toml').unlink(missing_ok=True)
            shutil.rmtree(directory / 'home' / '.config', ignore_errors=True)
            self.tasks[task['id']] = task
            atomic_json(directory / 'task.json', task)
        for item in self.trash.iterdir():
            if item.is_dir() and not item.is_symlink():
                self.tasks[item.name] = {'schemaVersion': 1, 'id': item.name, 'fileName': '待清理数据',
                    'state': 'cleanup_failed', 'stage': 'cleanup_failed', 'progress': 0,
                    'createdAt': now(), 'files': [], 'canRetry': False, 'message': '上次清理未完成，请再次 Clear'}

    def _persist(self, task_id):
        atomic_json(self.directory(task_id) / 'task.json', self.tasks[task_id])
        self._last_persist[task_id] = time.monotonic()

    def list(self):
        with self.lock:
            return copy.deepcopy(sorted(self.tasks.values(), key=lambda t: t['createdAt'], reverse=True))

    def get(self, task_id):
        with self.lock:
            if task_id not in self.tasks:
                raise KeyError(task_id)
            return copy.deepcopy(self.tasks[task_id])

    def update(self, task_id, **values):
        with self.lock:
            task = self.tasks[task_id]
            if task['state'] in TERMINAL:
                return
            task.update(values)
            # Bound fsync frequency while keeping terminal transitions durable.
            if 'stage' in values or 'state' in values or time.monotonic() - self._last_persist.get(task_id, 0) > 1:
                self._persist(task_id)

    def _register(self, task_id, process):
        with self.lock:
            if process is None:
                self.processes.pop(task_id, None)
            elif self.stopping.is_set():
                terminate_process(process)
            else:
                self.processes[task_id] = process

    def submit(self, source, filename, options, profile):
        options = validate_options(options)
        with self.lock:
            if not self.accepting:
                raise BusyError('服务正在停止，请稍后再试')
            task_id = str(uuid.uuid4())
            directory = self.tasks_dir / task_id
            directory.mkdir(mode=0o700)
            self.tasks[task_id] = {'schemaVersion': 1, 'id': task_id, 'fileName': filename,
                'state': 'queued', 'stage': 'uploading', 'progress': 0, 'message': '正在接收 PDF',
                'createdAt': now(), 'files': [], 'options': options,
                'service': ServiceStore.snapshot(profile), 'canRetry': False}
            try:
                self._persist(task_id)
                with (directory / 'input.pdf').open('wb') as dest:
                    shutil.copyfileobj(source, dest)
                    dest.flush()
                    os.fsync(dest.fileno())
                pages = validate_pdf(directory / 'input.pdf')
                if options['skipLastPages'] >= pages:
                    raise ValueError('跳过尾页后没有可翻译的页面')
                self.tasks[task_id].update(stage='queued', message='等待执行', pages=pages, canRetry=True)
                self._persist(task_id)
                future = self.executor.submit(self._run, task_id, copy.deepcopy(profile))
                self.futures.add(future)
                future.add_done_callback(self._forget_future)
                return copy.deepcopy(self.tasks[task_id])
            except Exception:
                self.tasks.pop(task_id, None)
                shutil.rmtree(directory, ignore_errors=True)
                raise

    def _forget_future(self, future):
        with self.lock:
            self.futures.discard(future)

    def _run(self, task_id, profile):
        directory = self.tasks_dir / task_id
        try:
            with self.lock:
                if not self.accepting:
                    self.tasks[task_id].update(state='interrupted', stage='interrupted', message='服务停止，任务未执行', endedAt=now())
                    self._persist(task_id)
                    return
                self.tasks[task_id].update(state='running', stage='preparing', startedAt=now(), message='准备翻译')
                self._persist(task_id)
            results = self.runner(directory, self.tasks[task_id]['options'], profile,
                                  lambda **v: self.update(task_id, **v),
                                  lambda process: self._register(task_id, process), self.stopping, self.assets)
            files = []
            for kind, path in results.items():
                path = Path(path).resolve()
                path.relative_to(directory.resolve())
                if not path.is_file():
                    raise RuntimeError('请求的结果文件缺失')
                suffix = '.csv' if path.suffix == '.csv' else '.pdf'
                files.append({'id': str(uuid.uuid4()), 'type': kind, 'path': str(path.relative_to(directory)),
                              'name': Path(self.tasks[task_id]['fileName']).stem + '.' + kind.replace('_', '-') + suffix,
                              'size': path.stat().st_size})
            if not files:
                raise RuntimeError('翻译结束但没有生成结果')
            with self.lock:
                if self.stopping.is_set():
                    raise InterruptedError('服务停止，任务已中断')
                self.tasks[task_id].update(state='succeeded', stage='completed', progress=100,
                                           message='翻译完成', files=files, endedAt=now())
                self._persist(task_id)
        except Exception as exc:
            log = TaskLog(directory / 'task.log', profile)
            try:
                log.write(str(exc))
            except OSError:
                pass
            from utils.error_catalog import classify_error_blob
            classification = classify_error_blob(log.tail())
            with self.lock:
                self.tasks[task_id].update(state='interrupted' if self.stopping.is_set() else 'failed',
                    stage='interrupted' if self.stopping.is_set() else 'failed', endedAt=now(),
                    message=classification.get('userMessage') or log.redact(str(exc))[-4000:],
                    errorCode=classification.get('errorCode', 'UNKNOWN_ERROR'),
                    hint=classification.get('hint', ''))
                self._persist(task_id)
        finally:
            (directory / 'engine.toml').unlink(missing_ok=True)
            profile.clear()

    def retry(self, task_id, profile):
        with self.lock:
            task = self.get(task_id)
            if task['state'] not in TERMINAL or not task.get('canRetry'):
                raise BusyError('此任务当前不能重试')
            with (self.directory(task_id) / 'input.pdf').open('rb') as source:
                return self.submit(source, task['fileName'], task['options'], profile)

    @contextmanager
    def download(self, task_id, file_id):
        with self.lock:
            task = self.get(task_id)
            if task['state'] != 'succeeded':
                raise BusyError('结果尚不可下载')
            item = next((f for f in task['files'] if f['id'] == file_id), None)
            if not item:
                raise KeyError(file_id)
            path = (self.directory(task_id) / item['path']).resolve()
            path.relative_to(self.directory(task_id).resolve())
            if not path.is_file():
                raise KeyError(file_id)
            self.downloads[task_id] = self.downloads.get(task_id, 0) + 1
        try:
            yield path, item
        finally:
            with self.lock:
                self.downloads[task_id] -= 1

    def clear(self, task_id):
        with self.lock:
            task = self.get(task_id)
            if task['state'] not in TERMINAL or self.downloads.get(task_id, 0):
                raise BusyError('运行中或下载中的任务不能清理')
            source = self.directory(task_id)
            target = self.trash / task_id
            if source.exists():
                source.rename(target)
            try:
                shutil.rmtree(target)
            except OSError:
                self.tasks[task_id].update(state='cleanup_failed', message='清理失败，请重试', files=[], canRetry=False)
                raise
            del self.tasks[task_id]
            self.downloads.pop(task_id, None)
            self._last_persist.pop(task_id, None)

    def clear_all(self):
        result = {'cleared': [], 'skipped': [], 'failed': []}
        with self.lock:
            for task_id in list(self.tasks):
                try:
                    self.clear(task_id)
                    result['cleared'].append(task_id)
                except BusyError:
                    result['skipped'].append(task_id)
                except OSError:
                    result['failed'].append(task_id)
        return result

    def shutdown(self, grace=600):
        with self.lock:
            self.accepting = False
            pending = list(self.futures)
        _, unfinished = wait(pending, timeout=grace) if pending else (set(), set())
        self.stopping.set()
        with self.lock:
            processes = list(self.processes.values())
        for process in processes:
            terminate_process(process)
        # A stuck PDF postprocessor may be force-stopped by Docker. Its durable
        # running manifest is recovered as interrupted by the next process.
        if unfinished:
            with self.lock:
                for task_id, task in self.tasks.items():
                    if task['state'] not in TERMINAL:
                        task.update(state='interrupted', stage='interrupted', endedAt=now(), message='服务停止，任务已中断')
                        self._persist(task_id)
        self.executor.shutdown(wait=not unfinished, cancel_futures=True)
        if not unfinished or all(f.done() for f in unfinished):
            self.lockfile.close()
        return not unfinished
