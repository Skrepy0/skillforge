"""契约工具：从 SkillContract 派生缺失字段与追问话术。"""

from __future__ import annotations

from skillforge.shared.types import SkillContract

_FIELD_QUESTIONS: dict[str, str] = {
    "title": "论文/项目的题目是什么？",
    "degree_level": "是本科还是硕士？",
    "core_question": "用一句话说明你的核心研究问题。",
    "methods": "打算用哪几种研究方法？至少两种。",
    "data_source": "数据从哪里来？问卷、公开数据集还是实验设备？",
    "expected_output": "预期成果是什么形式？论文、系统还是专利？",
    "gpa_rank": "GPA 专业排名是第几 / 共多少人？例如 3/120。",
    "comprehensive_rank": "综合测评排名是第几 / 共多少人？",
    "research_achievements": "有无论文、专利、竞赛？请说明题目、你的角色、状态。",
    "social_practice": "志愿服务或社会实践总时长多少小时？担任什么角色？",
    "target_word_count": "学校对字数有要求吗？没有我按默认值写。",
}


def missing_fields(contract: SkillContract, collected: dict[str, str]) -> list[str]:
    return [f for f in contract.required_fields if not collected.get(f, "").strip()]


def question_for(field: str) -> str:
    return _FIELD_QUESTIONS.get(field, f"请提供 {field} 的具体信息。")
