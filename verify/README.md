# Offline claim verification

Run from the repository root:

```sh
python3 -m verify.run
python3 -m verify.run --json
python3 -m verify.run --strict
python3 -m pytest tests/test_verify_run.py -q
```

The first command prints a PASS/WARN/FAIL table and exits nonzero on any failure.
Unregistered numeric wording is WARN by default and does not change the exit code.
Use `--strict` to make coverage gaps FAIL. Counts include all three statuses in
text and JSON output. Other failures remain failures in both modes.
JSON mode includes computed metrics, photo-level error details and the same checks.
No packages beyond Python's standard library are required for the checker.
It reads saved JSON and imports `ai.recognize.decide`; it never calls recognisers,
loads weights, opens images, uses credentials, or contacts a network endpoint.
Tests need pytest. `--root PATH --registry PATH` supports temporary fixture trees;
the decision function still comes from the installed/current repository code.

## Evidence and interpretation

The inputs are `docs/evidence/recognition/nemotron_run2.json`, `gemma4_api.json`
and `paligemma2_local.json`. Ground truth is `expected`, joined by unique `file`.
Mismatched photo sets, inconsistent labels, malformed votes and invalid successful
call latencies fail closed. Failed calls count as errors on labelled photos.
Unlabelled mix images contribute to agreement but never accuracy.

`recompute()` calculates per-model accuracy, per-class counts, failed calls,
percentages and median successful labelled-call latency. For every pair it reports
agreement on all photos and on labelled photos, labelled disagreements, the union
of erroneous photos flagged by disagreement, and photos both models miss.
Agreement compares `(ok, object)`; two equally failed answers agree but are not
correct. Confidence is used by `decide`, not by the agreement comparison.

Both ensembles use the repository's actual fragile-first `decide` function.
Ball confirmation means the chosen object is stress ball with at least two votes;
it is not a measured grasp outcome or proof of model independence. The triple
error report lists each wrong model and whether the photo was flagged. A shared
error means at least two models miss the same photo, even if their wrong labels
differ; it does not mean every model missed it. Flagged-error fractions count
unique photos, not individual wrong votes.

## Registry and lint

`claims.json` records exact text units, file paths and sources. Markdown units are
trimmed nonempty lines; HTML units are visible text nodes and image alt text,
with styles and scripts excluded. Thus inline HTML can split a sentence into
several units. Coverage reports every unregistered unit with a digit, including headings,
commands and model names; selected spelled-out claims are also registered.
New submission Markdown files are discovered automatically. Architecture, scorecard
and code-tour documents are also checked. Coverage is deliberately incomplete:
new editorial numbers, headings and commands stay visible as warnings until reviewed. This conservative
coverage check catches new numeric wording, but is not a semantic parser for
arbitrary spelled-out numbers or claims split across HTML nodes.

A source is either `{ "metric": "nemotron.accuracy", "value": "48/50" }`
or `{ "doc": "docs/OBJECT_RECOGNITION_RESULTS.md" }`. Optional `checks` attach
multiple metric/value comparisons to a unit. Each metric binding is reviewed
against the exact registered wording; formatting such as `48 of 50` and `48/50`
may represent the same value. `expected_metrics` separately checks the saved-run
baseline. Missing wording, missing sources, unknown metrics and numerical drift
fail. Uncovered numeric units warn unless `--strict` is selected. A document-source PASS means **trace exists
only**, not that its contents were recomputed or independently validated.
Historical runs, timings without saved evidence, simulation thresholds, prompt
experiments and planned settings retain document traces rather than invented
measurements. To update the registry, review the new text and its evidence;
do not merely replace expected numbers to silence failures.

Lint is case-insensitive for `works on the G1`, `Newton` (including plurals),
`96% in general`, `100% safe`, and `guarantee` (including inflections).
Only the G1 phrase has a local negation exception. Consequently quoted warnings
and phrases such as “not a guarantee” still fail the other literal rules.
These are review findings, not accusations that the author made a positive claim.

## Findings in the current checked-in documents

Reproduce with `python3 -m verify.run --json`. The registry retains published
values even when they disagree with saved evidence; it is not a green-status
allowlist. Stale exact text has been removed.

- The recognition report says “none shared”, but Nemotron and PaliGemma both
  miss `egg/egg-012.jpg` with different wrong labels. Gemma gets it right.
- PaliGemma latency in the README, architecture, model story and Rokoko submission
  is 0.21 s; saved successful labelled answers give 0.24 s. Another run may
  explain it but is not supplied as per-photo evidence.
- Literal forbidden-phrase findings include negative caveats and quoted warnings.
  They remain failures under the existing lint rule, not allegations of positive
  assertions. See the PR discrepancy list for semantic review findings.

Documents outside `verify/` are deliberately left untouched. These checks do not
rerun recognition, establish generalisation, measure real forces, or validate
hardware. Grasp results remain simulation; closure/break thresholds remain toy
values unless independently calibrated evidence is supplied.
