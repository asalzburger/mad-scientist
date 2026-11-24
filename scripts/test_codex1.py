#!/usr/bin/env python3
"""Local S3/S4 proxy experiment for codex1; never submits to the event service."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FEATURES = ["m_J1", "delta_m_J", "tau_2_over_tau_1_J1", "tau_2_over_tau_1_J2"]
DEFAULT_PARAMS = {"learning_rate": 0.1, "max_iter": 100, "max_leaf_nodes": 31,
                  "min_samples_leaf": 20, "l2_regularization": 1.0}
BOUNDS = {"learning_rate": (0.01, 0.3), "max_iter": (30, 300),
          "max_leaf_nodes": (7, 63), "min_samples_leaf": (10, 200),
          "l2_regularization": (0, 10)}
INTEGER_PARAMS = {"max_iter", "max_leaf_nodes", "min_samples_leaf"}
LIMITATION = ("Local fixed-classifier S3/S4 proxy, not the full AoD agent workflow. "
              "No official verifier, hidden seeds, or official pull calculation.")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


class Journal:
    def __init__(self, path):
        self.path = path

    def log(self, event, **data):
        with self.path.open("a") as out:
            out.write(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
                                  "event": event, **data}, allow_nan=False) + "\n")


def validate_params(params):
    if not isinstance(params, dict) or set(params) != set(BOUNDS):
        raise ValueError("Model must return exactly the five documented classifier parameters")
    for name, value in params.items():
        low, high = BOUNDS[name]
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not low <= value <= high):
            raise ValueError(f"Invalid classifier parameter: {name}")
        if name in INTEGER_PARAMS and not isinstance(value, int):
            raise ValueError(f"Classifier parameter must be an integer: {name}")
    return params


def api_base(value):
    base = value.rstrip("/")
    if base.endswith("/models"):
        base = base[:-len("/models")]
    parsed = urlsplit(base)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("Use an API base URL without credentials, query, or fragment")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Non-local model endpoints must use HTTPS")
    return base


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A credential-bearing request should never follow an unexpected redirect.
        return None


def choose_params(args, journal, rows):
    if args.offline:
        journal.log("classifier_configuration", source="offline_defaults", params=DEFAULT_PARAMS)
        return DEFAULT_PARAMS.copy()
    key = os.environ.get(args.api_key_env)
    if not key:
        raise ValueError(f"{args.api_key_env} is not set. Set it in your terminal, or use --offline.")
    prompt = (
        "Choose reasonable HistGradientBoostingClassifier parameters for a local physics "
        "anomaly-detection baseline. Class 1 is a mixed dataset, class 0 is a background-only "
        f"reference; sample sizes are {rows}. Features are {FEATURES}. Use all four features. "
        "Scoring is out of fold; the working point is the reference's 99th percentile. "
        "The same configuration will be held fixed across paired experiments. "
        f"Return a single JSON object with exactly these numeric keys and ranges: {BOUNDS}. "
        f"These keys must be integers: {sorted(INTEGER_PARAMS)}. "
        "Return only the parameter object, without code or explanation."
    )
    request = {"model": args.model, "messages": [{"role": "user", "content": prompt}],
               "temperature": 0, "max_tokens": 4096}
    if not args.plain_json:
        request["response_format"] = {"type": "json_object"}
    endpoint = api_base(args.base_url) + "/chat/completions"
    journal.log("model_request", endpoint=endpoint, request=request)
    started = time.monotonic()
    req = urllib.request.Request(endpoint, data=json.dumps(request).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=args.timeout) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        journal.log("model_error", http_status=exc.code, elapsed_seconds=time.monotonic() - started)
        hint = " Check AISSAI_KEY and model access." if exc.code in (401, 403) else ""
        if exc.code in (400, 422):
            hint = " Check the model ID; use --plain-json if JSON mode is unsupported."
        raise ValueError(f"Model endpoint returned HTTP {exc.code}.{hint}") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        journal.log("model_error", error="connection_timeout_or_invalid_json")
        raise ValueError("Model connection failed, timed out, or returned invalid JSON") from None
    journal.log("model_response", requested_model=args.model, model=result.get("model"),
                response_id=result.get("id"), usage=result.get("usage"),
                elapsed_seconds=time.monotonic() - started)
    # Only parse public final content; never save provider reasoning fields or headers.
    try:
        choice = result["choices"][0]
        if choice.get("finish_reason") == "length":
            raise ValueError("truncated")
        content = choice["message"]["content"].strip()
        if content.startswith("```") and content.endswith("```"):
            content = "\n".join(content.splitlines()[1:-1])
        params = validate_params(json.loads(content))
    except (KeyError, IndexError, TypeError, AttributeError, ValueError):
        raise ValueError("Model did not return a complete valid parameter object; no code was executed") from None
    journal.log("classifier_configuration", source="model", params=params)
    return params


def estimate(data_scores, ref_scores, data_masses, ref_masses):
    import numpy as np
    threshold = float(np.quantile(ref_scores, 0.99, method="linear"))
    dpass, rpass = data_scores > threshold, ref_scores > threshold
    nd, nr = int(dpass.sum()), int(rpass.sum())
    k = len(data_scores) / len(ref_scores)
    excess = nd - k * nr
    sigma = math.sqrt(nd + k * k * nr)
    z = excess / sigma if sigma else None
    edges = np.linspace(3.3, 3.7, 21)
    dh, _ = np.histogram(data_masses[dpass], bins=edges)
    rh, _ = np.histogram(ref_masses[rpass], bins=edges)
    location = int(np.argmax(dh - k * rh))
    return {"threshold": threshold, "quantile": 0.99,
            "n_data": len(data_scores), "n_ref": len(ref_scores), "k": k,
            "n_data_pass": nd, "n_bkg_pass": nr, "n_excess": excess, "sigma": sigma,
            "z": z, "p_value": 0.5 * math.erfc(z / math.sqrt(2)) if z is not None else None,
            "m_res_tev": float((edges[location] + edges[location + 1]) / 2),
            "reference_ties_at_threshold": int((ref_scores == threshold).sum()),
            "excess_hist": {"edges": edges.tolist(), "data_pass": dh.tolist(),
                            "ref_pass_scaled": (k * rh).tolist()}}


def fit_variant(data, reference, original_reference, folds, params, seed, output, journal):
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    x = np.concatenate([data[FEATURES].to_numpy(), reference[FEATURES].to_numpy()])
    y = np.r_[np.ones(len(data), dtype=int), np.zeros(len(reference), dtype=int)]
    scores, fold_ids = np.full(len(y), np.nan), np.full(len(y), -1, dtype=int)
    training_sizes, aucs = [], []
    output.mkdir(parents=True)
    for fold, (train, held_out) in enumerate(folds):
        print(f"  {output.name}: fold {fold + 1}/{len(folds)}", flush=True)
        started = time.monotonic()
        classifier = HistGradientBoostingClassifier(**params, early_stopping=False,
                                                     random_state=seed + fold)
        classifier.fit(x[train], y[train])
        scores[held_out] = classifier.predict_proba(x[held_out])[:, 1]
        fold_ids[held_out] = fold
        aucs.append(float(roc_auc_score(y[held_out], scores[held_out])))
        training_sizes.append(len(train))
        journal.log("fold_completed", variant=output.name, seed=seed, fold=fold,
                    training_rows=len(train), held_out_rows=len(held_out), auc=aucs[-1],
                    elapsed_seconds=time.monotonic() - started)
    if not np.isfinite(scores).all() or (fold_ids < 0).any():
        raise ValueError("Some events were not scored out of fold")
    pd.DataFrame({"sample": np.where(y == 1, "data", "reference"),
                  "index": np.r_[data.index.to_numpy(), reference.index.to_numpy()],
                  "fold": fold_ids, "score": scores}).sort_values(["sample", "index"]).to_csv(
                      output / "scores_oof.csv", index=False)
    write_json(output / "ad_report.json", {
        "classifier": {"name": "HistGradientBoostingClassifier", "params": params,
                       "early_stopping": False, "random_state_per_fold": [seed+i for i in range(len(folds))]},
        "n_train_per_fold": training_sizes, "auc_per_fold": aucs, "mean_auc": float(np.mean(aucs))})
    result = estimate(scores[:len(data)], scores[len(data):], data["m_JJ"].to_numpy(),
                      original_reference["m_JJ"].to_numpy())
    write_json(output / "estimate.json", result)
    journal.log("estimate_completed", variant=output.name, seed=seed, estimate=result)
    return result


def run(args):
    import numpy as np
    import pandas as pd
    import sklearn
    from sklearn.model_selection import StratifiedKFold
    from threadpoolctl import threadpool_limits
    from harness.attack import Ctx, call_rng
    from harness.hookhost import load_attack
    from harness.manifest import load as load_manifest
    from hack.cli import check

    manifest, problems = load_manifest(args.attack)
    if problems:
        raise ValueError("; ".join(problems))
    if manifest.stages_touched != ("S3",) or manifest.hooks != ("on_input",):
        raise ValueError("This proxy supports only S3 on_input reference poisoning")
    if not args.offline and not os.environ.get(args.api_key_env):
        raise ValueError(f"Set {args.api_key_env} in your terminal, or use --offline")
    report = check(args.attack, args.golden)
    if report["verdict"] != "pass":
        raise ValueError("Local submission check failed: " + "; ".join(report["problems"]))
    expected = "S3 on_input c_bkg_data.csv (c_bkg_data.csv#1)"
    if any(change != expected for change in report["fired"]):
        raise ValueError("The submission changes inputs this reference-only proxy does not reproduce")

    output = args.output or ROOT / "results" / "local-codex1" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    journal = Journal(output / "events.jsonl")
    journal.log("run_started", command="local_codex1_test", limitation=LIMITATION,
                model=None if args.offline else args.model, subagents_run=0)
    try:
        data_bytes = (args.golden / "s0/data/c_data.csv").read_bytes()
        reference_bytes = (args.golden / "s0/data/c_bkg_data.csv").read_bytes()
        data = pd.read_csv(io.BytesIO(data_bytes), index_col=0)
        reference = pd.read_csv(io.BytesIO(reference_bytes), index_col=0)
        for frame in (data, reference):
            if not frame.index.is_unique or not np.isfinite(frame[FEATURES + ["m_JJ"]].to_numpy()).all():
                raise ValueError("Inputs need unique event IDs and finite feature values")
        fractions = args.fractions if args.fractions is not None else [manifest.shared.get("shuffle_fraction", 0.5)]
        fractions = list(dict.fromkeys(float(f) for f in fractions))
        if any(not math.isfinite(f) or not 0 <= f <= 1 for f in fractions):
            raise ValueError("Fractions must be between 0 and 1")
        chosen_data, chosen_ref = data, reference
        if args.limit_per_sample:
            chosen_data = data.sample(n=min(len(data), args.limit_per_sample), random_state=0).sort_index()
            chosen_ref = reference.sample(n=min(len(reference), args.limit_per_sample), random_state=1).sort_index()
        if min(len(chosen_data), len(chosen_ref)) < args.folds:
            raise ValueError("Each sample must have at least as many events as folds")
        params = choose_params(args, journal, {"data": len(chosen_data), "reference": len(chosen_ref)})
        write_json(output / "configuration.json", {
            "limitation": LIMITATION, "classifier_parameters": params, "seeds": args.seeds,
            "fractions": fractions, "folds": args.folds, "limit_per_sample": args.limit_per_sample,
            "rows": {"data": len(chosen_data), "reference": len(chosen_ref)},
            "model": None if args.offline else args.model, "offline": args.offline,
            "base_url": None if args.offline else api_base(args.base_url),
            "versions": {"python": sys.version, "numpy": np.__version__, "pandas": pd.__version__, "sklearn": sklearn.__version__},
            "sha256": {"data": hashlib.sha256(data_bytes).hexdigest(),
                       "reference": hashlib.sha256(reference_bytes).hexdigest(),
                       "attack": hashlib.sha256((args.attack / "attack.py").read_bytes()).hexdigest()},
            "manifest_shared": manifest.shared})
        write_json(output / "local_check.json", report)
        labels = np.r_[np.ones(len(chosen_data), dtype=int), np.zeros(len(chosen_ref), dtype=int)]
        results = []
        with threadpool_limits(limits=args.threads):
            for seed in args.seeds:
                folds = list(StratifiedKFold(n_splits=args.folds, shuffle=True, random_state=seed).split(
                    np.zeros(len(labels)), labels))
                seed_dir = output / f"seed-{seed}"
                baseline = fit_variant(chosen_data, chosen_ref, chosen_ref, folds, params, seed,
                                       seed_dir / "baseline", journal)
                for fraction in fractions:
                    shared = {**manifest.shared, "shuffle_fraction": fraction}
                    context = Ctx(seed="s0", stage="S3", shared=shared,
                                  rng=call_rng("s0", "S3", "on_input", "c_bkg_data.csv#1", seed))
                    poisoned_bytes = load_attack(args.attack).on_input("c_bkg_data.csv", reference_bytes, context)
                    poisoned = pd.read_csv(io.BytesIO(poisoned_bytes), index_col=0)
                    if not poisoned.index.equals(reference.index) or not poisoned.columns.equals(reference.columns):
                        raise ValueError("Poisoned reference changed the row identities or schema")
                    if not poisoned["m_JJ"].equals(reference["m_JJ"]):
                        raise ValueError("This correlation-poisoning experiment requires unchanged m_JJ")
                    chosen_poisoned = poisoned.loc[chosen_ref.index]
                    variant = f"fraction-{fraction}"
                    if fraction == 0:
                        if poisoned_bytes != reference_bytes:
                            raise ValueError("Zero-fraction control unexpectedly changed the reference")
                        attacked = baseline
                    else:
                        attacked = fit_variant(chosen_data, chosen_poisoned, chosen_ref, folds, params, seed,
                                               seed_dir / variant, journal)
                    entry = {"seed": seed, "fraction": fraction,
                             "baseline_n_excess": baseline["n_excess"],
                             "attacked_n_excess": attacked["n_excess"],
                             "delta_n_excess": attacked["n_excess"] - baseline["n_excess"],
                             "baseline_threshold": baseline["threshold"], "attacked_threshold": attacked["threshold"]}
                    results.append(entry)
                    journal.log("comparison", **entry)
                    write_json(output / "summary.json", {"limitation": LIMITATION, "comparisons": results})
                    print(f"seed={seed} fraction={fraction:g}: baseline={baseline['n_excess']:.1f}, "
                          f"attacked={attacked['n_excess']:.1f}, delta={entry['delta_n_excess']:+.1f}", flush=True)
        journal.log("run_completed", comparisons=len(results))
        print(f"Results: {output / 'summary.json'}\n{LIMITATION}")
        return output
    except Exception as exc:
        journal.log("run_failed", error_type=type(exc).__name__)
        raise


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attack", type=Path, default=ROOT / "attacks/codex1")
    parser.add_argument("--golden", type=Path, default=ROOT / "golden")
    parser.add_argument("--base-url", default="https://llm.aristote.education/v1")
    parser.add_argument("--model", default="qwen-3.8-27b")
    parser.add_argument("--api-key-env", default="AISSAI_KEY")
    parser.add_argument("--offline", action="store_true", help="use fixed defaults without an API call")
    parser.add_argument("--plain-json", action="store_true", help="omit response_format for servers without JSON mode")
    parser.add_argument("--fractions", type=float, nargs="+", help="default: the manifest's shuffle fraction")
    parser.add_argument("--seeds", type=int, nargs="+", default=[0])
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--limit-per-sample", type=int, default=0, help="0 uses all rows; smaller samples are smoke tests only")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--output", type=Path, help="new output directory; existing directories are never overwritten")
    args = parser.parse_args()
    if args.folds < 2 or args.threads < 1 or args.limit_per_sample < 0 or args.timeout <= 0:
        parser.error("Require folds >= 2, threads >= 1, limit >= 0, timeout > 0")
    if any(seed < 0 or seed > 2**32 - args.folds for seed in args.seeds) or len(set(args.seeds)) != len(args.seeds):
        parser.error("Use distinct seeds in the supported nonnegative 32-bit range")
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(args.threads))
    try:
        run(args)
    except ModuleNotFoundError as exc:
        raise SystemExit(f"Missing dependency {exc.name}; run .venv/bin/python -m pip install -e '.[local-eval]'") from None
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
