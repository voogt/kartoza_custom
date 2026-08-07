import frappe

# Every Project money field except Estimated Cost and Total Sales Amount
# (via Sales Order) should always display as ZAR, regardless of the
# project's company currency. This only changes the displayed currency
# symbol/label - the underlying stored numbers are left untouched.
STANDARD_FIELDS = [
    "total_costing_amount",
    "total_purchase_cost",
    "total_billable_amount",
    "total_billed_amount",
    "total_consumed_material_cost",
    "gross_margin",
]


def execute():
    """Force Project's costing/margin currency fields to display as ZAR.

    fix_project_costing_currency.py and calculate_estimated_gross_margin.py
    previously pointed these fields at
    "Company:company:default_currency" so they'd match the project's own
    company (e.g. EUR for Kartoza Lda). Kartoza now wants these fields
    fixed to ZAR instead, ignoring the company currency - except Estimated
    Cost and Total Sales Amount, which stay tied to the company currency.
    """
    for fieldname in STANDARD_FIELDS:
        frappe.make_property_setter(
            {
                "doctype": "Project",
                "fieldname": fieldname,
                "property": "options",
                "value": "ZAR",
                "property_type": "Text",
            }
        )

    frappe.db.set_value(
        "Custom Field",
        "Project-custom_estimated_gross_margin",
        "options",
        "ZAR",
    )

    frappe.clear_cache(doctype="Project")
