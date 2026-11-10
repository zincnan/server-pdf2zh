'use strict';
const $ = (id) => document.getElementById(id);
const terminal = new Set(['succeeded', 'failed', 'interrupted', 'cleanup_failed']);
const stateLabels = {queued: '排队中', running: '翻译中', succeeded: '已完成', failed: '失败', interrupted: '已中断', cleanup_failed: '待清理'};
const outputLabels = {mono: '译文', dual: '双语', mono_cut: '裁剪译文', dual_cut: '裁剪双语', compare: '左右对照', crop_compare: '裁剪后对照', glossary: '术语表'};
const advanced = {transFirst: '译文在前', noWatermark: '不添加水印', ocr: '启用 OCR 兼容', autoOcr: '自动启用 OCR', skipReferences: '跳过参考文献', translateTableText: '原生表格文字翻译', saveGlossary: '导出术语表', disableGlossary: '关闭自动术语提取', ignoreCache: '忽略翻译缓存', skipClean: '跳过 PDF 清理', enhanceCompatibility: '增强兼容性', disableRichTextTranslate: '关闭富文本翻译', onlyIncludeTranslatedPage: '仅包含已翻译页面'};
let capabilities, serviceData = {activeId: null, services: []}, tasks = [], filter = 'all', events, pollTimer, editing = null, noticeTimer;
function element(tag, text, className) {const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el;}
function notice(message, error = false) {$('notice').textContent = message; $('notice').className = `notice${error ? ' error' : ''}`; $('notice').hidden = false; clearTimeout(noticeTimer); noticeTimer = setTimeout(() => {$('notice').hidden = true;}, 10000);}
async function api(path, options = {}) {
  const headers = {'X-PDF-AI-Translator-Request': '1', ...(options.headers || {})};
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, {...options, headers, cache: 'no-store'});
  const result = response.status === 204 ? null : await response.json();
  if (response.status === 401 && path !== '/api/session') {showLogin(); throw new Error('请重新输入访问密码');}
  if (!response.ok) throw new Error(result?.error || `请求失败 (${response.status})`);
  return result;
}
function showLogin() {events?.close(); clearInterval(pollTimer); $('workspace').hidden = true; $('login-view').hidden = false; $('services-dialog').close(); $('access-password').focus();}
function actionButton(text, action, className) {const button = element('button', text, className); button.type = 'button'; button.addEventListener('click', async () => {button.disabled = true; try {await action();} catch (error) {notice(error.message, true);} finally {button.disabled = false;}}); return button;}
async function loadServices() {
  serviceData = await api('/api/model-services');
  const select = $('active-service'); select.replaceChildren();
  const empty = element('option', '请选择并激活一个模型服务'); empty.value = ''; select.append(empty);
  for (const profile of serviceData.services.filter((p) => !p.needsConversion)) {const option = element('option', `${profile.name} · ${profile.model || profile.provider}`); option.value = profile.id; select.append(option);}
  select.value = serviceData.activeId || '';
  $('submit-task').disabled = !serviceData.activeId;
  renderServices();
}
function renderServices() {
  const list = $('services-list'); list.replaceChildren();
  $('services-warning').hidden = !serviceData.services.some((p) => p.needsConversion);
  $('services-warning').textContent = '部分旧配置需要转换。请编辑为受支持的服务，填写完整后再激活；原配置已备份。';
  if (!serviceData.services.length) list.append(element('p', '还没有模型服务。添加一个配置并激活后即可翻译。', 'muted small'));
  for (const profile of serviceData.services) {
    const active = profile.id === serviceData.activeId;
    const row = element('div', undefined, `service-row${active ? ' active' : ''}`);
    const description = element('div', undefined, 'service-description');
    const provider = capabilities.providers.find((p) => p.id === profile.provider);
    description.append(element('strong', profile.name + (profile.needsConversion ? ' · 待转换' : active ? ' · 当前激活' : '')),
      element('span', `${provider?.label || profile.provider}${profile.model ? ' / ' + profile.model : ''}${profile.hasApiKey ? ' · 已保存密钥' : ''}`)); row.append(description);
    if (!active && !profile.needsConversion) row.append(actionButton('激活', async () => {await api(`/api/model-services/${profile.id}/active`, {method: 'PUT'}); await loadServices();}));
    row.append(actionButton(profile.needsConversion ? '转换' : '编辑', () => editService(profile)), actionButton('删除', async () => {if (!confirm(`删除模型服务“${profile.name}”？已提交任务不受影响。`)) return; await api(`/api/model-services/${profile.id}`, {method: 'DELETE'}); if (editing?.id === profile.id) editService(null); await loadServices();})); list.append(row);
  }
}
function inferModel(model) {
  const name = model.trim().split('/').pop().toLowerCase();
  return capabilities.modelRules.find((rule) => new RegExp(rule.pattern).test(name)) || {id: 'openai', label: '标准 OpenAI / 未知模型'};
}
function updateModelControls() {
  const model = $('profile-model');
  if (!model) return;
  const family = inferModel(model.value);
  $('model-recognition').textContent = `自动识别：${family.label}。自定义模型别名可能无法识别。`;
  const enabled = $('thinking-enabled').checked;
  $('reasoning-effort').disabled = !enabled;
  const standard = family.id === 'openai' || family.id === 'openai-reasoning';
  $('reasoning-effort').setCustomValidity(enabled && standard && !$('reasoning-effort').value ? 'OpenAI 格式开启思考时，请选择具体的推理强度' : '');
  $('thinking-help').textContent = family.id === 'openai'
    ? '未知模型关闭思考时不发送思考参数，服务端默认行为仍由模型决定。'
    : '按模型类型自动生成思考开关；不支持的参数会由模型服务报错。';
}
function providerFields() {
  const provider = capabilities.providers.find((p) => p.id === $('provider').value);
  const current = editing && (editing.provider === provider.id || editing.needsConversion) ? editing : null;
  $('provider-fields').replaceChildren(); $('model-controls').replaceChildren();
  const labels = {apiUrl: 'Base URL', apiKey: 'API Key', model: 'Model ID'};
  for (const field of provider.fields) {
    const div = element('div', undefined, 'field'), label = element('label', labels[field]); label.htmlFor = `profile-${field}`;
    const input = element('input'); input.id = `profile-${field}`; input.dataset.profileField = field;
    input.type = field === 'apiKey' ? 'password' : field === 'apiUrl' ? 'url' : 'text';
    input.autocomplete = 'off'; input.maxLength = 4096;
    input.required = field !== 'apiKey' || !current?.hasApiKey;
    if (field === 'apiKey') input.placeholder = current?.hasApiKey ? '已保存；留空保留原密钥，输入新值替换' : '输入服务的 API Key';
    else {input.value = current?.[field] || ''; input.placeholder = field === 'apiUrl' ? 'https://api.example.com/v1' : '例如：Qwen/Qwen3-32B';}
    div.append(label, input);
    if (field === 'apiUrl') div.append(element('span', '填写 API 基础地址，无需追加 /chat/completions。', 'field-help'));
    $('provider-fields').append(div);
  }
  if (provider.id !== 'openaicompatible') {
    $('provider-fields').append(element('p', '使用 next 引擎内置翻译服务，无需填写模型地址或密钥。', 'field-help'));
    return;
  }
  const box = $('model-controls');
  const checks = element('div', undefined, 'check-grid model-checks');
  for (const [id, text, field] of [['json-mode', '启用 JSON 模式', 'enableJsonMode'], ['thinking-enabled', '启用思考', 'thinkingEnabled']]) {
    const label = element('label', text, 'check'), input = element('input');
    input.type = 'checkbox'; input.id = id; input.checked = current?.[field] || false;
    label.prepend(input); checks.append(label);
  }
  box.append(checks);
  const recognition = element('p', undefined, 'field-help'); recognition.id = 'model-recognition'; recognition.setAttribute('aria-live', 'polite'); box.append(recognition);
  const field = element('div', undefined, 'field'), label = element('label', '推理强度'); label.htmlFor = 'reasoning-effort';
  const select = element('select'); select.id = 'reasoning-effort';
  for (const value of capabilities.reasoningEfforts) {const option = element('option', value || '不发送（使用模型默认）'); option.value = value; select.append(option);}
  select.value = current?.reasoningEffort || '';
  field.append(label, select); box.append(field);
  const help = element('p', undefined, 'field-help'); help.id = 'thinking-help'; box.append(help);
  box.append(element('p', '不发送温度参数。推理强度由你按模型支持选择；JSON 模式仅在引擎需要结构化输出时启用。', 'field-help'));
  $('profile-model').addEventListener('input', updateModelControls);
  $('thinking-enabled').addEventListener('change', updateModelControls);
  select.addEventListener('change', updateModelControls);
  updateModelControls();
}
function editService(profile) {
  editing = profile; $('service-id').value = profile?.id || ''; $('service-name').value = profile?.name || '';
  $('provider').value = capabilities.providers.some((p) => p.id === profile?.provider) ? profile.provider : 'openaicompatible';
  $('service-form-title').textContent = profile?.needsConversion ? '转换旧配置' : profile ? '编辑模型服务' : '添加模型服务';
  $('service-error').textContent = ''; providerFields();
}
async function openServices(fresh = false) {if (fresh) editService(null); await loadServices(); if (!$('services-dialog').open) $('services-dialog').showModal();}
function renderTasks() {
  $('task-count').textContent = tasks.length;
  const active = tasks.filter((t) => !terminal.has(t.state)).length;
  $('task-stats').textContent = active ? `${active} 个进行中 · 最多同时执行 ${capabilities.concurrency} 个` : '结果保留到手动清理';
  const shown = tasks.filter((t) => filter === 'all' || (filter === 'active' ? !terminal.has(t.state) : terminal.has(t.state)));
  $('empty-state').hidden = shown.length > 0; $('tasks-list').replaceChildren();
  for (const task of shown) {
    const card = element('article', undefined, 'task-card');
    const header = element('div', undefined, 'task-header'); header.append(element('h3', task.fileName, 'task-name'), element('span', stateLabels[task.state] || task.state, `badge ${task.state}`)); card.append(header);
    const meta = element('div', undefined, 'task-meta');
    meta.append(document.createTextNode(`${task.service?.name || '未受理'}${task.service?.model ? ' / ' + task.service.model : ''} · `));
    const timer = element('span'); timer.dataset.started = task.startedAt || task.createdAt; if (task.endedAt) timer.dataset.ended = task.endedAt; meta.append(timer); card.append(meta);
    const progressRow = element('div', undefined, 'task-progress'), progress = element('progress'); progress.max = 100; progress.value = task.progress; progress.setAttribute('aria-label', '翻译进度'); progressRow.append(progress, element('span', `${task.progress}%`)); card.append(progressRow, element('p', task.message, 'task-message'));
    if (task.hint) card.append(element('p', task.hint, 'field-help'));
    const actions = element('div', undefined, 'task-actions');
    if (task.state === 'succeeded') for (const file of task.files) {
      const url = `/api/tasks/${task.id}/files/${file.id}`;
      const download = element('a', `下载${outputLabels[file.type] || file.type}`); download.href = url; download.download = file.name; actions.append(download);
      if (file.name.endsWith('.pdf')) {const preview = element('a', '预览'); preview.href = `${url}?preview=true`; preview.target = '_blank'; preview.rel = 'noopener'; actions.append(preview);}
    }
    if (terminal.has(task.state)) {
      if (task.canRetry) actions.append(actionButton('重新翻译', async () => {await api(`/api/tasks/${task.id}/retry`, {method: 'POST'}); await loadTasks(); notice('已使用当前激活模型服务创建新任务');}));
      actions.append(actionButton('Clear', async () => {if (!confirm(`清理“${task.fileName}”的原文、译文及全部任务数据？`)) return; await api(`/api/tasks/${task.id}`, {method: 'DELETE'}); await loadTasks();}, 'quiet danger-text clear-task'));
    }
    card.append(actions); $('tasks-list').append(card);
  }
  updateTimers();
}
function updateTimers() {document.querySelectorAll('[data-started]').forEach((el) => {const seconds = Math.max(0, Math.floor(((el.dataset.ended ? Date.parse(el.dataset.ended) : Date.now()) - Date.parse(el.dataset.started)) / 1000)); el.textContent = seconds < 60 ? `${seconds} 秒` : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;});}
async function loadTasks() {tasks = (await api('/api/tasks')).tasks; renderTasks();}
function connectEvents() {
  events?.close(); events = new EventSource('/events');
  events.onopen = () => {$('connection').textContent = '已连接'; $('connection').className = 'connection online';};
  events.onmessage = (event) => {try {const data = JSON.parse(event.data); if (data.type === 'tasks') {tasks = data.data; renderTasks();}} catch { /* Next snapshot repairs malformed events. */ }};
  events.onerror = () => {$('connection').textContent = '正在重连'; $('connection').className = 'connection offline';};
  clearInterval(pollTimer); pollTimer = setInterval(async () => {try {await loadTasks();} catch (error) {if (!$('workspace').hidden) {$('connection').textContent = '连接中断'; $('connection').className = 'connection offline';}}}, 10000);
}
async function enterWorkspace(sessionState) {
  capabilities = await api('/api/capabilities');
  $('provider').replaceChildren(); for (const provider of capabilities.providers) {const option = element('option', provider.label); option.value = provider.id; $('provider').append(option);}
  $('advanced-checks').replaceChildren(); for (const [name, label] of Object.entries(advanced)) {const row = element('label', label, 'check'); const checkbox = element('input'); checkbox.type = 'checkbox'; checkbox.name = name; checkbox.checked = capabilities.defaults[name]; row.prepend(checkbox); $('advanced-checks').append(row);}
  $('upload-help').textContent = `每份最大 ${Math.round(capabilities.maxUploadBytes / 1024 / 1024)} MB · 关闭页面后翻译仍会继续`;
  $('login-view').hidden = true; $('workspace').hidden = false; $('logout').hidden = !sessionState.required;
  editService(null); await loadServices(); await loadTasks(); connectEvents();
}
$('login-form').addEventListener('submit', async (event) => {event.preventDefault(); try {const state = await api('/api/session', {method: 'POST', body: JSON.stringify({password: $('access-password').value})}); $('access-password').value = ''; await enterWorkspace(state);} catch (error) {$('login-error').textContent = error.message;}});
$('logout').addEventListener('click', async () => {await api('/api/session', {method: 'DELETE'}); showLogin();});
$('manage-services').addEventListener('click', () => openServices().catch((e) => notice(e.message, true)));
$('add-service').addEventListener('click', () => openServices(true).catch((e) => notice(e.message, true)));
$('close-services').addEventListener('click', () => $('services-dialog').close());
$('new-service').addEventListener('click', () => editService(null)); $('provider').addEventListener('change', providerFields);
$('active-service').addEventListener('change', async () => {try {if ($('active-service').value) await api(`/api/model-services/${$('active-service').value}/active`, {method: 'PUT'}); await loadServices();} catch (error) {notice(error.message, true);}});
$('service-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const button = event.submitter; button.disabled = true;
  try {
    const profile = {name: $('service-name').value, provider: $('provider').value};
    document.querySelectorAll('[data-profile-field]').forEach((input) => {
      const field = input.dataset.profileField;
      if (field !== 'apiKey' || input.value || !editing?.hasApiKey) profile[field] = input.value;
    });
    if (profile.provider === 'openaicompatible') Object.assign(profile, {
      enableJsonMode: $('json-mode').checked,
      thinkingEnabled: $('thinking-enabled').checked,
      reasoningEffort: $('reasoning-effort').value,
    });
    const saved = await api('/api/model-services' + (editing ? '/' + editing.id : ''), {method: editing ? 'PATCH' : 'POST', body: JSON.stringify(profile)});
    if (!serviceData.activeId) await api(`/api/model-services/${saved.id}/active`, {method: 'PUT'});
    editService(null); await loadServices(); notice('模型服务已保存');
  } catch (error) {$('service-error').textContent = error.message;} finally {button.disabled = false;}
});
function showFiles() {$('selected-files').textContent = Array.from($('pdf-files').files).map((f) => `${f.name} (${(f.size / 1024 / 1024).toFixed(1)} MB)`).join('、');}
$('pdf-files').addEventListener('change', showFiles);
for (const name of ['dragenter', 'dragover']) $('dropzone').addEventListener(name, (event) => {event.preventDefault(); $('dropzone').classList.add('dragging');});
for (const name of ['dragleave', 'drop']) $('dropzone').addEventListener(name, (event) => {event.preventDefault(); $('dropzone').classList.remove('dragging'); if (name === 'drop' && event.dataTransfer.files.length) {$('pdf-files').files = event.dataTransfer.files; showFiles();}});
$('translate-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const button = $('submit-task'); button.disabled = true;
  try {
    const options = {...capabilities.defaults};
    for (const input of $('translate-form').elements) if (input.name in options) options[input.name] = input.type === 'checkbox' ? input.checked : input.type === 'number' ? Number(input.value) : input.value;
    const files = Array.from($('pdf-files').files);
    if (files.some((file) => file.size > capabilities.maxUploadBytes)) throw new Error('有文件超过上传大小限制');
    const failed = []; let submitted = 0;
    for (const file of files) {const body = new FormData(); body.append('file', file); body.append('options', JSON.stringify(options)); try {await api('/api/tasks', {method: 'POST', body}); submitted++;} catch (error) {failed.push(`${file.name}: ${error.message}`);}}
    await loadTasks(); notice(`已创建 ${submitted} 个翻译任务${failed.length ? '\n' + failed.join('\n') : ''}`, failed.length > 0);
    if (!failed.length) {$('pdf-files').value = ''; showFiles();}
  } catch (error) {notice(error.message, true);} finally {button.disabled = !serviceData.activeId;}
});
$('clear-all').addEventListener('click', async () => {if (!confirm('清理全部已结束任务及其文件？运行中和下载中的任务会保留，模型配置不受影响。')) return; try {const result = await api('/api/tasks', {method: 'DELETE'}); await loadTasks(); notice(`已清理 ${result.cleared.length} 个任务，跳过 ${result.skipped.length} 个，失败 ${result.failed.length} 个`, result.failed.length > 0);} catch (error) {notice(error.message, true);}});
document.querySelectorAll('[data-filter]').forEach((button) => button.addEventListener('click', () => {filter = button.dataset.filter; document.querySelectorAll('[data-filter]').forEach((b) => b.setAttribute('aria-pressed', String(b === button))); renderTasks();}));
setInterval(updateTimers, 1000);
(async () => {try {const state = await api('/api/session'); if (state.authenticated) await enterWorkspace(state); else showLogin();} catch (error) {showLogin(); $('login-error').textContent = '服务连接失败：' + error.message;}})();
