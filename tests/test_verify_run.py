"""Offline verifier regression tests; all mutations use temporary repositories."""
import json
from pathlib import Path
import shutil
import socket

import pytest

from verify.run import check, lint, main, recompute, targets, units

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo(tmp_path):
    evidence = tmp_path / 'docs/evidence/recognition'
    evidence.parent.mkdir(parents=True)
    shutil.copytree(ROOT / 'docs/evidence/recognition', evidence)
    for name in targets(ROOT):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('')
    return tmp_path


def change(repo, model, fn):
    path = repo / 'docs/evidence/recognition' / model
    rows = json.loads(path.read_text(encoding='utf-8'))
    fn(rows)
    path.write_text(json.dumps(rows))


def test_saved_counts_and_no_network(repo, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('network or model call attempted')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    import ai.recognize
    monkeypatch.setattr(ai.recognize, 'collect', forbidden)
    for name in ai.recognize.BACKENDS:
        monkeypatch.setitem(ai.recognize.BACKENDS, name, forbidden)
    values, details = recompute(repo)
    assert [values[m + '.accuracy'] for m in ('nemotron', 'gemma', 'paligemma')] == ['48/50', '49/50', '49/50']
    assert values['pair.accuracy'] == values['triple.accuracy'] == '50/50'
    assert values['triple.eggs'] == '20/20'
    assert values['triple.confirmed_balls'] == '22/22'
    assert values['pair.confirmed_balls'] == '21/22'
    assert [values[p + '.agreement'] for p in ('nemotron+gemma', 'nemotron+paligemma', 'gemma+paligemma')] == ['69/77', '68/77', '65/77']
    assert details['nemotron+paligemma']['shared_errors'] == ['egg/egg-012.jpg']
    assert values['triple.flagged_errors'] == '3/3'
    assert values['gemma.failed'] == 2
    assert values['gemma.labelled_failed'] == 0


@pytest.mark.parametrize('mutation,message', [
    (lambda rows: rows.append(rows[0]), 'duplicate'),
    (lambda rows: rows.pop(), 'sets differ'),
    (lambda rows: rows[0].update(expected='egg'), 'ground truths differ'),
    (lambda rows: rows[0].update(confidence=2), 'invalid confidence'),
])
def test_bad_evidence_fails(repo, mutation, message):
    change(repo, 'gemma4_api.json', mutation)
    with pytest.raises(ValueError, match=message):
        recompute(repo)


def test_failed_calls_count_as_errors_and_mix_is_unscored(repo):
    change(repo, 'nemotron_run2.json', lambda rows: rows[0].update(ok=False))
    values, _ = recompute(repo)
    assert values['nemotron.accuracy'] == '47/50'
    assert values['labelled'] == 50


def test_exact_claim_missing_wrong_value_new_claim_and_source(repo):
    path = repo / 'README.md'
    path.write_text('48 of 50\n')
    registry = {'claims': [{'file': 'README.md', 'text': '48 of 50',
                            'source': {'metric': 'nemotron.accuracy', 'value': '48/50'}}]}
    assert all(r[0] == 'PASS' for r in check(repo, registry, {'nemotron.accuracy': '48/50'}))
    assert any(r[0] == 'FAIL' for r in check(repo, registry, {'nemotron.accuracy': '47/50'}))
    path.write_text('49 of 50\n')
    failures = [r for r in check(repo, registry, {}) if r[0] == 'FAIL']
    assert any('exact text' in r[2] for r in failures)
    assert any(r[0] == 'WARN' and 'unregistered' in r[2]
               for r in check(repo, registry, {}))
    registry['claims'][0]['source'] = {'doc': 'missing.md'}
    assert any('document trace' in r[2] and r[0] == 'FAIL' for r in check(repo, registry, {}))


@pytest.mark.parametrize('text,expected', [
    ('works on the G1', True), ('It does not work; it works on the G1', True),
    ('Never write: "works on the G1"', False), ('It is not true that it works on the G1', False),
    ('not validated, but works on the G1', True), ('Newton', True),
    ('96% in general', True), ('100% safe', True), ('not a guarantee', True),
])
def test_lint(text, expected):
    assert bool(lint(text)) is expected


def test_html_visible_text_and_alt_not_css_or_base64(tmp_path):
    path = tmp_path / 'test.html'
    path.write_text('<style>100% safe</style><p>48/50</p><img src="data:123" alt="0.70 toy cap"><script>99</script>')
    assert units(path) == ['48/50', '0.70 toy cap']


def test_cli_success_failure_and_invalid_json(repo, tmp_path, capsys):
    registry = tmp_path / 'registry.json'
    registry.write_text(json.dumps({'claims': [], 'expected_metrics': {'pair.accuracy': '50/50'}}))
    assert main(['--root', str(repo), '--registry', str(registry), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['metrics']['triple.accuracy'] == '50/50'
    (repo / 'README.md').write_text('100% safe')
    assert main(['--root', str(repo), '--registry', str(registry)]) == 1
    assert 'FAIL' in capsys.readouterr().out
    registry.write_text('{')
    assert main(['--root', str(repo), '--registry', str(registry)]) == 1


def test_registry_contains_current_text_and_valid_traces():
    registry = json.loads((ROOT / 'verify/claims.json').read_text(encoding='utf-8'))
    values, _ = recompute(ROOT)
    results = check(ROOT, registry, values)
    assert not any(r[0] == 'FAIL' and ('exact text' in r[2] or 'document trace' in r[2])
                   for r in results)
    assert all(r[0] == 'WARN' for r in results if 'unregistered' in r[2])


def test_unknown_metric_cannot_pass_as_null(repo):
    (repo / 'README.md').write_text('value 1')
    registry = {'claims': [{'file': 'README.md', 'text': 'value 1',
                            'source': {'metric': 'typo', 'value': None}}]}
    assert any(r[0] == 'FAIL' for r in check(repo, registry, {}))


def test_shared_error_can_still_be_flagged_by_different_wrong_labels(repo):
    values, details = recompute(repo)
    assert values['nemotron+paligemma.labelled_agreement'] == '48/50'
    assert details['nemotron+paligemma']['unflagged_errors'] == []
    shared = next(r for r in details['triple.errors'] if len(r['wrong_models']) == 2)
    assert shared['file'] == 'egg/egg-012.jpg'
    assert shared['flagged'] is True
    assert shared['votes'] == {'nemotron': 'stress_ball', 'gemma': 'egg', 'paligemma': 'can'}


def test_all_failed_is_valid_and_counts_errors(repo):
    change(repo, 'nemotron_run2.json', lambda rows: [r.update(ok=False, latency_s=None) for r in rows])
    values, _ = recompute(repo)
    assert values['nemotron.accuracy'] == '0/50'
    assert values['nemotron.median_latency_2dp'] is None


def test_bad_latency_and_malformed_registry(repo):
    change(repo, 'gemma4_api.json', lambda rows: rows[0].update(latency_s=float('nan')))
    with pytest.raises(ValueError, match='latency'):
        recompute(repo)
    with pytest.raises(ValueError, match='claims array'):
        check(repo, [], {})


def test_new_submission_is_included(repo):
    (repo / 'docs/submission/new.md').write_text('New claim 99%')
    assert any(r[0] == 'WARN' and r[1].endswith('new.md') for r in check(repo, {'claims': []}, {}))


def test_inline_html_cannot_hide_forbidden_phrase(repo):
    (repo / 'deck/index.html').write_text('<p>works <em>on the</em> G1</p>')
    results = check(repo, {'claims': []}, {})
    assert any(r[0] == 'FAIL' and 'forbidden phrase: works on the G1' in r[2] for r in results)


@pytest.mark.parametrize('strict', [False, True])
def test_numeric_coverage_cli_severity_and_counts(repo, tmp_path, capsys, strict):
    (repo / 'README.md').write_text('New claim 99%\nAnother 12 seconds\n')
    registry = tmp_path / 'registry.json'
    registry.write_text(json.dumps({'claims': [], 'expected_metrics': {}}))
    args = ['--root', str(repo), '--registry', str(registry)]
    if strict:
        args.append('--strict')
    assert main(args) == int(strict)
    output = capsys.readouterr().out
    status = 'FAIL' if strict else 'WARN'
    assert f'2 {status}' in output
    assert f'{status} | README.md | unregistered numeric text:' in output
    assert main(args + ['--json']) == int(strict)
    report = json.loads(capsys.readouterr().out)
    assert report['counts'][status] == 2


@pytest.mark.parametrize('strict', [False, True])
def test_hard_failures_remain_failures(repo, strict):
    (repo / 'README.md').write_text('48 of 50\n100% safe\n')
    registry = {'claims': [
        {'file': 'README.md', 'text': 'missing 12', 'source': {'doc': 'README.md'}},
        {'file': 'README.md', 'text': '48 of 50',
         'source': {'metric': 'nemotron.accuracy', 'value': '48/50'}}]}
    results = check(repo, registry, {'nemotron.accuracy': '47/50'}, strict=strict)
    for detail in ('exact text', 'recomputed', 'forbidden phrase'):
        assert any(r[0] == 'FAIL' and detail in r[2] for r in results)
