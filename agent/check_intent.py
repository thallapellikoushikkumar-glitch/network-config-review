"""
Ask a fresh, non-interactive Claude Code session (your existing subscription,
not a paid API key) to verify a plain-English network intent against the
real Batfish server, by writing and running its own pybatfish query.

Usage:
    .venv\\Scripts\\python.exe agent\\check_intent.py "branch-01 LAN should reach 10.2.2.20 on UDP 514"
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPT_TEMPLATE = ROOT / "agent" / "check_prompt.md"


def build_prompt(intent: str) -> str:
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    return template.replace("{{INTENT}}", intent)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit('Usage: check_intent.py "your plain-English intent"')

    intent = " ".join(sys.argv[1:])
    prompt = build_prompt(intent)

    result = subprocess.run(
        [
            "claude",
            "-p",
            prompt,
            "--permission-mode",
            "dontAsk",
            "--allowedTools",
            "Bash",
        ],
        cwd=str(ROOT),
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
