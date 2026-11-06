# 个人调度助手

调度助手运行在已有 FastAPI 进程内，使用同一个 `Scheduler`。前端「调度助手」提供对话、工作流查询、草案工作台和执行回执。它可以查询任务与运行记录、准备新工作流、修改现有工作流、申请立即运行。

## 配置与启动

安装可选依赖：

```bash
pip install "schedflow[agent]"
```

源码环境使用 `uv sync --extra agent`。登录后进入「系统设置 → AI Agent」，选择供应商、填写模型和密钥，测试连接并保存，然后打开 Agent 开关。聊天页也提供「Agent 设置」入口和即时启停开关。

页面预置 OpenAI、DeepSeek、阿里云百炼 Qwen、Moonshot Kimi、智谱 GLM、Anthropic Claude、Google Gemini，以及自定义服务。模型建议是 2026-10-11 官方文档核实的示例，账户是否可用以供应商为准；模型 ID 与 API 根地址均可编辑。百炼地域与 Workspace ID 必须与密钥匹配。

OpenAI 预置使用 Responses，Claude 使用原生 Messages，其余使用各自的兼容协议参数。工具调用中的 reasoning_content、Gemini thought signature 和原生协议回传数据只在当次回合内保留，不展示为前端消息或保存为会话内容。DeepSeek 预置明确关闭 thinking：其思考模式要求跨用户回合保存并回传完整 reasoning_content，而本助手不持久化这些内容。连接测试用固定的无业务工具及其结果，验证完整工具循环，不发送工作流、日志、变量或个人会话。

Kimi 预置使用 `kimi-k2.6`，关闭思考模式。`kimi-k3` 和 `kimi-k2.7-code` 系列要求跨用户回合完整保留推理内容，当前助手不支持这些型号，启用或测试时会提示改用 K2.6；已有这类配置仍可停用。其他自填模型需要满足同样的历史兼容条件；自定义网关不能绕过供应商模型自身的协议要求。

密钥只写入服务端私有 SQLite 元数据库，查询接口只返回是否已配置。输入留空保留当前密钥；切换供应商、协议、地址或 Workspace 时必须填写新密钥或明确清除，防止将旧密钥发送到新服务。保护元数据库及其备份的文件访问权限；前端不会将模型密钥存入 localStorage。

保存后立即生效，数据库配置优先于环境变量，重启继续恢复。保存配置或关闭 Agent 会取消当前模型回复并保存终态；已接受的工作流继续执行。关闭期间可查看历史，不能提交新对话或新的草案确认。连接测试不会保存配置或自动启用。

也可使用环境变量启动；在尚未通过页面保存配置时，项目 `.env` 中的设置会生效。旧兼容服务配置保持原协议：

```dotenv
SCHEDFLOW_AGENT_ENABLED=true
SCHEDFLOW_AGENT_PROVIDER=custom
SCHEDFLOW_AGENT_PROTOCOL=chat_completions
SCHEDFLOW_AGENT_BASE_URL=https://api.openai.com/v1
SCHEDFLOW_AGENT_MODEL=your-model
SCHEDFLOW_AGENT_API_KEY=your-key
SCHEDFLOW_AGENT_ALLOW_CODE_GENERATION=false
```

本地兼容服务可选择「自定义」并使用 HTTP 本地地址；是否需要密钥由服务决定。地址应为 API 根路径（通常以 `/v1` 结尾），不包含 `/chat/completions`、查询参数、userinfo 或密钥。环境变量修改需要重启；已有页面配置时通过页面修改。通过 `schedflow-backend` 启动，或者从 `schedflow.api` 导入 `create_app(Scheduler())`；仅提供 REST 接口的 `schedflow.api.rest.create_app` 不挂载助手。

仓库后端容器包含 Agent 依赖。已有镜像需重新构建，然后按现有 Docker Compose 的 `.env` 挂载方式配置并重启。

未启用或没有模型配置时，前端显示配置说明，不发送模型请求。开发测试使用模拟模型，不代表任何真实供应商已接通。供应商必须支持 `tools` 工具调用协议。

预算参数为 `SCHEDFLOW_AGENT_MAX_STEPS`（默认 8）、`SCHEDFLOW_AGENT_TIMEOUT`（默认 60 秒）和 `SCHEDFLOW_AGENT_MAX_TOKENS`（默认 4096）。一次会话同一时间只生成一个回答。

## 使用流程

1. 在助手页输入「列出每天执行的工作流」，或从任务详情进入「询问助手」，带入明确任务上下文。
2. 要求修改、新建或运行时，助手生成草案；查询不需要确认。
3. 在工作台检查概览、DAG、参数与代码、差异。代码预览不会执行代码。
4. 点击具体草案上的确认按钮。新建默认保存为暂停；选择启用会生成需要重新确认的版本。
5. 查看服务端操作回执。立即运行先显示已接收/运行中，只有实际执行日志完成后才显示成功或失败。

确认前可以继续描述对草案的调整，例如「把刚才的草案改到九点」。助手会保留同一个工作流身份并生成新版本，旧草案不能再提交；互不相关的新建草案可以同时保留。

修改已完成的一次性任务时，草案默认保存为暂停，保留原触发器或使用新指定的触发器。需要重新调度时，在工作台明确选择启用并确认。

可以尝试「查看上次失败的节点」「把这个工作流改到每天九点」「创建两个节点，第二个依赖第一个」「运行当前工作流」。涉及重名任务或信息不完整时，应先提供明确 ID、时区或节点内容。

## 执行与恢复

确认接口只接受草案 ID 和版本，模型没有批准工具。草案保存服务端规范化内容；确认时校验配置摘要，另一个页面编辑过任务后旧草案不能覆盖它。重复确认返回同一个操作，不重复执行。

运行使用确认时固定的任务配置、独立 execution ID 和已有日志系统；固定配置不等于冻结脚本文件或 Python 模块内容。停止回答只取消模型生成，不取消已经接受的工作流。调度任务依旧按原规则执行。

会话、事件、草案和操作存储在既有 SQLite 元数据库。刷新或重新进入会读取服务端状态，事件按序号恢复。跨 SQLite 与 JobStore 的提交无法建立共同事务；无法确认结果时标记 `unknown`，不会自动重试工作流。进程重启后未完成回答标记中断，Agent 手动执行不自动重跑；应查看真实任务配置、运行日志与操作回执后决定下一步。

删除会话用于清理对话记录；必要的最小操作账本保留用于去重与对账。删除会话不会删除工作流或撤销已经接受的执行。`SCHEDFLOW_AGENT_RETENTION_DAYS` 默认 30，后端启动时清理超过保留期且没有活动操作的会话内容。

## 功能边界

模型与调度工具的循环由 [LangGraph StateGraph](https://docs.langchain.com/oss/python/langgraph/graph-api) 编排，使用显式步数、超时与上下文预算。没有自动重试工具副作用或自动恢复执行的 checkpoint；会话、草案和确认账本仍由业务层管理。LangGraph 属于 `agent` 可选依赖，核心调度器不依赖它，不需要部署 LangGraph Server 或开通 LangSmith。项目没有启用远端追踪。

本功能面向个人部署，复用既有登录认证，不引入多租户或沙箱。工具固定为调度查询和草案准备，没有自由终端、文件读写、任意网络请求或 SQL 工具。任务本身仍使用 SchedFlow 现有可信代码执行机制。

组合 `and` 触发器最多搜索 1000 轮交集；超出时报告搜索达到上限，避免不相交的周期一直占用服务线程。达到上限并不证明调度永远没有交集，稀疏的组合应拆分或重新选择触发器。

默认关闭新代码生成；需要生成或改变可执行内容时显式设置 `SCHEDFLOW_AGENT_ALLOW_CODE_GENERATION=true`，并在草案工作台逐项检查命令、脚本、函数引用、回调和条件边。已有可信任务的查询和调度修改不需要模板登记。

页面的高级设置也可控制新代码生成、模型轮数、超时、输出 token 和历史保留时间。开启新代码生成不会绕过工作台确认。

模型服务会收到所需的对话与任务投影；执行日志投影应截断并脱敏。任务参数中不要直接存放凭据，优先使用现有变量配置。在部署时选择适合个人数据的模型服务。助手文字只是说明，任务状态与操作结果以结构化回执为准。

草案工具向模型返回摘要，已有脚本源码保留在服务端和用户确认工作台。选中的任务与待确认草案通过独立的数据消息提供，不拼入系统指令。

供应商协议依据官方文档：[OpenAI](https://developers.openai.com/api/docs/guides/function-calling)、[DeepSeek](https://api-docs.deepseek.com/guides/thinking_mode/)、[百炼](https://help.aliyun.com/zh/model-studio/more-tools)、[Kimi](https://platform.kimi.com/docs/guide/use-thinking-models)、[GLM](https://docs.bigmodel.cn/cn/guide/models/text/glm-5.3)、[Claude](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)、[Gemini](https://ai.google.dev/gemini-api/docs/openai)。协议适配通过模拟 HTTP 测试验证；没有真实供应商密钥时不代表已完成该账户的联网验收，请使用页面的连接测试。
