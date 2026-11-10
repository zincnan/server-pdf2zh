"""Durable model profiles, explicit controls, and lossless v1 migration."""
import copy
from pathlib import Path
import re
import threading
import uuid
from urllib.parse import urlsplit

from utils.model_policy import EFFORTS, MODEL_DEFAULTS, model_family, model_options
from utils.storage import atomic_json, read_json

PROVIDERS = {
    'openaicompatible': 'OpenAI compatible',
    'google': 'Google 翻译',
    'bing': 'Bing 翻译',
}
SECRET_RE = re.compile(r'key|token|secret|password|auth', re.I)
PROFILE_FIELDS = ('id', 'revision', 'name', 'provider', 'apiUrl', 'apiKey', 'model', *MODEL_DEFAULTS)


def is_secret(key):
    return bool(SECRET_RE.search(key))


def provider_catalog():
    return [{'id': name, 'label': label,
             'fields': ['apiUrl', 'apiKey', 'model'] if name == 'openaicompatible' else []}
            for name, label in PROVIDERS.items()]


def validate_profile(profile):
    if profile['provider'] not in PROVIDERS:
        raise ValueError('此服务类型已下线，请编辑转换为受支持的服务')
    if not profile['name'] or len(profile['name']) > 120:
        raise ValueError('请输入不超过 120 字的服务名称')
    if profile['provider'] == 'openaicompatible':
        for key, label in [('apiUrl', 'Base URL'), ('apiKey', 'API Key'), ('model', 'Model ID')]:
            if not profile.get(key):
                raise ValueError(f'请填写 {label}')
        url = urlsplit(profile['apiUrl'])
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.fragment or url.query:
            raise ValueError('Base URL 必须是无内嵌凭据的 HTTP(S) 地址')
        _ = url.port  # Reject malformed ports before persisting the URL.
        model_options(profile)


def needs_conversion(profile):
    try:
        validate_profile(profile)
        return False
    except ValueError:
        return True


def legacy_bool(value):
    return value is True or str(value).lower() in ('true', '1')


class ServiceStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.data = read_json(path) if self.path.exists() else self.empty()
        version = self.data.get('schemaVersion')
        if version == 1:
            self._migrate_v1()
        elif version != 2:
            raise RuntimeError('不支持的模型服务配置版本，请保留数据卷并检查服务版本')

    @staticmethod
    def empty():
        return {'schemaVersion': 2, 'activeId': None, 'services': []}

    def _migrate_v1(self):
        # The original file and all unsupported extension fields survive in a
        # mode-0600 backup. Never mutate it on a subsequent startup.
        backup = self.path.with_name('services.v1.backup.json')
        if not backup.exists():
            atomic_json(backup, self.data)
        migrated = copy.deepcopy(self.data)
        migrated['schemaVersion'] = 2
        for profile in migrated['services']:
            old_provider = profile['provider']
            if old_provider in ('openai', 'openaicompatible'):
                prefix = 'openai' if old_provider == 'openai' else 'openai_compatible'
                extra = profile.pop('extraData', {})
                profile['enableJsonMode'] = legacy_bool(extra.get(prefix + '_enable_json_mode'))
                effort = extra.get(prefix + '_reasoning_effort', '')
                sending = legacy_bool(extra.get(prefix + '_send_reasoning_effort'))
                profile['thinkingEnabled'] = sending and effort not in ('', None, 'none')
                profile['reasoningEffort'] = str(effort) if sending and effort in EFFORTS else ''
                profile['provider'] = 'openaicompatible'
                if old_provider == 'openai':
                    profile['apiUrl'] = profile.get('apiUrl') or 'https://api.openai.com/v1'
                # These were the shipped engine defaults, now made explicit.
                profile['model'] = profile.get('model') or 'gpt-4o-mini'
                profile['revision'] += 1
            elif old_provider in ('google', 'bing'):
                for key in ('apiUrl', 'apiKey', 'model'):
                    profile[key] = ''
                profile.pop('extraData', None)
                profile.update(MODEL_DEFAULTS)
            # Unsupported providers stay intact on disk, not in active choices.
        active = next((p for p in migrated['services'] if p['id'] == migrated['activeId']), None)
        if active is None or needs_conversion(active):
            migrated['activeId'] = None
        atomic_json(self.path, migrated)
        self.data = migrated

    def _save(self):
        try:
            atomic_json(self.path, self.data)
        except BaseException:
            self.data = read_json(self.path) if self.path.exists() else self.empty()
            raise

    @staticmethod
    def public(profile):
        # Whitelist rather than redact arbitrary old fields. In particular,
        # legacy Tencent profiles used their model field for a credential ID.
        result = {key: copy.deepcopy(profile.get(key, '')) for key in PROFILE_FIELDS if key != 'apiKey'}
        result.update({key: profile.get(key, default) for key, default in MODEL_DEFAULTS.items()})
        if profile['provider'] == 'tencentmechinetranslation':
            result['model'] = ''
        result.update(hasApiKey=bool(profile.get('apiKey')), needsConversion=needs_conversion(profile),
                      modelFamily=model_family(profile.get('model', '')))
        return result

    def list(self):
        with self.lock:
            return {'activeId': self.data['activeId'], 'services': [self.public(p) for p in self.data['services']]}

    def _find(self, profile_id):
        return next((p for p in self.data['services'] if p['id'] == profile_id), None)

    def active(self):
        with self.lock:
            profile = self._find(self.data['activeId'])
            if not profile:
                raise ValueError('请先添加并激活一个模型服务')
            validate_profile(profile)
            return copy.deepcopy(profile)

    def put(self, data, profile_id=None):
        allowed = {'name', 'provider', 'apiUrl', 'apiKey', 'model', *MODEL_DEFAULTS}
        if not isinstance(data, dict) or set(data) - allowed:
            raise ValueError('模型服务包含不支持的字段')
        with self.lock:
            old = self._find(profile_id) if profile_id else None
            if profile_id and not old:
                raise KeyError(profile_id)
            profile = {'id': profile_id or str(uuid.uuid4()), 'revision': 0, 'name': '',
                       'provider': 'openaicompatible', 'apiUrl': '', 'apiKey': '', 'model': '', **MODEL_DEFAULTS}
            if old:
                profile.update({key: old[key] for key in PROFILE_FIELDS if key in old})
            for key, value in data.items():
                if key not in MODEL_DEFAULTS:
                    if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value):
                        raise ValueError(f'{key} 必须是有效文本')
                    value = value.strip()
                profile[key] = value
            if profile['provider'] in ('google', 'bing'):
                if set(data) - {'name', 'provider'}:
                    raise ValueError('Google 和 Bing 翻译只需填写配置名称')
                profile.update(apiUrl='', apiKey='', model='', **MODEL_DEFAULTS)
            elif profile.get('apiUrl'):
                # Accept a copied completions URL without duplicating its suffix.
                profile['apiUrl'] = re.sub(r'/chat/completions/?$', '', profile['apiUrl']).rstrip('/')
            validate_profile(profile)
            profile['revision'] += 1
            if old:
                self.data['services'][self.data['services'].index(old)] = profile
            else:
                self.data['services'].append(profile)
            self._save()
            return self.public(profile)

    def activate(self, profile_id):
        with self.lock:
            profile = self._find(profile_id)
            if not profile:
                raise KeyError(profile_id)
            validate_profile(profile)
            self.data['activeId'] = profile_id
            self._save()

    def delete(self, profile_id):
        with self.lock:
            profile = self._find(profile_id)
            if not profile:
                raise KeyError(profile_id)
            self.data['services'].remove(profile)
            if self.data['activeId'] == profile_id:
                self.data['activeId'] = None
            self._save()

    @staticmethod
    def snapshot(profile):
        return {**{key: profile[key] for key in ('id', 'revision', 'name', 'provider', 'model')},
                **{key: profile.get(key, default) for key, default in MODEL_DEFAULTS.items()}}
