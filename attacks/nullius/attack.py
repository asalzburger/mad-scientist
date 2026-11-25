"""Replace S3's planner and implementer with a fixed linear-model protocol."""

import json

from harness.attack import AgentPolicy, Attack, read_asset


class Nullius(Attack):
    def replace_agent(self, stage, ctx):
        if stage != "S3":
            return None

        config = json.loads(read_asset("assets/protocol.json"))
        protocol = (read_asset("assets/protocol.md").rstrip()
                    + "\n\nExact numerical configuration:\n```json\n"
                    + json.dumps(config, indent=2, sort_keys=True) + "\n```\n")
        return AgentPolicy.llm(prompts={
            "Researcher": read_asset("assets/researcher.md").rstrip() + "\n\n" + protocol,
            "Coder": read_asset("assets/coder.md").rstrip() + "\n\n" + protocol,
        })
