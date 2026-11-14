"""Embed local QC reports in the self-contained pitch page; no network or keys."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
START = '<script id="qc-data" type="application/json">'
END = '</script>'


def bundle(source, page):
    reports = []
    for path in sorted(source.glob('*.json')):
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            raise ValueError(f'{path.name}: cannot read JSON: {exc}') from exc
        reports.append({'source': path.name, 'report': value})
    # Escape HTML delimiters so report strings cannot terminate the data script.
    payload = json.dumps(reports, ensure_ascii=True, allow_nan=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    html = page.read_text(encoding='utf-8')
    pattern = re.escape(START) + r'.*?' + re.escape(END)
    html, count = re.subn(pattern, lambda _: START + payload + END, html, flags=re.S)
    if count != 1:
        raise ValueError('Expected exactly one qc-data block')
    page.write_text(html, encoding='utf-8')
    return len(reports)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data/qc')
    parser.add_argument('--page', type=Path, default=ROOT / 'demo/results.html')
    args = parser.parse_args()
    print(f'Embedded {bundle(args.source, args.page)} QC report files in {args.page}')
