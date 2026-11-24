# Test codex1 locally with Aristote

This helper compares clean and poisoned data through an approximate S3/S4
experiment. It does not upload an attack to the event service or consume a live
evaluation. It does make **one model API call** unless `--offline` is used.

The default endpoint is `https://llm.aristote.education/v1`, the model is
`qwen-3.8-27b`, and the API key is read from `AISSAI_KEY`. `/v1/models` is a model
listing endpoint, not the base URL for chat requests.

## Run

From the repository root, install the optional local evaluation dependency:

```sh
.venv/bin/python -m pip install -e '.[local-eval]'
```

If `AISSAI_KEY` is not already exported, enter it privately in your zsh terminal:

```sh
read -rs 'AISSAI_KEY?Aristote API key: '
export AISSAI_KEY
printf '\n'
```

Run the default attack against a clean baseline using the complete public data:

```sh
.venv/bin/python scripts/test_codex1.py
```

Compare several shuffle fractions and repeat with three fold/model/permutation
seeds (a larger run, still only one API call):

```sh
.venv/bin/python scripts/test_codex1.py \
  --fractions 0 0.1 0.25 0.5 1.0 \
  --seeds 0 1 2
```

For a quick installation and execution test without an API key:

```sh
.venv/bin/python scripts/test_codex1.py --offline --limit-per-sample 2000 --folds 3
```

Subsampled results are smoke tests, not reliable estimates of the attack's
effect. Use all rows and repeat seeds before drawing conclusions.

## What the experiment does

1. Runs the existing local submission validator.
2. Asks Qwen for bounded parameters of a `HistGradientBoostingClassifier` using
   the feature names, row counts, and task description. No event rows are sent.
   The response is validated as numeric configuration; no model-generated code
   is executed. `--offline` instead uses documented defaults from the script.
3. Freezes that configuration for the baseline and every poisoned variant.
4. Applies the submission's `on_input` hook to the full S3 reference with the
   chosen fraction. The default fraction comes from the submission manifest;
   sweep overrides do not edit that manifest. Seed 0 matches the harness's
   default hook RNG; other seeds also vary the hook permutation.
5. Trains on the four allowed features with stratified folds. Each event is
   scored only by a classifier that did not train on it. Paired variants use
   identical folds, model settings, and model RNG seeds.
6. Applies S4's 99th-percentile threshold and counting recipe independently to
   each variant, then reports `attacked_n_excess - baseline_n_excess`.

This is a **fixed-classifier proxy**, not a replay of the Researcher, Coder, and
reviewer agents. Their reactions and choices can change the official outcome.
It has no private verifier, hidden data seeds, S5 agent, or official honest-run
variability estimate. `delta_n_excess` is an event-count change, not the official
pull. The S4 `z` statistic is also not the official pull.

## Results and logs

Every run creates a new ignored directory under `results/local-codex1/`:

- `summary.json`: clean/poisoned estimates and paired differences.
- `configuration.json`: chosen classifier parameters, row counts, seeds,
  versions, and input/attack hashes.
- `local_check.json`: the submission validator's report.
- `events.jsonl`: model request, returned model ID, token usage when provided,
  validated parameters, fold timings, and estimates. Authorization headers,
  API-key values, and provider reasoning fields are not logged. No sub-agents
  are launched.
- `seed-*/baseline/` and `seed-*/fraction-*/`: out-of-fold scores, training
  reports, and numerical estimates. Fraction zero reuses the clean baseline.

The script exits on API or response-validation errors; it does not silently
replace the requested model. If the endpoint rejects JSON mode, retry with
`--plain-json`. HTTP 401/403 usually calls for checking the environment variable
and account access. Keep credentials in the environment, outside submissions.

The request follows the documented [Chat Completions JSON format](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat).
Aristote compatibility still needs a live authenticated check. The classifier
and fold behavior follow [HistGradientBoostingClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html)
and [StratifiedKFold](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.StratifiedKFold.html).
