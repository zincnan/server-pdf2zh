"""Existing pdf2zh_next provider field mappings, retained from the upstream service."""
apiKey = "apiKey"
apiUrl = "apiUrl"
model = "model"
extraData = "extraData"

pdf2zh_next_config_map = {
    "deepl": {
        apiKey: "deepl_auth_key"
    },
    "openai": {
        apiKey: "openai_api_key",
        model: "openai_model",
        apiUrl: "openai_base_url",
        extraData: [
            "openai_timeout",
            "openai_temperature",
            "openai_reasoning_effort",
            "openai_enable_json_mode",
            # pdf2zh_next <= 2.9.0 intentionally keeps this upstream typo for compatibility.
            "openai_send_temprature",
            "openai_send_reasoning_effort",
        ]
    },
    "aliyundashscope": {
        apiKey: "aliyun_dashscope_api_key",
        model: "aliyun_dashscope_model",
        apiUrl: "aliyun_dashscope_base_url",
        extraData: [
            "aliyun_dashscope_timeout",
            "aliyun_dashscope_temperature",
            "aliyun_dashscope_send_temperature",
            "aliyun_dashscope_enable_json_mode"
        ]
    },
    "xinference": {
        apiUrl: "xinference_host",
        model: "xinference_model"
    },
    "ollama": {
        apiUrl: "ollama_host",
        model: "ollama_model",
        extraData: [
            "num_predict"
        ]
    },
    "azureopenai": {
        apiKey: "azure_openai_api_key",
        model: "azure_openai_model",
        apiUrl: "azure_openai_base_url",
        extraData: [
            "azure_openai_api_version"
        ]
    },
    "modelscope": {
        apiKey: "modelscope_api_key",
        model: "modelscope_model",
        extraData: [
            "modelscope_enable_json_mode"
        ]
    },
    "zhipu": {
        apiKey: "zhipu_api_key",
        model: "zhipu_model",
        extraData:[
            "zhipu_enable_json_mode"
        ]
    },
    "siliconflow": {
        apiKey: "siliconflow_api_key",
        model: "siliconflow_model",
        apiUrl: "siliconflow_base_url",
        extraData: [
            "siliconflow_enable_thinking",
            "siliconflow_send_enable_thinking_param",
            "siliconflow_enable_json_mode",
        ]
    },
    "siliconflowfree": {
        extraData: [
            "siliconflow_free_enable_json_mode"
        ]
    },
    "tencentmechinetranslation": {
        apiKey: "tencentcloud_secret_key",
        model: "tencentcloud_secret_id"
    },
    "gemini": {
        apiKey: "gemini_api_key",
        model: "gemini_model",
        extraData: [
            "gemini_enable_json_mode"
        ]
    },
    "azure": {
        apiKey: "azure_api_key",
        apiUrl: "azure_endpoint"
    },
    "anythingllm": {
        apiKey: "anythingllm_apikey",
        apiUrl: "anythingllm_url"
    },
    "dify": {
        apiKey: "dify_apikey",
        apiUrl: "dify_url"
    },
    "grok": {
        apiKey: "grok_api_key",
        model: "grok_model",
        extraData: [
            "grok_enable_json_mode"
        ]
    },
    "groq": {
        apiKey: "groq_api_key",
        model: "groq_model",
        extraData: [
            "groq_enable_json_mode"
        ]
    },
    "deepseek": {
        apiKey: "deepseek_api_key",
        model: "deepseek_model",
        extraData: [
            "deepseek_enable_json_mode",
            "deepseek_thinking_mode",
            "deepseek_reasoning_effort"
        ]
    },
    "qwenmt": {
        apiKey: "qwenmt_api_key",
        model: "qwenmt_model",
        apiUrl: "qwenmt_base_url",
        extraData: [
            "ali_domains"
        ]
    },
    "openaicompatible": {
        apiKey: "openai_compatible_api_key",
        model: "openai_compatible_model",
        apiUrl: "openai_compatible_base_url",
        extraData: [
            "openai_compatible_timeout",
            "openai_compatible_temperature",
            "openai_compatible_reasoning_effort",
            "openai_compatible_send_temperature",
            "openai_compatible_send_reasoning_effort",
            "openai_compatible_enable_json_mode",
        ]
    },
    "claudecode": {
        apiUrl: "claude_code_path",
        model: "claude_code_model"
    }
}
