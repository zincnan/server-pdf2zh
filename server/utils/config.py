"""Validated request options and task-local next-engine configuration.

Provider mappings are retained from the original service. No request ever edits a shared engine configuration.
"""
import copy
import math
from pathlib import Path

import toml
from utils.config_map import pdf2zh_next_config_map
from utils.model_policy import model_options
from utils.table_mode import parse_table_mode

DEFAULTS = {
    'sourceLang': 'en', 'targetLang': 'zh-CN', 'qps': 4, 'poolSize': 0,
    'skipLastPages': 0, 'mono': True, 'dual': True, 'dualMode': 'LR',
    'mono_cut': False, 'dual_cut': False, 'compare': False, 'crop_compare': False,
    'transFirst': False, 'ocr': False, 'autoOcr': True, 'noWatermark': True,
    'saveGlossary': False, 'disableGlossary': True, 'skipClean': False,
    'enhanceCompatibility': False, 'disableRichTextTranslate': False,
    'translateTableText': False, 'skipReferences': False, 'ignoreCache': False,
    'onlyIncludeTranslatedPage': False, 'fontFamily': 'auto', 'tableMode': '',
    'pdf_w_offset': 40, 'pdf_h_offset': 20, 'pdf_offset_ratio': 5,
}
OUTPUTS = ('mono', 'dual', 'mono_cut', 'dual_cut', 'compare', 'crop_compare')


def validate_options(data, *, require_output=True):
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise ValueError('翻译参数包含不支持的字段')
    result = copy.deepcopy(DEFAULTS)
    result.update(data)
    for key, default in DEFAULTS.items():
        value = result[key]
        if isinstance(default, bool):
            if not isinstance(value, bool):
                raise ValueError(f'{key} 必须为布尔值')
        elif isinstance(default, int):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'{key} 必须为数字')
            if key != 'pdf_offset_ratio' and int(value) != value:
                raise ValueError(f'{key} 必须为整数')
            result[key] = value if key == 'pdf_offset_ratio' else int(value)
        elif not isinstance(value, str) or len(value) > 64:
            raise ValueError(f'{key} 无效')
    for key, lo, hi in [('qps', 1, 200), ('poolSize', 0, 128), ('skipLastPages', 0, 100000),
                        ('pdf_w_offset', 0, 500), ('pdf_h_offset', 0, 500), ('pdf_offset_ratio', 0.1, 100)]:
        if not lo <= result[key] <= hi:
            raise ValueError(f'{key} 必须在 {lo}–{hi} 之间')
    import re
    for key in ('sourceLang', 'targetLang'):
        if not re.fullmatch(r'[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{2,8}){0,2}', result[key]):
            raise ValueError('语言代码无效')
    if result['dualMode'] not in ('LR', 'TB') or result['fontFamily'] not in ('auto', 'serif', 'sans-serif', 'script'):
        raise ValueError('布局或字体选项无效')
    parse_table_mode(result['tableMode'])
    if require_output and not any(result[key] for key in OUTPUTS):
        raise ValueError('请至少选择一种 PDF 输出')
    return result


class Config:
    """Cropper-facing options plus an explicit TOML writer."""
    def __init__(self, options):
        self.options = validate_options(options)
        self.table_mode = parse_table_mode(self.options['tableMode'])
        self.skip_references = self.options['skipReferences']
        self.trans_first = self.options['transFirst']
        for key in ('pdf_w_offset', 'pdf_h_offset', 'pdf_offset_ratio'):
            setattr(self, key, self.options[key])

    def write(self, profile, destination, output_dir):
        cfg = toml.load(Path(__file__).parents[1] / 'config' / 'config.toml.example')
        # Start from the immutable shipped defaults. Enable exactly one provider.
        for key in list(cfg):
            if isinstance(cfg[key], bool):
                cfg[key] = False
        service = profile['provider']
        if service not in ('openaicompatible', 'google', 'bing'):
            raise ValueError('不支持的模型服务类型')
        cfg[service] = True
        mapping = pdf2zh_next_config_map.get(service, {})
        detail = cfg.setdefault(f'{service}_detail', {})
        credentials = copy.deepcopy(profile)
        for field in ('apiKey', 'apiUrl', 'model'):
            if field in mapping and credentials.get(field):
                detail[mapping[field]] = credentials[field]
        if service == 'openaicompatible':
            controls = model_options(profile)
            detail.update(openai_compatible_send_temperature=False,
                          openai_compatible_temperature='null',
                          openai_compatible_send_reasoning_effort=False,
                          openai_compatible_reasoning_effort='null',
                          openai_compatible_enable_json_mode=controls['enableJsonMode'])
        options = self.options
        cfg['translation'].update(lang_in=options['sourceLang'], lang_out=options['targetLang'],
                                  qps=options['qps'], output=str(output_dir),
                                  pool_max_workers=options['poolSize'] or 'null', ignore_cache=options['ignoreCache'],
                                  save_auto_extracted_glossary=options['saveGlossary'],
                                  no_auto_extract_glossary=options['disableGlossary'])
        cfg['pdf'].update(only_include_translated_page=options['onlyIncludeTranslatedPage'],
                          ocr_workaround=options['ocr'],
                          auto_enable_ocr_workaround=options['autoOcr'],
                          translate_table_text=options['translateTableText'] and not self.table_mode)
        path = Path(destination)
        with path.open('w', encoding='utf-8') as stream:
            toml.dump(cfg, stream)
        path.chmod(0o600)
        return cfg
