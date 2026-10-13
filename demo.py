"""Produces a deterministic example using entirely synthetic data."""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from operations_engine import Inquiry, OperationsEngine, DuplicateRequest, EngineError, InvalidTransition

T = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
engine = OperationsEngine()
case = engine.submit(Inquiry("DEMO-1001", "buyer@example.test", "rapid_response", "urgent",
                            "Repair an inoperative cooling unit", True, T))
initial = {
    "case_id": case.request_id,
    "team": case.assigned_team,
    "respond_by_utc": case.response_due.isoformat(),
    "initial_status": case.state.value,
}
engine.scope(case.request_id, "Alex", "coordinator", "Investigate cooling unit and propose safe next steps", T+timedelta(minutes=12))
engine.approve(case.request_id, "Taylor", "manager", T+timedelta(minutes=16))
engine.begin(case.request_id, "Morgan", "operator", T+timedelta(minutes=22))
engine.submit_qa(case.request_id, "Morgan", "operator", "SYNTHETIC-CHECK-17", T+timedelta(minutes=42))
engine.close(case.request_id, "Reese", "reviewer", T+timedelta(minutes=54))
refusals = {}
for label, bad in {
    "missing_consent": Inquiry("DEMO-1002", "someone@example.test", "site_upgrade", "standard", "Plan site upgrade", False, T),
    "invalid_service": Inquiry("DEMO-1003", "someone@example.test", "invalid", "standard", "Plan site upgrade", True, T),
}.items():
    try:
        engine.submit(bad)
    except EngineError as exc:
        refusals[label] = str(exc)
try:
    engine.submit(Inquiry("DEMO-1004", "BUYER@example.test", "rapid_response", "urgent", "New request", True, T))
except DuplicateRequest as exc:
    # This case has CLOSED, so a new request after closure can start.
    refusals["post_close_repeat"] = str(exc)
result = {
    "scenario": "FICTIONAL / SYNTHETIC", "scope": "LOCAL RULES PROTOTYPE; NO LIVE INTEGRATIONS",
    "intake": initial,
    "final_state": case.state.value,
    "qa_reviewer": case.qa_reviewer,
    "events_for_first_case": [ev.action for ev in engine.audit if ev.request_id == "DEMO-1001"],
    "blocked_examples": refusals,
    "case_count": len(engine.cases),
    "audit_event_count": len(engine.audit),
}
output = Path(__file__).resolve().parent / "examples" / "synthetic_walkthrough.json"
output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
print(json.dumps(result, indent=2))
