"""The existing next-engine translation and Cropper postprocessing pipeline."""
import os
import shutil
import sys
from pathlib import Path

import fitz
from utils.config import Config
from utils.cropper import Cropper
from utils.execute import TaskLog, execute_with_progress
from utils.table_runtime import FLAG, REFERENCE_FLAG, prepare_table_runtime_command
from utils.model_policy import POLICY_FLAG, runtime_policy
from utils.storage import atomic_json

ASSET_PARTS = {'fonts', 'models', 'cmap', 'tiktoken'}


def task_environment(directory, assets=None):
    directory = Path(directory)
    home, temporary = directory / 'home', directory / 'tmp'
    for path in (home, temporary, directory / 'output'):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    # HOME is changed only in this child's environment, never in the server.
    env = {k: v for k, v in os.environ.items() if not any(x in k.upper() for x in ('API_KEY', 'SECRET', 'ACCESS_TOKEN'))}
    env.update(HOME=str(home), TMPDIR=str(temporary), XDG_CACHE_HOME=str(home / '.cache'),
               XDG_CONFIG_HOME=str(home / '.config'), PYTHONUNBUFFERED='1',
               COLUMNS='140', LINES='40', TERM='xterm-256color', FORCE_COLOR='1')
    cache = home / '.cache' / 'babeldoc'
    cache.mkdir(parents=True, exist_ok=True)
    if assets and Path(assets).is_dir():
        # Link static files, not entire writable cache directories. Every DB and
        # unrecognized/generated file remains inside the task workspace.
        for part in ASSET_PARTS:
            source = Path(assets) / part
            if source.is_dir():
                for item in source.rglob('*'):
                    if item.is_file():
                        target = cache / part / item.relative_to(source)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if not target.exists():
                            target.symlink_to(item.resolve())
    return env


def run_pipeline(directory, options, profile, update, register, stopping, assets=None):
    directory = Path(directory).resolve()
    cfg = Config(options)
    options = cfg.options
    log = TaskLog(directory / 'task.log', profile)
    output = directory / 'output'
    env = task_environment(directory, assets)
    config_file = directory / 'engine.toml'
    cfg.write(profile, config_file, output)
    needs_mono = options['mono'] or options['mono_cut']
    needs_dual = any(options[k] for k in ('dual', 'dual_cut', 'compare', 'crop_compare'))
    command = [sys.executable, '-u', '-m', 'pdf2zh_next', str(directory / 'input.pdf'),
               '--config-file', str(config_file), '--' + profile['provider'],
               '--qps', str(options['qps']), '--output', str(output),
               '--lang-in', options['sourceLang'], '--lang-out', options['targetLang'],
               '--watermark-output-mode', 'no_watermark' if options['noWatermark'] else 'watermarked',
               # Internal duals always have a known order for Cropper.
               '--dual-translate-first']
    if not needs_mono:
        command.append('--no-mono')
    if not needs_dual:
        command.append('--no-dual')
    if options['dualMode'] == 'TB':
        command.append('--use-alternating-pages-dual')
    for key, flag in [('ocr', 'ocr-workaround'), ('autoOcr', 'auto-enable-ocr-workaround'),
                      ('skipClean', 'skip-clean'), ('enhanceCompatibility', 'enhance-compatibility'),
                      ('disableRichTextTranslate', 'disable-rich-text-translate')]:
        if options[key]:
            command.append('--' + flag)
    if options['fontFamily'] != 'auto':
        command += ['--primary-font-family', options['fontFamily']]
    if options['skipLastPages']:
        with fitz.open(directory / 'input.pdf') as doc:
            end = len(doc) - options['skipLastPages']
        if end < 1:
            raise ValueError('跳过尾页后没有可翻译的页面')
        command += ['--pages', f'1-{end}']
    if cfg.table_mode:
        command += [FLAG, cfg.table_mode]
    if cfg.skip_references:
        command.append(REFERENCE_FLAG)
    if profile['provider'] == 'openaicompatible':
        policy_path = directory / 'model-policy.json'
        atomic_json(policy_path, runtime_policy(profile))
        command += [POLICY_FLAG, str(policy_path)]
    update(stage='translating', message='正在解析与翻译 PDF')
    try:
        command = prepare_table_runtime_command(command)
        execute_with_progress(command, directory, env, update, register, log, stopping)
        update(stage='postprocessing', message='正在生成下载文件')
        return postprocess(directory, cfg, needs_mono, needs_dual, stopping)
    except Exception as exc:
        detail = log.redact(str(exc))
        tail = log.tail()
        if tail and tail not in detail:
            detail += '\n\n[引擎诊断]\n' + tail
        raise RuntimeError(detail.replace(str(directory), '[任务目录]')) from exc
    finally:
        # Credentials remain in the separately managed model service store.
        config_file.unlink(missing_ok=True)
        shutil.rmtree(directory / 'home' / '.config', ignore_errors=True)


def postprocess(directory, cfg, needs_mono, needs_dual, stopping):
    options = cfg.options
    out = directory / 'output'
    stem = 'input.' + ('no_watermark.' if options['noWatermark'] else '') + options['targetLang']
    mono = out / f'{stem}.mono.pdf'
    dual = out / f'{stem}.dual.pdf'
    for needed, path in ((needs_mono, mono), (needs_dual, dual)):
        if needed and not path.is_file():
            raise RuntimeError('翻译引擎未生成请求的 PDF，请查看任务日志')
    cropper = Cropper()
    results = {}
    if needs_dual:
        canonical = dual.with_name(f'{stem}.{options["dualMode"]}_dual.pdf')
        dual.replace(canonical)
        dual = canonical
        tb = dual
        if options['dualMode'] == 'LR' and any(options[k] for k in ('dual_cut', 'crop_compare', 'compare', 'dual')):
            _, tb_path = cropper.pdf_dual_mode(str(dual), 'LR', 'TB')
            tb = Path(tb_path)
        if options['dual']:
            selected = out / f'result.{options["dualMode"]}_dual.pdf'
            if options['dualMode'] == 'LR':
                cropper.merge_pdf(str(tb), str(selected), trans_first=cfg.trans_first)
            elif cfg.trans_first:
                shutil.copyfile(tb, selected)
            else:
                with fitz.open(tb) as source, fitz.open() as dest:
                    for index in range(0, len(source), 2):
                        if index + 1 < len(source):
                            dest.insert_pdf(source, from_page=index + 1, to_page=index + 1)
                        dest.insert_pdf(source, from_page=index, to_page=index)
                    dest.save(selected)
            results['dual'] = selected
        if options['compare']:
            path = out / 'result.compare.pdf'
            cropper.merge_pdf(str(tb), str(path), trans_first=cfg.trans_first)
            results['compare'] = path
        if options['dual_cut']:
            path = out / 'result.dual-cut.pdf'
            # dual-cut preserves the selected first-language order.
            source = results.get('dual') if options['dualMode'] == 'TB' else None
            if not cfg.trans_first and source is None:
                source = out / 'ordered.TB_dual.pdf'
                with fitz.open(tb) as doc, fitz.open() as dest:
                    for index in range(0, len(doc), 2):
                        if index + 1 < len(doc):
                            dest.insert_pdf(doc, from_page=index + 1, to_page=index + 1)
                        dest.insert_pdf(doc, from_page=index, to_page=index)
                    dest.save(source)
            cropper.crop_pdf(cfg, str(source or tb), 'dual', str(path), 'dual-cut')
            results['dual_cut'] = path
        if options['crop_compare']:
            path = out / 'result.crop-compare.pdf'
            cropper.crop_pdf(cfg, str(tb), 'dual', str(path), 'crop-compare')
            results['crop_compare'] = path
    if options['mono']:
        results['mono'] = mono
    if options['mono_cut']:
        path = out / 'result.mono-cut.pdf'
        cropper.crop_pdf(cfg, str(mono), 'mono', str(path), 'mono-cut')
        results['mono_cut'] = path
    if stopping.is_set():
        raise InterruptedError('服务停止，任务已中断')
    for path in results.values():
        with fitz.open(path) as doc:
            if not len(doc):
                raise RuntimeError('生成的 PDF 没有页面')
    if options['saveGlossary']:
        for path in out.glob('*.csv'):
            results['glossary'] = path
    return results
