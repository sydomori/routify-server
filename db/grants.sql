"""
makes audit-logs append-only at database level
takes away the app's ability to update or delete audit logs, while still allowing it to insert new ones
prevents accidental or malicious tampering with audit logs, which are critical for security and compliance
"""

REVOKE ALL ON TABLE audit_logs FROM :"app_role";  #Clears any existing permissions for the app on the audit_logs table

GRANT SELECT, INSERT ON TABLE audit_logs TO :"app_role"; # Grants INSERT for record() and SELECT for GET/audit/logs route

GRANT USAGE, SELECT ON SEQUENCE audit_logs_id_seq TO :"app_role"; #every new row gets an auto-incremented id, so the app needs to be able to use the sequence to get the next value

-- Verify as :"app_role" (both must FAIL with "permission denied"):
--   UPDATE audit_logs SET outcome = 'success' WHERE id = 1;
--   DELETE FROM audit_logs WHERE id = 1;