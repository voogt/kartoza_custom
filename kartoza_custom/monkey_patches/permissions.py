import frappe

logger = frappe.logger("kartoza_custom.permissions")

# Permission types that mutate data. Denied outright when the current
# request is flagged read-only by kartoza_custom.api_access.
WRITE_PTYPES = {"write", "create", "delete", "submit", "cancel", "amend", "import", "share"}


def apply_monkey_patches(*args, **kwargs):
    """Wrap frappe.permissions.has_permission to enforce read-only API keys.

    API-key-authenticated requests flagged read-only (see
    kartoza_custom.api_access) can never be granted a write-type
    permission, regardless of the user's roles.

    Safe to run repeatedly (request/job lifecycle).
    """
    import frappe.permissions as permissions

    if getattr(permissions, "_kartoza_read_only_patch_applied", False):
        return

    permissions._kartoza_original_has_permission = permissions.has_permission

    def has_permission(doctype, ptype="read", doc=None, user=None, raise_exception=True, **kwargs):
        if ptype in WRITE_PTYPES and frappe.flags.get("api_key_read_only"):
            return False
        return permissions._kartoza_original_has_permission(
            doctype, ptype, doc=doc, user=user, raise_exception=raise_exception, **kwargs
        )

    permissions.has_permission = has_permission
    permissions._kartoza_read_only_patch_applied = True
    logger.info("Applied read-only API key permission monkey patch")
