import frappe

from erpnext.projects.doctype.project.project import update_costing_and_billing


def execute():
    """Make Total Sales Amount (via Sales Order) genuinely ZAR-denominated.

    CustomProject.update_sales_amount now converts each linked Sales
    Order's base_net_total (in that order's own company currency) to ZAR,
    using the exchange rate on the order's own transaction_date, instead of
    leaving the total in the order's company currency. Point the field's
    currency label at ZAR to match the real converted value, and recompute
    existing projects so already-stored totals reflect the conversion.

    Timesheet-derived costing/billing figures (total_costing_amount,
    total_billable_amount) are entered in ZAR by convention at Kartoza, so
    they are left as-is - only Total Sales Amount needed real conversion
    here.
    """
    frappe.make_property_setter(
        {
            "doctype": "Project",
            "fieldname": "total_sales_amount",
            "property": "options",
            "value": "ZAR",
            "property_type": "Text",
        }
    )
    frappe.clear_cache(doctype="Project")

    for project in frappe.get_all("Project", filters={"status": ["!=", "Cancelled"]}, pluck="name"):
        update_costing_and_billing(project)
