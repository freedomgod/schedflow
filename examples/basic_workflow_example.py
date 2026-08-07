# ruff: noqa: RUF001,RUF002,DTZ005 - 示例中的中文标点与本地时间戳属于预期
"""
基础工作流示例（core API）

展示：并行下载 -> 并行处理 -> 聚合，依赖结果通过 ``_pre_results`` 自动传递。
运行：python examples/basic_workflow_example.py
"""

import time
from datetime import datetime

from schedflow.core import Workflow


def download_data(source: str) -> str:
    """模拟下载数据任务"""
    print(f"[{datetime.now():%H:%M:%S}] 开始下载: {source}")
    time.sleep(0.3)
    result = f"data_from_{source}"
    print(f"[{datetime.now():%H:%M:%S}] 下载完成: {result}")
    return result


def process_data(_pre_results, algorithm: str = "default") -> dict:
    """模拟处理数据任务（接收前置结果字典）"""
    data = next((v for v in _pre_results.values() if isinstance(v, str)), "")
    time.sleep(0.3)
    result = {"original": data, "processed": f"processed_{algorithm}_{data}"}
    print(f"[{datetime.now():%H:%M:%S}] 处理完成: {result['processed']}")
    return result


def aggregate_results(_pre_results) -> dict:
    """模拟聚合结果任务"""
    combined = [
        v for v in _pre_results.values()
        if isinstance(v, dict) and "processed" in v
    ]
    result = {"combined": combined, "summary": f"聚合了 {len(combined)} 个结果"}
    print(f"[{datetime.now():%H:%M:%S}] 聚合完成: {result['summary']}")
    return result


def create_workflow() -> Workflow:
    """构建 DAG：两个并行下载，各自处理后汇入聚合节点"""
    wf = Workflow("basic_example_workflow")
    wf.add_task("download_api", func=download_data, kwargs={"source": "api"})
    wf.add_task("download_db", func=download_data, kwargs={"source": "database"})
    wf.add_task("process_api", func=process_data)
    wf.add_task("process_db", func=process_data, kwargs={"algorithm": "enhanced"})
    wf.add_task("aggregate", func=aggregate_results)

    wf.add_edge("download_api", "process_api")
    wf.add_edge("download_db", "process_db")
    wf.add_edge("process_api", "aggregate")
    wf.add_edge("process_db", "aggregate")
    return wf


def analyze_results(log) -> None:
    """统计并打印执行日志"""
    succeeded = sum(1 for r in log.records.values() if r.status == "succeeded")
    failed = sum(1 for r in log.records.values() if r.status == "failed")
    skipped = sum(1 for r in log.records.values() if r.status == "skipped")
    print(f"工作流ID: {log.flow_id}  总耗时: {log.duration:.2f}s")
    print(f"成功: {succeeded}  失败: {failed}  跳过: {skipped}")
    for node_id, record in log.records.items():
        print(f"  {node_id}: {record.status}  结果={record.result}")


if __name__ == "__main__":
    print("SchedFlow 基础工作流示例（core API）")
    workflow = create_workflow()
    print(f"工作流创建完成（节点数: {len(workflow.to_dict()['nodes'])}）")
    execution_log = workflow.run(max_workers=2)
    analyze_results(execution_log)
    print("工作流执行完成！")
