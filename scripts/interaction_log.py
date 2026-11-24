#!/usr/bin/env python3
"""Collect project Codex activity locally using only the Python standard library."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parents[1]
VISIBLE_PHASES = {None, "commentary", "partial_answer", "final_answer", "final"}
TOOL_TYPES = {"function_call", "function_call_output", "custom_tool_call",
              "custom_tool_call_output", "web_search_call"}
ITEM_TYPES = {"CommandExecution", "FileChange", "McpToolCall", "DynamicToolCall",
              "CollabToolCall", "WebSearch", "ImageView", "Extension"}
LIFECYCLE_TYPES = {"task_started", "task_complete", "task_completed", "turn_aborted",
                   "agent_spawned", "agent_finished", "error", "warning",
                   "model_rerouted", "session_configured"}


def now():
    return datetime.now(timezone.utc).isoformat()


def pick(value, keys):
    return {k: value[k] for k in keys if k in value}


def atomic_json(path, value):
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    temp.replace(path)


def read_json(path, fallback):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return fallback


def account_event(state, event):
    counts = state["counts"]
    counts[event["event"]] = counts.get(event["event"], 0) + 1
    if event["event"] == "tokens":
        state["latest_usage"] = event["data"].get("thread_token_usage")
    elif event["event"] == "token_snapshot":
        state["snapshot_usage"] = (event["data"].get("info") or {}).get("total_token_usage")


def parent_id(meta):
    """Handle the local rollout's nested subagent/thread_spawn source."""
    def walk(obj):
        if not isinstance(obj, dict):
            return None
        for key in ("parent_thread_id", "parentThreadId", "parent_id"):
            if isinstance(obj.get(key), str):
                return obj[key]
        return next((v for child in obj.values() if (v := walk(child))), None)
    return walk(meta.get("source")) or walk(meta.get("thread_source"))


def normalize(row, context):
    """Allowlist visible activity; never copy internal prompts or reasoning."""
    kind = row.get("type")
    p = row.get("payload", {})
    subtype = p.get("type")
    data = None
    event = None
    if kind == "session_meta":
        context["session_id"] = p.get("id")
        data = pick(p, ("id", "session_id", "timestamp", "cwd", "originator",
                        "cli_version", "model_provider", "forked_from_id"))
        data["parent_thread_id"] = parent_id(p)
        event = "session"
    elif kind == "turn_context":
        context.update({"model": p.get("model"), "turn_id": p.get("turn_id")})
        data = pick(p, ("turn_id", "root_turn_id", "model", "effort", "cwd"))
        event = "model"
    elif kind == "token_usage_record":
        data = pick(p, ("thread_id", "session_id", "turn_id", "root_turn_id",
                        "response_id", "usage", "turn_token_usage", "thread_token_usage"))
        event = "tokens"
    elif kind == "response_item" and subtype == "message":
        role = p.get("role")
        if role not in {"user", "assistant"} or p.get("phase") not in VISIBLE_PHASES:
            return None
        if p.get("channel") in {"analysis", "justify", "confidence"}:
            return None
        content = []
        for part in p.get("content", []):
            if part.get("type") in {"input_text", "output_text", "text"}:
                content.append({"type": "text", "text": part.get("text", "")})
            else:
                # Record attachment presence, without duplicating binary media.
                content.append({"type": part.get("type"), "media": "not_copied"})
        data = {"role": role, "phase": p.get("phase"), "content": content}
        event = "message"
    elif kind == "response_item" and subtype in TOOL_TYPES:
        data = pick(p, ("type", "id", "call_id", "name", "arguments", "input",
                        "output", "status", "action"))
        event = "tool_result" if subtype.endswith("output") else "tool_call"
    elif kind == "event_msg" and subtype == "token_count":
        data = pick(p, ("info", "rate_limits"))
        event = "token_snapshot"
    elif kind == "event_msg" and subtype == "item_completed":
        item = p.get("item", {})
        item_type = item.get("type", "")
        if item_type in ITEM_TYPES or item_type.startswith("Collab"):
            data = pick(p, ("thread_id", "turn_id", "started_at_ms", "completed_at_ms"))
            data["item"] = item
            event = "action_completed"
        elif item_type in {"UserMessage", "AgentMessage"}:
            # Text is captured from response_item; keep only timing here.
            data = pick(p, ("thread_id", "turn_id", "started_at_ms", "completed_at_ms"))
            data["item"] = pick(item, ("id", "type", "phase"))
            event = "message_timing"
    elif kind == "event_msg" and (subtype in LIFECYCLE_TYPES or
                                  str(subtype).startswith("collab_")):
        data = pick(p, ("type", "turn_id", "root_turn_id", "started_at", "completed_at",
                        "call_id", "sender_thread_id", "receiver_thread_id",
                        "receiver_thread_ids", "new_thread_id", "agent_id", "status",
                        "prompt", "message", "error", "reason", "from_model", "to_model"))
        event = "lifecycle"
    if event is None:
        # Unknown schemas stay visible as metadata, without copying their contents.
        event = "record_omitted"
        data = {"record_type": kind, "payload_type": subtype,
                "reason": "internal_or_unsupported_record"}
    return {"schema_version": 1, "timestamp": row.get("timestamp"),
            "session_id": context.get("session_id"), "turn_id": context.get("turn_id"),
            "model": context.get("model"), "event": event, "data": data}


class Collector:
    def __init__(self, project, codex_home, output):
        self.project = project.resolve()
        self.codex_home = codex_home
        self.output = output
        self.state_dir = output / ".state"
        self.sessions_dir = output / "sessions"
        for path in (output, self.state_dir, self.sessions_dir):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state_path = self.state_dir / "cursors.json"
        self.state = read_json(self.state_path, {})
        self.seen = {}
        self.metadata = {}

    def discover(self):
        candidates = {}
        for name in ("sessions", "archived_sessions"):
            for path in (self.codex_home / name).rglob("*.jsonl"):
                if path not in self.metadata:
                    try:
                        with path.open("rb") as source:
                            first = source.readline()
                        row = json.loads(first)
                    except (OSError, ValueError):
                        continue  # A newly created file may not have its first line yet.
                    if row.get("type") != "session_meta":
                        continue
                    meta = row["payload"]
                    # Cache only identity and scope, never internal instruction contents.
                    self.metadata[path] = {"id": meta.get("id"), "cwd": meta.get("cwd"),
                                           "parent": parent_id(meta)}
                meta = self.metadata[path]
                sid = meta.get("id")
                if not isinstance(sid, str) or not sid or Path(sid).name != sid or sid in {".", ".."}:
                    continue
                candidates[sid] = (path, meta)
        selected = {sid for sid, (_, m) in candidates.items()
                    if m.get("cwd") and Path(m["cwd"]).resolve() == self.project}
        while True:
            expanded = selected | {sid for sid, (_, m) in candidates.items()
                                   if m.get("parent") in selected}
            if expanded == selected:
                break
            selected = expanded
        return [(sid, *candidates[sid]) for sid in sorted(selected)]

    def known_events(self, sid):
        if sid not in self.seen:
            ids = set()
            # The durable event log is authoritative if a checkpoint was lost.
            state = self.state[sid]
            state["counts"] = {}
            state.pop("latest_usage", None)
            state.pop("snapshot_usage", None)
            path = self.sessions_dir / f"{sid}.jsonl"
            if path.exists():
                with path.open("rb+") as src:
                    while True:
                        offset = src.tell()
                        line = src.readline()
                        if not line:
                            break
                        if not line.endswith(b"\n"):
                            # Repair only an incomplete final write after a crash.
                            src.truncate(offset)
                            break
                        event = json.loads(line)
                        ids.add(event["event_id"])
                        account_event(state, event)
            self.seen[sid] = ids
        return self.seen[sid]

    def sync(self):
        added = 0
        for sid, path, meta in self.discover():
            state = self.state.setdefault(sid, {"offset": 0, "line": 0,
                                                "context": {}, "counts": {}})
            known = self.known_events(sid)
            if path.stat().st_size < state["offset"]:
                # Re-read safely; content-derived IDs suppress previously collected rows.
                state.update(offset=0, line=0, context={})
            with path.open("rb") as source, (self.sessions_dir / f"{sid}.jsonl").open("ab") as target:
                source.seek(state["offset"])
                while True:
                    start = source.tell()
                    line = source.readline()
                    if not line or not line.endswith(b"\n"):
                        break
                    state["line"] += 1
                    try:
                        row = json.loads(line)
                        event = normalize(row, state["context"])
                    except (ValueError, TypeError, AttributeError) as exc:
                        event = {"schema_version": 1, "timestamp": None, "session_id": sid,
                                 "model": None, "turn_id": None, "event": "parse_error",
                                 "data": {"error_type": type(exc).__name__}}
                    state["offset"] = source.tell()
                    if event is None:
                        continue
                    event_id = hashlib.sha256(sid.encode() + b":" + line).hexdigest()
                    if event_id in known:
                        continue
                    event.update(event_id=event_id, collected_at=now(),
                                 source={"file": str(path), "line": state["line"], "offset": start})
                    target.write((json.dumps(event, ensure_ascii=False) + "\n").encode())
                    known.add(event_id)
                    added += 1
                    account_event(state, event)
                target.flush()
                os.fsync(target.fileno())
            state["source"] = str(path)
            state["parent_thread_id"] = meta.get("parent")
        atomic_json(self.state_path, self.state)
        atomic_json(self.output / "summary.json", {
            "updated_at": now(), "project": str(self.project),
            "sessions": {sid: {"model": s["context"].get("model"),
                                "parent_thread_id": s.get("parent_thread_id"),
                                "token_usage": s.get("latest_usage") or s.get("snapshot_usage"),
                                "events": s["counts"]} for sid, s in self.state.items()},
            "limits": ["Only activity persisted by Codex is available.",
                       "Private reasoning and internal instructions are excluded.",
                       "Binary attachments are represented by type, not copied.",
                       "Token usage is reported by the runtime, not per-tool estimates.",
                       "Unknown record schemas are logged as metadata only."]})
        return added


def collector_lock(output):
    path = output / ".state"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (path / "collector.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return None
    return lock


def is_running(output):
    lock = collector_lock(output)
    if lock is None:
        return True
    lock.close()
    return False


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "watch", "sync", "status", "stop"))
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--codex-home", type=Path,
                        default=Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")
    output = (args.output or args.project / "logs" / "interactions").resolve()
    state_dir = output / ".state"
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    stop = state_dir / "stop"
    if args.command == "status":
        print(json.dumps({"running": is_running(output), "output": str(output),
                          "watcher": read_json(state_dir / "watcher.json", None),
                          "summary": read_json(output / "summary.json", None)}, indent=2))
        return
    if args.command == "stop":
        stop.touch()
        print("Stop requested; collected logs are retained.")
        return
    if args.command == "start":
        if is_running(output):
            print(f"Collector already running: {output}")
            return
        stop.unlink(missing_ok=True)
        command = [sys.executable, str(Path(__file__).resolve()), "watch", "--project",
                   str(args.project.resolve()), "--codex-home", str(args.codex_home.resolve()),
                   "--output", str(output), "--interval", str(args.interval)]
        with (state_dir / "watcher.log").open("ab") as log:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                     start_new_session=True, close_fds=True)
        for _ in range(100):
            if child.poll() is not None:
                raise SystemExit(f"Collector exited; inspect {state_dir / 'watcher.log'}")
            if is_running(output) and (output / "summary.json").exists():
                print(f"Collector running (PID {child.pid}): {output}")
                return
            time.sleep(0.1)
        raise SystemExit("Collector started but is still initializing; run status.")
    lock = collector_lock(output)
    if lock is None:
        print("Collector is already active; it will sync automatically.")
        return
    try:
        collector = Collector(args.project, args.codex_home, output)
        if args.command == "sync":
            print(f"Collected {collector.sync()} new events into {output}")
            return
        started = now()
        while not stop.exists():
            added = collector.sync()
            atomic_json(state_dir / "watcher.json", {"pid": os.getpid(), "started_at": started,
                                                     "heartbeat": now(), "last_added": added})
            time.sleep(args.interval)
    finally:
        lock.close()


if __name__ == "__main__":
    main()
