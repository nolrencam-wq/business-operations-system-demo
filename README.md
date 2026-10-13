# From Business Idea to Working System

## A public-safe, fictional case-study prototype

This package demonstrates a bounded, locally executed portion of a wider **business operating system architecture**. The scenario and all data are fictional. This is an original demonstration, not a claim of client work or production operations.

### What is working in code

- Structured intake validation (contact fields, service choice, consent and time semantics)
- Request-key idempotency and detection of active duplicate requests
- Deterministic routing to service owners and illustrative response targets
- Human role gates for scoping, management approval, work start and QA closeout
- Independent QA reviewer check, plus review holds and manager resolution
- Time-based overdue-intake detection (returns case IDs, does not notify anyone)
- In-memory audit events and JSON-safe snapshots

### What is architecture only

Business offer design, CRM integration, appointment scheduling, external messages, database persistence, payments, human staffing, organizational adoption, real service delivery, production monitoring and security hardening. None of these is implemented or claimed here.

### How to run

Python 3.10+; no third-party dependencies.

```bash
python -m unittest discover -s tests -v
python demo.py
```

Run both commands from this folder. `demo.py` writes `examples/synthetic_walkthrough.json` with deterministic synthetic data. The tests check core rules and negative paths; they are not a production certification or independent external review.

### Design ownership and claims

Public demonstration prepared for Dingir Prime Labs. No private methodology or proprietary source library is included. No real person, business, customer contact, or external service is used. Do not confuse a test-verified local logic prototype with a deployed multiuser platform.
