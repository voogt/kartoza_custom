from frappe import local, session, get_roles
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
    # Only match SQL keywords if followed by likely SQL structure (e.g., whitespace and another keyword or parenthesis)
    r"\bUNION\b[\s\(]",
    r"\bSELECT\b\s+(?:\*|[a-zA-Z0-9_]+|\()",  # select * or select col or select(
    r"\bINSERT\b\s+INTO\b",
    r"\bUPDATE\b\s+[a-zA-Z0-9_]+\s+SET\b",
    r"\bDELETE\b\s+FROM\b",
    r"\bDROP\b\s+(?:TABLE|DATABASE)\b",
    r"\bALTER\b\s+TABLE\b",
    r"(SLEEP\s*\(|BENCHMARK\s*\(|IF\s*\()",
    r"(--|#|/\*|\*/|;)",
    r"XOR\(",
]


# In-memory storage for tracking repeated attempts per IP (SQLi)
IP_BLOCKS = {}  # {ip_address: {"count": int, "last_attempt": timestamp}}

## Spam tracking now uses Redis via frappe.cache()
def check_form_spam():
    """Prevent excessive form submissions from the same IP in a short period (anti-spam)."""
    if not local.request:
        return

    user = getattr(session, "user", None)
    if user and user != "Guest":
        roles = get_roles(user)
        if "Employee" in roles or "Customer Support Portal" in roles:
            return

    path = getattr(local.request, "path", "")
    method_ = (getattr(local.request, "method", "") or "").upper()
    if method_ != "POST":
        return
    # Only check for public/user-facing endpoints
    if not is_public_input_path(path):
        return

    data_dict = local.form_dict or {}
    
    ip = getattr(local.request, "remote_addr", "unknown")
    # Try to get real client IP if behind proxy
    forwarded = local.request.headers.get("X-Forwarded-For") if hasattr(local.request, "headers") else None
    if forwarded:
        ip = forwarded.split(",")[0].strip()

    try:
        frappe.logger("security_hooks").info(f"Form spam check: {ip} {path}")
    except Exception:
        pass
    now_ts = int(time.time())

    # Configurable spam limits
    SPAM_WINDOW = 60  # seconds
    MAX_FORMS_PER_WINDOW = 10
    BLOCK_DURATION = 120  # seconds (2 min block)

    cache = frappe.cache()
    key = f"form_spam:{ip}"
    block_key = f"form_spam_block:{ip}"

    # Check if IP is currently blocked
    blocked_until = cache.get(block_key)
    if blocked_until and int(blocked_until) > now_ts:
        if 'web_form' in data_dict:
            frappe.throw(_("You are temporarily blocked due to excessive form submissions. Please try again later."))
            return  # Ensure no further processing

    # Increment submission count in window
    count = cache.get(key)
    if count is None:
        cache.set(key, 1, ex=SPAM_WINDOW)
        count = 1
    else:
        count = cache.incr(key)

    if count > MAX_FORMS_PER_WINDOW:
        # Block for BLOCK_DURATION
        if 'web_form' in data_dict:
            cache.set(block_key, now_ts + BLOCK_DURATION, ex=BLOCK_DURATION)
            frappe.logger("security_hooks").warning(f"Form spam detected from {ip} on {path}")
            frappe.throw(_("Too many form submissions. Please wait a few minutes and try again."))
            return  # Ensure no further processing

# Configuration
MAX_ATTEMPTS = 3     # max attempts before temporary block
BLOCK_DURATION = 60 # seconds to block after max attempts (1 minute)

def check_sql_injection():

    
    if not local.request:
        return

    # Skip check if user is logged in and has Employee role
    user = getattr(session, "user", None)
    if user and user != "Guest":
        roles = get_roles(user)
        if "Employee" in roles or "Customer Support Portal" in roles:
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


    # Define keys to skip (fields likely to contain image/file data, or
    # password fields on login/sign-up which are never interpolated into
    # SQL and so trigger false positives when they contain characters like
    # "--", "#", ";" or SQL keywords)
    SKIP_KEYS = {
        "image", "file", "attachment", "filedata", "image_data", "img", "avatar", "photo", "picture", "signature",
        "pwd", "password", "new_password", "confirm_password", "old_password",
    }

    # Helper to detect large base64-like strings or embedded image data
    def is_image_or_base64(val):
        if not isinstance(val, str):
            return False
        # Skip if contains data URI for image
        if "data:image/" in val:
            return True
        # Skip if contains a long base64-like substring (500+ chars)
        base64_match = re.search(r'([A-Za-z0-9+/=\r\n]{500,})', val)
        if base64_match:
            return True
        return False

    # Concatenate only non-skipped and non-image/base64 fields for SQLi scan
    values = " ".join(
        str(v)
        for k, v in data_dict.items()
        if k.lower() not in SKIP_KEYS and not is_image_or_base64(v)
    )

    # Scan for patterns
    for pattern in SQLI_PATTERNS:
        if re.search(pattern, values, re.IGNORECASE):
            # Log attempt
            frappe.logger("security_hooks").warning(
                f"SQL Injection attempt from {ip}: {values}"
            )

            # Update attempts counter
            if ip not in IP_BLOCKS:
                IP_BLOCKS[ip] = {"count": 1, "last_attempt": now_ts}
            else:
                IP_BLOCKS[ip]["count"] += 1
                IP_BLOCKS[ip]["last_attempt"] = now_ts

            frappe.throw(_("Suspicious input detected. Request blocked."))
