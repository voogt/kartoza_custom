# security_hooks.py
import re
import time
import frappe
from frappe import _

# Safer SQLi patterns (focused, not overly broad)
SQLI_PATTERNS = [
    r"(?i)\bUNION\b.*\bSELECT\b",     # UNION ... SELECT
    r"(?i)\bSELECT\b.*\bFROM\b",      # SELECT ... FROM (catch real queries)
    r"(?i)SLEEP\s*\(\s*\d+\s*\)",     # SLEEP(n)
    r"(?i)BENCHMARK\s*\(",            # BENCHMARK(
    r"(?i)XOR\s*\(",                  # XOR(
    r"(?i)INFORMATION_SCHEMA",        # information_schema references
    r"(?i)CASE\s+WHEN\s+THEN",        # boolean-based payload patterns
    r"['\"].{0,50};",                 # quote followed shortly by semicolon (suspicious)
]

# Per-IP in-memory tracking (consider Redis for multi-worker)
IP_BLOCKS = {}          # { ip: {"count": int, "last_attempt": ts} }
MAX_ATTEMPTS = 3
BLOCK_DURATION = 600    # seconds

# Very conservative whitelist of public endpoints to scan
PUBLIC_WHITELIST_PREFIXES = [
    "/web_form",                           # ERPNext web forms
    "/login",                              # login POST
    "/contact-us", "/consulting-service",  # common web form slugs
    "/blog",                               # blog submissions
    "/print_format/download_pdf",          # print requests that can accept name/etc
]

def is_public_input_path(path):
    """Return True if path is likely to contain untrusted user-submitted data."""
    if not path:
        return False

    # Skip internal desk, assets, and common internal API calls
    if path.startswith("/app/") or path.startswith("/assets/"):
        return False

    # Skip internal API method calls to frappe.* (desk, core)
    # e.g. /api/method/frappe.desk.* or /api/method/frappe.integrations.*
    if path.startswith("/api/method/") and path.startswith("/api/method/frappe."):
        return False

    # Only allow scanning of known public prefixes OR anything that explicitly
    # contains "web_form" in the path (some endpoints include web_form in URL)
    if any(path.startswith(p) for p in PUBLIC_WHITELIST_PREFIXES):
        return True

    if "web_form" in path:
        return True

    # Default: do not treat as public input (safe)
    return False

def check_sql_injection():
    """Before-request hook: scan only public POST endpoints for SQLi patterns."""
    from frappe import local

    if not local.request:
        return

    path = local.request.path or ""
    method = (local.request.method or "").upper()

    # Only inspect POST requests
    if method != "POST":
        return

    # Only inspect a small, conservative set of public endpoints
    if not is_public_input_path(path):
        return

    ip = getattr(local.request, "remote_addr", "unknown")
    now_ts = time.time()

    # Cleanup expired blocks
    expired = [k for k, v in IP_BLOCKS.items() if now_ts - v.get("last_attempt", 0) > BLOCK_DURATION]
    for k in expired:
        del IP_BLOCKS[k]

    # If IP is blocked, throw and stop processing
    if ip in IP_BLOCKS and IP_BLOCKS[ip]["count"] > MAX_ATTEMPTS:
        frappe.logger("security_hooks").warning(f"Blocked repeated suspicious requests from {ip} to {path}")
        frappe.throw(_("Your IP is temporarily blocked due to repeated suspicious requests."))

    # Get form data (only form_dict for POST)
    data_dict = local.form_dict or {}
    # Only consider values longer than 6 chars (ignore tiny inputs)
    candidate_values = [str(v).strip() for v in data_dict.values() if v and len(str(v).strip()) > 6]
    if not candidate_values:
        return

    combined = " ".join(candidate_values)

    # Run regex patterns (stop at first match)
    for pattern in SQLI_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            # Log the attempt with truncated values (avoid huge logs)
            logged_value = combined if len(combined) < 200 else combined[:200] + "..."
            frappe.logger("security_hooks").warning(f"SQLi attempt from {ip} on {path}: {logged_value}")

            # Update counter for IP
            if ip not in IP_BLOCKS:
                IP_BLOCKS[ip] = {"count": 1, "last_attempt": now_ts}
            else:
                IP_BLOCKS[ip]["count"] += 1
                IP_BLOCKS[ip]["last_attempt"] = now_ts

            # Block the request
            frappe.throw(_("Suspicious input detected. Request blocked."))

    # No match -> continue normally
    return
