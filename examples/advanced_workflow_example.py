
"""
高级工作流示例（core API）

展示：任务重试、条件依赖边、混合任务类型（bash / python_script）、
调度器定时执行与事件订阅。
运行：python examples/advanced_workflow_example.py
"""

import time

from schedflow.core import Scheduler, Workflow
from schedflow.triggers import IntervalTrigger


def flaky_fetch(item_id: int) -> str:
    """前两次失败、第三次成功的任务，用于演示重试"""
    flaky_fetch._attempts = getattr(flaky_fetch, "_attempts", 0) + 1
    if flaky_fetch._attempts < 3:
        raise ValueError(f"模拟失败（第 {flaky_fetch._attempts} 次）")
    return f"item {item_id} fetched"


def should_notify(record) -> bool:
    """条件边：仅当前置任务成功且有结果时才放行"""
    return record.status == "succeeded" and bool(record.result)


def main() -> None:
    # 工作流：fetch（重试3次）-> report（bash，条件放行）与 summary（python_script）
    wf = Workflow("advanced_example_workflow")
    wf.add_task("fetch", func=flaky_fetch, kwargs={"item_id": 7}, retries=3)
    wf.add_task("report", type="bash", command="echo report generated")
    wf.add_task("summary", type="python_script", script="print('summary ok')")
    wf.add_edge("fetch", "report", condition=should_notify)
    wf.add_edge("fetch", "summary")

    log = wf.run(max_workers=3)
    for node_id, record in log.records.items():
        print(f"  {node_id}: {record.status}  结果={record.result}")
    print(f"总成功: {log.succeeded}")

    # 调度器定时执行 + 事件订阅
    scheduler = Scheduler()
    scheduler.on("job.succeeded", lambda e: print(f"事件: {e.kind} job={e.job_id}"))
    scheduler.add_job(wf, trigger=IntervalTrigger(seconds=5), job_id="advanced_job")
    scheduler.start()
    print("等待 6 秒让作业触发一次...")
    time.sleep(6)
    scheduler.shutdown()


if __name__ == "__main__":
    main()
