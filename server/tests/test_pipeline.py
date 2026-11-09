"""Real PDF layout checks around the retained Cropper implementation."""
import tempfile
import threading
import unittest
from pathlib import Path

import fitz
from utils.config import Config
from utils.pipeline import postprocess, task_environment


def make_pdf(path, labels, width=600):
    with fitz.open() as doc:
        for text in labels:
            page = doc.new_page(width=width, height=800)
            page.insert_text((75, 80), text)
            page.insert_text((375, 80), 'Right column ' + text)
        doc.save(path)


class PipelineTests(unittest.TestCase):
    def test_all_outputs_and_original_first_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / 'output'
            out.mkdir()
            make_pdf(out / 'input.no_watermark.zh-CN.mono.pdf', ['Translated'])
            make_pdf(out / 'input.no_watermark.zh-CN.dual.pdf', ['Translated', 'Original'])
            config = Config({'dualMode': 'TB', 'mono_cut': True, 'dual_cut': True,
                             'crop_compare': True, 'compare': True, 'transFirst': False})
            result = postprocess(root, config, True, True, threading.Event())
            self.assertEqual(set(result), {'mono', 'dual', 'mono_cut', 'dual_cut', 'crop_compare', 'compare'})
            with fitz.open(result['dual']) as doc:
                self.assertIn('Original', doc[0].get_text())
                self.assertIn('Translated', doc[1].get_text())
            with fitz.open(result['compare']) as doc:
                self.assertEqual(len(doc), 1)
                self.assertEqual(doc[0].rect.width, 1200)
                words = doc[0].get_text('words')
                self.assertLess(next(w[0] for w in words if w[4] == 'Original'),
                                next(w[0] for w in words if w[4] == 'Translated'))
            with fitz.open(result['dual_cut']) as doc:
                self.assertEqual(len(doc), 4)
                self.assertIn('Original', doc[0].get_text())

    def test_lr_dual_only_output_and_translated_first(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / 'output'
            out.mkdir()
            with fitz.open() as doc:
                page = doc.new_page(width=1200, height=800)
                page.insert_text((75, 80), 'Translated')
                page.insert_text((675, 80), 'Original')
                doc.save(out / 'input.no_watermark.zh-CN.dual.pdf')
            result = postprocess(root, Config({'mono': False, 'transFirst': True}), False, True, threading.Event())
            self.assertEqual(set(result), {'dual'})
            with fitz.open(result['dual']) as doc:
                self.assertEqual(doc[0].rect.width, 1200)
                self.assertIn('Translated', doc[0].get_text())

    def test_missing_requested_artifact_is_a_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, '未生成'):
                postprocess(Path(temp), Config({}), True, True, threading.Event())

    def test_static_assets_linked_but_document_cache_is_not_shared(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            assets = root / 'assets'
            (assets / 'models').mkdir(parents=True)
            (assets / 'models' / 'layout.onnx').write_bytes(b'static')
            (assets / 'cache.v1.db').write_bytes(b'never share')
            env_a = task_environment(root / 'a', assets)
            env_b = task_environment(root / 'b', assets)
            self.assertNotEqual(env_a['HOME'], env_b['HOME'])
            self.assertTrue((Path(env_a['HOME']) / '.cache/babeldoc/models/layout.onnx').is_symlink())
            self.assertFalse((Path(env_a['HOME']) / '.cache/babeldoc/cache.v1.db').exists())
            self.assertFalse((Path(env_b['HOME']) / '.cache/babeldoc/cache.v1.db').exists())


if __name__ == '__main__':
    unittest.main()
