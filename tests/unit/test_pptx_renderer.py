"""PptxRenderer：验证生成合法的 pptx 并能被 python-pptx 重新打开。"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pptx")

from typing import Any, cast

from pptx import Presentation  # noqa: E402
from skillforge.l2_capability.renderer.pptx_renderer import PptxRenderer  # noqa: E402
from skillforge.shared.errors import RenderError  # noqa: E402
from skillforge.shared.types import DraftDocument  # noqa: E402


def _shape_texts(shapes) -> list[str]:
    return [cast(Any, s).text_frame.text for s in shapes if s.has_text_frame]


def _draft() -> DraftDocument:
    return DraftDocument(
        "测试标题",
        [
            {"heading": "第一章", "body": "第一段内容。\n第二段内容。"},
            {"heading": "第二章", "body": "另一段内容。"},
        ],
        output="pptx",
    )


def test_render_produces_valid_pptx(tmp_path: Path):
    out = PptxRenderer().render(_draft(), tmp_path / "out.pptx")
    assert out.exists()
    assert out.stat().st_size > 0

    prs = Presentation(str(out))
    assert len(prs.slides) == 3

    # 标题页：标题 + 副标题
    title_texts = _shape_texts(prs.slides[0].shapes)
    assert any("测试标题" in t for t in title_texts)

    # 第一章：标题 + body
    first = prs.slides[1]
    title_shape = first.shapes.title
    assert title_shape is not None
    assert "第一章" in cast(Any, title_shape).text_frame.text

    body_texts = [
        cast(Any, s).text_frame.text for s in first.shapes if s.has_text_frame and s != title_shape
    ]
    combined = " ".join(body_texts)
    assert "第一段内容" in combined
    assert "第二段内容" in combined


def test_render_skips_empty_lines(tmp_path: Path):
    draft = DraftDocument(
        "T",
        [{"heading": "H", "body": "a\n\n   \nb"}],
        output="pptx",
    )
    out = PptxRenderer().render(draft, tmp_path / "out.pptx")
    prs = Presentation(str(out))
    slide = prs.slides[1]

    title_shape = slide.shapes.title
    body_shape = next(s for s in slide.shapes if s.has_text_frame and s != title_shape)
    assert body_shape.has_text_frame
    lines = [ln for ln in cast(Any, body_shape).text_frame.text.split("\n") if ln.strip()]
    assert lines == ["a", "b"]


def test_render_wraps_errors_as_render_error(tmp_path: Path, monkeypatch):
    import pptx

    class _Broken:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("broken")

    monkeypatch.setattr(pptx, "Presentation", _Broken)
    with pytest.raises(RenderError, match="pptx 渲染失败"):
        PptxRenderer().render(_draft(), tmp_path / "out.pptx")


def test_render_with_custom_template(tmp_path: Path):
    from pptx import Presentation

    # 造一个只有 2 个布局的最小模板
    template = tmp_path / "template.pptx"
    prs = Presentation()
    prs.save(str(template))

    draft = DraftDocument("T", [{"heading": "H", "body": "a\nb"}], output="pptx")
    out = PptxRenderer().render(
        draft,
        tmp_path / "out.pptx",
        template=template,
        layouts={"title": "Title Slide", "content": "Title and Content"},
    )
    assert out.exists()
    assert len(Presentation(str(out)).slides) == 2


def test_render_falls_back_when_layout_name_missing(tmp_path: Path):
    from pptx import Presentation

    template = tmp_path / "template.pptx"
    Presentation().save(str(template))

    draft = DraftDocument("T", [{"heading": "H", "body": "a"}], output="pptx")
    # 布局名不存在，回退索引，不抛异常
    out = PptxRenderer().render(
        draft,
        tmp_path / "out.pptx",
        template=template,
        layouts={"title": "NoSuchLayout", "content": "AlsoMissing"},
    )
    assert out.exists()


def test_render_missing_template_raises(tmp_path: Path):
    draft = DraftDocument("T", [], output="pptx")
    with pytest.raises(RenderError, match="pptx 渲染失败"):
        PptxRenderer().render(
            draft,
            tmp_path / "out.pptx",
            template=tmp_path / "nope.pptx",
        )


def test_template_example_slides_are_not_exported(tmp_path):
    template = tmp_path / "template.pptx"
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[0]).shapes.title.text = "SAMPLE ONLY"
    prs.save(str(template))
    out = PptxRenderer().render(_draft(), tmp_path / "out.pptx", template=template)
    result = Presentation(str(out))
    assert len(result.slides) == 3
    assert "SAMPLE ONLY" not in str([_shape_texts(s.shapes) for s in result.slides])


def test_long_body_is_paginated_without_losing_text(tmp_path):
    body = "\n".join("内容" * 80 for _ in range(10))
    out = PptxRenderer().render(
        DraftDocument("T", [{"heading": "H", "body": body}], output="pptx"), tmp_path / "out.pptx"
    )
    result = Presentation(str(out))
    assert len(result.slides) > 2
    text = "".join(
        s.text
        for slide in list(result.slides)[1:]
        for s in slide.shapes
        if s.has_text_frame and s != slide.shapes.title
    )
    assert text.replace("\n", "") == body.replace("\n", "")


def test_bound_template_preserves_design_and_uses_cover_section(tmp_path):
    template = (
        Path(__file__).resolve().parents[2]
        / "skills/subskills/hnu-digital-circuit-seminar-ppt/assets/template.pptx"
    )
    draft = DraftDocument(
        "MUX2",
        [
            {"heading": "封面", "body": "成员甲、成员乙"},
            {"heading": "设计原理", "body": "选择输入\n检查输出\n覆盖组合"},
        ],
        output="pptx",
    )
    out = PptxRenderer().render(draft, tmp_path / "bound.pptx", template=template)
    result, original = Presentation(str(out)), Presentation(str(template))
    assert len(result.slides) == 2
    for actual, source in zip(result.slides, [original.slides[0], original.slides[3]]):
        assert len(actual.shapes) == len(source.shapes)
        for shape, old in zip(actual.shapes, source.shapes):
            if shape.has_text_frame:
                continue
            assert (shape.left, shape.top, shape.width, shape.height) == (
                old.left,
                old.top,
                old.width,
                old.height,
            )
            if shape.shape_type == 13:
                assert shape.image.blob == old.image.blob
    texts = str([_shape_texts(slide.shapes) for slide in result.slides])
    assert "MUX2" in texts and "成员甲" in texts and "设计原理" in texts
    assert "title1" not in texts and "Generated by" not in texts


def test_bound_troubleshooting_wraps_long_points_without_losing_text(tmp_path):
    template = (
        Path(__file__).resolve().parents[2]
        / "skills/subskills/hnu-digital-circuit-seminar-ppt/assets/template.pptx"
    )
    points = [
        "选择方向反写：核对sel为零时选择a，为一时选择b，避免三目运算分支颠倒",
        "总线宽度不匹配：检查a、b和y声明一致，确认WIDTH参数为正整数",
        "顶层选择错误：确认工程顶层为mux2_bus，并检查设计文件已加入工程",
    ]
    draft = DraftDocument(
        "排错验证", [{"heading": "典型问题与排错", "body": "\n".join(points)}], output="pptx"
    )
    out = PptxRenderer().render(draft, tmp_path / "troubleshooting.pptx", template=template)
    slide = Presentation(str(out)).slides[1]
    boxes = [s for s in slide.shapes if s.has_text_frame and s.text in points]
    assert [s.text for s in boxes] == points
    assert all(s.text_frame.word_wrap for s in boxes)
    assert all(s.text_frame.paragraphs[0].runs[0].font.size.pt == 22 for s in boxes)
    boxes.sort(key=lambda s: s.top)
    assert all(a.top + a.height <= b.top for a, b in zip(boxes, boxes[1:]))


def test_bound_long_title_fits_template_box(tmp_path):
    template = (
        Path(__file__).resolve().parents[2]
        / "skills/subskills/hnu-digital-circuit-seminar-ppt/assets/template.pptx"
    )
    title = "二选一多路选择器：从 Verilog 设计到功能验证"
    out = PptxRenderer().render(
        DraftDocument(title, [], output="pptx"), tmp_path / "long.pptx", template=template
    )
    shape = next(s for s in Presentation(str(out)).slides[0].shapes if s.shape_id == 37)
    assert shape.text == title
    size = shape.text_frame.paragraphs[0].runs[0].font.size.pt
    assert size >= 24
    assert shape.text_frame.word_wrap is True


def test_bound_rejects_chapter_expansion_instead_of_creating_many_pages(tmp_path):
    template = (
        Path(__file__).resolve().parents[2]
        / "skills/subskills/hnu-digital-circuit-seminar-ppt/assets/template.pptx"
    )
    draft = DraftDocument(
        "MUX",
        [{"heading": "步骤一", "body": "\n".join(f"第{i}页：操作说明" for i in range(1, 13))}],
        output="pptx",
    )
    with pytest.raises(RenderError, match="页面|要点|分页"):
        PptxRenderer().render(draft, tmp_path / "expanded.pptx", template=template)


def test_cover_title_keeps_readable_font(tmp_path):
    template = (
        Path(__file__).resolve().parents[2]
        / "skills/subskills/hnu-digital-circuit-seminar-ppt/assets/template.pptx"
    )
    draft = DraftDocument("二选一多路选择器：从 Verilog 设计到功能验证", [], output="pptx")
    out = PptxRenderer().render(draft, tmp_path / "readable.pptx", template=template)
    title = next(s for s in Presentation(str(out)).slides[0].shapes if s.shape_id == 37)
    assert min(r.font.size.pt for p in title.text_frame.paragraphs for r in p.runs) >= 24


def test_twelve_section_deck_keeps_code_whole_and_comparison_columns(tmp_path):
    from skillforge.l2_capability.loader import Loader
    from skillforge.l2_capability.renderer.pptx_editor import PptxEditor

    root = Path(__file__).resolve().parents[2]
    contract = Loader(root / "skills").load("hnu-digital-circuit-seminar-ppt").contract
    sections = [{"heading": name, "body": "说明甲\n说明乙\n说明丙"} for name in contract.sections]
    sections[0]["body"] = "成员甲：设计\n成员乙：仿真\n成员丙：汇报"
    code = "module mux2(input wire a,b,sel, output wire y);\n  assign y = sel ? b : a;\nendmodule"
    sections[4]["body"] = f"```verilog\n{code}\n```"
    template = root / "skills/subskills/hnu-digital-circuit-seminar-ppt/assets/template.pptx"
    draft = DraftDocument("二选一多路选择器：从 Verilog 设计到功能验证", sections, output="pptx")
    out = PptxRenderer().render(draft, tmp_path / "twelve.pptx", template=template)
    prs = Presentation(str(out))
    assert len(prs.slides) == 12
    code_shapes = [
        s
        for slide in prs.slides
        for s in slide.shapes
        if s.has_text_frame and "module mux2" in s.text
    ]
    assert len(code_shapes) == 1 and code_shapes[0].text == code
    assert code_shapes[0].height.pt >= 3 * 16 * 1.25
    comparison = prs.slides[8]
    bodies = [s for s in comparison.shapes if s.has_text_frame and s.text.startswith("说明")]
    assert len({s.left for s in bodies}) == 3
    assert len({s.top for s in bodies}) == 1
    assert not any(
        i["kind"] == "possible_text_overflow" for i in PptxEditor(out).snapshot()["issues"]
    )
