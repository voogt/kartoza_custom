import frappe

from erpnext.projects.doctype.project.project import update_costing_and_billing


def execute():
    """Turn Project's "Estimated Gross Margin" fields into computed fields.

    custom_estimated_gross_margin/_% were plain Data fields that had to be
    typed in by hand. CustomProject.calculate_estimated_gross_margin now
    derives them from Total Sales Amount, so switch them to a read-only
    Currency/Percent pair (matching how Gross Margin/Gross Margin % are
    modelled) and backfill existing projects.
    """
    frappe.db.set_value(
        "Custom Field",
        "Project-custom_estimated_gross_margin",
        {
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "read_only": 1,
        },
    )
    frappe.db.set_value(
        "Custom Field",
        "Project-custom_estimated_gross_margin_",
        {
            "fieldtype": "Percent",
            "read_only": 1,
        },
    )
    # frappe.db.set_value bypasses Custom Field.on_update's schema sync, so
    # the column stays varchar(140) unless we sync it explicitly.
    frappe.db.updatedb("Project")
    frappe.clear_cache(doctype="Project")

    for project in frappe.get_all("Project", filters={"status": ["!=", "Cancelled"]}, pluck="name"):
        update_costing_and_billing(project)
