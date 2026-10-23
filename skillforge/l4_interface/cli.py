"""SkillForge CLI：命令行入口，只做参数解析与结果展示。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from skillforge.shared.errors import SkillForgeError
from skillforge.shared.paths import PathValidationError, resolve_output_path


def _ask_interactively(missing: list[str]) -> dict[str, str]:
    from skillforge.l3_orchestration.contract import question_for

    answers: dict[str, str] = {}
    print(f"\n需要补充 {len(missing)} 项信息：")
    for field in missing:
        answers[field] = input(f"  {question_for(field)} ").strip()
    return answers


def _cmd_run(args: argparse.Namespace) -> int:
    from skillforge.l3_orchestration.orchestrator import Orchestrator
    from skillforge.l4_interface.llm_client import OpenAICompatibleClient

    payload = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))

    try:
        llm = OpenAICompatibleClient()
    except SkillForgeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    orchestrator = Orchestrator.from_config(llm=llm)
    raw_out = payload.get("out_path")
    output_root = args.output_dir or os.getenv("SKILLFORGE_OUTPUT_DIR")
    try:
        safe_out = resolve_output_path(
            raw_out,
            Path(output_root) if output_root else None,
            require_root=False,
        )
    except PathValidationError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    result = orchestrator.run(
        request=payload.get("request", args.skill),
        collected=payload.get("collected", {}),
        ask_fn=_ask_interactively,
        out_path=safe_out,
        skill_name=args.skill,
        **(
            {
                "pptx_agent": True,
                "pptx_assets": _assets(
                    payload.get("assets", {}), Path(args.input).resolve().parent
                ),
                "pptx_preview": args.pptx_preview,
            }
            if args.pptx_agent
            else {}
        ),
    )

    printable = {k: v for k, v in result.items() if k != "draft"}
    print(json.dumps(printable, ensure_ascii=False, indent=2, default=str))

    if result["status"] == "delivered":
        draft = result.get("draft")
        if draft is not None and draft.output == "markdown":
            from skillforge.l2_capability.renderer.markdown_renderer import markdown_text

            print(markdown_text(draft))
        print(f"\n已生成：{result.get('output_path') or '（Markdown 草稿）'}")
        print("这是草稿，提交前请对照学校要求逐项核对。")
        return 0
    if result["status"] == "needs_input":
        print("\n信息不足，请补充后重试。")
        return 3
    return 1


def _assets(raw: dict, base: Path) -> dict[str, Path]:
    if not isinstance(raw, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in raw.items()
    ):
        raise SkillForgeError("assets 必须是素材别名到本地图片路径的映射")
    return {name: (base / value).resolve() for name, value in raw.items()}


def _cmd_pptx_inspect(args: argparse.Namespace) -> int:
    from skillforge.l2_capability.renderer.pptx_editor import PptxEditor

    print(json.dumps(PptxEditor(Path(args.input)).snapshot(), ensure_ascii=False, indent=2))
    return 0


def _cmd_pptx_edit(args: argparse.Namespace) -> int:
    from skillforge.l3_orchestration.pptx_agent import PptxAgent
    from skillforge.l4_interface.llm_client import OpenAICompatibleClient

    target = resolve_output_path(args.output, None, expected_suffix=".pptx")
    assert target is not None
    result = PptxAgent(OpenAICompatibleClient(), args.max_rounds, args.preview).run(
        Path(args.input),
        target,
        {"request": args.request},
        _assets(
            json.loads(Path(args.assets).read_text(encoding="utf-8-sig")),
            Path(args.assets).resolve().parent,
        )
        if args.assets
        else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "delivered" else 1


def _cmd_validate(_args: argparse.Namespace) -> int:
    from skillforge.l2_capability.registry import validate_all

    ok, messages = validate_all()
    for msg in messages:
        print(msg)
    return 0 if ok else 1


def _cmd_skills_list(_args: argparse.Namespace) -> int:
    import json as _json

    root = Path(__file__).resolve().parents[2] / "skills"
    index = _json.loads((root / "index.json").read_text(encoding="utf-8-sig"))
    for skill in index["skills"]:
        print(f"{skill['name']:<24} {skill.get('category', '-'):<14} {skill['description']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    from skillforge.shared.config import load_project_dotenv

    load_project_dotenv()
    parser = argparse.ArgumentParser(prog="skillforge", description="SkillForge 运行时 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="执行一次生成任务")
    p_run.add_argument("--skill", required=True)
    p_run.add_argument("--input", required=True, help="请求 JSON 路径")
    p_run.add_argument("--output-dir", default=None, help="允许的输出目录（可选）")
    p_run.add_argument("--pptx-agent", action="store_true", help="读取模板后用结构化操作编辑 PPT")
    p_run.add_argument(
        "--pptx-preview", action="store_true", help="编辑时渲染真实页面供视觉模型检查"
    )
    p_run.set_defaults(func=_cmd_run)

    p_val = sub.add_parser("validate", help="校验技能包契约与 index.json")
    p_val.set_defaults(func=_cmd_validate)

    p_inspect = sub.add_parser("pptx-inspect", help="读取 PPT 页面、元素 ID、文字、字体和尺寸")
    p_inspect.add_argument("--input", required=True)
    p_inspect.set_defaults(func=_cmd_pptx_inspect)

    p_edit = sub.add_parser("pptx-edit", help="通过 LLM 编辑已有 PPT，另存为新文件")
    p_edit.add_argument("--input", required=True)
    p_edit.add_argument("--output", required=True)
    p_edit.add_argument("--request", required=True)
    p_edit.add_argument("--assets", help="图片素材别名到本地路径的 JSON 文件")
    p_edit.add_argument("--max-rounds", type=int, default=12)
    p_edit.add_argument("--preview", action="store_true", help="使用真实渲染和视觉模型检查")
    p_edit.set_defaults(func=_cmd_pptx_edit)

    p_skills = sub.add_parser("skills", help="技能包管理")
    skills_sub = p_skills.add_subparsers(dest="skills_cmd", required=True)
    skills_sub.add_parser("list", help="列出所有技能").set_defaults(func=_cmd_skills_list)

    args = parser.parse_args(argv)
    if getattr(args, "pptx_preview", False) and not getattr(args, "pptx_agent", False):
        parser.error("--pptx-preview 需要同时启用 --pptx-agent")
    try:
        return args.func(args)
    except (SkillForgeError, PathValidationError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
