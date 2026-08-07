"""SchedFlow 快速入门指南（新 core API）。

本文件与文档首页的"快速示例"保持一致，使用 ``schedflow.core``
的显式接口，包含 5 个渐进式示例：

1. 基础：单个任务直接执行
2. 进阶：带参数与重试
3. 工作流：节点依赖与 _pre_results 结果传递
4. 任务类型：混合 python_callable / bash / python_script
5. 调度器：IntervalTrigger 定时执行 + 事件订阅

运行：python examples/quick_start_guide.py
"""

import sys
import time

# 兼容 Windows 默认 GBK 控制台（示例包含 emoji/中文输出）
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from schedflow.core import Scheduler, Workflow
from schedflow.triggers import IntervalTrigger


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


# ==================== 示例 1：基础 - 单个任务执行 ====================

def example_1_basic_task() -> None:
    print_header("示例 1：基础 - 单个任务执行")

    def greet(name: str = "World") -> str:
        return f"Hello, {name}!"

    wf = Workflow("hello")
    wf.add_task("greet", func=greet, kwargs={"name": "SchedFlow"})

    log = wf.run()
    record = log.records["greet"]
    print(f"  状态: {record.status}  结果: {record.result}")


# ==================== 示例 2：进阶 - 带参数和重试 ====================

def example_2_task_with_retry() -> None:
    print_header("示例 2：进阶 - 带参数和重试")

    call_count = 0

    def flaky(item_id: int) -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError(f"处理项目 {item_id} 失败（模拟错误）")
        return f"item {item_id} processed (attempt {call_count})"

    wf = Workflow("retry")
    # retries=3 表示最多尝试 3 次（含首次）
    wf.add_task("flaky", func=flaky, kwargs={"item_id": 1001}, retries=3)

    log = wf.run()
    record = log.records["flaky"]
    print(f"  状态: {record.status}  结果: {record.result}")
    print(f"  实际尝试次数: {call_count}")


# ==================== 示例 3：工作流 - 简单依赖关系 ====================

def example_3_simple_workflow() -> None:
    print_header("示例 3：工作流 - 简单依赖关系")

    def step_1() -> str:
        return "data_ready"

    def step_2(_pre_results) -> dict:
        # _pre_results 是 {"上游节点ID": 返回值} 字典
        data = _pre_results["step_1"]
        return {"input": data, "output": f"processed_{data}"}

    def step_3(_pre_results) -> str:
        result = _pre_results["step_2"]
        return f"报告生成完成，输入: {result['input']}"

    wf = Workflow("simple")
    wf.add_task("step_1", func=step_1)
    wf.add_task("step_2", func=step_2)
    wf.add_task("step_3", func=step_3)
    wf.add_edge("step_1", "step_2")
    wf.add_edge("step_2", "step_3")

    log = wf.run()
    for node_id, record in log.records.items():
        print(f"  {node_id}: {record.status} 结果={record.result}")


# ==================== 示例 4：混合多种任务类型 ====================

def example_4_mixed_task_types() -> None:
    print_header("示例 4：混合多种任务类型")

    def fetch(source: str) -> str:
        return f"data from {source}"

    def process(_pre_results) -> str:
        return _pre_results["fetch"].upper()

    def should_report(record) -> bool:
        return record.status == "succeeded" and bool(record.result)

    wf = Workflow("etl")
    wf.add_task("fetch", func=fetch, kwargs={"source": "api"})
    wf.add_task("process", func=process)                     # python_callable
    wf.add_task("report", type="bash", command="echo report generated")  # bash
    wf.add_task("summary", type="python_script", script="print('summary ok')")  # python_script
    wf.add_edge("fetch", "process")
    wf.add_edge("process", "report", condition=should_report)  # 条件边
    wf.add_edge("process", "summary")

    log = wf.run(max_workers=3)
    for node_id, record in log.records.items():
        print(f"  {node_id}: {record.status}")
    print(f"  总成功: {log.succeeded}")


# ==================== 示例 5：调度器定时执行 ====================

def example_5_scheduler() -> None:
    print_header("示例 5：调度器 - IntervalTrigger 定时执行")

    def tick() -> str:
        print("  [tick] 作业执行中...")
        return "ok"

    wf = Workflow("interval")
    wf.add_task("tick", func=tick)

    scheduler = Scheduler()
    scheduler.on("job.succeeded", lambda e: print(f"  事件: {e.kind} (job={e.job_id})"))
    scheduler.add_job(
        wf,
        trigger=IntervalTrigger(seconds=5),
        job_id="interval_job",
        misfire_grace_time=10,
        max_instances=1,
    )
    scheduler.start()

    # 说明：调度器主循环运行在后台守护线程，主线程需要保持存活。
    # 真实部署中一般用 while True: time.sleep(1) + Ctrl+C 退出；
    # 这里为了演示只等待 6 秒让作业触发一次，然后正常关闭。
    print("  等待 6 秒，让作业触发一次...")
    time.sleep(6)
    scheduler.shutdown()
    print("  调度器已停止。")


def main() -> None:
    print("🚀 SchedFlow 快速入门指南")
    print("（与 docs 首页快速示例一致的 core API）")
    example_1_basic_task()
    example_2_task_with_retry()
    example_3_simple_workflow()
    example_4_mixed_task_types()
    example_5_scheduler()
    print("\n🎉 快速入门指南执行完成！")
    print("下一步：查看 examples/ 下其它示例，或阅读 docs/ 用户指南。")


if __name__ == "__main__":
    main()
