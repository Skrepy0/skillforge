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
