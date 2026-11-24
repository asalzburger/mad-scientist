"""Exercise capture fidelity, privacy boundaries, restart recovery, and scope."""
import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "interaction_log.py"
spec = importlib.util.spec_from_file_location("interaction_log", MODULE_PATH)
log = importlib.util.module_from_spec(spec)
spec.loader.exec_module(log)


def row(kind, payload, timestamp="2026-11-24T09:00:00Z"):
    return {"timestamp": timestamp, "type": kind, "payload": payload}


def write_rows(path, rows, mode="w"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(mode) as out:
        for record in rows:
            out.write(json.dumps(record) + "\n")


def setup(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "codex"
    output = project / "logs"
    path = home / "sessions" / "2026" / "11" / "24" / "rollout-root.jsonl"
    write_rows(path, [row("session_meta", {"id": "root", "cwd": str(project),
                                           "base_instructions": "INTERNAL_PROMPT_SENTINEL"})])
    return project, home, output, path


def events(output, sid="root"):
    return [json.loads(line) for line in (output / "sessions" / f"{sid}.jsonl").read_text().splitlines()]


def test_visible_activity_and_exact_usage(tmp_path):
    project, home, output, path = setup(tmp_path)
    usage = {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 12,
             "reasoning_output_tokens": 5, "total_tokens": 112}
    write_rows(path, [
        row("turn_context", {"model": "test-model", "turn_id": "turn-1", "effort": "high"}),
        row("response_item", {"type": "message", "role": "user",
                              "content": [{"type": "input_text", "text": "Log this conversation."}]}),
        row("response_item", {"type": "message", "role": "assistant", "phase": "final_answer",
                              "content": [{"type": "output_text", "text": "Logging is active."}]}),
        row("response_item", {"type": "function_call", "name": "exec_command", "call_id": "call-1",
                              "arguments": "{\"cmd\":\"pwd\"}"}),
        row("response_item", {"type": "function_call_output", "call_id": "call-1", "output": "/project"}),
        row("event_msg", {"type": "item_completed", "started_at_ms": 100, "completed_at_ms": 250,
                          "item": {"type": "CommandExecution", "command": "pwd", "exit_code": 0,
                                   "aggregated_output": "/project"}}),
        row("token_usage_record", {"response_id": "response-1", "usage": usage,
                                   "thread_token_usage": usage}),
        row("event_msg", {"type": "token_count", "info": {"total_token_usage": usage}}),
    ], "a")
    collector = log.Collector(project, home, output)
    assert collector.sync() == 9
    recorded = events(output)
    assert [e["data"]["role"] for e in recorded if e["event"] == "message"] == ["user", "assistant"]
    assert next(e for e in recorded if e["event"] == "tool_result")["data"]["call_id"] == "call-1"
    assert next(e for e in recorded if e["event"] == "tokens")["data"]["usage"] == usage
    summary = json.loads((output / "summary.json").read_text())["sessions"]["root"]
    assert summary["model"] == "test-model"
    assert summary["token_usage"] == usage  # Never double-count the snapshot.
    assert collector.sync() == 0
    assert log.Collector(project, home, output).sync() == 0
    assert len(events(output)) == 9


def test_private_records_are_excluded(tmp_path):
    project, home, output, path = setup(tmp_path)
    write_rows(path, [
        row("response_item", {"type": "message", "role": "system", "content": [
            {"type": "input_text", "text": "SYSTEM_SENTINEL"}]}),
        row("response_item", {"type": "message", "role": "developer", "content": [
            {"type": "input_text", "text": "DEVELOPER_SENTINEL"}]}),
        row("response_item", {"type": "message", "role": "assistant", "channel": "analysis",
                              "content": [{"type": "output_text", "text": "ANALYSIS_SENTINEL"}]}),
        row("response_item", {"type": "reasoning", "summary": ["REASONING_SENTINEL"],
                              "encrypted_content": "ENCRYPTED_SENTINEL"}),
        row("event_msg", {"type": "item_completed", "item": {"type": "Reasoning",
                          "summary_text": "SUMMARY_SENTINEL", "raw_content": "RAW_SENTINEL"}}),
        row("world_state", {"state": "WORLD_SENTINEL"}),
    ], "a")
    log.Collector(project, home, output).sync()
    assert "SENTINEL" not in (output / "sessions" / "root.jsonl").read_text()


def test_partial_input_and_restart_checkpoint_loss(tmp_path):
    project, home, output, path = setup(tmp_path)
    collector = log.Collector(project, home, output)
    collector.sync()
    record = json.dumps(row("response_item", {"type": "custom_tool_call", "name": "example",
                                             "input": "hello"}))
    with path.open("a") as out:
        out.write(record[:30])
    assert collector.sync() == 0
    with path.open("a") as out:
        out.write(record[30:] + "\n")
    assert collector.sync() == 1
    (output / ".state" / "cursors.json").unlink()  # Append completed; checkpoint was lost.
    assert log.Collector(project, home, output).sync() == 0
    assert len(events(output)) == 2
    summary = json.loads((output / "summary.json").read_text())["sessions"]["root"]
    assert summary["events"] == {"session": 1, "tool_call": 1}


def test_crash_recovery_preserves_usage_and_repairs_partial_output(tmp_path):
    project, home, output, path = setup(tmp_path)
    write_rows(path, [row("turn_context", {"model": "test-model", "turn_id": "turn-1"}),
        row("token_usage_record", {"thread_token_usage": {"total_tokens": 100}})], "a")
    log.Collector(project, home, output).sync()
    output_path = output / "sessions" / "root.jsonl"
    original = output_path.read_bytes()
    with output_path.open("ab") as target:
        target.write(b'{"event_id": "partial')
    (output / ".state" / "cursors.json").unlink()
    assert log.Collector(project, home, output).sync() == 0
    assert output_path.read_bytes() == original
    summary = json.loads((output / "summary.json").read_text())["sessions"]["root"]
    assert summary["token_usage"] == {"total_tokens": 100}
    assert summary["model"] == "test-model"


def test_project_and_descendant_scope_with_archive_move(tmp_path):
    project, home, output, path = setup(tmp_path)
    child = home / "sessions" / "child.jsonl"
    write_rows(child, [row("session_meta", {"id": "child", "cwd": "/another-worktree",
        "source": {"subagent": {"thread_spawn": {"parent_thread_id": "root"}}}}),
        row("response_item", {"type": "custom_tool_call", "name": "test", "input": "child action"})])
    write_rows(home / "sessions" / "unrelated.jsonl", [row("session_meta", {
        "id": "unrelated", "cwd": "/unrelated-project"})])
    collector = log.Collector(project, home, output)
    assert collector.sync() == 3
    assert set(collector.state) == {"root", "child"}
    assert collector.state["child"]["parent_thread_id"] == "root"
    archive = home / "archived_sessions" / path.name
    archive.parent.mkdir()
    path.rename(archive)
    assert collector.sync() == 0
    assert len(events(output)) == 1


def test_cumulative_snapshot_fallback_stays_current(tmp_path):
    project, home, output, path = setup(tmp_path)
    write_rows(path, [row("event_msg", {"type": "token_count", "info": {
        "total_token_usage": {"total_tokens": 10}}})], "a")
    collector = log.Collector(project, home, output)
    collector.sync()
    write_rows(path, [row("event_msg", {"type": "token_count", "info": {
        "total_token_usage": {"total_tokens": 20}}})], "a")
    collector.sync()
    assert json.loads((output / "summary.json").read_text())["sessions"]["root"]["token_usage"] == {"total_tokens": 20}


def test_collector_lock_prevents_two_writers(tmp_path):
    lock = log.collector_lock(tmp_path)
    assert lock is not None
    try:
        assert log.is_running(tmp_path)
        assert log.collector_lock(tmp_path) is None
    finally:
        lock.close()
    assert not log.is_running(tmp_path)
