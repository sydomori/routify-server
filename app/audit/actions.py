"""
contains actions the audit log table should record
covers every event as pe the NFR's
"""

#---- auth -----
LOGIN_SUCCESS = "login.success"
LOGIN_FAILED = "login.failed"
LOGIN_LOCKOUT = "login.lockout"
PASSWORD_CHANGE = "password.change" # forced/normal change; NEVER log password values
MANAGER_BOOTSTRAP = "manager.bootstrap"
MANAGER_INVITE = "manager.invite"
DRIVER_CREATE = "driver.create"
DRIVER_DEACTIVATE = "driver.deactivate"
ACCESS_DENIED = "access.denied"              # role / ownership / inactive-account denials

# ---- trucks -----
TRUCK_CREATE = "truck.create"
TRUCK_UPDATE = "truck.update"
TRUCK_DELETE = "truck.delete"
DRIVER_ASSIGN = "driver.assign"
DRIVER_UNASSIGN = "driver.unassign"

# --- trips / orders ---
TRIP_START = "trip.start"
TRIP_END = "trip.end"
ORDER_ASSIGN = "order.assign"

# --- documents ---
DOCUMENT_UPLOAD = "document.upload"
DOCUMENT_VIEW = "document.view"
DOCUMENT_DOWNLOAD = "document.download"
DOCUMENT_VERIFY = "document.verify"
DOCUMENT_REJECT = "document.reject"
DOCUMENT_DELETE = "document.delete"

# --- communications ---
ISSUE_REPORT = "issue.report"
ISSUE_RESOLVE = "issue.resolve"

OUTCOME_SUCCESS = "success"
OUTCOME_DENIED = "denied"
OUTCOME_FAILED = "failed"

VALID_OUTCOMES = frozenset({OUTCOME_SUCCESS, OUTCOME_DENIED, OUTCOME_FAILED})
 
VALID_ACTIONS = frozenset(
    v for k, v in dict(globals()).items()
    if k.isupper() and isinstance(v, str) and "." in v
)