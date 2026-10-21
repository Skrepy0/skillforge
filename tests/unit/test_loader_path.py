"""Loader 路径校验：entry['path'] 不得逃逸 skills_root。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from skillforge.l2_capability.loader import Loader
from skillforge.l2_capability.registry import validate_all
from skillforge.shared.errors import ContractViolation


def _write_skill(root: Path, rel_path: str, name: str) -> Path:
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"---\nname: {name}\ndescription: test\nmetadata:\n"
        f"  required_fields: [x]\n  output: markdown\n  sections: [A]\n---\n\n# Body\n",
        encoding="utf-8",
    )
    return target


def _write_index(root: Path, path_value: object, name: str) -> None:
    (root / "index.json").write_text(
        json.dumps(
            {
                "name": "test-skills",
                "version": "0.1.0",
                "skills": [
                    {
                        "name": name,
                        "category": "test",
                        "path": path_value,
                        "triggers": ["测试"],
                        "description": "test",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# ---------- Loader.load ----------


def test_accepts_relative_skill_path(tmp_path: Path):
    _write_skill(tmp_path, "skill-a/SKILL.md", name="skill-a")
    _write_index(tmp_path, "skill-a/SKILL.md", name="skill-a")
    loaded = Loader(tmp_path).load("skill-a")
    assert loaded.contract.name == "skill-a"


def test_rejects_parent_escape(tmp_path: Path):
    _write_index(tmp_path, "../outside/SKILL.md", name="test-skill")
    with pytest.raises(ContractViolation, match="越界"):
        Loader(tmp_path).load("test-skill")


def test_rejects_absolute_path(tmp_path: Path):
    _write_index(tmp_path, "/etc/passwd", name="test-skill")
    with pytest.raises(ContractViolation, match="越界"):
        Loader(tmp_path).load("test-skill")


def test_rejects_non_string_path(tmp_path: Path):
    _write_index(tmp_path, 42, name="test-skill")
    with pytest.raises(ContractViolation, match="非法"):
        Loader(tmp_path).load("test-skill")


def test_rejects_empty_path(tmp_path: Path):
    _write_index(tmp_path, "   ", name="test-skill")
    with pytest.raises(ContractViolation, match="非法"):
        Loader(tmp_path).load("test-skill")


def test_rejects_non_skill_md(tmp_path: Path):
    _write_skill(tmp_path, "skill-a/other.md", name="skill-a")
    _write_index(tmp_path, "skill-a/other.md", name="skill-a")
    with pytest.raises(ContractViolation, match="非法"):
        Loader(tmp_path).load("skill-a")


def test_error_message_hides_absolute_path(tmp_path: Path):
    _write_index(tmp_path, "../outside/SKILL.md", name="test-skill")
    with pytest.raises(ContractViolation) as exc_info:
        Loader(tmp_path).load("test-skill")
    assert str(tmp_path) not in str(exc_info.value)


# ---------- references 符号链接 ----------


def test_skips_symlinked_references_outside_root(tmp_path: Path):
    if not hasattr(os, "symlink"):
        pytest.skip("OS 不支持符号链接")

    outside = tmp_path.parent / f"{tmp_path.name}-outside-ref"
    outside.mkdir(exist_ok=True)
    external_md = outside / "leak.md"
    external_md.write_text("secret", encoding="utf-8")

    _write_skill(tmp_path, "skill-a/SKILL.md", name="skill-a")
    refs_dir = tmp_path / "skill-a" / "references"
    refs_dir.mkdir()
    try:
        os.symlink(external_md, refs_dir / "leak.md")
    except OSError:
        pytest.skip("无权限创建符号链接")

    _write_index(tmp_path, "skill-a/SKILL.md", name="skill-a")
    loaded = Loader(tmp_path).load("skill-a")
    assert "leak.md" not in loaded.references
    assert "secret" not in "".join(loaded.references.values())


def test_reads_references_inside_root(tmp_path: Path):
    _write_skill(tmp_path, "skill-a/SKILL.md", name="skill-a")
    refs_dir = tmp_path / "skill-a" / "references"
    refs_dir.mkdir()
    (refs_dir / "ok.md").write_text("合法参考内容", encoding="utf-8")

    _write_index(tmp_path, "skill-a/SKILL.md", name="skill-a")
    loaded = Loader(tmp_path).load("skill-a")
    assert loaded.references == {"ok.md": "合法参考内容"}


# ---------- validate_all ----------


def test_validate_reports_escape_as_fail(tmp_path: Path):
    _write_index(tmp_path, "../outside/SKILL.md", name="test-skill")
    ok, messages = validate_all(tmp_path)
    assert not ok
    assert any("越界" in m for m in messages)
    for m in messages:
        assert str(tmp_path) not in m


def test_validate_reports_absolute_path_as_fail(tmp_path: Path):
    _write_index(tmp_path, "/etc/passwd", name="test-skill")
    ok, messages = validate_all(tmp_path)
    assert not ok
    assert any("越界" in m for m in messages)


def test_validate_accepts_normal_entry(tmp_path: Path):
    _write_skill(tmp_path, "skill-a/SKILL.md", name="skill-a")
    _write_index(tmp_path, "skill-a/SKILL.md", name="skill-a")
    ok, messages = validate_all(tmp_path)
    assert ok
    assert any("[OK]" in m and "skill-a" in m for m in messages)
