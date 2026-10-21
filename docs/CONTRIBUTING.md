# 贡献指南

感谢你愿意为 SkillForge 做贡献。本文档说明如何搭建环境、遵守哪些约定、以及两类贡献（改引擎、加技能包）分别怎么做。

---

## 1. 贡献类型

| 类型              | 典型改动                                     | 是否需要改引擎代码 |
| :---------------- | :------------------------------------------- | :----------------- |
| **新增技能包**    | 新增 `skills/subskills/<name>/SKILL.md`      | 否                 |
| **修改技能内容**  | 调整 `SKILL.md`、`references/`、`gates` 权重 | 否                 |
| **新增门禁规则**  | `l1_governance/rules/` 加模块 + 注册         | 是（单点）         |
| **改路由/配置**   | `config/*.yaml`                              | 否                 |
| **引擎功能/修复** | `l1`–`l4`、`shared/` 下的代码                | 是                 |

**优先欢迎前两类**。技能包是项目价值的核心，新增一个高质量赛道比改一行引擎代码更有用。

---

## 2. 环境搭建

### 前置要求

- Python **3.11+**（`requires-python = ">=3.11"`）
- [uv](https://docs.astral.sh/uv/)
- Git

### 初始化

```bash
git clone https://github.com/Skrepy0/skillforge.git
cd skillforge

# 核心依赖 + 开发工具（pytest / ruff / poe）
uv sync

# 需要开发 API 或真实调用 LLM 时，额外装 [api] extra
uv sync --extra api
```

**不要**手动 `python -m venv` 或 `pip install -e`。本项目用 `uv` 管理环境，`uv.lock` 保证版本一致。

### 验证环境

```bash
uv run skillforge --help
uv run skillforge validate
uv run poe check
```

三条都通过，环境就绪。

---

## 3. 项目结构速览

```text
skillforge/
├── config/              # 行为配置，不写死在代码里
├── skillforge/          # 运行时引擎（Python 包）
│   ├── l1_governance/   # 门禁：独立于生成器的质检
│   ├── l2_capability/   # 技能加载、prompt 组装、渲染
│   ├── l3_orchestration/# 路由、状态机、分章生成、定向重写
│   ├── l4_interface/    # CLI / API / Agent 宿主
│   └── shared/          # 跨层契约、配置、日志、异常
├── skills/              # 技能包（可独立发布，不含引擎代码）
│   ├── index.json
│   ├── version.json
│   └── subskills/<name>/SKILL.md
└── tests/
```

### 跨层依赖规则（强制）

```text
L4 → L3 → L2 → L1
         ↘  ↙
        shared
```

- **L4 → L3 → L2 → L1 单向依赖**，禁止反向。`l1` 不得 import `l3`。
- **任何层都可以依赖 `shared/`**，`shared/` 不得依赖任何 L 层。
- **跨层通信只通过 `shared/types.py` 的数据类**，不传裸 `dict`（入口反序列化处除外）。
- **`skills/` 只被 `l2_capability/loader.py` 读取**，其他层通过 `SkillContract` 访问技能信息。

违反依赖规则是 PR 被拒的最常见原因。

---

## 4. 开发工作流

### 提交前必跑

```bash
uv run poe check
```

它依次执行：

| 步骤        | 命令                    | 作用                             |
| :---------- | :---------------------- | :------------------------------- |
| `lint`      | `ruff check .`          | 代码检查                         |
| `fmt-check` | `ruff format --check .` | 格式检查（不修改文件）           |
| `validate`  | `skillforge validate`   | 技能包契约与 `index.json` 一致性 |
| `test`      | `pytest -q`             | 单元 + 集成测试                  |

**任一失败即停**。`validate` 排在 `test` 之前是有意的：先确保 CLI 入口和技能包能加载，再跑测试，避免“测试全绿但用户调不动命令行”。

### 自动格式化

```bash
uv run poe format     # 实际修改文件
uv run poe lint       # 只检查
```

VS Code 用户建议装 Ruff 扩展并在 `.vscode/settings.json` 里设 `"editor.formatOnSave": true`。

---

## 5. 代码规范

### 风格

- **Ruff** 统一 lint 与 format，配置在 `pyproject.toml` 的 `[tool.ruff]`。
- 行宽 **100**，目标版本 **py311**，引号 **双引号**。
- 启用的规则集：`E`、`W`、`F`、`I`、`UP`。不要随意加 `ignore` 来绕过问题。

### 类型注解

- 所有**公开函数**必须有完整的参数与返回类型注解。
- 内部函数至少标注返回值。
- 用 `from __future__ import annotations`，让注解延迟求值。
- 类型检查时用 `TYPE_CHECKING` 块导入仅用于注解的符号（如 `docx.document.Document`）。

### 命名

| 对象      | 约定                             | 示例                   |
| :-------- | :------------------------------- | :--------------------- |
| 模块      | 小写蛇形                         | `gate_runner.py`       |
| 类        | PascalCase                       | `SkillContract`        |
| 函数/变量 | 小写蛇形                         | `load_contract`        |
| 常量      | 大写蛇形                         | `DEFAULT_WORD_COUNT`   |
| 技能名    | 小写连字符，**必须与目录名一致** | `thesis-proposal`      |
| 配置键    | 小写蛇形                         | `similarity_threshold` |

### 错误处理

- 禁止 `except Exception: pass`。
- 新增异常必须继承 `shared/errors.py` 的 `SkillForgeError`。
- 降级逻辑**只在** `l3_orchestration/fallback.py` 实现，其他模块只负责抛异常。
- 捕获后要么转成 `SkillForgeError` 子类，要么记录日志后重新抛出。

### 日志

```python
logger.info(
    "route.decided",
    extra={
        "trace_id": tid,
        "session_id": sid,
        "layer": "l3",
        "skill": decision.skill,
    },
)
```

必带 `trace_id`、`session_id`（若有）、`layer`。**禁止打印用户原文全文**，敏感字段需脱敏。

---

## 6. 测试要求

| 层级 | 目录                 | 覆盖重点                   | 是否触网            |
| :--- | :------------------- | :------------------------- | :------------------ |
| 单元 | `tests/unit/`        | 纯函数、单模块、规则正反例 | 否                  |
| 集成 | `tests/integration/` | 端到端流程、降级路径       | 否（模型调用 mock） |

- **`l1_governance/` 与 `l3_orchestration/` 行覆盖率 ≥ 85%**，`l4_interface/` ≥ 60%。
- 新增门禁规则必须**同时提供通过用例和失败用例**。
- 测试不依赖真实 LLM。`LLMClient` 是 `Protocol`，测试里传一个返回固定字符串的 mock 即可。
- 使用 `tests/fixtures/` 下的样例数据，不要在测试里硬编码大段正文。

```bash
uv run pytest tests/unit -q              # 只跑单元
uv run pytest -q --cov=skillforge --cov-report=term-missing
```

---

## 7. 贡献路径 A：新增技能包

**不需要改引擎代码。** 三步完成：

### 7.1 创建目录与 `SKILL.md`

```text
skills/subskills/<name>/
├── SKILL.md
└── references/          # 可选
    └── review-criteria.md
```

`SKILL.md` 的 frontmatter 必须包含：

```yaml
---
name: <name> # 必须等于目录名
description: >- # 写清“做什么”和“何时触发”，嵌入口语化关键词
  ...
license: MIT
metadata:
  author: your-name
  version: "0.1.0"
  required_fields: [...] # 必需，驱动追问
  output: docx # 必需，markdown 或 docx
  sections: [...] # 必需，门禁据此校验结构
  gates: # 可选，覆盖默认权重
    fact_check: 0.5
---
```

正文建议按五段写：**角色 → 信息采集（强制追问）→ 结构化生成 → 导出 → 自检清单**。

### 7.2 登记到两个地方

- `skills/index.json` 的 `skills` 数组加一条（`name`、`path`、`triggers`、`category`、`description`）
- `skills/SKILL.md` 的分流表加一行（供纯 Agent 模式使用）

### 7.3 更新版本

- `skills/version.json` 的 `skills` 子表加一条
- 集合 `version` 升 minor（如 `0.1.0 → 0.2.0`）

### 7.4 验证

```bash
uv run skillforge validate
```

期望出现 `[OK]   <name>`。若报 `缺少 frontmatter` 或 `缺少契约字段`，按报错信息补齐。

### 7.5 质量底线

- **不得编造事实**：`SKILL.md` 里必须写明“缺失字段必须追问，不得编造”。
- **references/ 写“为什么”，不写“怎么做”**：生成步骤在 `SKILL.md`，评审规则、扣分点、话术库放 `references/`。
- **禁用词放 `config/gates.yaml`，不放 `references/`**：程序读配置，模型读参考，两者不混。

---

## 8. 贡献路径 B：修改引擎

### 新增一条门禁规则

1. `l1_governance/rules/<name>.py` 实现 `check(draft, contract, session, config) -> list[GateFailure]`。
2. `l1_governance/rules/__init__.py` 的 `RULES` 字典加一行映射。
3. `config/gates.yaml` 注册 `enabled` 与 `weight`（以及该规则需要的其他键）。
4. 补 `tests/unit/` 正反用例。
5. 若影响通过率，评估是否调整 `pass_threshold`。

**`gate_runner.py`、`scoring.py` 不需要改**——它们按 `RULES` 遍历、按权重汇总。

### 调整路由

只改 `config/routing.yaml`。注意置信度算法是 **命中词数 / 关键词总数**，关键词表越长，单个词命中越难达到阈值。每个技能建议只保留 **2–3 个最具区分度的关键词**。

### 接入新的 Agent 宿主

在 `l4_interface/agent_host.py` 加适配函数，**只做协议转换**，内部调 `Orchestrator.run()`。不得在 L4 写路由或门禁逻辑。

---

## 9. 提交与 PR 规范

### Commit message

用 Conventional Commits 风格：

```text
<type>(<scope>): <subject>

feat(l1): add fact_check rule for rank patterns
fix(l4): narrow decision.skill to str before load
docs(skills): add national-scholarship skill
chore(config): lower routing threshold to 0.5
```

`type` 取 `feat` / `fix` / `docs` / `test` / `refactor` / `chore` / `perf`。`scope` 用层名（`l1`–`l4`、`shared`、`skills`）或模块名。

### PR 检查清单

- [ ] `uv run poe check` 全绿
- [ ] 新增行为有对应测试
- [ ] 改了 `shared/types.py` 或 `SKILL.md` 契约字段，同步更新了开发文档
- [ ] 有用户可见的变更，更新了 `CHANGELOG.md` 的 `[Unreleased]`
- [ ] 破坏性变更在 PR 描述和 `CHANGELOG.md` 中都显式标注了

### 破坏性变更

以下情况视为破坏性，必须**升 major 版本**并在 `CHANGELOG.md` 写迁移步骤：

- 修改 `SkillContract` 字段语义
- 删除或重命名 `shared/types.py` 中的公开数据类
- 修改 `SKILL.md` frontmatter 的必需字段
- 删除已有技能包

---

## 10. 常见坑

### Windows 编码问题（高频）

- **不要用 PowerShell 的 `cat > file <<'EOF'` 或 heredoc 写 Python 文件**。PowerShell 不支持 Bash heredoc，会把内容写坏或写成空文件。
- **所有 `.py` / `.md` / `.json` / `.yaml` 文件保存为 UTF-8（无 BOM）**。
- 用 `utf-8-sig` 读取可能带 BOM 的文件（`shared/config.py`、`loader.py`、`registry.py` 已这样做）。
- 终端里看中文文件乱码是 PowerShell 用 GBK 解码 UTF-8 的显示问题，文件本身没坏。用 `uv run python -c "print(open('path', encoding='utf-8').read())"` 读取。

### `ImportError: cannot import name 'main'`

`[project.scripts]` 声明的入口点找不到函数。检查 `cli.py` 里 `def main` 是否**在模块顶层**（不在 `if` 块里），以及文件内容是否被误写成别的模块。用 `uv run python -c "import skillforge.l4_interface.cli as m; print('main' in dir(m))"` 验证。

### `Import "openai" could not be resolved`

`openai` 在 `[api]` extra 里。开发时 `uv sync --extra api`，或在 import 处加 `# type: ignore[import-not-found]`。

### `JSONDecodeError: Expecting value: line 1 column 1`

文件是空的或带 BOM。用 VS Code 重写为 UTF-8 无 BOM。

### `技能包 validate 失败`

- `name` 与目录名不一致
- `metadata` 缺 `required_fields` / `output` / `sections`
- `index.json` 的 `path` 写错
- frontmatter 不在文件第一行

---

## 11. 行为准则

- 对事不对人，评审针对代码和设计，不针对贡献者。
- 不确定的设计先开 issue 讨论，不要直接提大 PR。
- 技能包内容涉及真实评审规则时，注明依据（学校通知、赛事章程），不要凭印象写。
- 生成的草稿永远是草稿，**不编造事实**是这个项目的底线，贡献的技能包也必须遵守。

---

有问题开 issue，或直接在 PR 里 @ 维护者。
