# SchedFlow 示例目录

本目录包含 SchedFlow（单 core 调度栈）的使用示例，均使用
``schedflow.core`` 的显式 API。

## 目录结构

```
examples/
├── README.md                      # 此说明文档
├── quick_start_guide.py           # 快速入门指南（推荐先看）
├── basic_workflow_example.py      # 基础工作流：并行下载 -> 处理 -> 聚合
├── advanced_workflow_example.py   # 高级特性：重试 / 条件边 / 混合任务类型 / 事件
└── workflow/
    ├── run_trigger.py             # 触发器用法
    └── modelmixin_meta.py         # BaseModelMixin / 触发器模型元数据
```

## 快速开始

```bash
cd /path/to/schedflow
python examples/quick_start_guide.py
python examples/basic_workflow_example.py
python examples/advanced_workflow_example.py
```

## 核心概念

### 任务 (TaskSpec / Task)
任务节点是工作流的基本执行单元，支持 `python_callable`（函数或模块引用）、
`bash`（shell 命令）、`python`（脚本文件）、`python_script`（内联代码片段），
并支持重试（`retries`）、超时（`timeout`）、成功/失败回调。

### 工作流 (Workflow)
工作流是任务组成的有向无环图（DAG），通过 `add_task` / `add_edge` 构建；
执行时按拓扑分层并行，前置结果通过 `_pre_results` 自动注入，边可携带条件。

### 调度器 (Scheduler)
`schedflow.core.Scheduler` 是唯一的调度器：支持多执行器、多存储器
（按 alias 路由）、触发器调度、事件订阅与 jobstore 迁移。

### 触发器 (Trigger)
触发器定义执行时间计划：`interval` / `cron` / `date` / `calendarinterval` /
`and` / `or`，通过 `schedflow.triggers` 使用。

### 组件注册
执行器、存储器、触发器均通过静态注册表注册（`core.plugins` /
`triggers.registry`），不再使用 entry-points。
