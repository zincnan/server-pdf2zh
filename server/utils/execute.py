"""Linux PTY execution and progress parsing retained from the original service.

All mutable output, process and progress state belongs to one task context.
"""
import codecs
import collections
import os
import pty
import re
import select
import signal
import struct
import subprocess
import termios
import fcntl

ANSI = re.compile(r'\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]')
MAIN_PROGRESS_RE = re.compile(r'\btranslate\s+[^a-z\(\)\r\n]*?(\d+)/(\d+)\b', re.I)
STEP_PROGRESS_RE = re.compile(r'(.+?)\(\d+/\d+\)\s+.*?(\d+)/(\d+)')


def clean_text(text):
    return re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', ANSI.sub('', text))


def parse_progress(text):
    text = clean_text(text)
    match = MAIN_PROGRESS_RE.search(text)
    if match:
        current, total = map(int, match.groups())
        if total:
            return {'progress': min(99, int(current / total * 100)), 'message': f'翻译 {current}/{total}'}
    match = STEP_PROGRESS_RE.search(text)
    if match:
        return {'message': match.group(1).strip()[:240]}
    return {}


class TaskLog:
    def __init__(self, path, profile):
        self.path = path
        self.lines = collections.deque(maxlen=120)
        self.secrets = [str(profile.get('apiKey', ''))]
        from utils.services import is_secret
        self.secrets += [str(v) for k, v in profile.get('extraData', {}).items() if is_secret(k)]
        self.secrets = sorted((s for s in self.secrets if s), key=len, reverse=True)

    def redact(self, text):
        text = clean_text(str(text))
        for secret in self.secrets:
            text = text.replace(secret, '[REDACTED]')
        # Some SDKs print a URL query containing a credential.
        text = re.sub(r'(?i)([?&](?:key|api_key|token|access_token)=)[^\s&]+', r'\1[REDACTED]', text)
        return text

    def write(self, text):
        text = self.redact(text)
        for line in text.splitlines():
            if line.strip():
                self.lines.append(line[:1000])
        # Bound on-disk diagnostic data, without forwarding PDF text to stdout.
        if self.path.exists() and self.path.stat().st_size > 2 * 1024 * 1024:
            self.path.write_text('\n'.join(self.lines), encoding='utf-8')
        with self.path.open('a', encoding='utf-8') as stream:
            stream.write(text)
            if not text.endswith('\n'):
                stream.write('\n')

    def tail(self):
        return '\n'.join(list(self.lines)[-12:])[-4000:]


def terminate_process(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def execute_with_progress(command, directory, env, update, register, log, stopping):
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 140, 0, 0))
    process = None
    decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
    pending = ''
    try:
        process = subprocess.Popen(command, cwd=directory, env=env, stdout=slave, stderr=slave,
                                   close_fds=True, start_new_session=True)
        os.close(slave)
        slave = None
        register(process)
        while True:
            if stopping.is_set():
                raise InterruptedError('服务正在停止，任务可在重启后手动重试')
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    data = os.read(master, 8192)
                except OSError:
                    break
                if not data:
                    break
                pending += decoder.decode(data)
                segments = re.split(r'[\r\n]', pending)
                pending = segments.pop()[-16000:]
                for line in segments:
                    if line.strip():
                        log.write(line)
                        values = parse_progress(line)
                        if values:
                            update(**values)
            elif process.poll() is not None:
                break
        pending += decoder.decode(b'', final=True)
        if pending:
            log.write(pending)
        return_code = process.wait()
        if return_code:
            raise RuntimeError(f'翻译引擎退出，代码 {return_code}\n{log.tail()}')
    finally:
        if process and process.poll() is None:
            terminate_process(process)
        register(None)
        os.close(master)
        if slave is not None:
            os.close(slave)
