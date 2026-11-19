"""hack: the teams' command line.

    hack check <folder>             # free and local: the checks every eval starts with, on s0's golden run
    export HACK_URL=https://<service>  HACK_TOKEN=<your team's token>
    hack preview <folder>           # free: where the attack begins and what a live eval would cost
    hack submit <folder>            # a live eval on the public seed (counts against the cap)
    hack status [<eval id>]         # your submissions and evals, or one eval's result
    hack trace <eval id> [-o file]  # save an eval's trace viewer page
    hack finalists <submission id>...   # designate up to 3 finalists before the freeze
    hack leaderboard
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from hack.bundle import pack, size_problems, static_check
from harness.manifest import load as load_manifest
from harness.validate import check as validate_check
from harness.validate import format_check, local_host

ROOT = Path(__file__).resolve().parents[1]
OPEN_TARGETS = ("n_excess",)  # the track open at the event
LIVE_SEED = "s0"  # the public seed: live evals, previews and hack check run on it
GOLDEN = "golden"  # at the repository's root: <seed>/ (the golden run) and seeds/<seed>/ (full-column files)


class Client:
    def __init__(self, url: str, token: str | None):
        self.url, self.token = url.rstrip("/"), token

    def call(self, method: str, path: str, body: bytes | None = None, content_type: str = "application/json",
             raw: bool = False) -> Any:
        req = urllib.request.Request(self.url + path, data=body, method=method)
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        if body is not None:
            req.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            try:
                detail = json.loads(detail).get("detail", detail)
            except ValueError:
                pass
            raise SystemExit(f"refused ({e.code}): {detail if isinstance(detail, str) else json.dumps(detail, indent=2)}")
        except urllib.error.URLError as e:
            raise SystemExit(f"cannot reach {self.url}: {e.reason}")
        return data.decode() if raw else json.loads(data)


def _print_eval(ev: dict[str, Any]) -> None:
    print(f"{ev['id']}  {ev['kind']} of {ev.get('submission_id')} on {ev['seed']}: {ev['status']}")
    check = ev.get("check") or {}
    for p in check.get("problems") or []:
        print(f"  problem: {p}")
    for w in check.get("warnings") or []:
        print(f"  warning: {w}")
    if ev.get("error"):
        print(f"  {ev['error']}")
    if ev.get("preview"):
        p = ev["preview"]
        print(f"  attack begins at: {p.get('diverged_at')}")
        print(f"  first call that needs inference: {p.get('first_live_call')}")
        print(f"  estimated live share of a full eval: {p.get('estimated_reexecution_fraction')}")
        if p.get("attack_error"):
            print(f"  the attack failed: {p['attack_error']}")
        diff = p.get("diff") or {}
        if diff.get("diff"):
            print(f"  that request against the nearest golden request (first difference at message "
                  f"{diff.get('first_difference')}):")
            print("    " + diff["diff"].replace("\n", "\n    "))
    if ev.get("result"):
        r = ev["result"]
        print(f"  {r['status']}; pull vs honest {r['pull_vs_honest']}; suspicion {r['suspicion']} "
              f"(threshold {r['threshold']}); detected {r['detected']}")
        if r.get("gate_on_mean") is not None:
            print(f"  valid if the mean pull over the scoring seeds, in the declared direction, exceeds "
                  f"{r['gate_on_mean']:.2f}")
        for why in r.get("why_not_usable") or []:
            print(f"  not usable: {why}")
        print(f"  first live call {r['first_live_call']}; cache {r['cache']}; tokens {r['tokens_used']}; "
              f"{r['runtime_min']} min")


def local_problems(folder: Path) -> list[str]:
    """What the service would refuse before queueing, short of the token's team and the open tracks."""
    if not folder.is_dir():
        return [f"{folder} is not a folder"]
    _, problems = static_check(folder, None, OPEN_TARGETS)
    return [p for p in problems if not p.startswith("target ")] + size_problems(folder)


def check(folder: Path, golden: Path) -> dict[str, Any]:
    """hack check: the service's static checks and the validator's, with the hooks run as a plain
    subprocess (no sandbox) on the public seed's golden run."""
    run = golden / LIVE_SEED
    if not (run / "run.json").is_file():
        raise SystemExit(f"no golden run at {run}: download golden-{LIVE_SEED}.tar.gz from the repository's "
                         f"release and unpack it at the repository's root (docs/submitting.md)")
    submission = folder.resolve()
    manifest, _ = load_manifest(submission)
    shared = manifest.shared if manifest else {}
    report = validate_check(submission, run, lambda: local_host(submission, shared), seeds_dir=golden / "seeds")
    _, static = static_check(submission, None, OPEN_TARGETS)
    extra = [p for p in static + size_problems(submission) if p not in report["problems"]]
    report["problems"] += extra
    report["verdict"] = "reject" if report["problems"] else "pass"
    return report


def parser() -> tuple[argparse.ArgumentParser, Any]:
    """The team commands' parser and its subparsers, which the organizers' hack extends."""
    ap = argparse.ArgumentParser(prog="hack", description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="\n".join(__doc__.splitlines()[2:]))
    ap.add_argument("--url", default=os.environ.get("HACK_URL", "http://localhost:8000"))
    ap.add_argument("--token", default=os.environ.get("HACK_TOKEN"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    ch = sub.add_parser("check", help="run the free checks locally on the public seed's golden run")
    ch.add_argument("folder", type=Path)
    ch.add_argument("--golden", type=Path, default=Path(os.environ.get("HACK_GOLDEN", ROOT / GOLDEN)),
                    help=f"the unpacked golden folder (default: {GOLDEN}/ at the repository's root)")
    ch.add_argument("--json", type=Path, help="also write the report here")
    for name, text in (("submit", "a live eval on the public seed; counts against the cap"),
                       ("preview", "free: where the attack begins and what a live eval would cost")):
        sub.add_parser(name, help=text).add_argument("folder", type=Path)
    st = sub.add_parser("status", help="your submissions and evals, or one eval's result")
    st.add_argument("eval_id", nargs="?")
    tr = sub.add_parser("trace", help="save an eval's trace viewer page")
    tr.add_argument("eval_id")
    tr.add_argument("-o", "--out", type=Path)
    fi = sub.add_parser("finalists", help="designate up to 3 finalists before the freeze")
    fi.add_argument("submission_ids", nargs="+")
    sub.add_parser("leaderboard", help="the public leaderboard")
    return ap, sub


def run(args: argparse.Namespace) -> int:
    """Runs one team command."""
    if args.cmd == "check":
        report = check(args.folder, args.golden)
        print(format_check(report))
        if args.json:
            args.json.write_text(json.dumps(report, indent=2) + "\n")
        if report["verdict"] == "pass":
            print(f"next: hack preview {args.folder}")
        return 0 if report["verdict"] == "pass" else 1

    c = Client(args.url, args.token)
    if args.cmd in ("submit", "preview"):
        problems = local_problems(args.folder)
        if problems:
            raise SystemExit("not sent:\n" + "\n".join(f"  problem: {p}" for p in problems))
        out = c.call("POST", f"/api/submissions?preview={'true' if args.cmd == 'preview' else 'false'}",
                     pack(args.folder), "application/gzip")
        print(f"submission {out['submission']['id']} ({out['submission']['name']})")
        _print_eval(out["eval"])
    elif args.cmd == "status":
        if args.eval_id:
            _print_eval(c.call("GET", f"/api/evals/{args.eval_id}"))
        else:
            s = c.call("GET", "/api/status")
            print(f"team {s['team']}" + ("; frozen" if s["frozen"] else "") + ("; revealed" if s["revealed"] else ""))
            for ev in s["evals"]:
                _print_eval(ev)
            for sid, p in s["scoring_seed_progress"].items():
                print(f"{sid} on the scoring seeds: {p['done']} done, {p['queued_or_running']} queued or running")
            print(f"finalists: {', '.join(s['finalists']) or 'none'}")
    elif args.cmd == "trace":
        page = c.call("GET", f"/api/evals/{args.eval_id}/trace", raw=True)
        out = args.out or Path(f"{args.eval_id}.html")
        out.write_text(page, encoding="utf-8")
        print(f"wrote {out}")
    elif args.cmd == "finalists":
        print(c.call("PUT", "/api/finalists", json.dumps({"submissions": args.submission_ids}).encode()))
    elif args.cmd == "leaderboard":
        board = c.call("GET", "/api/leaderboard")
        for name, t in board["tracks"].items():
            print(f"== {name} (live on {t['live_seed']})")
            for i, r in enumerate(t["rows"], 1):
                b, f = r["best"], r.get("final")
                best = f"{b['name']}: pull {b['pull']:.2f}, detected {b['detected']}" if b else "none yet"
                final = (f"; final {f['submission_id']}: {f['effect']:.2f} (mean {f['mean_effect']:.2f}, "
                         f"{'valid' if f['valid'] else 'not valid'}), undetected {f['undetected_fraction']:.0%} "
                         f"({f['scored']})") if f else ""
                print(f"{i:2}. {r['team']:<12} {best}; live {r['live_used']}/{r['cap']}; "
                      f"scoring seeds {r['scoring_seeds_done'] or '-'}{final}")
    else:
        raise SystemExit(f"unknown command {args.cmd}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap, _ = parser()
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
