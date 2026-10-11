import copy
from datetime import UTC, datetime, timedelta

import pytest

from schedflow.core import Job, MemoryJobStore, Scheduler, Workflow
from schedflow.core.jobstore import JobConflictError
from schedflow.triggers.interval import IntervalTrigger


def payload(job_id="planned"):
    workflow = Workflow(flow_id="flow")
    workflow.add_task("task", type="python_script", script="print(1)")
    job = Job(workflow, IntervalTrigger(seconds=60), job_id=job_id)
    data = job.to_dict()
    data["status"] = "paused"
    return data


def test_paused_create_is_disarmed_before_store_can_observe_it():
    class ObservingStore(MemoryJobStore):
        def add(self, job):
            assert job.status == "paused"
            assert job.next_run_time is None
            super().add(job)

    scheduler = Scheduler(jobstore=ObservingStore())
    created = scheduler.apply_job_command("create", payload())
    assert created.status == "paused"
    assert scheduler.get_job("planned") is created


def test_create_checks_duplicate_ids_across_stores():
    scheduler = Scheduler()
    scheduler.add_jobstore(MemoryJobStore(), alias="other")
    scheduler.add_job(Workflow(), job_id="planned", jobstore_alias="other")
    with pytest.raises(JobConflictError):
        scheduler.apply_job_command("create", payload())
    assert scheduler.get_jobstore("default").get("planned") is None


def test_stale_full_config_hash_rejects_update():
    scheduler = Scheduler()
    scheduler.apply_job_command("create", payload())
    old_hash = scheduler.job_config_hash("planned")
    scheduler.reschedule_job("planned", IntervalTrigger(seconds=120))
    with pytest.raises(ValueError, match="configuration changed"):
        scheduler.apply_job_command("update", payload(), expected_hash=old_hash)


@pytest.mark.parametrize(
    "field,value",
    [
        ("executor_alias", "absent"),
        ("jobstore_alias", "absent"),
        ("max_instances", 0),
        ("workflow_timeout", -1),
    ],
)
def test_invalid_candidate_leaves_existing_object_unchanged(field, value):
    scheduler = Scheduler()
    old = scheduler.apply_job_command("create", payload())
    before = copy.deepcopy(old.to_dict())
    candidate = payload()
    candidate["name"] = "partial mutation"
    candidate[field] = value
    with pytest.raises((ValueError, KeyError)):
        scheduler.apply_job_command(
            "update", candidate, expected_hash=scheduler.job_config_hash("planned")
        )
    assert scheduler.get_job("planned") is old
    assert old.to_dict() == before


def test_hash_ignores_fire_time_and_includes_full_configuration():
    from schedflow.core.commands import config_hash

    data = payload()
    same = copy.deepcopy(data)
    same["next_run_time"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    assert config_hash(data) == config_hash(same)
    for field, value in [
        ("status", "running"),
        ("priority", 9),
        ("trigger", None),
        ("executor_alias", "other"),
    ]:
        changed = copy.deepcopy(data)
        changed[field] = value
        assert config_hash(data) != config_hash(changed)
    assert config_hash(data) == config_hash(dict(reversed(list(data.items()))))


def test_update_replaces_candidate_and_rejects_store_migration():
    scheduler = Scheduler()
    old = scheduler.apply_job_command("create", payload())
    changed = payload()
    changed["name"] = "approved"
    result = scheduler.apply_job_command(
        "update", changed, expected_hash=scheduler.job_config_hash("planned")
    )
    assert result is not old
    assert old.name is None
    scheduler.add_jobstore(MemoryJobStore(), alias="other")
    changed["jobstore_alias"] = "other"
    with pytest.raises(ValueError, match="migration"):
        scheduler.apply_job_command(
            "update", changed, expected_hash=scheduler.job_config_hash("planned")
        )


def test_command_accepts_zero_misfire_grace_time():
    scheduler = Scheduler()
    data = payload()
    data["misfire_grace_time"] = 0
    assert scheduler.apply_job_command("create", data).misfire_grace_time == 0
