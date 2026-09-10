"""断点续跑示例：第一次失败，第二次 resume 只重跑未完成节点。"""

from schedflow.core import Scheduler, Workflow

attempts = {"a": 0, "b": 0, "c": 0}


def task_a() -> str:
    attempts["a"] += 1
    return "A"


def task_b() -> str:
    attempts["b"] += 1
    if attempts["b"] == 1:
        raise RuntimeError("transient failure on first run")
    return "B"


def task_c(_pre_results) -> str:
    attempts["c"] += 1
    # _pre_results only contains direct predecessors (here: b).
    return _pre_results["b"] + "C"


def main() -> None:
    workflow = Workflow("resume-demo")
    workflow.add_task("a", func=task_a)
    workflow.add_task("b", func=task_b)
    workflow.add_task("c", func=task_c)
    workflow.add_edge("a", "b")
    workflow.add_edge("b", "c")

    scheduler = Scheduler()
    scheduler.add_job(workflow, job_id="resume-demo")

    first = scheduler.run_job_now("resume-demo")
    print("first run succeeded:", first.succeeded)
    print("first attempts:", attempts)

    resumed = scheduler.run_job_now("resume-demo", mode="resume")
    print("resume succeeded:", resumed.succeeded)
    print("resumed nodes:", [
        node_id
        for node_id, record in resumed.records.items()
        if record.resumed
    ])
    print("resume attempts:", attempts)
    print("final result:", resumed.records["c"].result)


if __name__ == "__main__":
    main()
