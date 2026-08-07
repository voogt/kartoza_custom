import frappe

from erpnext.projects.doctype.project.project import update_costing_and_billing


def execute():
    """Make Total Billed Amount (via Sales Invoice) genuinely ZAR-denominated.

    CustomProject.update_billed_amount now converts each linked Sales
    Invoice line's base_net_amount (in that invoice's own company
    currency) to ZAR, using the exchange rate on the invoice's own
    posting_date, instead of leaving the total in the invoice's company
    currency. Its currency label was already set to ZAR by
    set_project_costing_fields_to_zar.py; only the underlying value was
    still wrong.

    Recompute existing projects via update_costing_and_billing (not just
    update_billed_amount in isolation) so total_billed_amount, gross_margin,
    per_gross_margin, and custom_estimated_gross_margin/_% all get
    refreshed together and saved in one go, the same way the live
    SalesInvoice.update_project()/SalesOrder.update_project() call paths
    bundle their updates before a single db_update().
    """
    for project in frappe.get_all("Project", filters={"status": ["!=", "Cancelled"]}, pluck="name"):
        update_costing_and_billing(project)
