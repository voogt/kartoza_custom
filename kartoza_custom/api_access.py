import frappe

READ_ONLY_FIELD = "custom_api_read_only"


def enforce_read_only_for_api_key_auth():
    """Restrict the current request to read-only when authenticated via API key.

    Applies only when the authenticated user's profile has API access
    restricted to read-only (User.custom_api_read_only).

    Registered as an `auth_hooks` callback, which runs after
    `validate_auth_via_api_keys` (or OAuth/session login) has already
    resolved `frappe.session.user`. Session-cookie logins and OAuth bearer
    tokens are left untouched.
    """
    if not frappe.request:
        return

    user = frappe.session.user
    if not user or user == "Guest":
        return

    auth_header = frappe.get_request_header("Authorization", "")
    auth_type = auth_header.split(" ")[0].lower() if auth_header else ""
    if auth_type not in ("token", "basic"):
        return

    if frappe.db.get_value("User", user, READ_ONLY_FIELD):
        frappe.flags.api_key_read_only = True
