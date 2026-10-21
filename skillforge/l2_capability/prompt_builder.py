"""按章节组装生成 prompt：技能指令 + 契约 + 已采集字段 + 参考知识。"""

from __future__ import annotations

from skillforge.l2_capability.loader import LoadedSkill


def build_section_prompt(
    skill: LoadedSkill,
    section: str,
    collected: dict[str, str],
) -> str:
    contract = skill.contract

    collected_lines = (
        "\n".join(f"- {field}: {value}" for field, value in collected.items() if value) or "（无）"
    )

    refs = (
        "\n\n".join(f"### {name}\n{content}" for name, content in skill.references.items())
        or "（无）"
    )

    return f"""# 技能：{contract.name}

## 技能指令
{skill.instructions}

## 写作契约
- 输出形态：{contract.output}
- 全文章节顺序：{" → ".join(contract.sections)}
- 本次只写其中一章：**{section}**

## 已采集信息（只能使用这些事实，禁止编造）
{collected_lines}

## 参考知识
{refs}

## 任务
只输出“{section}”这一章的正文，不要输出标题、不要输出其他章节、不要加解释。
字数控制在 150–500 字。所有数字必须来自上方“已采集信息”。
"""
