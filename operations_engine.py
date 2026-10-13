"""Public-safe illustrative operations-engine prototype.

Fictional scenario. No database, notifications, CRM, money movement, AI, or deployment.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
import re


class EngineError(ValueError):
    """Caller supplied invalid or unauthorized operation."""


class DuplicateRequest(EngineError):
    """New request matches an existing active case."""


class InvalidTransition(EngineError):
    """Current state/role does not authorize action."""


class State(str, Enum):
    TRIAGED = "TRIAGED"
    SCOPED = "SCOPED"
    APPROVED = "APPROVED"
    IN_PROGRESS = "IN_PROGRESS"
    QA_PENDING = "QA_PENDING"
    CLOSED = "CLOSED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


SERVICE_OWNER = {
    "rapid_response": "Response Desk",
    "preventive_care": "Service Planning",
    "site_upgrade": "Projects Team",
}
SLA_HOURS = {"urgent": 2, "priority": 8, "standard": 24}
ALLOWED_ROLES = {"coordinator", "manager", "operator", "reviewer"}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class Inquiry:
    request_id: str
    email: str
    service: str
    urgency: str
    summary: str
    consent: bool
    received_at: datetime


@dataclass
class Case:
    request_id: str
    normalized_email: str
    service: str
    urgency: str
    summary: str
    assigned_team: str
    response_due: datetime
    state: State = State.TRIAGED
    scope: str | None = None
    approved_by: str | None = None
    operator: str | None = None
    qa_evidence: str | None = None
    qa_reviewer: str | None = None
    review_reason: str | None = None
    previous_state: State | None = None


@dataclass(frozen=True)
class Event:
    index: int
    request_id: str
    actor: str
    action: str
    from_state: str | None
    to_state: str
    at: datetime


class OperationsEngine:
    """Deterministic local state and rule prototype (in-memory only)."""

    def __init__(self) -> None:
        self.cases: dict[str, Case] = {}
        self.audit: list[Event] = []
        self._idempotence: dict[str, tuple[Any, ...]] = {}

    @staticmethod
    def _now(dt: datetime | None = None) -> datetime:
        value = dt or datetime.now(timezone.utc)
        if value.tzinfo is None or value.utcoffset() is None:
            raise EngineError("A timezone-aware timestamp is required")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _fingerprint(inquiry: Inquiry) -> tuple[Any, ...]:
        return (
            inquiry.email.strip().lower(), inquiry.service,
            inquiry.urgency, inquiry.summary.strip(),
            inquiry.consent, inquiry.received_at.isoformat(),
        )

    def _append(self, request_id: str, actor: str, action: str,
                before: State | None, after: State, at: datetime) -> None:
        self.audit.append(Event(len(self.audit) + 1, request_id, actor, action,
                                before.value if before else None, after.value, at))

    def submit(self, inquiry: Inquiry) -> Case:
        if not inquiry.request_id.strip():
            raise EngineError("Request ID is required")
        when = self._now(inquiry.received_at)
        fingerprint = self._fingerprint(inquiry)
        if inquiry.request_id in self.cases:
            if self._idempotence[inquiry.request_id] == fingerprint:
                return self.cases[inquiry.request_id]
            raise DuplicateRequest("Request ID reuse with different content")
        email = inquiry.email.strip().lower()
        if not EMAIL.fullmatch(email):
            raise EngineError("Valid email is required")
        if not inquiry.consent:
            raise EngineError("Intake consent is required")
        if inquiry.service not in SERVICE_OWNER:
            raise EngineError("Unsupported service")
        if inquiry.urgency not in SLA_HOURS:
            raise EngineError("Unsupported urgency")
        if not inquiry.summary.strip():
            raise EngineError("Request summary is required")
        for case in self.cases.values():
            if (case.normalized_email == email and case.service == inquiry.service
                    and case.state != State.CLOSED):
                raise DuplicateRequest("Similar active request requires manual review")
        case = Case(
            request_id=inquiry.request_id,
            normalized_email=email, service=inquiry.service,
            urgency=inquiry.urgency, summary=inquiry.summary.strip(),
            assigned_team=SERVICE_OWNER[inquiry.service],
            response_due=when + timedelta(hours=SLA_HOURS[inquiry.urgency]),
        )
        self.cases[inquiry.request_id] = case
        self._idempotence[inquiry.request_id] = fingerprint
        self._append(case.request_id, "intake", "submit", None, State.TRIAGED, when)
        return case

    def _get(self, request_id: str) -> Case:
        try:
            return self.cases[request_id]
        except KeyError as exc:
            raise EngineError("Unknown request ID") from exc

    @staticmethod
    def _guard(actor: str, role: str, allowed: set[str]) -> None:
        if not actor.strip() or role not in ALLOWED_ROLES or role not in allowed:
            raise InvalidTransition("Role/actor not authorized for this operation")

    def _move(self, case: Case, actor: str, action: str, target: State,
              at: datetime | None = None) -> None:
        when = self._now(at)
        before = case.state
        case.state = target
        self._append(case.request_id, actor, action, before, target, when)

    def scope(self, request_id: str, actor: str, role: str, scope: str,
              at: datetime | None = None) -> Case:
        self._guard(actor, role, {"coordinator"})
        case = self._get(request_id)
        if case.state != State.TRIAGED:
            raise InvalidTransition("Only triaged inquiries can be scoped")
        if not scope.strip():
            raise EngineError("Scope must not be empty")
        case.scope = scope.strip()
        self._move(case, actor, "scope", State.SCOPED, at)
        return case

    def approve(self, request_id: str, actor: str, role: str,
                at: datetime | None = None) -> Case:
        self._guard(actor, role, {"manager"})
        case = self._get(request_id)
        if case.state != State.SCOPED or not case.scope:
            raise InvalidTransition("Manager can approve only a scoped request")
        case.approved_by = actor
        self._move(case, actor, "approve", State.APPROVED, at)
        return case

    def begin(self, request_id: str, actor: str, role: str,
              at: datetime | None = None) -> Case:
        self._guard(actor, role, {"operator"})
        case = self._get(request_id)
        if case.state != State.APPROVED or not case.approved_by:
            raise InvalidTransition("Work cannot begin without management approval")
        case.operator = actor
        self._move(case, actor, "begin", State.IN_PROGRESS, at)
        return case

    def submit_qa(self, request_id: str, actor: str, role: str, evidence: str,
                  at: datetime | None = None) -> Case:
        self._guard(actor, role, {"operator"})
        case = self._get(request_id)
        if case.state != State.IN_PROGRESS or actor != case.operator:
            raise InvalidTransition("Only assigned operator can submit work to QA")
        if not evidence.strip():
            raise EngineError("QA evidence reference is required")
        case.qa_evidence = evidence.strip()
        self._move(case, actor, "submit_qa", State.QA_PENDING, at)
        return case

    def close(self, request_id: str, actor: str, role: str,
              at: datetime | None = None) -> Case:
        self._guard(actor, role, {"reviewer"})
        case = self._get(request_id)
        if case.state != State.QA_PENDING or not case.qa_evidence:
            raise InvalidTransition("QA evidence and QA_PENDING state required")
        if actor == case.operator:
            raise InvalidTransition("Operator cannot be sole final reviewer")
        case.qa_reviewer = actor
        self._move(case, actor, "close", State.CLOSED, at)
        return case

    def flag_review(self, request_id: str, actor: str, role: str, reason: str,
                    at: datetime | None = None) -> Case:
        self._guard(actor, role, {"coordinator", "manager"})
        case = self._get(request_id)
        if case.state in {State.CLOSED, State.NEEDS_REVIEW}:
            raise InvalidTransition("Cannot hold closed or already-held case")
        if not reason.strip():
            raise EngineError("Review reason is required")
        case.previous_state = case.state
        case.review_reason = reason.strip()
        self._move(case, actor, "flag_review", State.NEEDS_REVIEW, at)
        return case

    def resolve_review(self, request_id: str, actor: str, role: str,
                       at: datetime | None = None) -> Case:
        self._guard(actor, role, {"manager"})
        case = self._get(request_id)
        if case.state != State.NEEDS_REVIEW or case.previous_state is None:
            raise InvalidTransition("No review hold to resolve")
        previous = case.previous_state
        case.review_reason = None
        case.previous_state = None
        self._move(case, actor, "resolve_review", previous, at)
        return case

    def overdue_intakes(self, as_of: datetime) -> list[str]:
        """Returns triaged cases whose initial response target is overdue; sends nothing."""
        when = self._now(as_of)
        return sorted(c.request_id for c in self.cases.values()
                      if c.state == State.TRIAGED and c.response_due < when)

    def snapshot(self) -> dict[str, Any]:
        """Safe serialization for synthetic demonstration output only."""
        def case_json(case: Case) -> dict[str, Any]:
            obj = asdict(case)
            obj["response_due"] = case.response_due.isoformat()
            obj["state"] = case.state.value
            obj["previous_state"] = case.previous_state.value if case.previous_state else None
            return obj
        return {
            "scoped_prototype": True,
            "cases": {id_: case_json(c) for id_, c in self.cases.items()},
            "events": [{**asdict(ev), "at": ev.at.isoformat()} for ev in self.audit],
        }
