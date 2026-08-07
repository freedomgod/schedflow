# SchedFlow 前端设计概要

> 本文档详细描述了 SchedFlow 工作流调度系统的功能特性和设计需求，供前端设计 AI 参考，以产出更现代化的 UI 设计方案。

---

## 一、产品定位

**SchedFlow** 是一个基于 DAG（有向无环图）的工作流调度管理平台。它将传统的定时任务从单一函数调用升级为可视化的 DAG 工作流——任务节点之间通过依赖边连接，支持并行执行、条件分支、重试机制，并提供完整的 Web 管理面板。

**目标用户**：Python 开发者、DevOps 工程师、数据工程师。

**核心体验关键词**：专业、高效、可视化、可控、可靠。

---

## 二、技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Python FastAPI |
| 前端框架 | 不限 |
| UI 组件库 | 不限 |
| 状态管理 | 不限 |
| 路由 | 不限 |
| DAG 可视化 | LogicFlow + dagre (自动布局) |
| 实时通信 | SSE (Server-Sent Events) |
| Markdown 渲染 | marked |
| 构建工具 | 不限 |

---

## 三、系统页面结构与功能清单

### 1. 认证系统

#### 1.1 系统初始化 (`/init-setup`)
- **场景**：首次启动系统时，没有任何管理员账号
- **功能**：创建首个管理员账号（用户名 + 密码，密码最短 6 位）
- **设计要点**：引导式初始化流程，简洁专业的欢迎页，强调安全性

#### 1.2 登录页 (`/login`)
- **功能**：用户名 + 密码登录，获取 JWT Token
- **设计要点**：居中登录卡片，品牌 Logo/名称，暗色/亮色适配

#### 1.3 路由守卫
- 未初始化 → 跳转 `/init-setup`
- 未登录 → 跳转 `/login`
- 已登录 → 自动跳过登录页

---

### 2. 仪表盘 (`/dashboard`) — 首页

**功能模块**：

| 模块 | 内容 |
|------|------|
| 欢迎横幅 | 系统标题 + 当前日期（中文格式） |
| 基础设施告警 | 当有 JobStore 或 Executor 启动失败时，展示红色 Alert 错误信息 |
| 统计卡片（4 个） | 调度器状态（RUNNING/PAUSED/STOPPED）、任务总数、运行中数量、已暂停数量 |
| 最近任务列表 | 最近 5 个任务，显示名称、执行器/存储后端、运行状态标签、下次运行时间，点击可跳转详情 |
| 快捷操作 | 管理任务、执行器配置、暂停/恢复调度器、系统设置等按钮 |

**设计要点**：一目了然的状态总览，关键指标突出显示，异常状态醒目提示。

---

### 3. 任务管理 (`/jobs`) — 核心模块

#### 3.1 任务列表页 (`/jobs`)
| 功能 | 说明 |
|------|------|
| 创建任务 | 按钮触发创建对话框，支持快速创建（选择任务类型：Python Callable / Python 文件 / Python 脚本 / Bash 命令）和 DAG 工作流创建 |
| 搜索过滤 | 按名称搜索、按状态筛选（运行中/已暂停）、按执行器筛选、按存储后端筛选 |
| 表格展示 | 名称、ID、状态开关（可一键切换运行/暂停）、执行器、存储后端、下次运行时间 |
| 行操作 | 详情、复制任务、删除任务 |
| 状态切换 | 列表中的开关可直接切换任务运行/暂停状态 |

#### 3.2 任务详情页 (`/jobs/:id`)
**只读模式**：
- 基本信息描述列表：ID、名称、状态标签、执行器（可点击查看配置）、存储后端（可点击查看配置）、下次运行时间（含 SSE 实时更新指示灯）、触发器（可点击查看配置）、Markdown 描述、DAG 工作流可视化
- DAG 只读画布：节点按状态着色（成功=绿、失败=红、跳过=橙、运行中=蓝、等待=灰），点击节点弹出节点信息侧边栏

**编辑模式**（3 个 Tab）：
| Tab | 编辑内容 |
|-----|---------|
| 基本信息 | 名称、运行/暂停开关、Markdown 描述（源码/预览双模式）、执行器选择、存储后端选择、高级选项（容错时间、合并执行、最大实例数） |
| 触发器配置 | 触发器类型选择（cron/interval/date/calendarinterval/and/or），动态表单配置参数 |
| 工作流 DAG | 可视化 DAG 编辑器（添加/删除/复制节点、拖拽连线、自动布局、缩放、右键菜单），点击节点/边弹出配置抽屉 |

**实时更新**：
- 通过 SSE (Server-Sent Events) 实时推送 `next_run_time` 变化
- 更新时"下次运行"指示灯闪烁动画

**配置弹窗**：点击执行器/存储后端/触发器名称时，弹出配置详情对话框。

---

### 4. 任务日志 (`/logs`) — 执行追踪

**三栏布局**：

| 栏 | 宽度 | 内容 |
|----|------|------|
| 左栏 | 220px | 任务选择器（搜索 + 任务列表，选中高亮） |
| 中栏 | 300px | 执行记录列表（按时间倒序），每条记录显示时间和节点状态摘要 |
| 右栏 | 弹性 | DAG 可视化画布 + 节点执行详情侧边抽屉 |

**交互流程**：
1. 左侧选择任务 → 中栏加载该任务的执行历史
2. 中栏选择某次执行 → 右栏渲染 DAG 图（节点按执行状态着色）
3. 点击 DAG 节点 → 右侧滑出执行详情抽屉（状态、耗时、结果、错误信息、stdout/stderr、退出码等）

**设计要点**：三栏布局清晰展现"任务→执行→节点"的层级关系，执行状态颜色编码一致，面板动画流畅。

---

### 5. 组件配置管理

#### 5.1 存储后端配置 (`/storage-config`)
| 功能 | 说明 |
|------|------|
| 统计卡片 | 已配置存储器数量、存储任务总数、可用存储类型数 |
| 新增存储器 | 选择存储类型（SQLAlchemy/Redis/MongoDB/Memory），填写配置参数 |
| 编辑存储器 | 修改类型和配置，可能触发数据迁移提示 |
| 删除存储器 | 确认删除（警告数据丢失） |
| 数据迁移 | 切换存储类型时的数据迁移功能 |

**支持的存储类型**：Memory、SQLAlchemy（支持 SQLite/PostgreSQL/MySQL 等）、Redis、MongoDB

#### 5.2 执行器配置 (`/executor-config`)
| 功能 | 说明 |
|------|------|
| 统计卡片 | 已配置执行器数量、引用任务总数、可用插件类型数 |
| 新增执行器 | 选择执行器类型（ThreadPool/ProcessPool/AsyncIO/Debug 等），填写配置参数 |
| 编辑执行器 | 修改类型和配置 |
| 删除执行器 | 确认删除 |

**支持的执行器类型**：ThreadPool、ProcessPool、AsyncIO、Gevent、Tornado、Twisted、Debug

---

### 6. 系统设置 (`/settings`)

| Tab | 内容 |
|-----|------|
| 主题设置 | 亮色/暗色模式切换（即时生效，持久化到后端） |
| 变量管理 | 键值对变量的增删改查（用于任务参数化配置），含变量名、值、描述、创建/更新时间 |
| API Key 管理 | 创建/查看/编辑/删除 API Key，创建时展示完整密钥（仅一次），显示密钥前缀、状态（启用/禁用）、最后使用时间、过期时间 |

---

## 四、核心技术特性

### 1. DAG 工作流编辑器

- **可视化画布**：基于 LogicFlow 的节点-边图编辑器
- **节点类型**（4 种，不同颜色区分）：
  - Python Callable（蓝色 `#409eff`）— 引用 Python 函数
  - Python File（蓝色）— 执行 Python 脚本文件
  - Python Snippet（蓝色）— 执行 Python 代码片段
  - Bash（红色 `#f56c6c`）— 执行 Shell 命令
- **节点图标**：每种类型有独特的 SVG 内嵌图标（Python Logo / Bash 终端图标）
- **交互操作**：
  - 拖拽移动节点
  - 从节点拖出连线创建依赖边
  - 点击节点/边弹出配置抽屉（480px 宽）
  - 右键菜单（复制、编辑、删除节点）
  - 滚轮缩放、按钮缩放、重置缩放
  - dagre 自动布局（从上到下拓扑排列）
- **节点配置**：
  - 名称、描述
  - 任务类型选择
  - 函数引用 / 脚本路径 / 脚本内容 / 命令
  - 键值对参数（支持 string/number/boolean 类型）
  - 完成回调函数引用
  - 最大重试次数
- **边配置**：名称、描述（预留条件函数配置）
- **只读模式**：节点仅可查看、不可编辑，节点按执行状态着色
- **环检测**：添加会形成环的边时自动阻止并提示
- **拓扑执行可视化**：同一层级的节点并行执行，层级间串行执行

### 2. 实时状态推送 (SSE)

- 任务详情页通过 SSE 连接实时获取 `next_run_time` 更新
- 更新时 UI 有视觉反馈（绿色指示灯闪烁动画）
- 自动重连机制

### 3. 主题系统

- 亮色/暗色双主题
- 使用 CSS 变量统一样式
- 主题切换即时生效，持久化到后端 SQLite
- DAG 画布背景、文本颜色等均适配主题

### 4. 认证与安全

- JWT Token 认证
- 可插拔认证后端（AuthBackend 抽象基类）
- API Key 管理（用于外部 API 调用认证）
- 系统初始化向导
- 密码最小长度校验

### 5. 任务调度核心概念

| 概念 | 说明 |
|------|------|
| Job（任务） | 一个被调度的定时工作单元，包含名称、触发器、执行器、存储后端等 |
| DAG | 有向无环图工作流，由多个 TaskNode 和 Edge 组成 |
| TaskNode（任务节点） | DAG 中的执行单元，支持 Python Callable/File/Snippet 和 Bash 四种类型 |
| Edge（依赖边） | 节点间的有向依赖，可附带条件判断函数 |
| Trigger（触发器） | 决定任务何时执行（Cron / Interval / Date / CalendarInterval / And / Or 组合） |
| Executor（执行器） | 执行任务的计算资源池（ThreadPool / ProcessPool / AsyncIO 等） |
| JobStore（存储后端） | 任务持久化存储（Memory / SQLAlchemy / Redis / MongoDB 等） |
| WorkflowExecutionLog | 每次 DAG 执行的完整记录（节点状态、耗时、结果、异常） |
| 任务状态 | PENDING → RUNNING → SUCCEEDED / FAILED / SKIPPED |
| 失败传播 | 上游节点失败后，所有下游节点标记为 SKIPPED |
| 结果传递 | 上游结果自动注入为 `_pre_results` 供下游节点使用 |

### 6. 并行执行模型

```
Layer 1 (并行): [task_a] [task_b]
     ↓              ↓
Layer 2 (并行): [task_c]
     ↓
Layer 3 (并行): [task_d]
```

- 按拓扑层级分组
- 层间串行执行
- 层内并行执行（max_workers 可配置）

---

## 五、设计方向建议

### 当前痛点（需要改进）
1. UI 风格较传统，缺乏现代感
2. Element Plus 默认风格，品牌辨识度不足
3. DAG 画布的视觉精致度可提升
4. 信息密度和层次感需要优化
5. 缺乏微交互动效

### 建议设计方向

1. **现代仪表盘风格**：采用卡片式布局、数据可视化（迷你图表）、渐变/玻璃态效果
2. **深色模式优先**：为开发者场景优化暗色主题的视觉舒适度
3. **精致的 DAG 可视化**：
   - 节点设计更精致（渐变填充、阴影、状态光晕）
   - 连线动画（执行中流水动画）
   - 执行状态实时反馈（节点边框脉冲动画）
   - 迷你地图导航
4. **响应式侧边栏**：可折叠的导航菜单，图标 + 文字模式切换
5. **统一的色彩系统**：建立 Design Token（主色、成功/警告/危险/信息色、表面色、文字层级色）
6. **微交互**：按钮悬停、卡片悬浮、状态切换过渡动画、骨架屏加载
7. **空状态设计**：每个列表/图表都有精心设计的空状态插图和引导文案
8. **操作确认**：危险操作（删除、迁移）有清晰的确认流程

### 竞品参考
- Temporal UI（工作流可视化标杆）
- Airflow UI（DAG 调度参考）
- Prefect UI（现代化工作流 UI）
- n8n（节点编辑器交互）
- Vercel / Linear（现代化设计语言）

---

## 六、API 接口总览

### Jobs (`/api/v1/jobs`)
- `POST /jobs` — 创建任务（支持旧式 API 和 DAG 工作流）
- `GET /jobs` — 列出所有任务
- `GET /jobs/{id}` — 获取任务详情（含 DAG 数据）
- `PUT /jobs/{id}` — 更新任务配置
- `DELETE /jobs/{id}` — 删除任务
- `POST /jobs/{id}/pause` — 暂停任务
- `POST /jobs/{id}/resume` — 恢复任务
- `POST /jobs/{id}/reschedule` — 重新调度

### Scheduler (`/api/v1/scheduler`)
- `GET /scheduler/status` — 调度器状态
- `POST /scheduler/pause` — 暂停调度器
- `POST /scheduler/resume` — 恢复调度器
- `POST /scheduler/shutdown` — 关闭调度器

### Logs (`/api/v1/logs`)
- `GET /logs/{job_id}` — 获取任务执行日志列表
- `GET /logs/{job_id}/{flow_log_id}` — 获取单次执行详情

### Components (`/api/v1/components`)
- `GET /components/triggers` — 可用触发器
- `GET /components/executors` — 可用执行器
- `GET /components/jobstores` — 可用存储后端
- `GET /components/executors/plugins` — 执行器插件（含参数 schema）
- `GET /components/jobstores/plugins` — 存储插件（含参数 schema）
- `GET/POST/PUT/DELETE /components/executors/configure/*` — 执行器配置 CRUD
- `GET/POST/PUT/DELETE /components/jobstores/configure/*` — 存储配置 CRUD + 数据迁移

### Auth (`/api/v1/auth`)
- `GET /auth/init-status` — 检查是否需要初始化
- `POST /auth/init-setup` — 创建管理员
- `POST /auth/login` — 登录获取 Token
- `GET/POST/PUT/DELETE /auth/apikeys` — API Key 管理

### SSE (`/api/v1/sse`)
- `GET /sse/jobs/{job_id}/next-run-time` — 实时推送任务下次执行时间

### Settings (`/api/v1/settings`)
- `GET/PUT /settings/theme` — 主题设置
- `GET/POST/PUT/DELETE /settings/variables` — 变量管理

**统一返回格式**：`{"code": 0, "data": ..., "message": "ok"}`

---

## 七、数据模型关键类型（TypeScript）

```typescript
// 任务类型
type TaskType = 'python_callable' | 'python' | 'python_scripts' | 'bash'

// 节点执行状态
type NodeStatus = 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'SKIPPED'

// 任务运行状态
type JobStatus = 'RUNNING' | 'PAUSED'

// DAG 节点
interface DagNode {
  node_id: string
  task_node: {
    task_id: string
    name: string
    description?: string
    func: { type: TaskType; ref?: string; script_path?: string; script?: string; command?: string; kwargs: Record<string, unknown> }
    done_callback?: { ref: string } | null
    stop_max_attempt_number?: number
  }
}

// DAG 边
interface DagEdge {
  id?: string
  name?: string
  description?: string
  source: string
  target: string
}

// 执行记录
interface ExecutionLog {
  flow_log_id: string
  start_time: string
  end_time: string
  duration: number
  node_records: Record<string, NodeExecutionRecord>
  dag?: DagData
}
```

---

*文档生成日期：2026-07-18*
*建议将此文档作为前端设计 AI（如 Claude Design、v0、Bolt 等）的输入提示词。*
