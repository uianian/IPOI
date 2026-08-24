from __future__ import annotations

from typing import Any

from service.analysis_runner import StreamHub, _publish_completed_result
from service.routes_analysis import AnalysisStartBody, _resolve_enable_embellishment
from service.analysis_store import AnalysisStore


class RecordingStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.result: dict[str, Any] | None = None
        self.meta: dict[str, Any] = {"status": "reporting"}

    def write_result(self, analysis_id: str, result: dict[str, Any]) -> None:
        self.result = result
        self.calls.append(("write_result", analysis_id))

    def update_meta(
        self,
        analysis_id: str,
        *,
        notify: bool = True,
        **fields: Any,
    ) -> None:
        self.meta.update(fields)
        self.calls.append(("update_meta", {"analysis_id": analysis_id, "notify": notify}))


class RecordingHub:
    def __init__(self, store: RecordingStore) -> None:
        self.store = store
        self.events: list[str] = []

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        if event_type == "report_ready":
            assert self.store.result is not None
            assert self.store.meta["status"] == "completed"
            assert self.store.meta["phase"] == "report"
            assert self.store.calls[-1][1]["notify"] is False
        self.events.append(event_type)


def test_report_ready_is_emitted_only_after_completed_result_is_persisted() -> None:
    store = RecordingStore()
    hub = RecordingHub(store)
    report = {"overallScore": 68, "riskLevel": "HIGH"}
    result = {"status": "completed", "report": report}

    _publish_completed_result(
        store=store,  # type: ignore[arg-type]
        hub=hub,  # type: ignore[arg-type]
        analysis_id="analysis_test_000001",
        result=result,
        report=report,
        overall=68,
        risk_level="HIGH",
        completed_at="2026-08-20T00:00:00Z",
        dossier_paths={"master": "master.json"},
    )

    assert [name for name, _ in store.calls] == ["write_result", "update_meta"]
    assert hub.events == ["report_ready", "agent_status", "analysis_complete"]
    assert store.result == result
    assert store.meta["overallScore"] == 68


def test_real_store_never_notifies_completed_before_report_ready(tmp_path) -> None:
    store = AnalysisStore(analyses_dir=tmp_path)
    analysis_id = "analysis_test_000002"
    store.create(
        analysis_id=analysis_id,
        client_project_id="project-test",
        task_id="task-test",
        parse_meta={},
    )
    hub = StreamHub(store, analysis_id)
    notifications: list[tuple[str, list[str]]] = []

    def record_notification(notified_analysis_id: str) -> None:
        events, _ = store.read_events_from(notified_analysis_id, 0)
        notifications.append(
            (
                str(store.read_meta(notified_analysis_id).get("status")),
                [str(event.get("event")) for event in events],
            )
        )

    store._notify = record_notification  # type: ignore[method-assign]
    report = {"overallScore": 68, "riskLevel": "HIGH"}
    result = {"status": "completed", "report": report}

    _publish_completed_result(
        store=store,
        hub=hub,
        analysis_id=analysis_id,
        result=result,
        report=report,
        overall=68,
        risk_level="HIGH",
        completed_at="2026-08-20T00:00:00Z",
        dossier_paths={},
    )

    assert store.read_result(analysis_id) == result
    assert store.read_meta(analysis_id)["status"] == "completed"
    assert not any(
        status == "completed" and "report_ready" not in event_types
        for status, event_types in notifications
    )
    events, _ = store.read_events_from(analysis_id, 0)
    assert [event["event"] for event in events] == [
        "report_ready",
        "agent_status",
        "analysis_complete",
    ]



def test_analysis_start_embellishment_inherits_parse_meta_and_accepts_override() -> None:
    inherited_body = AnalysisStartBody(clientProjectId="project-test")
    disabled_body = AnalysisStartBody(
        clientProjectId="project-test", enableEmbellishment=False
    )
    assert inherited_body.enableEmbellishment is None
    assert _resolve_enable_embellishment(inherited_body.enableEmbellishment, {"enableEmbellishment": True}) is True
    assert _resolve_enable_embellishment(inherited_body.enableEmbellishment, {"enableEmbellishment": False}) is False
    assert _resolve_enable_embellishment(inherited_body.enableEmbellishment, {}) is False
    assert _resolve_enable_embellishment(disabled_body.enableEmbellishment, {"enableEmbellishment": True}) is False
