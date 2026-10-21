"""SkillForge CLI：命令行入口，只做参数解析与结果展示。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skillforge.shared.errors import SkillForgeError


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
    result = orchestrator.run(
        request=payload.get("request", args.skill),
        collected=payload.get("collected", {}),
        ask_fn=_ask_interactively,
        out_path=Path(payload["out_path"]) if payload.get("out_path") else None,
    )

    printable = {k: v for k, v in result.items() if k != "draft"}
    print(json.dumps(printable, ensure_ascii=False, indent=2, default=str))

    if result["status"] == "delivered":
        print(f"\n已生成：{result.get('output_path') or '（Markdown 草稿）'}")
        print("这是草稿，提交前请对照学校要求逐项核对。")
        return 0
    if result["status"] == "needs_input":
        print("\n信息不足，请补充后重试。")
        return 3
    return 1


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
    parser = argparse.ArgumentParser(prog="skillforge", description="SkillForge 运行时 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="执行一次生成任务")
    p_run.add_argument("--skill", required=True)
    p_run.add_argument("--input", required=True, help="请求 JSON 路径")
    p_run.set_defaults(func=_cmd_run)

    p_val = sub.add_parser("validate", help="校验技能包契约与 index.json")
    p_val.set_defaults(func=_cmd_validate)

    p_skills = sub.add_parser("skills", help="技能包管理")
    skills_sub = p_skills.add_subparsers(dest="skills_cmd", required=True)
    skills_sub.add_parser("list", help="列出所有技能").set_defaults(func=_cmd_skills_list)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
