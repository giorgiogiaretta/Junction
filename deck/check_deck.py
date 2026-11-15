#!/usr/bin/env python3
"""Offline wording/number lint for audience copy; not a semantic fact checker."""
import argparse
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?:\s*/\s*\d+(?:[.,]\d+)?)?%?(?!\w)")
FORBIDDEN = (
    r"works on (?:the )?g1", r"funziona sul g1", r"96\s*%\s*in general",
    r"(?:measured|real|physical)\s+(?:contact\s+)?forces?\s+(?:in\s+)?newtons?",
    r"\d+(?:[.,]\d+)?\s*(?:newtons?\b|N\b)",
    r"only model fast enough", r"no data leaves", r"guaranteed safety",
)


def normalise(text):
    return re.sub(r"\s+", " ", unicodedata.normalize('NFKC', text)).strip()


def numbers(text):
    """Keep ratios/percentages whole; accept decimal comma and trailing zeroes."""
    found = set()
    for match in NUMBER.finditer(text):
        raw = match.group().replace(',', '.')
        percent = '%' if raw.endswith('%') else ''
        found.add('/'.join(str(Decimal(p.strip()).normalize())
                          for p in raw.rstrip('%').split('/')) + percent)
    return found


class CopyParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.copy = []
        self.sources = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'section' and 'slide' in attrs.get('class', '').split():
            self.sources.append(attrs.get('data-sources', '').split())
        # Layout dimensions, script constants, navigation and slide counters are
        # not evidence numbers. Footers contain only source paths and counters.
        skip = tag in {'style', 'script', 'nav', 'footer'} or bool(self.stack and self.stack[-1][1])
        if tag not in {'meta', 'br', 'hr', 'img', 'input', 'link'}:
            self.stack.append((tag, skip))
        if not skip:
            self.copy.extend(attrs[key] for key in ('alt', 'title') if key in attrs)
            if 'aria-label' in attrs and tag != 'section':
                self.copy.append(attrs['aria-label'])
        for key in ('src', 'href'):
            value = attrs.get(key, '')
            if value and not value.startswith(('#', 'data:')):
                self.errors.append(f'external dependency/link: {value}')

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if not self.stack or not self.stack[-1][1]:
            self.copy.append(data)


def check(html_path, notes_path, docs_path):
    parser = CopyParser()
    parser.feed(html_path.read_text())
    # Sources and heading counters are structural. All spoken numeric copy is checked.
    notes = re.sub(r'^Sources:.*$', '', notes_path.read_text(), flags=re.M)
    notes = re.sub(r'^(## )\d+\s*—', r'\1', notes, flags=re.M)
    copies = {'HTML': normalise(' '.join(parser.copy)), 'notes': normalise(notes)}
    errors = parser.errors
    corpus = '\n'.join(p.read_text(errors='replace') for p in sorted(docs_path.rglob('*'))
                       if p.is_file() and p.suffix in {'.md', '.txt', '.json', '.csv'})
    documented = numbers(corpus)
    if not documented:
        errors.append('no numeric documentation corpus found')
    for label, copy in copies.items():
        for pattern in FORBIDDEN:
            match = re.search(pattern, copy, re.I)
            if match:
                errors.append(f'{label}: forbidden wording: {match.group()}')
        missing = numbers(copy) - documented
        if missing:
            errors.append(f'{label}: numbers absent from docs/: {", ".join(sorted(missing))}')
    if len(parser.sources) != 12:
        errors.append(f'expected 12 slides, got {len(parser.sources)}')
    for i, sources in enumerate(parser.sources, 1):
        if not sources:
            errors.append(f'slide {i}: missing source paths')
        for source in sources:
            if not (ROOT / source).is_file():
                errors.append(f'slide {i}: source does not exist: {source}')
    return errors


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--html', type=Path, default=ROOT / 'deck/index.html')
    ap.add_argument('--notes', type=Path, default=ROOT / 'deck/notes.md')
    ap.add_argument('--docs', type=Path, default=ROOT / 'docs')
    args = ap.parse_args()
    errors = check(args.html, args.notes, args.docs)
    if errors:
        print('\n'.join(f'FAIL: {e}' for e in errors), file=sys.stderr)
        return 1
    print('PASS: 12 slides; cited files exist; no forbidden wording or undocumented numeric tokens.')
    print('Numeric presence is not semantic proof: review units, scope and source conflicts manually.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
