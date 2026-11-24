"""Validate the local proxy's counting, paired folds, and credential handling."""
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import urllib.error

import numpy as np
import pandas as pd
import pytest


PATH = Path(__file__).resolve().parents[2] / "scripts/test_codex1.py"
spec = importlib.util.spec_from_file_location("local_codex1", PATH)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_s4_counting_and_uncertainty():
    reference = np.arange(100) / 100
    data = np.r_[np.zeros(97), [0.985, 0.99, 1]]
    result = runner.estimate(data, reference, np.full(100, 3.5), np.full(100, 3.5))
    assert result["threshold"] == pytest.approx(0.9801)
    assert result["n_data_pass"] == 3 and result["n_bkg_pass"] == 1
    assert result["n_excess"] == 2 and result["sigma"] == 2
    assert result["z"] == 1
    assert result["p_value"] == pytest.approx(0.1586552539)
    assert sum(result["excess_hist"]["data_pass"]) == 3
    assert sum(result["excess_hist"]["ref_pass_scaled"]) == 1


def test_ties_do_not_pass_and_zero_uncertainty_is_explicit():
    values, masses = np.full(100, 0.5), np.full(100, 3.5)
    result = runner.estimate(values, values, masses, masses)
    assert result["reference_ties_at_threshold"] == 100
    assert result["n_data_pass"] == result["n_bkg_pass"] == 0
    assert result["z"] is None and result["p_value"] is None


@pytest.mark.parametrize("change", [{"max_iter": 301}, {"max_iter": 40.0},
                                   {"max_iter": True}, {"learning_rate": float("nan")},
                                   {"arbitrary_code": "execute me"}])
def test_model_configuration_is_bounded(change):
    with pytest.raises(ValueError):
        runner.validate_params({**runner.DEFAULT_PARAMS, **change})


def test_url_normalization_and_credentials():
    assert runner.api_base("https://llm.aristote.education/v1/models/") == "https://llm.aristote.education/v1"
    for url in ("https://user:secret@example.com/v1", "https://example.com/v1?key=secret",
                "http://example.com/v1", "file:///tmp/api"):
        with pytest.raises(ValueError):
            runner.api_base(url)


def test_model_request_and_log_redaction(tmp_path, monkeypatch):
    monkeypatch.setenv("AISSAI_KEY", "test-credential-sentinel")
    received = []
    response = {"model": "qwen-3.8-27b", "id": "fake-response", "usage": {"total_tokens": 42},
                "choices": [{"finish_reason": "stop", "message": {
                    "content": json.dumps(runner.DEFAULT_PARAMS),
                    "reasoning_content": "private-reasoning-sentinel"}}]}

    class FakeOpener:
        def open(self, req, timeout):
            received.append(req)
            return io.BytesIO(json.dumps(response).encode())

    monkeypatch.setattr(runner.urllib.request, "build_opener", lambda *args: FakeOpener())
    args = SimpleNamespace(offline=False, api_key_env="AISSAI_KEY", model="qwen-3.8-27b",
                           plain_json=False, base_url="https://llm.aristote.education/v1/models",
                           timeout=5)
    path = tmp_path / "events.jsonl"
    result = runner.choose_params(args, runner.Journal(path), {"data": 100, "reference": 100})
    assert result == runner.DEFAULT_PARAMS
    assert len(received) == 1
    assert received[0].full_url == "https://llm.aristote.education/v1/chat/completions"
    assert received[0].get_header("Authorization") == "Bearer test-credential-sentinel"
    logged = path.read_text()
    assert "test-credential-sentinel" not in logged
    assert "private-reasoning-sentinel" not in logged
    assert '"total_tokens": 42' in logged


def test_http_errors_never_log_provider_body(tmp_path, monkeypatch):
    monkeypatch.setenv("AISSAI_KEY", "test-credential-sentinel")

    class FakeOpener:
        def open(self, req, timeout):
            raise urllib.error.HTTPError(req.full_url, 401, "unauthorized", {},
                                         io.BytesIO(b"echoed test-credential-sentinel"))

    monkeypatch.setattr(runner.urllib.request, "build_opener", lambda *args: FakeOpener())
    args = SimpleNamespace(offline=False, api_key_env="AISSAI_KEY", model="qwen-3.8-27b",
                           plain_json=False, base_url="https://llm.aristote.education/v1", timeout=5)
    path = tmp_path / "events.jsonl"
    with pytest.raises(ValueError, match="HTTP 401"):
        runner.choose_params(args, runner.Journal(path), {"data": 100, "reference": 100})
    assert "test-credential-sentinel" not in path.read_text()


def test_predictions_are_held_out_and_preserve_event_ids(tmp_path, monkeypatch):
    pytest.importorskip("sklearn")
    from sklearn.model_selection import StratifiedKFold
    import sklearn.ensemble
    fitted = []

    class MemorizingClassifier:
        def __init__(self, **kwargs):
            pass

        def fit(self, x, y):
            self.seen = set(x[:, 0])
            fitted.append(self.seen)

        def predict_proba(self, x):
            assert not self.seen.intersection(x[:, 0]), "Training event leaked into scoring"
            score = np.linspace(0.1, 0.9, len(x))
            return np.column_stack([1 - score, score])

    monkeypatch.setattr(sklearn.ensemble, "HistGradientBoostingClassifier", MemorizingClassifier)
    data = pd.DataFrame({f: np.arange(10, dtype=float) for f in runner.FEATURES}, index=range(10, 20))
    reference = pd.DataFrame({f: np.arange(10, 20, dtype=float) for f in runner.FEATURES}, index=range(30, 40))
    data["m_JJ"], reference["m_JJ"] = 3.5, 3.5
    labels = np.r_[np.ones(10), np.zeros(10)]
    folds = list(StratifiedKFold(2, shuffle=True, random_state=0).split(np.zeros(20), labels))
    out = tmp_path / "variant"
    runner.fit_variant(data, reference, reference, folds, runner.DEFAULT_PARAMS, 0, out,
                       runner.Journal(tmp_path / "events.jsonl"))
    scores = pd.read_csv(out / "scores_oof.csv")
    assert len(fitted) == 2 and len(scores) == 20
    assert scores["score"].notna().all()
    assert scores[scores["sample"] == "data"]["index"].tolist() == list(range(10, 20))
    assert scores[scores["sample"] == "reference"]["index"].tolist() == list(range(30, 40))
