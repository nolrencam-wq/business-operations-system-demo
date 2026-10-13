import unittest
from datetime import datetime, timedelta, timezone
from operations_engine import (OperationsEngine, Inquiry, State, EngineError,
                               DuplicateRequest, InvalidTransition)

T = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)

def inp(id="A1", email="name@example.test", service="rapid_response",
        urgency="urgent", consent=True, at=T, summary="A repair request"):
    return Inquiry(id, email, service, urgency, summary, consent, at)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.e = OperationsEngine()

    def test_routes_emergency(self):
        case = self.e.submit(inp())
        self.assertEqual(case.assigned_team, "Response Desk")
        self.assertEqual(case.response_due, T + timedelta(hours=2))

    def test_routes_all_offers(self):
        options=[("rapid_response", "Response Desk"), ("preventive_care", "Service Planning"),
                 ("site_upgrade", "Projects Team")]
        for idx, (service, team) in enumerate(options):
            case=self.e.submit(inp(id=str(idx), email=f"{idx}@example.test", service=service))
            self.assertEqual(case.assigned_team, team)

    def test_urgency_targets(self):
        for idx, (urgency,hours_) in enumerate([("urgent",2),("priority",8),("standard",24)]):
            case=self.e.submit(inp(id=str(idx),email=f"{idx}@example.test",urgency=urgency))
            self.assertEqual(case.response_due, T+timedelta(hours=hours_))

    def test_no_consent_refused(self):
        with self.assertRaises(EngineError): self.e.submit(inp(consent=False))
        self.assertEqual(len(self.e.cases),0)

    def test_bad_email_refused(self):
        with self.assertRaises(EngineError): self.e.submit(inp(email="not-email"))

    def test_unknown_service_refused(self):
        with self.assertRaises(EngineError): self.e.submit(inp(service="unknown"))

    def test_unknown_urgency_refused(self):
        with self.assertRaises(EngineError): self.e.submit(inp(urgency="unknown"))

    def test_empty_summary_refused(self):
        with self.assertRaises(EngineError): self.e.submit(inp(summary=" "))

    def test_naive_timestamp_refused(self):
        with self.assertRaises(EngineError): self.e.submit(inp(at=datetime(2026,10,13)))

    def test_repeat_idempotent_no_extra_event(self):
        a=self.e.submit(inp()); b=self.e.submit(inp())
        self.assertIs(a,b)
        self.assertEqual(len(self.e.audit),1)

    def test_id_reuse_different_payload_refused(self):
        self.e.submit(inp())
        with self.assertRaises(DuplicateRequest): self.e.submit(inp(summary="Other work"))

    def test_active_case_duplicate_normalized_email(self):
        self.e.submit(inp())
        with self.assertRaises(DuplicateRequest): self.e.submit(inp(id="A2",email="NAME@EXAMPLE.TEST"))

    def test_other_service_same_email_allowed(self):
        self.e.submit(inp())
        self.e.submit(inp(id="A2",service="site_upgrade"))
        self.assertEqual(len(self.e.cases),2)

    def test_cannot_begin_without_scope_approval(self):
        self.e.submit(inp())
        with self.assertRaises(InvalidTransition): self.e.begin("A1","Ops","operator")

    def test_only_coordinator_can_scope(self):
        self.e.submit(inp())
        with self.assertRaises(InvalidTransition): self.e.scope("A1","Ops","operator","Replace part")

    def test_only_manager_can_approve(self):
        self.e.submit(inp()); self.e.scope("A1","Coord","coordinator","Inspect")
        with self.assertRaises(InvalidTransition): self.e.approve("A1","Coord","coordinator")

    def test_no_qa_without_evidence(self):
        self.e.submit(inp());self.e.scope("A1","Coord","coordinator","Inspect")
        self.e.approve("A1","Mgr","manager");self.e.begin("A1","Ops","operator")
        with self.assertRaises(EngineError): self.e.submit_qa("A1","Ops","operator"," ")

    def test_cannot_close_without_qa(self):
        self.e.submit(inp())
        with self.assertRaises(InvalidTransition):self.e.close("A1","Reviewer","reviewer")

    def test_operator_cannot_review_own_work(self):
        self.e.submit(inp());self.e.scope("A1","Coord","coordinator","Inspect")
        self.e.approve("A1","Mgr","manager");self.e.begin("A1","Ops","operator")
        self.e.submit_qa("A1","Ops","operator","TEST-01")
        with self.assertRaises(InvalidTransition):self.e.close("A1","Ops","reviewer")

    def test_full_authorized_lifecycle(self):
        self.e.submit(inp());self.e.scope("A1","Coord","coordinator","Inspect")
        self.e.approve("A1","Mgr","manager");self.e.begin("A1","Ops","operator")
        self.e.submit_qa("A1","Ops","operator","CHECK-01")
        self.e.close("A1","QA","reviewer")
        self.assertEqual(self.e.cases["A1"].state,State.CLOSED)
        self.assertEqual(len(self.e.audit),6)

    def test_manager_must_resolve_hold(self):
        self.e.submit(inp());self.e.flag_review("A1","Coord","coordinator","Incomplete request")
        with self.assertRaises(InvalidTransition):self.e.resolve_review("A1","Coord","coordinator")
        self.e.resolve_review("A1","Mgr","manager")
        self.assertEqual(self.e.cases["A1"].state,State.TRIAGED)

    def test_cannot_hold_closed_case(self):
        self.e.submit(inp());self.e.scope("A1","Coord","coordinator","Inspect")
        self.e.approve("A1","Mgr","manager");self.e.begin("A1","Ops","operator")
        self.e.submit_qa("A1","Ops","operator","CHECK-01");self.e.close("A1","QA","reviewer")
        with self.assertRaises(InvalidTransition):self.e.flag_review("A1","Coord","coordinator","Too late")

    def test_overdue_triaged_only(self):
        self.e.submit(inp())
        self.e.submit(inp(id="A2", email="b@example.test",service="site_upgrade", urgency="standard"))
        self.assertEqual(self.e.overdue_intakes(T+timedelta(hours=3)),["A1"])
        self.e.scope("A1","Coord","coordinator","Inspect")
        self.assertEqual(self.e.overdue_intakes(T+timedelta(hours=100)),["A2"])

    def test_snapshot_is_json_serializable(self):
        import json
        self.e.submit(inp())
        data=self.e.snapshot()
        self.assertIn('cases',data)
        json.dumps(data)

    def test_new_case_after_closed_is_allowed(self):
        self.e.submit(inp());self.e.scope("A1","Coord","coordinator","Inspect")
        self.e.approve("A1","Mgr","manager");self.e.begin("A1","Ops","operator")
        self.e.submit_qa("A1","Ops","operator","CHECK-01");self.e.close("A1","QA","reviewer")
        self.e.submit(inp(id="A2", email="NAME@EXAMPLE.TEST"))
        self.assertEqual(self.e.cases["A2"].state,State.TRIAGED)


if __name__ == '__main__': unittest.main()
