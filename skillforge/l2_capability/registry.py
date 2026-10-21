"""读取 index.json，校验与各 SKILL.md frontmatter 的一致性。"""

from __future__ import annotations

import json
from pathlib import Path

from skillforge.l2_capability.loader import _build_contract, parse_skill_file
from skillforge.shared.errors import ContractViolation

SKILLS_ROOT = Path(__file__).resolve().parents[2] / "skills"


def validate_all(skills_root: Path | None = None) -> tuple[bool, list[str]]:
    root = skills_root or SKILLS_ROOT
    messages: list[str] = []
    ok = True

    index_path = root / "index.json"
    if not index_path.exists():
        return False, [f"[FAIL] 找不到 {index_path}"]

    index = json.loads(index_path.read_text(encoding="utf-8-sig"))
    for entry in index.get("skills", []):
        name = entry.get("name", "")
        skill_path = root / entry.get("path", "")

        try:
            fm, _ = parse_skill_file(skill_path)
            contract = _build_contract(fm, skill_path)
        except ContractViolation as exc:
            ok = False
            messages.append(f"[FAIL] {name}: {exc}")
            continue

        if contract.name != name:
            ok = False
            messages.append(f"[FAIL] name 不一致: index={name}, frontmatter={contract.name}")
            continue
        if skill_path.parent.name != name:
            ok = False
            messages.append(f"[FAIL] 目录名不一致: {skill_path.parent.name}")
            continue

        messages.append(f"[OK]   {name}")

    return ok, messages
