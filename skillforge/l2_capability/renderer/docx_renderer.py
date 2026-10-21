"""DraftDocument -> .docx，复用 skills/utils/docx_common.py 的排版函数。"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from skillforge.shared.errors import RenderError
from skillforge.shared.types import DraftDocument


def _load_docx_common(path: Path) -> ModuleType:
    if not path.exists():
        raise RenderError(f"找不到排版工具: {path}")
    spec = importlib.util.spec_from_file_location("docx_common", path)
    if spec is None or spec.loader is None:
        raise RenderError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for fn in ("new_document", "add_heading", "add_paragraph", "save"):
        if not hasattr(module, fn):
            raise RenderError(f"{path} 缺少函数: {fn}")
    return module


class DocxRenderer:
    def __init__(self, skills_root: Path) -> None:
        self._common = _load_docx_common(Path(skills_root) / "utils" / "docx_common.py")

    def render(self, draft: DraftDocument, out_path: Path) -> Path:
        try:
            doc = self._common.new_document()
            self._common.add_heading(doc, draft.title, level=0)
            for section in draft.sections:
                self._common.add_heading(doc, section["heading"], level=1)
                for para in section["body"].split("\n"):
                    if para.strip():
                        self._common.add_paragraph(doc, para.strip())
            out_path = Path(out_path)
            self._common.save(doc, str(out_path))
        except Exception as exc:
            raise RenderError(f"docx 渲染失败: {exc}") from exc
        return out_path
