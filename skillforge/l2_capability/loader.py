"""按路径加载 SKILL.md 与 references，返回 SkillContract 与指令正文。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from skillforge.shared.errors import ContractViolation, SkillNotFound
from skillforge.shared.types import SkillContract

REQUIRED_META = {"required_fields", "output", "sections"}
VALID_OUTPUT = {"markdown", "docx", "pptx"}


def _resolve_entry_path(skills_root: Path, raw: object, name: str) -> Path:
    """解析 index.json 的 entry['path']，校验不逃逸 skills_root。

    校验项：
    - raw 必须是非空字符串
    - 不得为绝对路径
    - resolve 后必须位于 skills_root 内（拦 ..、绝对路径、符号链接逃逸）
    - 文件名必须为 SKILL.md

    所有失败抛 ContractViolation；错误信息不含服务器绝对路径。
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ContractViolation(f"技能路径非法: {name}")

    text = raw.strip()
    if text.startswith(("/", "\\")):
        raise ContractViolation(f"技能路径越界: {name}")

    p = Path(text)
    if p.is_absolute():
        raise ContractViolation(f"技能路径越界: {name}")

    root = skills_root.resolve()
    try:
        candidate = (root / p).resolve()
        candidate.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ContractViolation(f"技能路径越界: {name}") from exc

    if candidate.name != "SKILL.md":
        raise ContractViolation(f"技能路径非法: {name}")

    return candidate


def _is_inside(root: Path, path: Path) -> bool:
    """path 解析后是否仍位于 root 内。用于拦截符号链接逃逸。"""
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError):
        return False
    return True


@dataclass(frozen=True)
class LoadedSkill:
    contract: SkillContract
    instructions: str
    references: dict[str, str]


def parse_skill_file(path: Path) -> tuple[dict, str]:
    """解析 SKILL.md，返回 (frontmatter, 正文)。"""
    if not path.exists():
        raise ContractViolation(f"技能文件不存在: {path.name}")

    text = path.read_text(encoding="utf-8-sig")
    if not text.startswith("---"):
        raise ContractViolation(f"{path.name} 缺少 frontmatter")

    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ContractViolation(f"{path.name} frontmatter 未闭合")

    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        raise ContractViolation(f"{path.name} frontmatter 解析失败: {exc}") from exc

    if not isinstance(fm, dict):
        raise ContractViolation(f"{path.name} frontmatter 顶层必须是映射")

    return fm, parts[2].lstrip("\n")


def _build_contract(fm: dict, path: Path) -> SkillContract:
    meta = fm.get("metadata") or {}
    if not isinstance(meta, dict):
        raise ContractViolation(f"{path.name} metadata 必须是映射")

    missing = REQUIRED_META - set(meta)
    if missing:
        raise ContractViolation(f"{path.name} metadata 缺少契约字段: {sorted(missing)}")

    output = meta.get("output")
    if output not in VALID_OUTPUT:
        raise ContractViolation(f"{path.name} output 非法: {output}")

    sections = meta.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ContractViolation(f"{path.name} sections 必须是非空列表")

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
        self.skills_root = Path(skills_root).resolve()

    def _index(self) -> list[dict]:
        import json

        index_path = self.skills_root / "index.json"
        if not index_path.exists():
            raise SkillNotFound("找不到索引文件 index.json")
        data = json.loads(index_path.read_text(encoding="utf-8-sig"))
        return list(data.get("skills", []))

    def _resolve_entry_path(self, raw: object, name: str) -> Path:
        return _resolve_entry_path(self.skills_root, raw, name)

    def _resolve_path(self, name: str) -> Path:
        for entry in self._index():
            if entry.get("name") == name:
                return self._resolve_entry_path(entry.get("path"), name)
        raise SkillNotFound(f"技能不存在: {name}")

    def load(self, name: str) -> LoadedSkill:
        skill_path = self._resolve_path(name)
        fm, body = parse_skill_file(skill_path)
        contract = _build_contract(fm, skill_path)

        if contract.name != name:
            raise ContractViolation(f"name 不一致: frontmatter={contract.name}, 请求={name}")

        refs_dir = skill_path.parent / "references"
        references: dict[str, str] = {}
        if refs_dir.is_dir():
            for ref in sorted(refs_dir.glob("*.md")):
                if not _is_inside(self.skills_root, ref):
                    continue
                references[ref.name] = ref.read_text(encoding="utf-8-sig")

        return LoadedSkill(contract=contract, instructions=body, references=references)

    def load_contract(self, name: str) -> SkillContract:
        return self.load(name).contract
