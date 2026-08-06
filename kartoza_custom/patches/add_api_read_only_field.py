import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute():
    """Add the "Restrict API to Read-Only" checkbox to the User doctype.

    Grandfathers in users who already have an API key so this change
    does not silently break existing integrations that write via API
    key/secret.
    """
    create_custom_field(
        "User",
        {
            "fieldname": "custom_api_read_only",
            "label": "Restrict API to Read-Only",
            "fieldtype": "Check",
            "insert_after": "api_key",
            "permlevel": 1,
            "default": "1",
            "description": (
                "When checked, requests authenticated with this user's API key/secret "
                "can only read data. Create, write, delete, submit, cancel and other "
                "write operations are blocked, regardless of the user's roles."
            ),
        },
    )

    frappe.db.set_value(
        "User",
        {"api_key": ["is", "set"]},
        "custom_api_read_only",
        0,
        update_modified=False,
    )
