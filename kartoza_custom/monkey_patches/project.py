# my_app/overrides/project.py

import frappe
from frappe.utils import flt

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

    def update_sales_amount(self):
        """Sum linked Sales Orders' totals, converted to ZAR.

        erpnext.projects.doctype.project.project.Project.update_sales_amount
        sums base_net_total, which is in each Sales Order's own company
        currency (e.g. EUR for Kartoza Lda). erpnext.selling.doctype.
        sales_order.sales_order.SalesOrder.update_project() calls this
        method directly whenever a linked Sales Order is submitted or
        cancelled, then writes it straight to the database with db_update()
        - bypassing save()/validate(), so the "preserve user value" logic in
        validate() below never runs for this path. That direct call is how
        total_sales_amount actually gets overwritten in practice. Convert
        each order's total to ZAR using the exchange rate on its own
        transaction_date (matching how base_net_total itself was derived
        using the rate at the time), so the figure is comparable across
        companies regardless of which currency the order was raised in.
        """
        from erpnext.setup.utils import get_exchange_rate

        sales_orders = frappe.get_all(
            "Sales Order",
            filters={"project": self.name, "docstatus": 1},
            fields=["base_net_total", "company", "transaction_date"],
        )

        total_sales_amount = 0
        for sales_order in sales_orders:
            company_currency = frappe.get_cached_value("Company", sales_order.company, "default_currency")
            exchange_rate = get_exchange_rate(company_currency, "ZAR", sales_order.transaction_date)
            total_sales_amount += flt(sales_order.base_net_total) * flt(exchange_rate)

        self.total_sales_amount = total_sales_amount

    def update_billed_amount(self):
        """Sum linked Sales Invoices' totals, converted to ZAR.

        Mirrors update_sales_amount() above: erpnext.projects.doctype.
        project.project.Project.update_billed_amount sums base_net_amount,
        which is in each Sales Invoice's own company currency.
        erpnext.accounts.doctype.sales_invoice.sales_invoice.SalesInvoice.
        update_project() calls this method directly (bypassing save()/
        validate()) whenever a linked Sales Invoice is submitted or
        cancelled, then writes straight to the database with db_update() -
        that direct call is how total_billed_amount actually gets
        overwritten in practice. Convert each invoice line's amount to ZAR
        using the exchange rate on that invoice's own posting_date, so the
        figure is comparable across companies regardless of which currency
        it was raised in.

        The two query branches mirror upstream's get_billed_amount_from_parent
        (invoices linked via Sales Invoice.project, only counting items with
        no project of their own) and get_billed_amount_from_child (items
        linked via Sales Invoice Item.project directly).
        """
        from erpnext.setup.utils import get_exchange_rate

        rows = frappe.db.sql(
            """
            select si_item.base_net_amount as base_net_amount,
                si.company as company, si.posting_date as posting_date
            from `tabSales Invoice` si
            join `tabSales Invoice Item` si_item on si_item.parent = si.name
            where si_item.project is null
                and si.project is not null
                and si.project = %(project)s
                and si.docstatus = 1

            union all

            select si_item.base_net_amount as base_net_amount,
                si.company as company, si.posting_date as posting_date
            from `tabSales Invoice Item` si_item
            join `tabSales Invoice` si on si.name = si_item.parent
            where si_item.project = %(project)s
                and si_item.docstatus = 1
            """,
            {"project": self.name},
            as_dict=True,
        )

        exchange_rates = {}
        total_billed_amount = 0
        for row in rows:
            company_currency = frappe.get_cached_value("Company", row.company, "default_currency")
            cache_key = (company_currency, row.posting_date)
            if cache_key not in exchange_rates:
                exchange_rates[cache_key] = get_exchange_rate(company_currency, "ZAR", row.posting_date)
            total_billed_amount += flt(row.base_net_amount) * flt(exchange_rates[cache_key])

        self.total_billed_amount = total_billed_amount

    def validate(self):
        # preserve user values
        user_percent = self.percent_complete
        user_sales = self.total_sales_amount

        super().validate()

        self.percent_complete = user_percent
        self.total_sales_amount = user_sales
        # total_sales_amount was just restored to the user-facing value above,
        # so recompute against that rather than the transient Sales Order sum
        # update_costing() saw.
        self.calculate_estimated_gross_margin()

    def update_costing(self):
        super().update_costing()
        self.fix_timesheet_currency_conversion()
        self.calculate_gross_margin()
        self.calculate_estimated_gross_margin()

    def calculate_estimated_gross_margin(self):
        """Gross margin against the full contracted Sales Order value.

        calculate_gross_margin() (upstream) weighs Total Billed Amount, so a
        project reads as a heavy loss until invoicing catches up with work
        done, even if the underlying deal is profitable. This mirrors that
        formula but substitutes Total Sales Amount, the project's full
        contracted value, so custom_estimated_gross_margin/_% reflect the
        deal as a whole rather than only what has been invoiced so far.
        """
        expense_amount = (
            flt(self.total_costing_amount)
            + flt(self.total_purchase_cost)
            + flt(self.get("total_consumed_material_cost", 0))
        )

        self.custom_estimated_gross_margin = flt(flt(self.total_sales_amount) - expense_amount, 2)
        if self.total_sales_amount:
            self.custom_estimated_gross_margin_ = flt(
                self.custom_estimated_gross_margin / flt(self.total_sales_amount) * 100, 2
            )
        else:
            self.custom_estimated_gross_margin_ = 0

    def fix_timesheet_currency_conversion(self):
        """Recompute Timesheet-derived totals using company-currency amounts.

        erpnext.projects.doctype.project.project.Project.update_costing sums
        Timesheet Detail's costing_amount/billing_amount, which are in the
        Timesheet's own currency, not the company's default currency. That
        mixes currencies with the Sales Order/Invoice totals (which use
        base_ amounts, already in company currency), so the margin is wrong
        whenever a timesheet is entered in a currency other than the
        project's company currency. base_costing_amount/base_billing_amount
        are the same amounts already converted at the timesheet's exchange
        rate, so use those instead.
        """
        from frappe.query_builder.functions import Sum

        TimesheetDetail = frappe.qb.DocType("Timesheet Detail")
        totals = (
            frappe.qb.from_(TimesheetDetail)
            .select(
                Sum(TimesheetDetail.base_costing_amount).as_("costing_amount"),
                Sum(TimesheetDetail.base_billing_amount).as_("billing_amount"),
            )
            .where((TimesheetDetail.project == self.name) & (TimesheetDetail.docstatus == 1))
        ).run(as_dict=True)[0]

        self.total_costing_amount = totals.costing_amount or 0
        self.total_billable_amount = totals.billing_amount or 0
