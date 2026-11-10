# Model configuration

PDF AI Translator supports OpenAI-compatible Chat Completions endpoints, Google Translate, and Bing Translate. Native Anthropic Messages endpoints are not supported; Claude models may be used through an OpenAI-compatible endpoint.

OpenAI-compatible profiles require an explicit Base URL, API Key, and Model ID. A copied `/chat/completions` suffix is removed from the Base URL. For local endpoints that do not validate keys, provide the placeholder key required by that endpoint. Editing a profile without submitting a new key preserves the stored key; APIs never return it.

## Request controls

JSON mode and thinking default to off. Reasoning effort defaults to omitted; available levels are `low`, `medium`, `high`, `xhigh`, and `max`. Standard OpenAI requests require a specific effort when thinking is enabled.

Recognition ignores case and strips the Model ID namespace before checking its prefix:

| Model family | Thinking on | Thinking off |
| --- | --- | --- |
| `deepseek…` | `thinking.type="enabled"`, with optional selected effort | `thinking.type="disabled"`; effort omitted |
| `qwen…` / `qwq…` | `enable_thinking=true`, with optional selected effort | `enable_thinking=false`; effort omitted |
| o1/o3/o4 and GPT-5/GPT-6 families | Selected `reasoning_effort` | `reasoning_effort="none"` |
| Other models / custom aliases | Standard OpenAI `reasoning_effort` | Thinking fields omitted; server defaults apply |

Aliases can prevent recognition. Unsupported fields or effort levels are reported by the model service; the app does not silently substitute another value. JSON mode enables API-level JSON constraints only when the engine requests structured output.

Temperature is omitted from every compatible-model request. This uses the endpoint's defaults and is not equivalent to temperature 0. Individual requests retain their SDK timeout; the PDF translation job has no overall time limit.

## Profile migration

The first upgrade from schema v1 saves `/data/config/services.v1.backup.json` with restricted permissions, then migrates the active store to v2. Existing OpenAI profiles become compatible profiles with their effective default URL and model saved explicitly. Compatible profiles retain their endpoint, model, and credentials.

Other service types remain as records requiring conversion. They cannot be activated until edited into a supported type. An unusable active profile is cleared without selecting a replacement. The backup includes the original credentials and is not deleted by job cleanup.
