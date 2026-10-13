"""
contains actions the audit log table should record
covers every event as pe the NFR's
"""

#----auth-----
LOGIN_SUCCESS = "login.success"
LOGIN_FAILED = "login.failed"
LOGIN_LOCKOUT = "login.lockout"
PASSWORD_CHANGE = "password.change" # forced/normal change; NEVER log password values
MANAGER_BOOTSTRAP = "manager.bootstrap"
MANAGER_INVITE = "manager.invite"
DRIVER_CREATE = "driver.create"
DRIVER_DEACTIVATE = "driver.deactivate"
ACCESS_DENIED = "access.denied"              # role / ownership / inactive-account denials