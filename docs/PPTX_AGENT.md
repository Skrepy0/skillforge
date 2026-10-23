# PPT 编辑代理

原来的流程是分章节生成纯文字，再由固定布局渲染。新增的可选模式让模型先读取模板，
再通过结构化操作编辑 PowerPoint，每次操作后重新检查当前状态。
默认保留模板的背景、装饰、配色和字体体系，允许调整排版。

## 从模板生成

在原命令上增加 `--pptx-agent`：

```powershell
uv run --extra api skillforge run --skill hnu-digital-circuit-seminar-ppt --input examples/ppt-request.json --output-dir ./outputs --pptx-agent
```

这个模式明确选择 `--skill` 指定的技能，先检查必填资料，读取该技能的实际模板页面。
模型获得用户资料、章节顺序、技能参考资料，以及每页元素的 ID、文字、字体、尺寸和位置。
它可以选择原页进行修改，也可以复制适合的模板页并删除示例页。
不再调用原来的分章节正文生成和固定文字填槽流程；也不使用原来的正文门禁评分。
生成任务还会按章节计划检查总页数，封面章节计入总数；结构问题或页数不符时不能声明完成。
事实准确性仍需人工复核。

## 普通 PPT 生成的页面预算

原来的生成命令（不加 `--pptx-agent`）也使用单页预算：一个章节对应一张内容页，
如果章节包含“封面”，则复用封面而不再额外增加一页。当前数电技能的12个章节导出12页。

封面已有题目和 `member_info` 时直接使用采集资料，不调用 LLM；同样适用于封面重写。
重复的封面题目会自动清理。封面成员说明使用独立容量检查和字号适配，不受正文每条20字的限制。

模板旁的 `template.bindings.json` 可用 `page_plan` 声明每页的 `purpose`（职责）、
`code_field`（已采集代码的来源字段）和 `avoid`（以 `|` 分隔的非本页主题词）。
数电技能将步骤二作为唯一的设计代码页，直接保留 `code_snippet`，不再让模型重新生成。
步骤三负责文件与编译检查，步骤四负责功能验证方案；这些职责同时用于提示词和格式门禁。

普通要点即便被模型放进 Markdown、text 或评论式 Python 围栏，也会按正文解析和校验；
只有真实源代码才进入代码文本框。`title/content/notes` 或 `heading/body` 单页 JSON 会提取正文，
题目和讲稿不会混入正文。Python/JS 的 PPT 生成脚本会被拒绝并反馈重写，不能通过代码围栏绕过要点预算。

- 每页最多3条简短要点，每条建议约20个汉字，总长最多80字符；20字不作为失败条件，必要的排错动作可完整表达并自动换行，导出时继续检查实际模板容量。重复的章节标题会清理。
- 代码块作为一个整体，最多12行、每行100字符；未加代码围栏的完整 Verilog 模块也作为整体处理。
- 生成器对超量页面最多尝试3次，仍不合格则明确失败，不再自动拆成几十页。
- PPT 格式门禁不再使用文章的1800字目标；页数和内容结构不能被其他规则的高分抵消。
- 用户明确未提供截图时，不允许描述图中红框或箭头；未提供实验结果时需标明预期。
- 模板正文按内容块重新排版，对比页分栏；标题优先使用可用空间和换行，最低24磅，
  仍放不下时明确报错，不再缩到约12磅。代码使用完整文本框，最低16磅。

这些限制用于阻止不合格稿件交付，不会通过截断正文来凑页数。视觉效果仍需实际渲染检查。

## 编辑已有 PPT

```powershell
uv run --extra api skillforge pptx-edit --input outputs/mux2-seminar.pptx --output outputs/mux2-edited.pptx --request "保留模板风格。封面标题合理分为两行，保持至少24磅；调整文本框，避免与成员信息重叠。"
```

必须另存为新文件。默认最多12轮，可以通过 `--max-rounds 20` 调整（2至30轮）。
每轮最多100条操作。模型无法执行 Python、shell 或原始 XML，也不能自行读取图片路径。

可用操作：

| 操作 | 能力 |
| --- | --- |
| `text` | 替换文字，沿用模板第一段/第一个文字片段的样式 |
| `style` | 字号、字体、粗体、颜色、段落对齐 |
| `move` | 位置和宽高；所有坐标与尺寸均为 pt |
| `add_text` | 添加文本框 |
| `add_shape` | 矩形、圆角矩形、椭圆、右箭头 |
| `add_image` | 插入用户明确提供的本地 PNG/JPEG 图片 |
| `clone_slide` / `delete_slide` | 复制模板整页、删除无关页 |
| `delete_shape` | 删除元素；被现有动画引用的元素暂不允许删除 |
| `fade_in` | 元素自动淡入，支持时长和延时 |

动画写入 PresentationML 的 `timing`、`animEffect` 和 `spTgt` 元素。
参考：[Microsoft AnimateEffect](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.presentation.animateeffect?view=openxml-3.0.1)。
当前不支持点击触发、运动路径或任意动画效果，也没有直接编辑组合形状内部元素的操作。
替换文字不保留原内容的混合行内格式；模板第一段的基本样式会保留。

模型必须返回结构化 JSON；兼容接口返回的完整 JSON 代码块也会被接受。
默认官方端点启用 JSON 模式；自定义 `OPENAI_BASE_URL` 端点默认只使用提示词约束和本地校验，
避免发送该端点可能不支持的 `response_format` 参数。支持该参数的端点可配置
`SKILLFORGE_JSON_MODE=true`，不支持的端点可显式设为 `false`。

## 提供图片

生成请求 JSON 可选增加 `assets`，路径相对于该请求 JSON 所在目录。
这是用户提供给编辑器的明确素材清单，不会交由模型访问任意磁盘路径：

```json
{
  "assets": {
    "waveform": "assets/waveform.png"
  }
}
```

编辑已有 PPT 时，用 `--assets examples/ppt-assets.json` 提供同样的别名映射：

```json
{"waveform": "assets/waveform.png"}
```

模型只能通过 `waveform` 等别名选择素材。当前不会自动搜索、生成或下载图片。

## 真实预览与检查

默认使用结构信息和启发式溢出检查，不代表模型已看到实际幻灯片。
字体继承、字体替换、重叠、图片裁切等问题需要真实渲染才能可靠判断。

安装 LibreOffice、Poppler，并确保 `soffice`、`pdftoppm` 在 PATH 中，使用支持图片输入的模型后：

```powershell
# 生成时
uv run --extra api skillforge run --skill hnu-digital-circuit-seminar-ppt --input examples/ppt-request.json --output-dir ./outputs --pptx-agent --pptx-preview

# 编辑时
uv run --extra api skillforge pptx-edit --input outputs/mux2-seminar.pptx --output outputs/mux2-edited.pptx --request "检查并修复文字溢出" --preview
```

开启后通过 LibreOffice 生成 PDF，再渲染为 PNG 提交给模型。每轮最多查看4页；
修改过的页面需要重新查看。缺少渲染器或客户端不支持视觉时明确报错。
LibreOffice 与 PowerPoint 的渲染可能有差异，动画实际播放仍需在目标软件检查。

## 输出与诊断

- 完成：输出目标 PPT 和同名 `.edit.json` 操作记录。
- 尚有结构问题或达到轮数上限：输出 `.review.pptx` 和 `.review.edit.json`，状态为
  `needs_review`，退出码1。不会覆盖正常目标文件。
- 非法操作：本批修改全部撤销，错误回传模型后重试。
- `.edit.json` 包括操作、执行反馈、最终页面信息、完成状态和是否启用真实预览。
  其中包含文稿内容，请按原始文稿相同方式管理。

可先只读检查任意 PPT：

```powershell
uv run skillforge pptx-inspect --input outputs/mux2-seminar.pptx
```

页面标识是 PPT 内的稳定 slide ID，元素标识是该页 shape ID，均不等于显示页码。
整个编辑请求最大180000字符（含任务和快照）；超过限制需要拆分文稿。
