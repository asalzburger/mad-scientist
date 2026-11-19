import io
import json
import os
import subprocess
import sys
import tarfile
import textwrap
from pathlib import Path

import pytest

from hack import bundle, cli

ROOT = Path(__file__).resolve().parents[2]
INPUTS = {"S2": ["dataset.json"], "S3": ["features.json"], "S4": ["scores_oof.csv"],
          "S5": ["dataset.json", "features.json", "ad_report.json", "scores_oof.csv", "estimate.json"]}


@pytest.fixture
def golden(tmp_path):
    """A golden folder as the release unpacks it: s0/, a small recorded honest run, and seeds/s0/,
    the seed's full-column files."""
    kit = tmp_path / "golden"
    run = kit / "s0"
    (run / "data").mkdir(parents=True)
    (run / "data" / "c_data.csv").write_text(",m_JJ\n0,3.5\n")
    (run / "data" / "c_bkg_data.csv").write_text(",m_JJ\n0,3.4\n")
    for stage in ("S1", "S2", "S3", "S4", "S5"):
        (run / stage / "task").mkdir(parents=True)
        (run / stage / "in").mkdir()
        (run / stage / "task" / "brief.txt").write_text(f"Stage {stage} brief.\n")
        (run / stage / "task" / "reprompt.txt").write_text("Call end_project when done.\n")
        for name in INPUTS.get(stage, []):
            (run / stage / "in" / name).write_text(f"{name} contents\n")
    stages = [{"stage": s, "prompt_tokens": 100, "completion_tokens": 0} for s in ("S1", "S2", "S3", "S4", "S5")]
    (run / "run.json").write_text(json.dumps({"seed": "s0", "status": "complete", "stages": stages}))
    (kit / "seeds" / "s0").mkdir(parents=True)
    (kit / "seeds" / "s0" / "c_bkg_data_full.csv").write_text(",m_JJ,pxj1\n0,3.4,1.0\n")
    return kit


MOUNT = '''
from harness.attack import Attack

class Mount(Attack):
    def on_input(self, name, data, ctx):
        if ctx.stage == "S2" and name == "c_bkg_data_full.csv":
            return ctx.read(name)
        return data
'''


def write(tmp_path, code=MOUNT, name="hello", target="n_excess", stages=("S2",), hooks=("on_input",)):
    sub = tmp_path / name.replace(" ", "_")
    sub.mkdir()
    (sub / "attack.py").write_text(textwrap.dedent(code))
    (sub / "WRITEUP.md").write_text("# What it does\n")
    (sub / "manifest.yaml").write_text(
        f"team: team-01\nname: '{name}'\nattack_class: input-poisoning\nstages_touched: {list(stages)}\n"
        f"hooks: {list(hooks)}\nintended_direction: '+'\ntarget: {target}\n")
    return sub


def test_hack_check_passes_a_declared_attack_on_the_golden_folder(tmp_path, golden, capsys):
    sub = write(tmp_path)
    assert cli.main(["check", str(sub), "--golden", str(golden), "--json", str(tmp_path / "r.json")]) == 0
    out = capsys.readouterr().out
    assert out.startswith("PASS") and "next: hack preview" in out
    report = json.loads((tmp_path / "r.json").read_text())
    # the full-column files come from the golden folder's seeds/, as the service offers them
    assert report["fired"] == ["S2 on_input c_bkg_data_full.csv (c_bkg_data_full.csv#1)"]


@pytest.mark.parametrize("kw, message", [
    ({"name": "bad name"}, "name must be"),
    ({"target": "significance"}, "is not open at this event"),
    ({"stages": ("S3",)}, "which manifest.yaml does not declare"),
])
def test_hack_check_rejects_what_the_service_would_refuse(tmp_path, golden, capsys, kw, message):
    sub = write(tmp_path, **kw)
    assert cli.main(["check", str(sub), "--golden", str(golden)]) == 1
    out = capsys.readouterr().out
    assert out.startswith("REJECT") and message in out


def test_hack_check_applies_the_bundle_limits(tmp_path, golden, monkeypatch, capsys):
    monkeypatch.setattr(bundle, "MAX_FILES", 2)
    assert cli.main(["check", str(write(tmp_path)), "--golden", str(golden)]) == 1
    assert "a bundle may hold at most 2" in capsys.readouterr().out


def test_hack_check_without_the_golden_folder_says_where_to_get_it(tmp_path):
    with pytest.raises(SystemExit, match="golden-s0.tar.gz"):
        cli.main(["check", str(write(tmp_path)), "--golden", str(tmp_path / "nowhere")])


def test_submit_refuses_locally_before_sending(tmp_path):
    sub = write(tmp_path)
    (sub / "WRITEUP.md").unlink()
    with pytest.raises(SystemExit, match="not sent:\n  problem: WRITEUP.md is missing"):
        cli.main(["--url", "http://127.0.0.1:9", "submit", str(sub)])


def test_bundles_leave_out_caches_and_links(tmp_path):
    sub = write(tmp_path)
    (sub / "__pycache__").mkdir()
    (sub / "__pycache__" / "attack.cpython-312.pyc").write_bytes(b"x")
    (sub / "agents").mkdir()
    (sub / "agents" / "s4.py").write_text("def run(inputs, ctx):\n    return {}\n")
    (sub / "link.py").symlink_to(sub / "attack.py")
    with tarfile.open(fileobj=io.BytesIO(bundle.pack(sub)), mode="r:gz") as tar:
        names = sorted(tar.getnames())
    assert names == ["hello/WRITEUP.md", "hello/agents/s4.py", "hello/attack.py", "hello/manifest.yaml"]


def test_the_team_commands_need_only_the_sdk_the_manifest_and_the_check():
    probe = ("import sys, hack.cli\n"
             "print(sorted(m for m in sys.modules if m.split('.')[0] in ('harness', 'service', 'pandas', 'numpy')))\n")
    out = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, capture_output=True, text=True, check=True,
                         env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert json.loads(out.stdout.replace("'", '"')) == ["harness", "harness.attack", "harness.hookhost",
                                                        "harness.manifest", "harness.stages", "harness.validate"]


def test_a_preview_names_its_first_live_call_in_words(capsys):
    cli._print_eval({"id": "team-01-002-preview-s0-e19908", "kind": "preview", "submission_id": "team-01-002",
                     "seed": "s0", "status": "done",
                     "preview": {"diverged_at": "S4 on_input scores_oof.csv (scores_oof.csv#1)",
                                 "first_live_call": {"call": 134, "eval": "s0/S4", "kind": "tool"},
                                 "estimated_reexecution_fraction": 0.158}})
    out = capsys.readouterr().out
    assert "first live call: S4, call 134 (a tool call)" in out
    assert cli._call({"call": 151, "eval": "s0/S5", "kind": "llm"}) == "S5, call 151 (a model call)"
    assert cli._call(None) == "none"


def test_the_team_hack_has_no_admin_commands(capsys):
    with pytest.raises(SystemExit):
        cli.main(["admin", "freeze"])
    assert "invalid choice: 'admin'" in capsys.readouterr().err
