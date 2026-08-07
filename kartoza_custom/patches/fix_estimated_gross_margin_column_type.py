import frappe


def execute():
    """Fix the DB column type for the Estimated Gross Margin fields.

    calculate_estimated_gross_margin.py changed these Custom Fields from
    Data to Currency/Percent via frappe.db.set_value, which updates the
    Custom Field record but bypasses Custom Field.on_update's schema sync
    (frappe.db.updatedb), leaving the underlying columns as varchar(140).

    Some values in those columns also have more than the 9 fractional
    digits the target decimal(21,9) columns allow (raw Python float
    arithmetic, e.g. "-810511.8977037941"), which makes the ALTER TABLE
    fail with "Data truncated" under strict SQL mode. Blank/null/non-numeric
    leftovers from the fields' Data-field days (e.g. "TBC") would trip the
    same error on the round() below, so reset anything that isn't already a
    plain decimal string before rounding what's left to 2 decimal places.
    """
    for fieldname in ("custom_estimated_gross_margin", "custom_estimated_gross_margin_"):
        frappe.db.sql(
            f"""
            update `tabProject`
            set `{fieldname}` = '0'
            where `{fieldname}` is null
               or trim(`{fieldname}`) = ''
               or `{fieldname}` not regexp '^-?[0-9]+(\\.[0-9]+)?$'
            """
        )
        frappe.db.sql(
            f"""
            update `tabProject`
            set `{fieldname}` = round(`{fieldname}`, 2)
            where `{fieldname}` != '0'
            """
        )

    # Alter just these two columns directly (instead of frappe.db.updatedb,
    # which bundles every numeric column on Project into one ALTER and
    # silently swallows the real error on failure), so a real failure here
    # surfaces instead of being caught and printed as a one-line query dump.
    frappe.db.sql_ddl(
        """
        ALTER TABLE `tabProject`
        MODIFY `custom_estimated_gross_margin` decimal(21,9) not null default 0,
        MODIFY `custom_estimated_gross_margin_` decimal(21,9) not null default 0
        """
    )
