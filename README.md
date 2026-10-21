# SkillForge

垂直领域 AI 技能包的编排与治理运行时：路由匹配技能 → 契约驱动追问 → 分章生成 → 门禁质检 → 定向重写 → 导出 docx。

技能包以数据形式声明，生成结果必须过独立门禁，**不编造事实**是这个项目的底线。它不试图"一键生成完美文书"，而是把"缺什么信息、哪里不合格、该改哪一章"显式暴露出来，让人做最后判断。

## 特性

- **技能包即数据**：技能以 `skills/subskills/<name>/SKILL.md`（YAML frontmatter + 正文）声明，`skills/index.json` 注册，不含可执行代码。引擎不会动态执行 `skills/` 下的任何 `.py`。
- **四层引擎**：L4 接入 → L3 编排 → L2 能力 → L1 门禁，单向依赖，`shared/` 提供跨层契约。
- **独立门禁**：5 条规则（`cliche_check` 套话 / `format_check` 格式 / `repetition_check` 重复 / `sensitive_check` 敏感词 / `placeholder_check` 占位符）独立于生成器质检草稿，按权重打分，只对 error 级问题定向重写失败章节。
- **三类宿主**：CLI（`skillforge run`）、FastAPI（`POST /generate`）、Agent 宿主纯函数接口（`agent_host.handle`）。
- **安全内置**：API key 鉴权、per-key/per-IP 固定窗口限流、输出路径白名单、prompt injection 边界清洗（`DATA_BEGIN`/`DATA_END` + 伪造标记中和）、`index.json` 路径不逃逸、结构化日志 + trace_id 贯通。

## 环境要求

- Python **3.11+**
- [uv](https://docs.astral.sh/uv/)

## 安装

```bash
git clone https://github.com/Skrepy0/skillforge.git
cd skillforge

# 核心依赖（python-docx、python-dotenv、pyyaml）+ 开发工具（ruff / mypy / pytest / poe）
uv sync

# 需要 API、跑 API 测试或真实调用 LLM 时
uv sync --extra api
```

### 配置环境变量

复制 `.env.example` 为 `.env`，填入真实值：

```bash
# Linux/macOS
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

运行时**自动加载** `.env`——`load_project_dotenv()` 从当前工作目录向上查找第一个 `.env` 并加载，不需要 `uv run --env-file`。**shell 已设置的变量优先**，`.env` 不会覆盖它们；CI 注入的 secret 不会被本地 `.env` 覆盖。

`.env` 已在 `.gitignore` 中，不会被提交。

### LLM 配置

`OpenAICompatibleClient` 走 OpenAI 兼容接口，读取以下环境变量：

| 变量               | 说明                             |
| :----------------- | :------------------------------- |
| `OPENAI_API_KEY`   | LLM 提供商的 API key（**必需**） |
| `OPENAI_BASE_URL`  | 兼容端点（可选，默认官方端点）   |
| `SKILLFORGE_MODEL` | 模型名，默认 `gpt-4o-mini`       |

优先级：shell 环境变量 > `.env` > 代码默认值。

### API 服务端配置

FastAPI 接入额外读取：

| 变量                               | 说明                                                       |
| :--------------------------------- | :--------------------------------------------------------- |
| `SKILLFORGE_API_KEY`               | `/generate` 的 `X-API-Key` 鉴权密钥                        |
| `SKILLFORGE_RATE_LIMIT_PER_MINUTE` | 每分钟请求上限，默认 30，`0` 表示禁用                      |
| `SKILLFORGE_OUTPUT_DIR`            | 允许的文件输出目录；未配置时携带 `out_path` 的请求返回 403 |

## 快速开始（CLI）

当前仓库只注册了一个测试技能 `test-skill`（`required_fields: ["topic"]`），用于验证路由、门禁、prompt 边界链路。

```bash
# 列出已注册技能
uv run skillforge skills list

# 校验技能包契约与 index.json 一致性
uv run skillforge validate
```

创建 `input.json`：

**Linux / macOS**

```bash
cat > input.json <<'EOF'
{
  "request": "帮我写点东西",
  "collected": {"topic": "示例主题"},
  "out_path": "out.docx"
}
EOF
```

**Windows PowerShell**（无 BOM）

```powershell
@'
{
  "request": "帮我写点东西",
  "collected": {"topic": "示例主题"},
  "out_path": "out.docx"
}
'@ | Set-Content -Encoding utf8NoBOM input.json
```

执行生成：

```bash
uv run skillforge run --skill test-skill --input input.json

# 限制输出目录（也可用 SKILLFORGE_OUTPUT_DIR，命令行参数优先）
uv run skillforge run --skill test-skill --input input.json --output-dir ./out
```

`.env` 自动加载，无需 `--env-file`。

### `input.json` 字段

| 字段        | 类型             | 说明                                                        |
| :---------- | :--------------- | :---------------------------------------------------------- |
| `request`   | `str`            | 用户原始请求，路由据此匹配技能                              |
| `collected` | `dict[str, str]` | 已采集字段，**只保留目标技能 `required_fields` 中声明的键** |
| `out_path`  | `str \| null`    | docx 输出相对路径；省略或为 `null` 时只返回草稿，不落盘     |

`collected` 的字段由目标技能的 `required_fields` 决定，**契约外字段会被白名单过滤丢弃**。用 `uv run skillforge skills list` 查看已注册技能，或直接读对应 `SKILL.md` 的 `required_fields`。

### CLI 输出

成功时输出 JSON：

```json
{
  "status": "delivered",
  "session_id": "a1b2...",
  "skill": "test-skill",
  "gate": { "passed": true, "score": 1.0, "threshold": 0.8 },
  "failures": null,
  "output_path": "out.docx"
}
```

> 实际输出中 `gate` 是 `GateResult` 数据类，被 `json.dumps(..., default=str)` 序列化为字符串。这里展示的是逻辑结构，便于阅读。

缺信息时 `status` 为 `needs_input`，`missing` 列出缺失字段，CLI 会**交互式追问**并读取终端输入后继续。门禁不通过且重写轮次用尽时 `status` 为 `fallback`，返回降级模板和失败原因。

返回码：`0` 交付成功，`1` 降级/失败，`2` LLM 初始化失败，`3` 信息不足。

### 说明

- `skillforge run` **需要装 `[api]` extra**——它使用 `OpenAICompatibleClient`，依赖 `openai` 包。
- 生成结果是**草稿**，`gate` 与 `failures` 随 JSON 输出，提交前须自行核对。
- `out_path` 走 `shared/paths.py` 校验：拒绝 `..`、非 `.docx`、含控制字符（无论是否配置输出根目录）。**CLI 模式未配置输出根目录时，绝对路径和深层路径原样放行**——本地工具，用户即操作者。如需限制，设 `SKILLFORGE_OUTPUT_DIR` 或加 `--output-dir`（命令行参数优先于环境变量），此时绝对路径、符号链接逃逸、超过 3 层的相对路径都会被拒。API 模式未配置 `SKILLFORGE_OUTPUT_DIR` 时，携带 `out_path` 的请求返回 **403**；已配置时，绝对路径、`..`、符号链接逃逸等非法路径返回 **400**。

## API 模式

`create_app` 的 `llm` 参数不会自动构造——**零参调用得到的是一个 `/generate` 永远返回 503 的应用**（`check_ready` 拦在入口）。生产用法是写一个入口脚本，显式传入 `OpenAICompatibleClient`：

```python
# server.py
from skillforge.l4_interface.api import create_app
from skillforge.l4_interface.llm_client import OpenAICompatibleClient

app = create_app(
    llm=OpenAICompatibleClient(),  # 未传时 /generate 返回 503
    api_key="...",  # 或 SKILLFORGE_API_KEY
    rate_limit_per_minute=30,  # 或 SKILLFORGE_RATE_LIMIT_PER_MINUTE
    allowed_output_dir="./out",  # 或 SKILLFORGE_OUTPUT_DIR
)
```

启动：

```bash
uv run --extra api uvicorn server:app --port 8000
```

`.env` 由 `create_app()` 内部自动加载，启动命令不需要 `--env-file`。

端点：

| 端点             | 鉴权        | 说明                                   |
| :--------------- | :---------- | :------------------------------------- |
| `POST /generate` | `X-API-Key` | 生成草稿，超限返回 429 + `Retry-After` |
| `GET /healthz`   | 无          | 健康检查，不需要鉴权                   |

调用示例：

```bash
# 把 <your-api-key> 换成 .env 里 SKILLFORGE_API_KEY 的值
curl -X POST http://127.0.0.1:8000/generate \
  -H "X-API-Key: <your-api-key>" \
  -H "X-Trace-Id: trace-123" \
  -H "Content-Type: application/json" \
  -d '{"request": "帮我写点东西", "collected": {"topic": "示例主题"}}'
```

> **注意**：`.env` 由 Python 进程加载，**shell 里读不到 `$SKILLFORGE_API_KEY`**。要么 curl 里直接填 key，要么在启动 uvicorn 的 shell 里先 `source .env`（Windows 用 `. .\.env` 需配合脚本，或直接填 key 更省事）。

响应里的 `output_path` 只回显**相对路径**，不泄露服务端绝对路径。`X-Trace-Id` 头可选，为空时服务端自动生成 UUID，并贯通该请求的所有日志。

## Agent 宿主

`agent_host.handle` 是给 Claude/Codex/Cursor 等宿主的纯函数接口，不阻塞、不 I/O：

```python
from skillforge.l4_interface.agent_host import handle
from skillforge.l4_interface.llm_client import OpenAICompatibleClient

result = handle(
    request="帮我写点东西",
    collected={"topic": "示例主题"},
    llm=OpenAICompatibleClient(),
)
if result["status"] == "needs_input":
    # 宿主负责向用户追问，补全后重调
    ...
```

`handle` 内部同样调用 `load_project_dotenv()`，不需要额外加载 `.env`。

## 项目结构

```text
skillforge/
├── l1_governance/    # 门禁规则 + 打分（GateRunner / scoring / observability）
├── l2_capability/    # 技能加载、prompt 组装、sanitize、docx 渲染
├── l3_orchestration/ # 路由、状态机、并发生成、重写、降级
├── l4_interface/     # CLI / FastAPI / Agent 宿主 / LLM 客户端
└── shared/           # 契约类型、配置、错误、日志、路径校验

skills/               # 技能包（index.json + subskills/<name>/SKILL.md）
config/
├── settings.yaml     # 模型、超时、重写轮次、并发
├── routing.yaml      # 关键词、相似度阈值、澄清策略
├── gates.yaml        # 5 条规则的开关、权重、词表
└── logging.yaml      # 级别、采样率、trace 头名

tests/                # unit + integration（不触网，LLM mock）
docs/CONTRIBUTING.md  # 贡献指南
CHANGELOG.md          # 变更记录
.env.example          # 环境变量模板
```

## 开发

```bash
uv run poe format    # 格式化（会实际修改文件）
uv run poe check     # lint → fmt-check → typecheck → validate → test
```

`poe check` 不含 `format`，五步都是只读检查，本地和 CI 结果一致。提交前先跑 `poe format` 再跑 `poe check`。

### 测试

```bash
uv run pytest tests/unit -q                       # 只跑单元
uv run pytest -q                                  # 全量，--cov 已在 addopts 中
uv run pytest tests/unit/test_api_security.py -q  # 需要 --extra api
```

测试不触网，LLM 调用通过 mock 固定。API 测试用 `pytest.importorskip("fastapi")` 保护，没装 `[api]` extra 时整体跳过。

贡献指南见 [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)，变更记录见 [`CHANGELOG.md`](CHANGELOG.md)。

## License

[MIT](./LICENSE)
