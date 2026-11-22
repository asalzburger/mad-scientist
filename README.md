# mad-scientist

Mad Scientist is a science-sabotage hackathon built around red-teaming a modified Agents of
Discovery (AoD), a recently proposed multi-agent pipeline for analyses in high-energy physics.
Teams attack AoD running its original task, an honest anomaly-detection analysis of the LHC
Olympics R&D data, split here into five stages. The goal is to move the reported signal excess
as far as you can, in a direction you declare, without the pipeline's checks catching you.

This repository is what a team needs to write, check and submit attacks. The pipeline itself runs
on the event service: you send it attacks with the `hack` command.

## Start here

| Read | For |
| --- | --- |
| `docs/handbook.md` | The rules, the schedule, how attacks are scored and detected, and the limits |
| `docs/submitting.md` | Setting up, `hack check`, previews, live evals and reading results |
| `docs/attack.md` | What an attack is, what makes one succeed, and the four hooks by example |
| `docs/hook_api.md` | The hooks, `ctx`, replacing a stage, and `manifest.yaml` |
| `docs/stages.md` | What each of the five stages reads, writes and is told |
| `docs/faq.md` | Common questions |
| `template/hello_world/` | The smallest complete submission |
| `examples/` | Worked attacks, and one small demo per hook kind |

## Quick start

You need Python 3.11 or later. Check first:

```bash
python3 -c 'import sys; assert sys.version_info >= (3, 11), sys.version'   # prints nothing if new enough
```

If it fails (macOS's own `python3` is 3.9), install a newer Python and use it by name in the
`venv` line below, for example `python3.12 -m venv .venv` (`docs/submitting.md`, "Set up").

```bash
git clone https://github.com/nsurijr/mad-scientist.git && cd mad-scientist
python3 -m venv .venv && . .venv/bin/activate
pip install --upgrade pip && pip install -e '.[dev]'
curl -fLO https://github.com/nsurijr/mad-scientist/releases/latest/download/golden-s0.tar.gz
tar xzf golden-s0.tar.gz                  # s0's honest golden run, for hack check

mkdir -p attacks && cp -r template/hello_world attacks/hello   # then set your team's name in its manifest.yaml
hack check attacks/hello                  # free and local

export HACK_URL=https://<the service's address> HACK_TOKEN=<your team's token>
hack preview attacks/hello                # free: where the attack begins, and what it would cost
hack submit attacks/hello                 # a live eval on s0
hack status
```

If `curl` stops with an error, download `golden-s0.tar.gz` from the repository's Releases page
instead, then unpack it as above.

If `hack` stops with `SSL: CERTIFICATE_VERIFY_FAILED`, your Python can't find its root
certificates. With a Python from python.org on macOS, run its `Install Certificates.command` once
(for example `open "/Applications/Python 3.12/Install Certificates.command"`, matching your
version). Otherwise, run `pip install certifi` in the venv, then
`export SSL_CERT_FILE="$(python -m certifi)"`.

## Layout

| Path | What it holds |
| --- | --- |
| `harness/attack.py` | The hook interface: `Attack`, `ctx`, `AgentPolicy` and the helpers |
| `harness/` | Also the hook host and the scripted-replacement runner (the same files the eval's sandbox runs), the manifest schema, and the local check |
| `hack/` | The `hack` command |
| `pipeline/stages/` | What each stage is told: the briefs, the re-prompt and S5's numeric questions |
| `pipeline/aod/` | Agents of Discovery's source, for reading: the agents, their prompts and their tools |
| `template/hello_world/` | A complete submission to copy |
| `examples/` | Worked attacks and hook demos |
| `tests/` | The repository's tests (`pytest -q`) |
| `golden/` | s0's golden run, once you unpack it (not in git) |

`EXPORTED_FROM` names the version of the event's code this copy was made from.
