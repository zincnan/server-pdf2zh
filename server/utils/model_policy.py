"""Model-ID recognition and task-local OpenAI-compatible request controls."""
import re

POLICY_FLAG = '--model-policy-file'
EFFORTS = ('', 'low', 'medium', 'high', 'xhigh', 'max')
MODEL_DEFAULTS = {'enableJsonMode': False, 'thinkingEnabled': False, 'reasoningEffort': ''}
# Shared with the browser through capabilities; namespaces are stripped first.
MODEL_RULES = (
    {'id': 'deepseek', 'label': 'DeepSeek', 'pattern': '^deepseek'},
    {'id': 'qwen', 'label': 'Qwen / QwQ', 'pattern': '^(qwen|qwq)'},
    {'id': 'openai-reasoning', 'label': 'OpenAI 推理模型', 'pattern': '^(o[134]($|[-.])|gpt-[56]($|[-.]))'},
)


def model_family(model):
    name = str(model).strip().rsplit('/', 1)[-1].lower()
    for rule in MODEL_RULES:
        if re.search(rule['pattern'], name):
            return rule['id']
    return 'openai'


def model_options(profile):
    options = {key: profile.get(key, default) for key, default in MODEL_DEFAULTS.items()}
    for key in ('enableJsonMode', 'thinkingEnabled'):
        if type(options[key]) is not bool:
            raise ValueError(f'{key} 必须是布尔值')
    if not isinstance(options['reasoningEffort'], str) or options['reasoningEffort'] not in EFFORTS:
        raise ValueError('推理强度必须是不发送、low、medium、high、xhigh 或 max')
    if options['thinkingEnabled'] and model_family(profile.get('model', '')) in ('openai', 'openai-reasoning') and not options['reasoningEffort']:
        raise ValueError('OpenAI 格式开启思考时，请选择具体的推理强度')
    return options


def request_fields(profile):
    """Return only effective request controls, never temperature or secrets."""
    options = model_options(profile)
    family = model_family(profile.get('model', ''))
    enabled = options['thinkingEnabled']
    result = {}
    if family == 'deepseek':
        result['thinking'] = {'type': 'enabled' if enabled else 'disabled'}
    elif family == 'qwen':
        result['enable_thinking'] = enabled
    elif not enabled and family == 'openai-reasoning':
        result['reasoning_effort'] = 'none'
    if enabled and options['reasoningEffort']:
        result['reasoning_effort'] = options['reasoningEffort']
    return result


def runtime_policy(profile):
    options = model_options(profile)
    return {'model': profile['model'], **options}


def install_model_policy(policy):
    """Decorate the existing translator only inside this engine/worker process.

    Keep its prompts, rate limiting, cache, JSON-mode behavior, usage accounting
    and retries. Both normal and LLM translation calls use instance.options.
    """
    from pdf2zh_next.translator.translator_impl.openai import OpenAITranslator

    fields = request_fields(policy)
    enabled_json = model_options(policy)['enableJsonMode']
    original = OpenAITranslator.__init__

    def initialize(instance, *args, **kwargs):
        original(instance, *args, **kwargs)
        instance.options.pop('temperature', None)
        instance.options.pop('reasoning_effort', None)
        instance.options.pop('extra_body', None)
        instance.options['extra_body'] = fields.copy()
        instance.enable_json_mode = enabled_json
        instance.add_cache_impact_parameters('web_model_policy', {
            'fields': fields, 'jsonMode': enabled_json, 'temperature': 'omitted',
        })

    OpenAITranslator.__init__ = initialize

    def restore():
        OpenAITranslator.__init__ = original

    return restore
