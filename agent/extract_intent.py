"""
Read whatever is currently uncommitted in configs/vars/*.yml (vs the last
git commit) and extract the intent the human who made the change already
wrote down — nothing is guessed or inferred.

Two ways to state intent, both written directly in the YAML by whoever
makes the change, right next to what they changed:

  1. An explicit tag:      ip: 172.16.14.2   # intent: fix the wrong subnet
  2. A Cisco ACL remark:   - "remark allow syslog from branch LAN"
                           - "permit udp ... eq 514"

Works on any field, not just ACLs, since it reads the actual comment text
in the git diff rather than the parsed YAML structure. If a change has
neither, it is reported as having no stated intent - nothing is guessed
in its place.

Usage:
    .venv\\Scripts\\python.exe agent\\extract_intent.py
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VARS_DIR = ROOT / "configs" / "vars"

INTENT_TAG_RE = re.compile(r"#\s*intent:\s*(.+)\s*$", re.IGNORECASE)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(ROOT), capture_output=True, text=True
    )
    return result.stdout


def changed_vars_files() -> list[Path]:
    status = git("status", "--porcelain", "--", str(VARS_DIR))
    paths = []
    for line in status.splitlines():
        rel = line[3:].strip()
        if rel.endswith(".yml"):
            paths.append(ROOT / rel)
    return paths


def extract_intents(path: Path) -> list[dict]:
    rel = path.relative_to(ROOT).as_posix()
    diff = git("diff", "-U0", "HEAD", "--", rel)
    if not diff.strip():
        diff = git("diff", "--cached", "-U0", "HEAD", "--", rel)

    findings: list[dict] = []
    pending_intent: str | None = None
    block_lines: list[str] = []

    def flush_block():
        nonlocal pending_intent, block_lines
        if block_lines:
            findings.append({
                "lines": list(block_lines),
                "intent": pending_intent,
            })
        pending_intent = None
        block_lines = []

    for line in diff.splitlines():
        if line.startswith(("+++", "---", "diff ", "index ")):
            continue
        if line.startswith("@@"):
            flush_block()  # a new hunk = a new, unrelated change location
            continue
        if not line.startswith("+"):
            continue

        content = line[1:]
        stripped = content.strip()

        tag_match = INTENT_TAG_RE.search(content)
        if tag_match:
            intent_text = tag_match.group(1).strip()
            data_part = content[:tag_match.start()].strip()
            if data_part:
                # inline: the tag shares a line with the actual changed data
                flush_block()
                pending_intent = intent_text
                block_lines.append(data_part)
                flush_block()
            else:
                # standalone comment line - applies to the lines that follow
                flush_block()
                pending_intent = intent_text
            continue

        if stripped.lower().startswith("- \"remark") or stripped.lower().startswith("remark"):
            flush_block()
            pending_intent = re.sub(r'^[-"\s]*remark\s*', "", stripped, flags=re.IGNORECASE).rstrip('"')
            continue

        if not stripped or stripped.startswith("#"):
            continue  # a plain comment with no intent tag - not attributable

        block_lines.append(stripped)

    flush_block()
    return findings


def main() -> None:
    files = changed_vars_files()
    if not files:
        print("No uncommitted changes in configs/vars/ - nothing to extract.")
        return

    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        findings = extract_intents(path)
        if not findings:
            print(f"{rel}: changed, but no data lines detected (formatting only?).")
            continue

        print(f"\n=== {rel} ===")
        for f in findings:
            if f["intent"]:
                print(f'[stated] intent: {f["intent"]}')
            else:
                print("[unstated] no intent written for this change")
            for line in f["lines"]:
                print(f"    changed: {line}")


if __name__ == "__main__":
    main()
