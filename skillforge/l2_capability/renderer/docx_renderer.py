"""DraftDocument -> .docx，使用受信任的 docx_common 模块。"""

from __future__ import annotations

from pathlib import Path

from skillforge.l2_capability.renderer import docx_common
from skillforge.shared.errors import RenderError
from skillforge.shared.types import DraftDocument


class DocxRenderer:
    def render(self, draft: DraftDocument, out_path: Path) -> Path:
        try:
            doc = docx_common.new_document()
            docx_common.add_heading(doc, draft.title, level=0)
            for section in draft.sections:
                docx_common.add_heading(doc, section["heading"], level=1)
                for para in section["body"].split("\n"):
                    if para.strip():
                        docx_common.add_paragraph(doc, para.strip())
            out_path = Path(out_path)
            docx_common.save(doc, str(out_path))
        except Exception as exc:
            raise RenderError(f"docx 渲染失败: {exc}") from exc
        return out_path
