# my_app/overrides/project.py

import frappe
from erpnext.projects.doctype.project.project import Project


class CustomProject(Project):

    def onload(self):
        super().onload()

        if not self.total_sales_amount:
            self.total_sales_amount = self.get_total_sales_amount_from_sales_order_items()

    def get_total_sales_amount_from_sales_order_items(self):
        """Sum the amount of submitted Sales Order Items linked to this project.

        total_sales_amount is a manually editable field (see validate below),
        so it is not kept in sync automatically. This backfills it on load
        when it is still 0, e.g. for projects created before it was set.
        """
        total_sales_amount = frappe.db.sql(
            """
            select sum(soi.base_amount)
            from `tabSales Order Item` soi
            inner join `tabSales Order` so on so.name = soi.parent
            where soi.custom_project = %s
            """,
            self.name,
        )

        return total_sales_amount[0][0] if total_sales_amount and total_sales_amount[0][0] else 0

    def validate(self):
        # preserve user values
        user_percent = self.percent_complete
        user_sales = self.total_sales_amount

        super().validate()

        self.percent_complete = user_percent
        self.total_sales_amount = user_sales