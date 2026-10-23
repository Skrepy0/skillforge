from skillforge.l2_capability.loader import LoadedSkill
from skillforge.l2_capability.pptx_content import slide_blocks, slide_content_errors
from skillforge.l3_orchestration.task_queue import TaskQueue
from skillforge.shared.types import SkillContract


def test_comment_only_fence_is_prose_not_code():
    body = "```python\n# - 建立工程\n# - 添加设计文件\n# - 检查编译结果\n```"
    blocks = slide_blocks(body, "步骤一")
    assert [b.text for b in blocks] == ["建立工程", "添加设计文件", "检查编译结果"]
    assert not any(b.code for b in blocks)


def test_json_slide_wrapper_extracts_content_without_rendering_notes():
    body = """```json
{"title":"步骤一","content":["建立工程","添加文件","编译检查"],"notes":"讲解45秒"}
```"""
    blocks = slide_blocks(body, "步骤一")
    assert [b.text for b in blocks] == ["建立工程", "添加文件", "编译检查"]
    assert not any(b.code for b in blocks)


def test_code_fence_cannot_bypass_bullet_budget_or_render_ppt_script():
    assert slide_content_errors("```markdown\n- 要点甲\n- 要点乙\n- 要点丙\n- 要点丁\n```")
    script = """```python
slide = ppt.slides.add_slide(slide_layouts[1])
slide.shapes.title.text = "步骤二"
content = slide.placeholders[1]
content.text = "检查设计"
```"""
    assert slide_content_errors(script, "步骤二")


def test_provided_code_page_never_calls_llm_and_keeps_exact_source():
    class LLM:
        def complete(self, prompt):
            raise AssertionError("用户已提供设计代码，不应生成PPT脚本替换它")

    code = "module mux2;\nassign y = sel ? b : a;\nendmodule"
    plan = {"设计": {"purpose": "展示设计代码", "code_field": "code_snippet"}}
    skill = LoadedSkill(
        SkillContract("ppt", "", ["code_snippet"], "pptx", ["设计"], pptx_page_plan=plan), "", {}
    )
    result = TaskQueue(LLM()).generate_all(skill, {"code_snippet": code})
    assert slide_blocks(result["设计"])[0].text == code
    assert slide_content_errors("仅列设计目标", "设计", {"code_snippet": code}, plan["设计"])


def test_cover_uses_collected_members_without_retrying_llm():
    class LLM:
        def complete(self, prompt):
            raise AssertionError("封面已有题目和成员分工，无需让模型重复生成")

    members = "演示用虚构成员：成员甲负责设计，成员乙负责仿真方案，成员丙负责汇报。"
    context = {"topic_title": "二选一多路选择器", "member_info": members}
    skill = LoadedSkill(
        SkillContract("ppt", "", ["topic_title", "member_info"], "pptx", ["封面"]), "", {}
    )
    assert TaskQueue(LLM()).generate_all(skill, context) == {"封面": members}
    assert slide_content_errors(members, "封面", context) == []


def test_cover_title_is_cleaned_instead_of_rejected():
    from skillforge.l2_capability.pptx_content import normalize_slide_content

    title = "二选一多路选择器"
    body = f"# 封面\n**题目**：{title}\n成员甲：负责设计\n成员乙：负责仿真"
    context = {"topic_title": title}
    cleaned = normalize_slide_content(body, "封面", context)
    assert cleaned == "成员甲：负责设计\n成员乙：负责仿真"
    assert slide_content_errors(body, "封面", context) == []
    assert normalize_slide_content(cleaned, "封面", context) == cleaned


def test_cover_role_can_reference_topic_without_causing_retries():
    context = {"topic_title": "二选一多路选择器"}
    body = "成员甲：负责二选一多路选择器设计与汇报"
    assert slide_content_errors(body, "封面", context) == []


def test_code_is_one_atomic_block_and_duplicate_heading_is_removed():
    body = "## 设计\n```verilog\nmodule mux2;\n  assign y = sel ? b : a;\nendmodule\n```"
    blocks = slide_blocks(body, "设计")
    assert len(blocks) == 1 and blocks[0].code
    assert "module mux2" in blocks[0].text and "endmodule" in blocks[0].text
    assert slide_content_errors(body, "设计") == []


def test_missing_screenshot_and_unmeasured_results_are_not_presented_as_evidence():
    context = {"screenshots": "未提供真实截图", "problem_description": "不声称已完成实验"}
    assert slide_content_errors("红框标注选择信号", context=context)
    assert slide_content_errors("测试用例均达到预期", context=context)
    assert slide_content_errors("预期：sel=0时输出a", context=context) == []


def test_generation_retries_overlong_section_with_single_page_feedback():
    class LLM:
        def __init__(self):
            self.prompts = []

        def complete(self, prompt):
            self.prompts.append(prompt)
            return (
                "第一页：工程\n第二页：仿真" if len(self.prompts) == 1 else "新建工程\n添加设计文件"
            )

    skill = LoadedSkill(SkillContract("ppt", "", [], "pptx", ["步骤一"]), "", {})
    llm = LLM()
    assert TaskQueue(llm).generate_all(skill, {}) == {"步骤一": "新建工程\n添加设计文件"}
    assert len(llm.prompts) == 2
    assert "禁止生成第一页" in llm.prompts[1]


def test_unfenced_verilog_module_stays_together():
    code = "module mux2;\nassign y = sel ? b : a;\nendmodule"
    blocks = slide_blocks(code)
    assert len(blocks) == 1 and blocks[0].code and blocks[0].text == code


def test_pptx_format_is_mandatory_even_with_low_score_threshold():
    from skillforge.l1_governance.gate_runner import GateRunner
    from skillforge.shared.config import GatesConfig
    from skillforge.shared.types import DraftDocument, SessionState

    contract = SkillContract("ppt", "", [], "pptx", ["步骤"])
    draft = DraftDocument(
        "MUX", [{"heading": "步骤", "body": "第一页：设计\n第二页：验证"}], output="pptx"
    )
    result = GateRunner(GatesConfig(0.0, {"format_check": {"enabled": True, "weight": 1}})).run(
        draft, contract, SessionState("session", "ppt")
    )
    assert not result.passed


def test_readable_troubleshooting_sentences_do_not_fail_at_twenty_chinese_characters():
    body = (
        "选择方向反写：核对sel为零时选择a，为一时选择b，避免三目运算分支颠倒\n"
        "总线宽度不匹配：检查a、b和y声明一致，确认WIDTH参数为正整数\n"
        "顶层选择错误：确认工程顶层为mux2_bus，并检查设计文件已加入工程"
    )

    class LLM:
        def complete(self, prompt):
            return body

    skill = LoadedSkill(SkillContract("ppt", "", [], "pptx", ["典型问题与排错"]), "", {})
    assert TaskQueue(LLM()).generate_all(skill, {})["典型问题与排错"] == body
    assert slide_content_errors(body, "典型问题与排错") == []


def test_point_character_limit_is_still_enforced():
    errors = slide_content_errors("排" * 81, "典型问题与排错")
    assert any("第1条" in error and "81字符" in error and "80字符上限" in error for error in errors)
    assert slide_content_errors("排" * 80, "典型问题与排错") == []
