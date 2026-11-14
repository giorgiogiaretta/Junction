# Raw model answers behind the recognition numbers (photos are NOT in the repo)
Per-photo rows `{file, expected, object, confidence, ok, latency_s}` from 14/11 (our 77 head-camera photos: 50 labelled by folder name ball/can/egg, 27 unlabelled `mix`). `expected` is the folder name; photo names are the only identifier. One person, one place, one day.
- `nemotron_run2.json`: Nemotron 3.5 Super VL (Verda endpoint), thinking off, second full run: 48/50.
- `gemma4_api.json`: gemma-4-26b-a4b-it on the Google API: 49/50.
- `paligemma2_local.json`: PaliGemma 2 3B mix 224 on our Verda A100 (3-option prompt, through the SSH tunnel; confidence is null): 49/50.
Recompute: `python -m ai.crosscheck docs/evidence/recognition/nemotron_run2.json docs/evidence/recognition/gemma4_api.json --names nemotron,gemma4` (agreement, disagreements) and the ensemble with `ai.recognize.decide` (see docs/OBJECT_RECOGNITION_RESULTS.md).
