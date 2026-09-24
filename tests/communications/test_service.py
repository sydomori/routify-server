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