"""按路径加载 SKILL.md 与 references，返回 SkillContract 与指令正文。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from skillforge.shared.errors import ContractViolation, SkillNotFound
from skillforge.shared.types import SkillContract

REQUIRED_META = {"required_fields", "output", "sections"}
VALID_OUTPUT = {"markdown", "docx"}


@dataclass(frozen=True)
class LoadedSkill:
    contract: SkillContract
    instructions: str  # SKILL.md 的 Markdown 正文
    references: dict[str, str]  # 文件名 -> 内容


def parse_skill_file(path: Path) -> tuple[dict, str]:
    """解析 SKILL.md，返回 (frontmatter, 正文)。frontmatter 非映射或未闭合抛 ContractViolation。"""
    if not path.exists():
        raise ContractViolation(f"技能文件不存在: {path}")

    text = path.read_text(encoding="utf-8-sig")
    if not text.startswith("---"):
        raise ContractViolation(f"{path} 缺少 frontmatter")

    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ContractViolation(f"{path} frontmatter 未闭合")

    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        raise ContractViolation(f"{path} frontmatter 解析失败: {exc}") from exc

    if not isinstance(fm, dict):
        raise ContractViolation(f"{path} frontmatter 顶层必须是映射")

    return fm, parts[2].lstrip("\n")


def _build_contract(fm: dict, path: Path) -> SkillContract:
    meta = fm.get("metadata") or {}
    if not isinstance(meta, dict):
        raise ContractViolation(f"{path} metadata 必须是映射")

    missing = REQUIRED_META - set(meta)
    if missing:
        raise ContractViolation(f"{path} metadata 缺少契约字段: {sorted(missing)}")

    output = meta.get("output")
    if output not in VALID_OUTPUT:
        raise ContractViolation(f"{path} output 非法: {output}")

    sections = meta.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ContractViolation(f"{path} sections 必须是非空列表")

    return SkillContract(
        name=str(fm.get("name", "")),
        description=str(fm.get("description", "")),
        required_fields=list(meta.get("required_fields") or []),
        output=output,
        sections=[str(s) for s in sections],
        gates=dict(meta.get("gates") or {}),
        version=str(meta.get("version", "0.1.0")),
    )


class Loader:
    def __init__(self, skills_root: Path) -> None:
        self.skills_root = Path(skills_root)

    def _index(self) -> list[dict]:
        index_path = self.skills_root / "index.json"
        if not index_path.exists():
            raise SkillNotFound(f"找不到索引文件: {index_path}")
        import json

        data = json.loads(index_path.read_text(encoding="utf-8-sig"))
        return list(data.get("skills", []))

    def _resolve_path(self, name: str) -> Path:
        for entry in self._index():
            if entry.get("name") == name:
                return self.skills_root / entry["path"]
        raise SkillNotFound(f"技能不存在: {name}")

    def load(self, name: str) -> LoadedSkill:
        skill_path = self._resolve_path(name)
        fm, body = parse_skill_file(skill_path)
        contract = _build_contract(fm, skill_path)

        if contract.name != name:
            raise ContractViolation(
                f"{skill_path} name 不一致: frontmatter={contract.name}, 请求={name}"
            )

        refs_dir = skill_path.parent / "references"
        references = {}
        if refs_dir.is_dir():
            for ref in sorted(refs_dir.glob("*.md")):
                references[ref.name] = ref.read_text(encoding="utf-8-sig")

        return LoadedSkill(contract=contract, instructions=body, references=references)

    def load_contract(self, name: str) -> SkillContract:
        return self.load(name).contract
