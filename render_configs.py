"""
Render device configs from Jinja2 templates + YAML vars.

Usage:
    python render_configs.py

Reads configs/vars/*.yml, renders each against configs/templates/router.conf.j2,
writes the result to configs/rendered/<hostname>.cfg — these rendered files are
what Batfish actually reads as the network snapshot.

Before writing anything, every ACL defined in a vars file is parsed with
core.acl_parser to catch a syntax mistake here, at render time, instead of
finding out from a confusing Batfish error later.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core.acl_parser import parse_acl, ACLParseError

ROOT = Path(__file__).resolve().parent
VARS_DIR = ROOT / "configs" / "vars"
TEMPLATES_DIR = ROOT / "configs" / "templates"
RENDERED_DIR = ROOT / "configs" / "rendered"


def validate_acls(device_vars: dict, source_file: Path) -> None:
    """Parse every ACL's rule lines to catch typos before rendering."""
    for acl in device_vars.get("acls", []):
        acl_text = "\n".join(acl["lines"])
        try:
            parse_acl(acl_text)
        except ACLParseError as exc:
            raise SystemExit(
                f"ACL validation failed in {source_file.name}, "
                f"ACL {acl['name']!r}: {exc}"
            ) from exc


def render_all() -> list[Path]:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("router.conf.j2")

    RENDERED_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for vars_file in sorted(VARS_DIR.glob("*.yml")):
        device_vars = yaml.safe_load(vars_file.read_text(encoding="utf-8"))
        validate_acls(device_vars, vars_file)

        rendered_text = template.render(**device_vars)
        out_path = RENDERED_DIR / f"{device_vars['hostname']}.cfg"
        out_path.write_text(rendered_text, encoding="utf-8")
        written.append(out_path)
        print(f"rendered {vars_file.name} -> {out_path.relative_to(ROOT)}")

    return written


if __name__ == "__main__":
    render_all()
