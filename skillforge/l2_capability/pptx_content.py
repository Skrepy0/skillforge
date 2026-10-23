"""Single-slide content contract shared by generation, review, and template rendering."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

MAX_POINT_CHARS = 80


@dataclass(frozen=True)
class SlideBlock:
    text: str
    code: bool = False
    language: str = ""


def _plain(text: str) -> str:
    text = text.strip()
    while True:
        cleaned = re.sub(r"^#{1,6}\s+|^[-*+•]\s+|^\d+[.)、]\s*", "", text)
        if cleaned == text:
            break
        text = cleaned
    return re.sub(r"\*\*(.+?)\*\*|`([^`]+)`", lambda m: m[1] or m[2], text)


def normalize_slide_content(body: str, heading: str, context: dict[str, str] | None = None) -> str:
    """Cover facts are supplied by the user; they do not need creative generation."""
    if heading not in ("封面", "Cover"):
        try:
            blocks = slide_blocks(body, heading)
        except ValueError:
            # Keep invalid input intact so the shared validator can report it.
            return body
        return "\n".join(f"```{b.language}\n{b.text}\n```" if b.code else b.text for b in blocks)
    context = context or {}
    members = context.get("member_info", "").strip()
    if members:
        # Preserve the user's names, roles, and qualifiers (e.g. fictional members).
        return members
    title = context.get("topic_title", "").strip()
    lines = []
    for raw in body.splitlines():
        text = _plain(raw)
        if text.rstrip("：:") in ("封面", "Cover"):
            continue
        candidate = re.sub(r"^(?:题目|标题|Title)\s*[:：]\s*", "", text, flags=re.I)
        if title and "".join(candidate.split()) == "".join(title.split()):
            continue
        if text:
            lines.append(text)
    return "\n".join(lines)


def _fenced_blocks(text: str, language: str, heading: str, depth: int) -> list[SlideBlock]:
    if re.search(
        r"\b(?:ppt|prs)\.slides|\bslide\.(?:shapes|placeholders)|\bpptxgenjs\b|\bslide_layouts\b",
        text,
    ):
        raise ValueError(
            "收到的是PPT生成脚本，不是页面正文；请直接给出本页要点，不要生成Python或JS制图代码"
        )
    stripped = text.strip()
    if language == "json" or (stripped.startswith("{") or re.match(r'^\[\s*(?:\{|"|\])', stripped)):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError("页面JSON包装无效，请直接输出正文要点") from exc
        if not isinstance(data, dict) or set(data) - {
            "title",
            "heading",
            "content",
            "body",
            "notes",
        }:
            raise ValueError(
                "只接受单页title/content/notes或heading/body结构，不要输出整套幻灯片JSON"
            )
        if ("content" in data) == ("body" in data):
            raise ValueError("单页JSON必须且只能包含content或body之一")
        content = data.get("content", data.get("body"))
        if isinstance(content, list) and all(isinstance(x, str) for x in content):
            content = "\n".join(content)
        if not isinstance(content, str):
            raise ValueError("单页正文必须是字符串或字符串列表")
        return slide_blocks(content, heading, depth + 1)
    nonempty = [line for line in text.splitlines() if line.strip()]
    if nonempty and all(re.match(r"^\s*(?:#|//|[-*+•]\s)", line) for line in nonempty):
        prose = "\n".join(re.sub(r"^\s*(?:#|//)\s?", "", line) for line in nonempty)
        return slide_blocks(prose, heading, depth + 1)
    if re.search(
        r"(?m)^\s*(?:module|endmodule|assign|always(?:_comb|_ff)?|initial|entity|architecture)\b",
        text,
    ):
        return [SlideBlock(text, True, "verilog" if language != "vhdl" else "vhdl")]
    if language in {"", "markdown", "md", "text", "plaintext"}:
        return slide_blocks(text, heading, depth + 1)
    if language in {
        "python",
        "javascript",
        "js",
        "typescript",
        "ts",
        "c",
        "cpp",
        "java",
        "sql",
        "bash",
    }:
        return [SlideBlock(text, True, language)]
    raise ValueError("代码围栏没有可识别的领域代码，请改为普通正文要点")


def slide_blocks(body: str, heading: str = "", _depth: int = 0) -> list[SlideBlock]:
    """Unwrap prose/JSON transport formats; only actual source code is atomic."""
    if _depth > 4:
        raise ValueError("页面包装嵌套过深，请直接输出正文")
    # Raw single-page JSON is a transport wrapper too, not visible slide text.
    if body.lstrip().startswith("{") or re.match(r'^\s*\[\s*(?:\{|"|\])', body):
        return _fenced_blocks(body, "json", heading, _depth)
    blocks: list[SlideBlock] = []
    code: list[str] | None = None
    implicit_code = False
    language = ""
    for raw in body.splitlines():
        if raw.strip().startswith("```"):
            if code is None:
                code, language = [], raw.strip()[3:].strip().lower()
            elif raw.strip() == "```":
                blocks.extend(_fenced_blocks("\n".join(code), language, heading, _depth))
                code, language = None, ""
            else:
                code.append(raw)
            continue
        if code is not None:
            code.append(raw.rstrip())
            if implicit_code and re.search(r"\bendmodule\b", raw):
                blocks.append(SlideBlock("\n".join(code), True, "verilog"))
                code, implicit_code = None, False
        elif raw.strip():
            if re.match(r"\s*module\s+\w+", raw):
                if re.search(r"\bendmodule\b", raw):
                    blocks.append(SlideBlock(raw.rstrip(), True, "verilog"))
                else:
                    code, implicit_code = [raw.rstrip()], True
                continue
            if re.search(r"\b(?:ppt|prs)\.slides|\bslide\.(?:shapes|placeholders)", raw):
                raise ValueError("PPT生成脚本不能作为页面正文，请直接输出要点")
            text = _plain(raw)
            if text.rstrip("：:") != heading.rstrip("：:"):
                blocks.append(SlideBlock(text))
    if code is not None:
        raise ValueError("代码块未闭合，请使用完整的三反引号代码块")
    return blocks


def supplied_slide_content(
    heading: str, context: dict[str, str], plan: dict[str, str]
) -> str | None:
    if heading in ("封面", "Cover") and context.get("member_info", "").strip():
        return normalize_slide_content("", heading, context)
    code = context.get(plan.get("code_field", ""), "").strip()
    if code:
        try:
            blocks = slide_blocks(code)
        except ValueError:
            return None
        if len(blocks) == 1 and blocks[0].code:
            return normalize_slide_content(code, heading, context)
    return None


def fit_slide_content(
    body: str,
    heading: str,
    context: dict[str, str],
    plan: dict[str, str],
) -> str:
    """Fit excess short points into three slots without deleting or rewriting text.

    Only adjacent prose can be joined. Keep the original if no partition satisfies
    the existing validator, including its factual and per-point constraints.
    """
    body = normalize_slide_content(body, heading, context)
    if heading in ("封面", "Cover"):
        return body
    try:
        blocks = slide_blocks(body, heading)
    except ValueError:
        return body
    if not 3 < len(blocks) <= 12 or any(block.code for block in blocks):
        return body
    # Three contiguous groups preserve order, qualifiers, and all source facts.
    for first in range(1, len(blocks) - 1):
        for second in range(first + 1, len(blocks)):
            groups = (blocks[:first], blocks[first:second], blocks[second:])
            candidate = "\n".join("；".join(block.text for block in group) for group in groups)
            if not slide_content_errors(candidate, heading, context, plan):
                return candidate
    return body


def slide_content_errors(
    body: str,
    heading: str = "",
    context: dict[str, str] | None = None,
    plan: dict[str, str] | None = None,
) -> list[str]:
    body = normalize_slide_content(body, heading, context)
    if heading in ("封面", "Cover"):
        if not body.strip():
            return ["封面成员分工为空"]
        if len(body) > 200:
            return ["封面成员分工超过200字符，请精简资料或使用单独的成员页"]
        return []
    try:
        blocks = slide_blocks(body, heading)
    except ValueError as exc:
        return [str(exc)]
    errors = []
    context = context or {}
    plan = plan or {}
    for forbidden in plan.get("avoid", "").split("|"):
        if forbidden.strip() and forbidden.strip().casefold() in body.casefold():
            errors.append(f"本页职责为“{plan.get('purpose', heading)}”，不要扩展到“{forbidden}”")
    if re.match(r"\s*module\s", context.get("code_snippet", "")) and any(
        b.code and b.language not in {"verilog", "systemverilog"} for b in blocks
    ):
        errors.append("已提供的是Verilog设计代码，不要输出Python/JS等制图程序或无关代码")
    if plan and not plan.get("code_field") and any(b.code for b in blocks):
        errors.append("本页仅需正文要点，设计代码由指定代码页统一展示，不要重复")
    supplied = supplied_slide_content(heading, context, plan) if plan.get("code_field") else None
    if supplied is not None:
        expected = ["".join(b.text.split()) for b in slide_blocks(supplied) if b.code]
        actual = ["".join(b.text.split()) for b in blocks if b.code]
        if actual != expected:
            errors.append("本页须完整保留已采集的设计代码，不要输出排版脚本或自行改写代码")
    if re.search(r"未提供|没有|无真实|暂无", context.get("screenshots", "")) and re.search(
        r"红框|红色框|红箭头|红色箭头|截图中|如图所示", body
    ):
        errors.append("未提供真实截图，只能写观察信号或验证方案，不能描述图中红框或箭头")
    if re.search(r"不声称已完成|不编造实测|预期结果", context.get("problem_description", "")):
        expected_label = re.search(r"(?:^|\n)\s*预期(?:结果|输出)?\s*[:：]", body)
        if not expected_label and re.search(
            r"已完成(?:实验|仿真|验证)|实测表明|测试用例均达到|(?:验证|证明).{0,15}完全吻合"
            r"|(?:^|\n)\s*完成[^\n]{0,30}设计与验证(?!方案)",
            body,
        ):
            errors.append("未提供实测结果，请明确描述为预期结果或验证计划")
    if not blocks:
        errors.append("页面正文为空")
    if len(blocks) > 3:
        errors.append(f"页面最多3条要点或代码块，实际{len(blocks)}条；精简本页，不要分页")
    for index, block in enumerate(blocks, 1):
        if block.code:
            if not block.text.strip():
                errors.append("代码块不能为空")
            if len(block.text.splitlines()) > 12 or any(
                len(line) > 100 for line in block.text.splitlines()
            ):
                errors.append("代码块最多12行、每行100字符，必须作为整体保留在本页")
        else:
            if re.search(r"第[一二三四五六七八九十百\d]+页|（续\s*\d+）", block.text):
                errors.append("当前章节只对应1页，禁止生成第一页、第二页或续页大纲")
            if len(block.text) > MAX_POINT_CHARS:
                errors.append(
                    f"第{index}条要点共{len(block.text)}字符，超过{MAX_POINT_CHARS}字符上限；"
                    "请保留问题与检查动作，精简说明，不要截断句子"
                )
    return list(dict.fromkeys(errors))
