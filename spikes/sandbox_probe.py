"""M0 spike 1: whether the Bash sandbox blocks egress on this runner.

One short agent turn with the Builder's own options, except that the gate
lets the command through: the model runs one command that tries curl and a
plain socket, and the probe prints what came back. Costs a few cents on the
triage model. Pass: `curl_exit` is not 0, `socket_ok` is absent, and the run
ends with subtype `success`.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import ResultMessage, ToolResultBlock, UserMessage, query

from guildkit import agents

COMMAND = (
    "curl -sS -m 10 -o /dev/null -w '%{http_code}' https://example.com;"
    ' echo " curl_exit=$?";'
    " python3 -c \"import socket; socket.create_connection(('example.com', 443), 5);"
    " print('socket_ok')\" 2>&1 | tail -1"
)
PROMPT = (
    "Run exactly this command with the Bash tool, once, then reply with the"
    " tool's complete output and nothing else:\n" + COMMAND
)


class ProbeGate(agents.Gate):
    """The Builder's gate, with the command patterns lifted for Bash."""

    def reason(self, tool: str, tool_input: dict[str, Any]) -> str | None:
        """Let any Bash command run; the sandbox is what is under test."""
        if tool == "Bash":
            return None
        return super().reason(tool, tool_input)


async def main(model: str) -> int:
    """Run the probe and return 0 when the sandbox blocked both connections."""
    with tempfile.TemporaryDirectory(prefix="spike-") as tmp:
        root = Path(tmp) / "checkout"
        root.mkdir()
        gate = ProbeGate(root, role="builder", reject=[])
        options = agents.options(
            root=root,
            config_dir=Path(tmp) / "cfg",
            system_prompt="You run one command and report its output verbatim.",
            role="builder",
            model=model,
            max_turns=3,
            cap_usd=0.05,
            effort="low",
            gate=gate,
        )
        outputs: list[str] = []
        subtype = "no_result"
        async for message in query(prompt=PROMPT, options=options):
            if isinstance(message, UserMessage) and isinstance(message.content, list):
                for block in message.content:
                    if isinstance(block, ToolResultBlock):
                        outputs.append(str(block.content))
            elif isinstance(message, ResultMessage):
                subtype = message.subtype
    text = "\n".join(outputs)
    print(f"subtype={subtype} denials={len(gate.denied)}")
    print("tool output:")
    print(text or "(none)")
    blocked = "curl_exit=0" not in text and "socket_ok" not in text
    print("verdict:", "blocked" if blocked and subtype == "success" else "NOT blocked")
    return 0 if blocked and subtype == "success" else 1


if __name__ == "__main__":
    sys.exit(
        asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "claude-haiku-5-5"))
    )
