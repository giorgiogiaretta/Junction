"""Offline bundler regressions. Run: python3 -m unittest discover -s demo -p 'test_*.py'."""
import json
from pathlib import Path
import tempfile
import unittest

from build_results import START, END, bundle


class BundleTests(unittest.TestCase):
    def test_missing_reports_produce_empty_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / 'page.html'
            page.write_text(START + '["stale"]' + END)
            self.assertEqual(bundle(Path(tmp) / 'missing', page), 0)
            self.assertEqual(page.read_text(), START + '[]' + END)

    def test_report_html_is_inert_and_roundtrips(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'qc'
            source.mkdir()
            value = {'take_id': '</script><script>alert(1)</script>', 'score': 42}
            (source / 'take.json').write_text(json.dumps(value))
            page = root / 'page.html'
            page.write_text('before' + START + '[]' + END + 'after')
            self.assertEqual(bundle(source, page), 1)
            payload = page.read_text().split(START)[1].split(END)[0]
            self.assertNotIn('<', payload)
            self.assertEqual(json.loads(payload)[0]['report'], value)
            self.assertTrue(page.read_text().endswith('after'))

    def test_invalid_json_does_not_overwrite_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'bad.json').write_text('{')
            page = root / 'page.html'
            original = START + '[]' + END
            page.write_text(original)
            with self.assertRaises(ValueError):
                bundle(root, page)
            self.assertEqual(page.read_text(), original)


if __name__ == '__main__':
    unittest.main()
