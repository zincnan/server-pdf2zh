"""Single-user translation preferences, independent of jobs and model secrets."""
import copy
from collections import OrderedDict
from pathlib import Path
import threading

from utils.config import DEFAULTS, validate_options
from utils.languages import LANGUAGES
from utils.storage import atomic_json, read_json

PREFERENCE_FIELDS = frozenset(DEFAULTS) - {'compare'}
LANGUAGE_CODES = frozenset(language['code'] for language in LANGUAGES)


def validate_preferences(data):
    if not isinstance(data, dict) or set(data) - {'translationOptions'}:
        raise ValueError('设置包含不支持的字段')
    options = data.get('translationOptions')
    if not isinstance(options, dict) or set(options) - PREFERENCE_FIELDS:
        raise ValueError('翻译设置包含不支持的字段')
    result = validate_options(options, require_output=False)
    if any(result[key] not in LANGUAGE_CODES for key in ('sourceLang', 'targetLang')):
        raise ValueError('请选择语言列表中的语言')
    return {key: value for key, value in result.items() if key in PREFERENCE_FIELDS}


def validate_update(data):
    if not isinstance(data, dict) or set(data) - {'translationOptions', 'writerId', 'sequence'}:
        raise ValueError('设置包含不支持的字段')
    validate_preferences({'translationOptions': data.get('translationOptions')})
    writer, sequence = data.get('writerId'), data.get('sequence')
    if 'writerId' in data or 'sequence' in data:
        if (not isinstance(writer, str) or not 1 <= len(writer) <= 80
                or type(sequence) is not int or not 1 <= sequence <= 2**53 - 1):
            raise ValueError('设置更新顺序无效')
    return writer, sequence


class PreferenceStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        # Only delivery ordering metadata lives here. Preferences remain on disk.
        # Old HTTP requests cannot survive a service restart.
        self.writers = OrderedDict()
        try:
            data = read_json(self.path) if self.path.exists() else {'translationOptions': {}}
            self.options = validate_preferences(data)
        except (ValueError, TypeError) as exc:
            raise ValueError('翻译设置文件无效，请检查 config/preferences.json；原文件已保留') from exc

    def get(self):
        with self.lock:
            return {'translationOptions': copy.deepcopy(self.options)}

    def patch(self, data):
        # Check the patch before merging, so unknown fields are never discarded.
        writer, sequence = validate_update(data)
        with self.lock:
            changes = data['translationOptions']
            previous = self.writers.get(writer, {}) if writer is not None else {}
            if writer is not None:
                changes = {key: value for key, value in changes.items() if sequence > previous.get(key, 0)}
            if not changes:
                return self.get()
            options = validate_preferences({'translationOptions': {**self.options, **changes}})
            atomic_json(self.path, {'translationOptions': options})
            self.options = options
            if writer is not None:
                self.writers[writer] = {**previous, **{key: sequence for key in changes}}
                self.writers.move_to_end(writer)
                if len(self.writers) > 256:
                    self.writers.popitem(last=False)
            return self.get()
