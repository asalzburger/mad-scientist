"""One local model call. Not a pipeline run and not a hack preview.

Replays the first S2 Researcher request from the golden trace, with the
human1 note inserted into the brief the way on_context does, and prints
the reply. The key stays in the environment (hacktoken).
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRACE = ROOT / "golden/s0/S2/trace/trace.jsonl"
BRIEF = ROOT / "golden/s0/S2/task/brief.txt"
ATTACK = ROOT / "attacks/human1/attack.py"


def note() -> str:
    text = ATTACK.read_text()
    start = text.index('NOTE = """') + len('NOTE = """')
    return text[start:text.index('"""', start)]


def first_request() -> dict:
    record = json.loads(TRACE.open().readline())
    request = record["request"] | {"model": os.environ["LLM_MODEL"]}
    for key in ("seed", "reasoning_effort"):
        request.pop(key, None)
    brief = BRIEF.read_text().rstrip("\n")
    amended = brief + "\n" + note()
    for msg in request["messages"]:
        content = msg.get("content")
        if isinstance(content, str) and brief in content:
            msg["content"] = content.replace(brief, amended, 1)
    return request


def reply_text(message: dict) -> str:
    lines = []
    if message.get("content"):
        lines.append(message["content"])
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        lines.append(f"tool {fn.get('name')} {fn.get('arguments')}")
    if message.get("reasoning_content"):
        lines.append("reasoning: " + message["reasoning_content"][:1200])
    return "\n".join(lines) if lines else "(empty reply)"


def main() -> int:
    missing = [name for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL") if not os.environ.get(name)]
    if missing:
        sys.exit("missing " + ", ".join(missing) + " — run hacktoken in this terminal first")
    if not TRACE.is_file():
        sys.exit(f"missing {TRACE}")

    request = first_request()
    url = os.environ["LLM_BASE_URL"].rstrip("/") + "/chat/completions"
    post = urllib.request.Request(
        url,
        data=json.dumps(request).encode(),
        headers={"Authorization": f"Bearer {os.environ['LLM_API_KEY']}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(post, timeout=600) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        sys.exit(f"model request failed: {exc.code} {exc.read().decode()[:2000]}")

    print(body["choices"][0]["message"] and reply_text(body["choices"][0]["message"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
