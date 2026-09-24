from types import SimpleNamespace
from app.communications import service
from app.communications.models import NotificationLog, TruckIssue

def test_report_issue_persists_even_when_sms_fails(app, db, monkeypatch):
    """The spec's explicit rule: 'The TruckIssue itself is created even if
    the SMS send fails — the record matters more than the alert.'"""
    def _raise(*args, **kwargs):
        raise RuntimeError("provider is down")

    # Patch where it's USED (service.send_sms), not where it's defined
    # (providers.sms_provider.send_sms) — a common mocking mistake, since
    # service.py imported the function by name into its own namespace.
    monkeypatch.setattr(service, "send_sms", _raise)

    issue = service.report_issue(
        truck_id=1,
        driver_id=2,
        type="fuel",
        description="Tank low on the A2 route",
        manager_phone="+254700000000",
    )

    assert issue.id is not None
    assert issue.status == "open"

    failed_log = NotificationLog.query.filter_by(status="failed").first()
    assert failed_log is not None
    assert failed_log.channel == "sms"

def test_send_onboarding_sms_never_raises_on_provider_failure(app, db, monkeypatch):
    """auth.service.onboard_driver() must be able to call this without
    wrapping it in its own try/except — the guarantee lives here."""
    monkeypatch.setattr(service, "send_sms", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))

    # Should not raise:
    service.send_onboarding_sms(phone="+254700000000", temp_password="temp123")

    log = NotificationLog.query.filter_by(channel="sms", status="failed").first()
    assert log is not None
    assert log.recipient == "+254700000000"

def test_send_manager_invite_email_never_raises_on_provider_failure(app, db, monkeypatch):
    """Same guarantee, email channel — auth.service.onboard_manager() relies
    on this not raising either."""
    monkeypatch.setattr(service, "send_email", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("smtp down")))

    fake_user = SimpleNamespace(name="Jane Manager", email="jane@example.com")

    # Should not raise:
    service.send_manager_invite_email(fake_user, invite_link="https://routify.app/invite/abc123")

    log = NotificationLog.query.filter_by(channel="email", status="failed").first()
    assert log is not None
    assert log.recipient == "jane@example.com"


def test_resolve_issue_transitions_status_and_sets_resolved_at(app, db):
    issue = TruckIssue(truck_id=1, driver_id=2, type="mechanical", status="open")
    db.session.add(issue)
    db.session.commit()

    resolved = service.resolve_issue(issue.id)

    assert resolved.status == "resolved"
    assert resolved.resolved_at is not None