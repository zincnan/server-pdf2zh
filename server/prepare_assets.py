"""Prepare verified BabelDOC static assets at image build time.

Reuse the engine's download/checksum functions with longer build-time network
budgets. Retry against the same temporary cache, preserving completed files.
"""
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


async def download():
    import httpx
    import tiktoken
    from babeldoc.assets import assets

    tiktoken.get_encoding('o200k_base')
    tiktoken.get_encoding('cl100k_base')
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=20),
                                 limits=httpx.Limits(max_connections=12)) as client:
        async def model():
            path = assets.get_cache_file_path('doclayout_yolo_docstructbench_imgsz1024.onnx', 'models')
            checksum = assets.DOCLAYOUT_YOLO_DOCSTRUCTBENCH_IMGSZ1024ONNX_SHA3_256
            if assets.verify_file(path, checksum):
                return
            last_error = None
            for source in ('modelscope', 'huggingface', 'hf-mirror'):
                try:
                    await assets.download_file(client, assets.DOC_LAYOUT_ONNX_MODEL_URL[source], path, checksum)
                    return
                except Exception as exc:
                    last_error = exc
                    print(f'Layout asset source {source} failed; trying next source', flush=True)
            raise RuntimeError('All layout asset sources failed') from last_error
        await asyncio.gather(assets.download_all_fonts_async(client), assets.download_all_cmaps_async(client), model())


def main():
    destination = Path(os.environ.get('ASSET_DIR', '/opt/pdf2zh-assets'))
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        env = {**os.environ, 'HOME': temporary}
        for attempt in range(3):
            result = subprocess.run([sys.executable, __file__, '--download'], env=env)
            if result.returncode == 0:
                break
            if attempt == 2:
                raise RuntimeError('Static asset preparation failed after three attempts')
            print('Retrying asset preparation with already downloaded files', flush=True)
            time.sleep(2)
        cache = Path(temporary) / '.cache' / 'babeldoc'
        for name in ('fonts', 'models', 'cmap', 'tiktoken'):
            if (cache / name).is_dir():
                shutil.copytree(cache / name, destination / name, dirs_exist_ok=True)
    print('Static translation assets ready', flush=True)


if __name__ == '__main__':
    if '--download' in sys.argv:
        asyncio.run(download())
    else:
        main()
