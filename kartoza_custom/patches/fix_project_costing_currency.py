import frappe

from erpnext.projects.doctype.project.project import update_costing_and_billing

# These Currency fields on Project have no "options" set, so they render
# using the global default currency symbol instead of the project's company
# currency. estimated_costing/gross_margin already point at
# "Company:company:default_currency"; bring the rest in line via Property
# Setters so the fix survives erpnext app updates.
CURRENCY_FIELDS = [
    "total_costing_amount",
    "total_purchase_cost",
    "total_sales_amount",
    "total_billable_amount",
    "total_billed_amount",
    "total_consumed_material_cost",
]


def execute():
    """Fix Project costing/billing fields showing the wrong currency.

    Also recalculates existing projects so totals saved before the
    CustomProject.update_costing fix (mixing Timesheet-currency amounts
    with company-currency amounts) get corrected.
    """
    for fieldname in CURRENCY_FIELDS:
        frappe.make_property_setter(
            {
                "doctype": "Project",
                "fieldname": fieldname,
                "property": "options",
                "value": "Company:company:default_currency",
                "property_type": "Text",
            }
        )

    for project in frappe.get_all("Project", filters={"status": ["!=", "Cancelled"]}, pluck="name"):
        update_costing_and_billing(project)
