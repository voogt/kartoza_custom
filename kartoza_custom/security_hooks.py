import re
import time
from frappe import _
import frappe

# SQL injection patterns
SQLI_PATTERNS = [
    r"(\bUNION\b|\bSELECT\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b|\bDROP\b|\bALTER\b)",
    r"(\bSLEEP\s*\(|\bBENCHMARK\s*\(|\bIF\s*\()",
    r"(--|#|/\*|\*/|;)",
    r"XOR\(",
]

# In-memory storage for tracking repeated attempts per IP
IP_BLOCKS = {}  # {ip_address: {"count": int, "last_attempt": timestamp}}

# Configuration
MAX_ATTEMPTS = 3     # max attempts before temporary block
BLOCK_DURATION = 600 # seconds to block after max attempts (10 minutes)

def check_sql_injection():
    from frappe import local
    from frappe.utils.response import build_response

    if not local.request:
        return

    ip = local.request.remote_addr
    now_ts = time.time()

    # Clean up expired blocks
    expired_ips = [k for k, v in IP_BLOCKS.items() if now_ts - v.get("last_attempt", 0) > BLOCK_DURATION]
    for k in expired_ips:
        del IP_BLOCKS[k]

    # Block IP if previously exceeded
    if ip in IP_BLOCKS and IP_BLOCKS[ip]["count"] > MAX_ATTEMPTS:
        frappe.throw(_("Your IP is temporarily blocked due to repeated suspicious requests."))

    # Merge POST/GET data
    if local.request.method == "POST":
        data_dict = local.form_dict
    else:
        data_dict = local.request.args.to_dict(flat=True)

    values = " ".join(str(v) for v in data_dict.values())

    # Scan for patterns
    for pattern in SQLI_PATTERNS:
        if re.search(pattern, values, re.IGNORECASE):
            # Log attempt
            frappe.logger("security_hooks").warn(
                f"SQL Injection attempt from {ip}: {values}"
            )

            # Update attempts counter
            if ip not in IP_BLOCKS:
                IP_BLOCKS[ip] = {"count": 1, "last_attempt": now_ts}
            else:
                IP_BLOCKS[ip]["count"] += 1
                IP_BLOCKS[ip]["last_attempt"] = now_ts

            frappe.throw(_("Suspicious input detected. Request blocked."))
