# The pipeline, for reading

These files are here so you can read exactly what the pipeline's agents are told and can do. The
event service runs its own copy, so editing them here changes nothing in an eval.

- `stages/`: each stage's brief (`S1_data_prep.txt` … `S5_report.txt`), the re-prompt a Researcher
  gets after a reply without a tool call (`reprompt.txt`), and S5's numeric questions. The runner
  fills in `{n_data}`, `{n_reference}` and `{n_rows}` per seed. To change what a stage is told, use
  `on_context`.
- `aod/`: Agents of Discovery's source. The roles' system prompts are in `aod/ai_agent/agents/`,
  the tools in `aod/ai_agent/tools/`, and `aod/README.md` lists what was changed from upstream AoD to
  run it here. To change a role's prompt, replace it with `AgentPolicy.llm`.

`docs/stages.md` describes the stages.
