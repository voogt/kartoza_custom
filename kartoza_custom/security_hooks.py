# Only scan public endpoints for SQL injection
def is_public_input_path(path):
    """Return True if path is NOT a known safe internal endpoint (scan all user-facing endpoints)."""
    if not path:
        return False
    # Skip internal desk, assets, and common internal API calls
    if path.startswith("/app/") or path.startswith("/assets/"):
        return False
    # Skip internal API method calls to frappe.* (desk, core)
    if path.startswith("/api/method/frappe."):
        return False
    # Otherwise, treat as public/user-facing (including /, /web_form, etc)
    return True
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
    if not local.request:
        return

    path = getattr(local.request, "path", "")
    method = (getattr(local.request, "method", "") or "").upper()

    # Only inspect POST requests to public endpoints
    if method != "POST":
        return
    if not is_public_input_path(path):
        return

    ip = getattr(local.request, "remote_addr", "unknown")
    now_ts = time.time()

    # Clean up expired blocks
    expired_ips = [k for k, v in IP_BLOCKS.items() if now_ts - v.get("last_attempt", 0) > BLOCK_DURATION]
    for k in expired_ips:
        del IP_BLOCKS[k]

    # Block IP if previously exceeded
    # if ip in IP_BLOCKS and IP_BLOCKS[ip]["count"] > MAX_ATTEMPTS:
    #     frappe.throw(_("Your IP is temporarily blocked due to repeated suspicious requests."))

    # Only scan form_dict for POST
    data_dict = local.form_dict or {}
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
