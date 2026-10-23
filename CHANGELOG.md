# Changelog

本文件格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## \[Unreleased]

- 修复任意代码围栏绕过PPT正文预算的问题：还原评论式要点和单页JSON包装，拒绝将PPT生成脚本写入幻灯片。
- 新增模板页面职责计划，生成、重写和门禁统一使用；指定代码页直接保留用户提供的领域代码。

- 修复 PPT 按文章1800字门禁检查的问题；新增单页预算、超量反馈重试和强制结构校验。
- 模板导出按章节复用页面，保持 Verilog 代码块完整，对比页分栏；长标题使用可用空间与换行，保留24磅下限。
- PPT 编辑代理生成时检查计划页数，CLI 始终使用显式 `--skill`；拒绝在缺少截图时描述图中标注。

- 缺少 LLM 时在采集完成、进入生成前报错，保留无 LLM 的澄清与追问。
- API 在应用创建时构造并复用 Orchestrator，减少配置加载与组件重复创建。
- 渲染期复用 shared 路径校验，并强制匹配契约后缀；CLI 保留绝对路径支持，API 继续拒绝绝对路径。
- API 门禁辅助函数补充类型标注，FastAPI 版本读取统一的 `__version__`。

- 新增带 TTL 和容量上限的会话存储层，支持通过 `session_id` 续传多轮采集。

- 修复 `FixedWindowRateLimiter` 过期 bucket 不清理导致的内存增长；按间隔惰性清理，docstring 明确单进程内存限流假设。

- `OpenAICompatibleClient` 新增 `complete_system` 实现，修复文档与实现不一致；与 `complete` 共用重试与结果校验逻辑。

### Added

- 新增 Markdown 渲染器，支持通过 `out_path` 保存 UTF-8 `.md` 文件，复用输出目录与契约后缀校验。
- 新增 `examples/ppt-request.json`，补齐数字电路 PPT 技能路由关键词。
- README 补充 Ollama 本地接入、Markdown 文件输出及 PPT 示例运行说明。
- LLM 调用新增可配置指数退避重试（默认最多重试 3 次），覆盖超时、限流、连接错误与 5xx；禁用 SDK 内置重试以避免叠加。
- 新增 `LLMError`，统一调用失败与空内容异常；TaskQueue 规范化第三方客户端异常，保持整轮失败并由 L3 统一降级。

### Fixed

- CLI 与 `run_file` 在 Markdown 交付后显示正文，修复仅提示成功却看不到草稿的问题。
- 修正文档中测试技能输出为 `.docx`、请求未命中路由及仅注册一个技能的过时描述。

## \[0.1.0] - 2026-10-21

首个可用版本：四层引擎、五个门禁规则、三个技能包，以及一轮安全加固。

### 引擎

#### Added

**L1 门禁层**

- `cliche_check`：套话检测，词表来自 `gates.yaml` 的 `phrases`，同一章节同一短语只记一条
- `format_check`：章节齐全性、顺序一致性、总字数区间（目标值优先级：`session.collected` > 配置 > 兜底）
- `repetition_check`：单行重复超过 `max_repeat` 记 warning，整章重复率超过 `max_ratio` 记 error
- `sensitive_check`：敏感词检测，词表独立（`gates.yaml` 的 `words`），默认 severity 为 error
- `placeholder_check`：检测 `TODO`、`待补充`、`XXX`、`【】` 等占位符残留
- `GateRunner`：按 `gates.yaml` 的 `enabled` 开关逐条执行规则，单条规则异常降级为 warning，不阻断整轮
- `scoring.compute`：加权汇总为 `GateResult`，每条 error 扣 0.2，warning 不计分
- `observability.log_gate_result`：每次门禁输出一行结构化日志，含 `score`、`rules_failed`

**L2 能力层**

- `Loader`：解析 `SKILL.md` 的 YAML frontmatter 与正文，按需加载 `references/*.md`
- `registry.validate_all`：校验 `index.json` 与各 `SKILL.md` 的 `name`、目录名、契约字段一致性
- `prompt_builder`：拆分 `build_system_prompt()` 与 `build_user_prompt()`，`build_section_prompt()` 保留为单字符串兼容接口
- `sanitize`：`filter_collected` 白名单过滤、`sanitize_field_value` 去控制字符、`truncate` 截断并中和边界标记
- `DocxRenderer`：`DraftDocument` → `.docx`，零参数构造，静态导入 `docx_common`
- `docx_common`：随包安装的受信任排版函数，宋体/黑体、首行缩进、两端对齐

**L3 编排层**

- `Router`：关键词匹配 + 置信度打分（命中词数 / 关键词总数），低置信度或分差过小触发澄清
- `StateMachine`：显式迁移表，非法迁移抛 `SkillForgeError`，终态不接受任何事件
- `SessionManager`：会话创建、字段合并、草稿设置、重写轮次递增
- `TaskQueue`：分章并发生成，优先走 `complete_system`，回退到单字符串 `complete`
- `Rewriter`：依据 `GateResult` 只重写 severity 为 error 的章节，其余保留
- `Fallback`：澄清、追问、模板兜底三种降级，按异常类型分派
- `Orchestrator`：串起路由 → 采集 → 生成 → 门禁 → 重写 → 渲染的完整状态机

**L4 接入层**

- CLI：`skillforge run`、`skillforge validate`、`skillforge skills list`，`run` 支持交互式追问
- FastAPI：`POST /generate`、`GET /healthz`，请求/响应用 Pydantic 模型
- `OpenAICompatibleClient`：OpenAI 兼容接口，同时实现 `complete` 与 `complete_system`
- `agent_host.handle`：供 Claude/Codex/Cursor 等宿主的纯函数接口

**shared**

- `types`：`SkillContract`、`GateResult`、`SessionState`、`RouteDecision`、`DraftDocument` 等跨层契约
- `config`：加载 `config/*.yaml`，支持 `SKILLFORGE_<SECTION>_<KEY>` 环境变量覆盖，启动时 schema 校验
- `errors`：`SkillForgeError` 及其子类，降级策略按异常类型分派
- `logger`：JSON lines 结构化日志，必带 `trace_id`、`session_id`、`layer`
- `paths`：`resolve_output_path`、`ensure_parent`、`PathValidationError`，API 与 CLI 共用
- `version`：引擎版本单一来源

**工具链与配置**

- `config/settings.yaml`、`routing.yaml`、`gates.yaml`、`logging.yaml` 四个配置文件
- Poe 任务：`lint`、`format`、`fmt-check`、`validate`、`test`、`check`（四步串联）
- Ruff 统一 lint 与 format，行宽 100，目标 py311
- pytest + pytest-cov，`--cov=skillforge --cov-report=term-missing`
- `.github/workflows/ci.yml`：矩阵 Python 3.11 / 3.12 / 3.13，`uv sync --group dev` 后跑 `uv run poe check`
- 新增 mypy 类型检查任务 `poe typecheck`，并入 `poe check` 检查链
- `[dependency-groups] dev` 新增 `mypy>=1.10`
- `[tool.mypy]` 配置：`strict = false` 起步、`ignore_missing_imports = true` 兼容 `[api]` extra 的可选依赖
- 编排层接入结构化日志：`route.decided` / `route.clarify` / `collect.missing` /
  `generate.start` / `generate.done` / `gate.round` / `rewrite.round` /
  `run.delivered` / `run.fallback`，统一携带 `trace_id`、`session_id`、`layer`
- `Orchestrator.run` 在 `trace_id` 为空时自动生成 UUID；`run_file` 显式生成并传入
- API `/generate` 从 `config.logging.trace_header`（默认 `X-Trace-Id`）读取请求头作为 trace_id
- `get_logger` 支持 `sample_rate < 1.0` 的采样（`0.0` 全丢，仅测试用）

#### Changed

- `openai`、`fastapi`、`pydantic`、`uvicorn` 下沉到 `[api]` extra，核心依赖仅 `python-docx`、`pyyaml`；`validate` 与 `skills list` 不需要装 LLM SDK
- `DocxRenderer.__init__` 不再接收 `skills_root`，移除对技能包路径的依赖
- `LLMClient` 协议只声明必需的 `complete`；`complete_system` 拆入独立的 `SystemPromptLLMClient` 协议，用 `isinstance` 探测，不影响只实现 `complete` 的 stub
- `gates.yaml` 权重重新分配为总和 1.0（cliche 0.25、format 0.25、repetition 0.15、sensitive 0.20、placeholder 0.15），`pass_threshold` 调整为 0.80
- `_validate_gates` 扩展校验 `sensitive_check.words` 与 `placeholder_check.markers` 类型
- `requires-python` 从 `>=3.10` 收紧到 `>=3.11`，与 `.python-version`、Ruff `target-version` 对齐
- 添加`python-dotenv`，支持读取`.env`文件
- 添加对`pptx`格式的文档的支持

#### Fixed

- Windows 下 `index.json` 带 BOM 导致 `JSONDecodeError`：所有文件读取改用 `utf-8-sig`
- PowerShell heredoc 写 Python 文件导致内容错乱：文档明确要求用编辑器保存为 UTF-8（无 BOM）
- `docx.Document` 是工厂函数而非类，类型注解改用 `docx.document.Document`
- `BaseStyle` 存根缺 `font` 属性：`cast(ParagraphStyle, ...)` 收窄
- `rPr`/`rFonts` 可能为 `None`：改用 `get_or_add_rPr()` / `get_or_add_rFonts()`
- `RouteDecision.skill` 与 `allowed_root` 的类型收窄，消除 `str | None` 赋给 `str` 的错误
- `api.py` 的 `from __future__ import annotations` 导致 FastAPI 把 body 误判为查询参数（422）：该文件移除该导入
- `api.py` 的 `create_app(llm=...)` 补 `LLMClient | None` 类型标注
- `state_machine.py` 用 `allowed is None` 替代 `not allowed`，消除 Optional 收窄歧义
- `llm_client.py` 移除多余的 `# type: ignore[import-not-found]`（`ignore_missing_imports` 已覆盖）
- `JsonFormatter` 之前只输出硬编码的 `trace_id` / `session_id` / `layer`，
  `observability.log_gate_result` 传入的 `passed`、`score`、`rules_failed`
  等业务字段被静默丢弃；改为输出所有 extra 字段（logging 标准属性除外），
  值为 `None` 的字段跳过
- `orchestrator.run_file` 默认输出文件名按技能 `output` 决定：docx 技能用 `output.docx`，pptx 技能用 `output.pptx`，markdown 技能不落盘。之前固定 `output.docx` 导致 pptx 技能在后缀校验时抛 `RenderError`
- 删除 `api.py` 中未被调用的 `_resolve_out_path`（`/generate` 实际使用 `shared/paths.py` 的 `resolve_output_path`）
- `GenerateRequest.out_path` 描述更新为支持 `.docx` / `.pptx`

#### Security

- **路径逃逸**：`index.json` 的 `entry["path"]` 经 `_resolve_entry_path` 校验，拒绝绝对路径、`..` 与符号链接逃逸；`references/*.md` 逐个做 `is_relative_to(skills_root)` 检查，越界跳过；`validate_all` 复用同一校验，错误信息不含绝对路径
- **动态代码执行**：`DocxRenderer` 不再通过 `importlib` 执行 `skills/utils/docx_common.py`，改为静态导入受信任的 `skillforge/l2_capability/renderer/docx_common.py`；`skills/utils/docx_common.py` 保留供技能脚本复用，加注释说明不再被渲染器加载
- **API 鉴权**：`create_app(api_key=...)` 或 `SKILLFORGE_API_KEY` 环境变量，`X-API-Key` 头经 `secrets.compare_digest` 校验；缺失或不一致返回 401，错误响应不含密钥；未配 key 时不会静默关闭鉴权
- **限流**：`FixedWindowRateLimiter` 实现 per-key / per-IP 固定窗口限流，超限返回 429 + `Retry-After`；限流 bucket 用 key 的 SHA-256 哈希，原始 key 不进任何持久结构；`rate_limit_per_minute=0` 仅用于测试/本地
- **输出路径白名单**：`create_app(allowed_output_dir=...)` 或 `SKILLFORGE_OUTPUT_DIR`；未配置时请求携带 `out_path` 返回 403；配置后拒绝绝对路径、`..`、非 `.docx`、符号链接逃逸、超过 3 层深度、含 NUL/控制字符；响应只回显相对路径，不泄露服务端绝对路径
- **Prompt injection 边界**：`sanitize.py` 的白名单过滤 + `DATA_BEGIN`/`DATA_END` 显式边界 + 伪造标记中和；`Orchestrator` 两处 merge 均过 `filter_collected`，契约外字段进不了 session；`Rewriter` 对门禁 `evidence` 清洗并包边界，防止间接注入
- **服务端就绪检查**：既无 `llm` 又无 `api_key` 时 `/generate` 返回 503，避免“只缺 key 就静默放行”的降级漏洞

### 技能包

#### Added

- `thesis-proposal`：毕业论文开题报告，七章结构，含 `references/review-criteria.md`（7 条评审扣分点）
- `national-scholarship`：国家奖学金申请书，六章结构，`fact_check` 权重高于默认，含 `references/review-criteria.md`
- `test-skill`：最小测试技能，用于验证路由、门禁、prompt 边界链路

#### Changed

- 三个技能包的 `SKILL.md` 均声明 `required_fields`、`output`、`sections` 契约字段，由 `registry.validate_all` 校验

### Tests

- 门禁规则：`test_cliche_check`、`test_format_check`、`test_repetition_check`、`test_sensitive_check`、`test_placeholder_check`，每条规则覆盖命中 / 未命中 / 配置覆盖 / 默认兜底
- 编排层：`test_router`、`test_state_machine`、`test_session`、`test_task_queue`、`test_rewrite`、`test_orchestrator_filter`
- 能力层：`test_loader_path`（路径逃逸）、`test_docx_renderer`（功能 + 不执行 skills 代码）、`test_prompt_boundary`、`test_rewrite_sanitize`、`test_sanitize`
- 接入层：`test_api_security`（鉴权 / 限流 / 401 / 429）、`test_api_out_path`（403 / 400 / 放行 / 不泄露绝对路径）、`test_llm_client_parse`、`test_cli`
- 基础设施：`test_config`（加载 / 缺字段 / 非映射 / 环境变量覆盖 / `_validate_gates`）、`test_registry`
- 集成：`test_gate_flow`、`test_format_gate_flow`、`test_cliche_gate_flow`
- 新增 `test_orchestrator_run_file.py`：覆盖 pptx / docx / markdown 三种 `output` 的默认输出路径

## \[0.0.1] - 2026-10-20

### 引擎

#### Added

- 项目骨架：`pyproject.toml`、`.gitignore`、`README.md`、`LICENSE`
- `uv` 环境管理，`uv.lock` 锁定依赖
- Ruff 格式化与 lint 配置
- Poe 任务：`lint`、`format`、`fmt-check`、`validate`、`test`
- `skillforge/shared/version.py` 作为版本单一来源
- 四层目录骨架：`l1_governance/`、`l2_capability/`、`l3_orchestration/`、`l4_interface/`、`shared/`
- `skills/` 目录骨架：`index.json`、`version.json`、`SKILL.md`、`subskills/`
- 添加SKILL：`hnu-digital-circuit-seminar-ppt`
