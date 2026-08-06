import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute():
    """Add the "Restrict API to Read-Only" checkbox to the User doctype.

    Unchecked by default, including for newly created users. Admins opt a
    user into read-only API access explicitly on their profile.
    """
    create_custom_field(
        "User",
        {
            "fieldname": "custom_api_read_only",
            "label": "Restrict API to Read-Only",
            "fieldtype": "Check",
            "insert_after": "api_key",
            "permlevel": 1,
            "default": "0",
            "description": (
                "When checked, requests authenticated with this user's API key/secret "
                "can only read data. Create, write, delete, submit, cancel and other "
                "write operations are blocked, regardless of the user's roles."
            ),
        },
    )
