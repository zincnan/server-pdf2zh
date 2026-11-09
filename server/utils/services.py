"""Persistent model profiles; API callers never receive stored credentials."""
import copy
import math
import re
import threading
import uuid
from urllib.parse import urlsplit

from utils.config_map import pdf2zh_next_config_map
from utils.deepseek_thinking import normalize_deepseek_extra_data
from utils.storage import atomic_json, read_json

LABELS = {'openaicompatible': 'OpenAI 兼容', 'openai': 'OpenAI', 'deepseek': 'DeepSeek',
          'ollama': 'Ollama', 'siliconflow': 'SiliconFlow', 'siliconflowfree': 'SiliconFlow 免费',
          'aliyundashscope': '阿里云百炼', 'gemini': 'Gemini', 'google': 'Google 翻译', 'bing': 'Bing 翻译'}
# CLI executors are intentionally unavailable in the container Web API.
PROVIDERS = {k: v for k, v in pdf2zh_next_config_map.items() if k != 'claudecode'}
PROVIDERS.update({'google': {}, 'bing': {}})
SECRET_RE = re.compile(r'key|token|secret|password|auth', re.I)


def is_secret(key):
    return bool(SECRET_RE.search(key))


def coerce_extra(key, value):
    if any(x in key for x in ('enable_', 'send_')):
        if isinstance(value, bool):
            return value
        if str(value).lower() in ('true', 'false'):
            return str(value).lower() == 'true'
        raise ValueError(f'{key} 必须是布尔值')
    if key == 'num_predict':
        if isinstance(value, bool) or not str(value).isdigit() or not 1 <= int(value) <= 100000:
            raise ValueError('num_predict 必须为 1–100000 的整数')
        return int(value)
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise ValueError(f'{key} 类型无效')
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f'{key} 必须是有限数值')
    if isinstance(value, str) and len(value) > 4096:
        raise ValueError(f'{key} 太长')
    return value


def provider_catalog():
    result = []
    for name, mapping in PROVIDERS.items():
        result.append({'id': name, 'label': LABELS.get(name, name),
                       'fields': [key for key in ('apiUrl', 'apiKey', 'model') if key in mapping],
                       'extraFields': [{'key': key, 'secret': is_secret(key),
                                        'type': 'boolean' if any(x in key for x in ('enable_', 'send_')) else 'text'}
                                       for key in mapping.get('extraData', [])]})
    return result


class ServiceStore:
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.data = read_json(path) if path.exists() else {'schemaVersion': 1, 'activeId': None, 'services': []}
        if self.data.get('schemaVersion') != 1:
            raise RuntimeError('不支持的模型服务配置版本，请保留数据卷并检查服务版本')

    def _save(self):
        try:
            atomic_json(self.path, self.data)
        except BaseException:
            self.data = read_json(self.path) if self.path.exists() else {'schemaVersion': 1, 'activeId': None, 'services': []}
            raise

    @staticmethod
    def public(profile):
        profile = copy.deepcopy(profile)
        profile['hasApiKey'] = bool(profile.pop('apiKey', ''))
        secrets = []
        for key in list(profile.get('extraData', {})):
            if is_secret(key):
                if profile['extraData'].pop(key):
                    secrets.append(key)
        profile['secretExtraFields'] = secrets
        return profile

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
            return copy.deepcopy(profile)

    def put(self, data, profile_id=None):
        if not isinstance(data, dict):
            raise ValueError('模型服务必须是 JSON 对象')
        allowed = {'name', 'provider', 'apiUrl', 'apiKey', 'model', 'extraData'}
        if set(data) - allowed:
            raise ValueError('模型服务包含不支持的字段')
        with self.lock:
            old = self._find(profile_id) if profile_id else None
            if profile_id and not old:
                raise KeyError(profile_id)
            profile = copy.deepcopy(old or {'id': str(uuid.uuid4()), 'revision': 0, 'name': '',
                                           'provider': 'openaicompatible', 'apiUrl': '', 'apiKey': '', 'model': '', 'extraData': {}})
            if 'provider' in data and old and data['provider'] != old['provider']:
                profile.update(apiUrl='', apiKey='', model='', extraData={})
            for key, value in data.items():
                if key == 'extraData':
                    continue
                if not isinstance(value, str) or len(value) > 4096:
                    raise ValueError(f'{key} 必须是有效文本')
                profile[key] = value.strip()
            if not profile['name'] or len(profile['name']) > 120:
                raise ValueError('请输入不超过 120 字的服务名称')
            mapping = PROVIDERS.get(profile['provider'])
            if mapping is None:
                raise ValueError('不支持的模型服务商')
            if profile['apiUrl']:
                url = urlsplit(profile['apiUrl'])
                if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.fragment or url.query:
                    raise ValueError('API URL 必须是无内嵌凭据的 HTTP(S) 地址')
            extra = data.get('extraData', {})
            if not isinstance(extra, dict) or set(extra) - set(mapping.get('extraData', [])):
                raise ValueError('包含此服务商不支持的扩展参数')
            for key, value in extra.items():
                if value in ('', None):
                    profile['extraData'].pop(key, None)
                else:
                    profile['extraData'][key] = coerce_extra(key, value)
            if profile['provider'] == 'deepseek':
                normalize_deepseek_extra_data(profile, {})
            profile['revision'] += 1
            if old:
                self.data['services'][self.data['services'].index(old)] = profile
            else:
                self.data['services'].append(profile)
            self._save()
            return self.public(profile)

    def activate(self, profile_id):
        with self.lock:
            if not self._find(profile_id):
                raise KeyError(profile_id)
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
        return {key: profile[key] for key in ('id', 'revision', 'name', 'provider', 'model')}
