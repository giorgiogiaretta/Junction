"""Offline evidence checker. Only saved JSON and ai.recognize.decide are used."""
import argparse
from html.parser import HTMLParser
from itertools import combinations
import json
from pathlib import Path
import re
import statistics
import math

MODELS = {'nemotron': 'nemotron_run2.json', 'gemma': 'gemma4_api.json',
          'paligemma': 'paligemma2_local.json'}
TARGETS = ['README.md', 'deck/index.html', 'deck/notes.md',
           'docs/OBJECT_RECOGNITION_RESULTS.md', 'docs/STORY_MODELS.md']


def targets(root):
    return TARGETS + [p.relative_to(root).as_posix()
                      for p in sorted((root / 'docs/submission').glob('*.md'))]


class Prose(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        # Alt text is a claim too; exclude attributes such as image data and CSS.
        self.parts.extend(v for k, v in attrs if k == 'alt' and v)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def units(path):
    text = path.read_text(encoding='utf-8')
    if path.suffix == '.html':
        parser = Prose()
        parser.feed(text)
        return parser.parts
    return [line.strip() for line in text.splitlines() if line.strip()]


def recompute(root):
    from ai.recognize import decide
    runs = {}
    for name, filename in MODELS.items():
        rows = json.loads((root / 'docs/evidence/recognition' / filename).read_text())
        if not isinstance(rows, list) or not rows:
            raise ValueError(f'{name}: expected nonempty row array')
        index = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f'{name}: expected row object')
            key = row['file']
            if not isinstance(key, str) or not key:
                raise ValueError(f'{name}: invalid photo identifier')
            if key in index:
                raise ValueError(f'{name}: duplicate photo {key}')
            if row['expected'] not in (None, 'egg', 'stress_ball', 'can'):
                raise ValueError(f'{name}: unknown ground truth {key}')
            if not isinstance(row['ok'], bool) or not isinstance(row['object'], str):
                raise ValueError(f'{name}: invalid vote {key}')
            conf = row['confidence']
            if conf is not None and (type(conf) not in (float, int) or not 0 <= conf <= 1):
                raise ValueError(f'{name}: invalid confidence {key}')
            latency = row['latency_s']
            if row['ok'] and (type(latency) not in (int, float) or not math.isfinite(latency) or latency < 0):
                raise ValueError(f'{name}: invalid latency {key}')
            index[key] = row
        runs[name] = index
    first = runs['nemotron']
    if not first:
        raise ValueError('empty evidence')
    for name, run in runs.items():
        if run.keys() != first.keys():
            raise ValueError(f'{name}: photo sets differ')
        if any(run[k]['expected'] != first[k]['expected'] for k in first):
            raise ValueError(f'{name}: ground truths differ')
    labelled = [k for k in sorted(first) if first[k]['expected'] is not None]
    if not labelled:
        raise ValueError('no labelled photos')
    values = {'photos': len(first), 'labelled': len(labelled),
              'mix': len(first) - len(labelled)}
    details = {}
    def correct(row):
        return row['ok'] and row['object'] == row['expected']
    for name, run in runs.items():
        good = sum(correct(run[k]) for k in labelled)
        values[name + '.accuracy'] = f'{good}/{len(labelled)}'
        values[name + '.percent'] = 100 * good / len(labelled)
        values[name + '.errors'] = len(labelled) - good
        values[name + '.failed'] = sum(not row['ok'] for row in run.values())
        values[name + '.labelled_failed'] = sum(not run[k]['ok'] for k in labelled)
        latencies = [run[k]['latency_s'] for k in labelled if run[k]['ok']]
        values[name + '.median_latency_2dp'] = round(statistics.median(latencies), 2) if latencies else None
        for label in ('egg', 'stress_ball', 'can'):
            keys = [k for k in labelled if first[k]['expected'] == label]
            values[f'{name}.{label}'] = f'{sum(correct(run[k]) for k in keys)}/{len(keys)}'
        details[name + '.errors'] = [k for k in labelled if not correct(run[k])]
    for a, b in combinations(runs, 2):
        prefix = a + '+' + b
        disagree = [k for k in sorted(first) if
                    (runs[a][k]['ok'], runs[a][k]['object']) !=
                    (runs[b][k]['ok'], runs[b][k]['object'])]
        scored = [k for k in disagree if k in labelled]
        errors = [k for k in labelled if not correct(runs[a][k]) or not correct(runs[b][k])]
        shared = [k for k in labelled if not correct(runs[a][k]) and not correct(runs[b][k])]
        values[prefix + '.agreement'] = f'{len(first)-len(disagree)}/{len(first)}'
        values[prefix + '.labelled_agreement'] = f'{len(labelled)-len(scored)}/{len(labelled)}'
        values[prefix + '.disagreements'] = len(scored)
        values[prefix + '.flagged_errors'] = f'{len(set(errors) & set(scored))}/{len(errors)}'
        values[prefix + '.shared_errors'] = len(shared)
        details[prefix] = {'disagreements': scored, 'shared_errors': shared,
                           'unflagged_errors': sorted(set(errors) - set(scored))}
    for name, models in [('pair', ['nemotron', 'gemma']), ('triple', list(runs))]:
        decisions = {k: decide([runs[m][k] for m in models]) for k in labelled}
        values[name + '.accuracy'] = f'{sum(decisions[k]["object"] == first[k]["expected"] for k in labelled)}/{len(labelled)}'
        eggs = [k for k in labelled if first[k]['expected'] == 'egg']
        balls = [k for k in labelled if first[k]['expected'] == 'stress_ball']
        values[name + '.eggs'] = f'{sum(decisions[k]["object"] == "egg" for k in eggs)}/{len(eggs)}'
        values[name + '.confirmed_balls'] = f'{sum(decisions[k]["object"] == "stress_ball" and decisions[k]["agree"] >= 2 for k in balls)}/{len(balls)}'
    errors = [k for k in labelled if any(not correct(run[k]) for run in runs.values())]
    flagged = [k for k in errors if len({(run[k]['ok'], run[k]['object']) for run in runs.values()}) > 1]
    values['triple.flagged_errors'] = f'{len(flagged)}/{len(errors)}'
    values['triple.shared_errors'] = sum(sum(not correct(run[k]) for run in runs.values()) >= 2 for k in labelled)
    details['triple.error_photos'] = errors
    details['triple.errors'] = [
        {'file': k, 'expected': first[k]['expected'],
         'wrong_models': [m for m, run in runs.items() if not correct(run[k])],
         'votes': {m: run[k]['object'] for m, run in runs.items()},
         'flagged': k in flagged} for k in errors]
    return values, details


# Negation is local to the clause, not any unrelated 'not' in the paragraph.
def lint(text):
    findings = []
    for match in re.finditer(r'\bworks\s+on\s+the\s+G1\b|\bNewton\w*|96\s*%\s+in\s+general\b|100\s*%\s+safe\b|\bguarantee\w*', text, re.I):
        phrase = match.group()
        if phrase.lower().startswith('works'):
            prefix = re.split(r'[.;!?\n]|\bbut\b', text[:match.start()], flags=re.I)[-1]
            if re.search(r'\b(?:not|never|doesn.t|does not|cannot|can.t)\b[^.;!?]{0,60}$', prefix, re.I):
                continue
        findings.append(phrase)
    return findings


def check(root, registry, values):
    if not isinstance(registry, dict) or not isinstance(registry.get('claims'), list):
        raise ValueError('registry must contain a claims array')
    results = []
    def add(ok, name, info):
        results.append(('PASS' if ok else 'FAIL', name, info))
    texts = {}
    for file in targets(root):
        try:
            texts[file] = units(root / file)
        except OSError as exc:
            add(False, file, str(exc))
    for i, claim in enumerate(registry['claims']):
        file, text = claim['file'], claim['text']
        name = f'claim {i+1} {file}'
        add(text in texts.get(file, []), name, 'exact text present')
        source = claim['source']
        if 'metric' in source:
            value = values.get(source['metric'])
            expected = source['value']
            add(source['metric'] in values and value == expected, name, f'{source["metric"]}: claimed {expected}, recomputed {value}')
        else:
            path = root / source['doc']
            add(path.is_file(), name, f'document trace only: {source["doc"]}; not recomputed')
        for binding in claim.get('checks', []):
            value = values.get(binding['metric'])
            add(binding['metric'] in values and value == binding['value'], name, f'{binding["metric"]}: claimed {binding["value"]}, recomputed {value}')
    covered = {(c['file'], c['text']) for c in registry['claims']}
    for file, parts in texts.items():
        for part in parts:
            if re.search(r'\d', part) and (file, part) not in covered:
                add(False, file, 'unregistered numeric text: ' + part[:160])
        # Join visible HTML nodes so inline markup cannot hide a phrase.
        separator = ' ' if file.endswith('.html') else '\n'
        for phrase in lint(separator.join(parts)):
            add(False, file, 'forbidden phrase: ' + phrase)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--registry', type=Path, default=Path(__file__).with_name('claims.json'))
    parser.add_argument('--json', action='store_true', help='machine-readable metrics, photo details and checks')
    args = parser.parse_args(argv)
    try:
        values, details = recompute(args.root)
        registry = json.loads(args.registry.read_text())
        results = check(args.root, registry, values)
        for key, expected in registry['expected_metrics'].items():
            results.insert(0, ('PASS' if values.get(key) == expected else 'FAIL', key,
                               f'expected {expected}; recomputed {values.get(key)}'))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        values, details = {}, {}
        results = [('FAIL', 'input', str(exc))]
    if args.json:
        print(json.dumps({'metrics': values, 'details': details, 'checks': results}, indent=2))
    else:
        print('STATUS | CHECK | DETAIL')
        for row in results:
            print(' | '.join(row))
        print(f'{sum(r[0] == "PASS" for r in results)} PASS; {sum(r[0] == "FAIL" for r in results)} FAIL')
    return int(any(row[0] == 'FAIL' for row in results))


if __name__ == '__main__':
    raise SystemExit(main())
