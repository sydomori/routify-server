from app.audit import actions

REQUIRED = {
    "login.success", "login.failed", "login.lockout", "password.change",
    "manager.bootstrap", "manager.invite", "driver.create", "driver.deactivate",
    "driver.assign", "trip.start", "trip.end", "order.assign",
    "issue.report", "issue.resolve", "document.upload", "document.view",
    "document.download", "document.verify", "document.reject",
    "document.delete", "access.denied",
}

def test_all_required_actions_are_defined():
    """
     security : make sure nothing that must be audited is missing
    """
    assert REQUIRED <= actions.VALID_ACTIONS

def test_action_values_are_unique():
    """
     edge: no two constants share a value
    """
    values = [v for k,v in vars(actions).items() if k.isupper() and isinstance(v,str) and "." in v]
    assert len(set(values)) == len(values)

def test_password_change_action_exists():
    """
     security: password.change is recordable (auth's forced
     password-change flow, with no password values).
    """
    assert actions.PASSWORD_CHANGE == "password.change"

def test_outcomes_are_exactly_the_three_allowed():
    """
     validation: outcomes are exactly success, denied and failed.
    """
    assert actions.VALID_OUTCOMES == {"success", "denied", "failed"}

def test_outcomes_are_not_mistaken_for_actions():
    """
     edge: an outcome string can never pass as an action
    """
    assert not (actions.VALID_OUTCOMES & actions.VALID_ACTIONS)