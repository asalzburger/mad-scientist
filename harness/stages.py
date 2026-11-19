"""The pipeline's five stages, what each takes in and hands over, and where an attack's hooks apply.

Shared by the runner (harness/runner.py), which runs the stages, and the validator
(harness/validate.py), which exercises a submission's hooks on a recorded run without running
anything. Only the hook host and the standard library are imported here, so the validator runs
with neither the runner nor the pipeline's own dependencies.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from harness.hookhost import HookError, HookHost

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "c_bkg_data.csv"  # the background-only reference: attackable through on_input; c_data.csv is locked
# The same events with the LHCO jet columns. Never in an honest stage's /data:
# on_input is offered each one empty, and returning its bytes (ctx.read) mounts it for that stage.
# c_data_full.csv is locked like c_data.csv; c_bkg_data_full.csv may be changed like the reference.
DATA_FULL, REFERENCE_FULL = "c_data_full.csv", "c_bkg_data_full.csv"


@dataclass(frozen=True)
class Stage:
    name: str
    brief: str
    inputs: tuple[str, ...] = ()  # earlier stages' outputs, mounted at /in
    outputs: tuple[str, ...] = ()  # files the stage must leave in its working folder
    numeric_questions: str | None = None


STAGES = (
    Stage("S1", "S1_data_prep.txt", outputs=("dataset.json",)),
    Stage("S2", "S2_features.txt", ("dataset.json",), ("features.json",)),
    Stage("S3", "S3_anomaly_scores.txt", ("features.json",), ("scores_oof.csv", "ad_report.json")),
    Stage("S4", "S4_signal_estimate.txt", ("scores_oof.csv",), ("estimate.json",)),
    Stage("S5", "S5_report.txt",
          ("dataset.json", "features.json", "ad_report.json", "scores_oof.csv", "estimate.json"),
          ("final_report.md", "scores.csv"), numeric_questions="S5_numeric_questions.json"),
)
STAGE_BY_NAME = {s.name: s for s in STAGES}


def digest(value: Any) -> str:
    """The SHA-256 of a hook's value: bytes as they are, text as UTF-8, anything else as canonical
    JSON (sorted keys, no whitespace, the form harness/keys.py uses for cache keys)."""
    if isinstance(value, str):
        value = value.encode()
    elif not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                           allow_nan=False).encode()
    return hashlib.sha256(value).hexdigest()


class Hooks:
    """The runner's side of an attack: applies the hook host's hooks at each site, logs every call,
    and reports the first change (where the attack begins) to on_first_change."""

    def __init__(self, host: HookHost, on_first_change: Callable[[str], None] = lambda where: None):
        self.host, self.on_first_change = host, on_first_change
        self.diverged_at: str | None = None
        self.calls: list[dict] = []
        self.error: str | None = None
        self.replaced: set[str] = set()  # stages a replacement runs: the other hooks skip them
        self._n: Counter[str] = Counter()
        self._lock = threading.Lock()

    def has(self, hook: str) -> bool:
        return hook in self.host.hooks

    def replacement(self, stage: str) -> dict | None:
        """The stage's AgentPolicy (AgentPolicy.to_json()) if the attack replaces it, else None."""
        policy = self.apply("replace_agent", stage, "stage", None, {})
        if policy is not None:
            self.replaced.add(stage)
        return policy

    def apply(self, hook: str, stage: str, what: str, value: Any, args: dict, agent: str | None = None) -> Any:
        """The hook's version of value (bytes, text or task files); value itself when the attack
        does not implement this hook or replaces the stage."""
        if not self.has(hook) or stage in self.replaced:
            return value
        with self._lock:
            self._n[f"{stage}/{hook}/{what}"] += 1
            call_id = f"{what}#{self._n[f'{stage}/{hook}/{what}']}"
            try:
                new = self.host.call(hook, stage, call_id, args, agent)
            except HookError as e:
                self.error = str(e)
                raise
            changed = new != value
            self.calls.append({"stage": stage, "hook": hook, "what": what, "call_id": call_id, "agent": agent,
                               "changed": changed, "before": digest(value), "after": digest(new)})
            if changed and self.diverged_at is None:
                self.diverged_at = f"{stage} {hook} {what} ({call_id})"
                self.on_first_change(self.diverged_at)
            return new
