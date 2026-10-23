"""Markdown 草稿的文本展示与文件输出。"""

from pathlib import Path

from skillforge.shared.errors import RenderError
from skillforge.shared.types import DraftDocument


def markdown_text(draft: DraftDocument) -> str:
    parts = [f"# {draft.title}"]
    for section in draft.sections:
        parts.extend([f"## {section['heading']}", section["body"]])
    return "\n\n".join(parts) + "\n"


class MarkdownRenderer:
    def render(self, draft: DraftDocument, out_path: Path) -> Path:
        try:
            out_path.write_text(markdown_text(draft), encoding="utf-8")
        except OSError as exc:
            raise RenderError("Markdown 渲染失败") from exc
        return out_path
