# Changelog

本文件格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.1.0] - 2026-10-21

### 引擎

#### Added

- L1 门禁层：`cliche_check`、`format_check` 两条规则，支持 `gates.yaml` 配置词表与权重
- L2 能力层：`Loader` 解析 SKILL.md frontmatter，`DocxRenderer` 复用技能包排版函数
- L3 编排层：`Router` 关键词路由、`StateMachine` 阶段迁移、`Rewriter` 定向重写
- L4 接入层：CLI（`run` / `validate` / `skills list`）、FastAPI、Agent 宿主接口
- `shared/`：`SkillContract`、`GateResult`、`SessionState` 等跨层契约

#### Changed

- `openai`、`fastapi`、`pydantic` 下沉到 `[api]` extra，核心依赖仅 `python-docx`、`pyyaml`

### 技能包

#### Added

- `test-skill`：用于测试

## [0.0.1] - 2026-10-20

### 引擎

#### Added

- 项目骨架：`pyproject.toml`、`uv` 环境、Ruff 格式化、Poe 任务
