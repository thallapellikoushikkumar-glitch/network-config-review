"""
Look at whatever is currently uncommitted in configs/vars/*.yml (compared to
the last git commit) and infer, as best it can, what each change was trying
to do — without a human typing an intent sentence.

Two confidence levels are reported, deliberately kept distinct:
  - "stated"   -> a `remark` line right next to an added/changed ACL rule.
                  This is a real, human-written statement of intent, just
                  not typed into this tool directly.
  - "inferred" -> no remark/comment anywhere nearby. This is a structural
                  description of what changed, not a known intent — it
                  could be wrong about *why* the change was made.

Usage:
    .venv\\Scripts\\python.exe agent\\infer_intent.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
VARS_DIR = ROOT / "configs" / "vars"


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


def load_old_version(path: Path) -> dict | None:
    rel = path.relative_to(ROOT).as_posix()
    text = subprocess.run(
        ["git", "show", f"HEAD:{rel}"], cwd=str(ROOT), capture_output=True, text=True
    )
    if text.returncode != 0:
        return None  # file didn't exist at HEAD (newly added)
    return yaml.safe_load(text.stdout) or {}


def find_remark_for(lines: list[str], target_index: int) -> str | None:
    for i in range(target_index - 1, -1, -1):
        if lines[i].strip().lower().startswith("remark"):
            return lines[i].strip()[len("remark"):].strip()
        if lines[i].strip().lower().startswith(("permit", "deny")):
            break  # hit the previous rule with no remark of its own
    return None


def diff_acls(old: dict, new: dict) -> list[dict]:
    findings = []
    old_acls = {a["name"]: a for a in old.get("acls", [])}
    new_acls = {a["name"]: a for a in new.get("acls", [])}

    for name, new_acl in new_acls.items():
        old_lines = old_acls.get(name, {}).get("lines", [])
        new_lines = new_acl.get("lines", [])
        added = [l for l in new_lines if l not in old_lines]
        for line in added:
            if line.strip().lower().startswith(("permit", "deny")):
                idx = new_lines.index(line)
                remark = find_remark_for(new_lines, idx)
                if remark:
                    findings.append({
                        "confidence": "stated",
                        "summary": f'ACL "{name}": new rule `{line.strip()}`',
                        "intent": remark,
                    })
                else:
                    findings.append({
                        "confidence": "inferred",
                        "summary": f'ACL "{name}": new rule `{line.strip()}` (no remark present)',
                        "intent": f"a new rule was added to {name} with no stated reason — best guess: allow/deny the traffic this line literally describes",
                    })
    return findings


def diff_scalar_fields(old: dict, new: dict, path: str = "") -> list[dict]:
    findings = []
    if isinstance(new, dict):
        for key, new_val in new.items():
            if key == "acls":
                continue  # handled separately, with remark lookup
            old_val = old.get(key) if isinstance(old, dict) else None
            sub_path = f"{path}.{key}" if path else key
            if isinstance(new_val, (dict, list)):
                findings.extend(diff_scalar_fields(old_val, new_val, sub_path))
            elif new_val != old_val:
                findings.append({
                    "confidence": "inferred",
                    "summary": f"{sub_path}: `{old_val}` -> `{new_val}`",
                    "intent": f"no remark/comment available — this is a structural field change only, purpose unknown",
                })
    elif isinstance(new, list):
        old_by_name = {}
        if isinstance(old, list):
            for item in old:
                if isinstance(item, dict) and "name" in item:
                    old_by_name[item["name"]] = item
        for item in new:
            if isinstance(item, dict) and "name" in item:
                old_item = old_by_name.get(item["name"], {})
                findings.extend(diff_scalar_fields(old_item, item, f"{path}[{item['name']}]"))
    return findings


def main() -> None:
    files = changed_vars_files()
    if not files:
        print("No uncommitted changes in configs/vars/ — nothing to infer.")
        return

    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        old = load_old_version(path)
        if old is None:
            print(f"{rel}: new file, no previous version to diff against — skipping inference.")
            continue
        new = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

        findings = diff_acls(old, new) + diff_scalar_fields(old, new)
        if not findings:
            print(f"{rel}: changed, but no field-level difference detected (formatting only?).")
            continue

        print(f"\n=== {rel} ===")
        for f in findings:
            print(f"[{f['confidence']}] {f['summary']}")
            print(f"    intent: {f['intent']}")


if __name__ == "__main__":
    main()
