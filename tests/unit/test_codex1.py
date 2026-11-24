"""Check the attack's distribution invariants and declared scope."""

import csv
import importlib.util
import io
from collections import Counter
from pathlib import Path

import pytest

from harness.attack import Ctx, call_rng


PATH = Path(__file__).resolve().parents[2] / "attacks" / "codex1" / "attack.py"
spec = importlib.util.spec_from_file_location("codex1_attack", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def context(fraction=0.5, stage="S3", seed="s0"):
    return Ctx(seed=seed, stage=stage,
               rng=call_rng(seed, stage, "on_input", "c_bkg_data.csv#1"),
               shared={"shuffle_fraction": fraction})


@pytest.fixture
def reference():
    # Precise decimal text and nonsequential row IDs catch accidental numeric
    # reserialization or use of row labels as positional indexes.
    lines = [",m_JJ,m_J1,delta_m_J,tau_2_over_tau_1_J1,tau_2_over_tau_1_J2"]
    lines += [f"{2*i+7},3.50000000000000001,0.11,0.38,0.4,{i / 100:.18f}"
              for i in range(100)]
    return ("\r\n".join(lines) + "\r\n").encode()


def parse(data):
    return list(csv.reader(io.StringIO(data.decode(), newline="")))


@pytest.mark.parametrize("fraction", [0.1, 0.25, 0.5, 1.0])
def test_preserves_marginals_and_all_other_cells(reference, fraction):
    attack = module.CorrelationPoisoning()
    output = attack.on_input("c_bkg_data.csv", reference, context(fraction))
    assert output == attack.on_input("c_bkg_data.csv", reference, context(fraction))
    before, after = parse(reference), parse(output)
    assert before[0] == after[0]
    assert len(before) == len(after)
    column = before[0].index(module.FEATURE)
    for col in range(len(before[0])):
        original = [r[col] for r in before[1:]]
        changed = [r[col] for r in after[1:]]
        assert Counter(original) == Counter(changed)
        if col != column:
            assert original == changed
    changed_rows = sum(a[column] != b[column] for a, b in zip(before[1:], after[1:]))
    assert 0 < changed_rows <= int(100 * fraction)


@pytest.mark.parametrize("stage,name", [
    ("S1", "c_bkg_data.csv"), ("S2", "c_bkg_data.csv"),
    ("S4", "c_bkg_data.csv"), ("S5", "c_bkg_data.csv"),
    ("S3", "c_data.csv"), ("S3", "features.json"),
    ("S3", "c_bkg_data_full.csv"), ("S3", "c_data_full.csv"),
])
def test_only_declared_stage_and_file_can_change(reference, stage, name):
    assert module.CorrelationPoisoning().on_input(name, reference, context(stage=stage)) is reference


@pytest.mark.parametrize("fraction", [0, 0.001, 0.01])
def test_no_change_returns_original_bytes(reference, fraction):
    assert module.CorrelationPoisoning().on_input("c_bkg_data.csv", reference, context(fraction)) is reference


@pytest.mark.parametrize("fraction", [-0.1, 1.1, float("nan"), float("inf"), True, "0.5", None])
def test_invalid_fraction_is_rejected(reference, fraction):
    with pytest.raises(ValueError, match="shuffle_fraction"):
        module.CorrelationPoisoning().on_input("c_bkg_data.csv", reference, context(fraction))


def test_constant_feature_is_a_byte_identical_noop(reference):
    rows = parse(reference)
    for row in rows[1:]:
        row[-1] = "0.12345678901234567890"
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\r\n").writerows(rows)
    data = output.getvalue().encode()
    assert module.CorrelationPoisoning().on_input("c_bkg_data.csv", data, context(1)) is data
