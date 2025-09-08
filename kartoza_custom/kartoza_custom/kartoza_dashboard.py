import json
import frappe
from frappe import whitelist
from frappe import _
from frappe.utils.global_search import search as default_search
from frappe.utils import now_datetime
from frappe.model.naming import make_autoname
from frappe.core.doctype.communication.email import make
from datetime import datetime, timedelta
import calendar
import requests
from .dashboard_helpers import get_rates, get_month_ranges, get_month_label, getBacklogSalesOrders, get_billing_data, get_departments, get_salary_slips, get_timesheet_data, compute_department_summary, get_all_data

@frappe.whitelist(allow_guest=True)
def get_staff_count(start_date, end_date):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []

    for start, end in ranges:
        opening_count_sql = f"""
            SELECT COUNT(name) as opening_staff 
            FROM `tabEmployee`
            WHERE date_of_joining < '{start}'
            AND designation NOT IN ('Sub-Contractor')
            AND (relieving_date IS NULL OR relieving_date > '{start}' )
            AND (contract_end_date IS NULL OR contract_end_date > '{start}')
        """
        new_staff_count_sql = f"""
            SELECT COUNT(name) as new_staff FROM `tabEmployee` 
            WHERE date_of_joining >= '{start}' 
            AND designation NOT IN ('Sub-Contractor')
            AND date_of_joining <= '{end}' 
        """
        departure_staff_count_sql = f"""
            SELECT COUNT(name) as departure_staff FROM `tabEmployee` 
            WHERE relieving_date >= '{start}' 
            AND designation NOT IN ('Sub-Contractor')
            AND relieving_date <= '{end}' 
        """

        opening_count = frappe.db.sql(opening_count_sql, as_dict=True)[0].opening_staff or 0
        new_staff_count = frappe.db.sql(new_staff_count_sql, as_dict=True)[0].new_staff or 0
        departure_staff_count = frappe.db.sql(departure_staff_count_sql, as_dict=True)[0].departure_staff or 0
        closing_count = opening_count + new_staff_count - departure_staff_count

        month_label = get_month_label(start)

        chart_data.append({
            "month": month_label,
            "opening_count": opening_count,
            "new_staff_count": new_staff_count,
            "departure_staff_count": departure_staff_count,
            "closing_count": closing_count
        })

    # Transform chart_data for stacked chart
    labels = [row["month"] for row in chart_data]

    new_staff_values = [row["new_staff_count"] for row in chart_data]
    departure_values = [row["departure_staff_count"] for row in chart_data]
    closing_values = [row["closing_count"] for row in chart_data]
    opening_values = [row["opening_count"] for row in chart_data]

    data = {
        "element_id": "staff_count",
        "type": "single",
        "title": "Staff Count",
        "labels": labels,
        "isReverse": False,
        "total_cards": [],
        "datasets": [
            {
                "type": "bar",
                "name": "New Staff",
                "values": new_staff_values
            },
            {
                "type": "bar",
                "name": "Departures",
                "values": departure_values
            },
            {
                "type": "bar",
                "name": "Opening Count",
                "values": opening_values
            },
            {
                "type": "bar",
                "name": "Closing Count",
                "values": closing_values
            }
        ]
    }

    return data


@frappe.whitelist(allow_guest=True)
def get_utilisation(start_date, end_date):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []
    total_external = 0
    total_internal = 0
    total_investment = 0
    total_no_project_linked = 0

    for start, end in ranges:
        sql = f"""
            SELECT
                (
                    CASE
                        WHEN p.project_type = 'External' THEN p.project_type
                        WHEN p.project_type = 'Internal' THEN p.project_type
                        WHEN p.project_type = 'Investment' THEN p.project_type
                        ELSE 'No Project Linked'
                    END
                ) as `project_type`,
                SUM(
                    CASE
                        WHEN p.project_type IN ('External', 'Internal', 'Investment') AND task.is_billable = 1 THEN tsd.hours
                        ELSE 0
                    END
                ) AS `billable_hours`
                
            FROM `tabTimesheet Detail` tsd

            JOIN `tabTimesheet` ts
                ON ts.name = tsd.parent
                AND ts.status in ('Submitted', 'Draft', 'Billed', 'Completed')
            JOIN `tabEmployee` emp
                ON ts.employee = emp.name AND emp.custom_utilization = '1'
            JOIN `tabProject` p
                ON tsd.project = p.name
                AND p.project_type in ('External', 'Internal', 'Investment') OR p.project_type = ""
                
            LEFT JOIN `tabTask` task
                ON task.name = tsd.task
                
            WHERE tsd.from_time >= '{start} 00:00:00' 
            AND tsd.to_time <= '{end} 23:59:59' 
            GROUP BY p.project_type
            """

        results = frappe.db.sql(sql, as_dict=True)

        no_project_linked = 0
        external = 0
        internal = 0
        investment = 0

        for result in results:
            if result.project_type == 'No Project Linked':
                no_project_linked = result.billable_hours
                total_no_project_linked += no_project_linked
            elif result.project_type == 'External':
                external = result.billable_hours
                total_external += external
            elif result.project_type == 'Internal':
                internal = result.billable_hours
                total_internal += internal
            elif result.project_type == 'Investment':
                investment = result.billable_hours
                total_investment += investment

        month_label = get_month_label(start)

        chart_data.append({
            "month": month_label,
            "no_project_linked": f"{no_project_linked:.2f}",
            "external": f"{external:.2f}",
            "internal": f"{internal:.2f}",
            "investment": f"{investment:.2f}",
        })

    # Transform chart_data for stacked chart
    labels = [row["month"] for row in chart_data]

    no_project_linked_values = [row["no_project_linked"] for row in chart_data]
    external_values = [row["external"] for row in chart_data]
    internal_values = [row["internal"] for row in chart_data]
    investment_values = [row["investment"] for row in chart_data]

    data = {
        "element_id": "utilisation",
        "isReverse": False,
        "type": "single",
        "title": "Utilisation",
        "total_cards": [
            {
                "title": "Total No Project Linked Hours",
                "value": f"{total_no_project_linked:.2f}"
            },
            {
                "title": "Total External Hours",
                "value": f"{total_external:.2f}"
            },
            {
                "title": "Total Internal Hours",
                "value": f"{total_internal:.2f}"
            },
            {
                "title": "Total Investment Hours",
                "value": f"{total_investment:.2f}"
            }
        ],
        "labels": labels,
        "datasets": [
            {
                "type": "bar",
                "name": "No Project Linked",
                "values": no_project_linked_values
            },
            {
                "type": "bar",
                "name": "External",
                "values": external_values
            },
            {
                "type": "bar",
                "name": "Internal",
                "values": internal_values
            },
            {
                "type": "bar",
                "name": "Investment",
                "values": investment_values
            }
        ]
    }

    return data


@frappe.whitelist(allow_guest=True)
def get_projects_data(start_date, end_date):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []
    total_backlog = 0
    total_projects_closed_value = 0

    for start, end in ranges:
        zar_rate = get_rates(end, "EUR")

        project_closed_sql = f"""
            SELECT
                (CASE
                    WHEN company = 'Kartoza (Pty) Ltd' THEN
                        total_billed_amount
                    ELSE
                        total_billed_amount * {zar_rate}
                END) AS total_billed_amount,
                total_costing_amount,
                ROUND(
                    ( (CASE
                        WHEN company = 'Kartoza (Pty) Ltd' THEN total_billed_amount
                        ELSE total_billed_amount * {zar_rate}
                    END) - total_costing_amount
                    ) 
                ) AS gross_margin
            FROM `tabProject`
            WHERE status = 'Completed'
            AND actual_end_date >= '{start}'
            AND actual_end_date <= '{end}'
            """

        project_closed_results = frappe.db.sql(project_closed_sql, as_dict=True)

        value = 0
        gross_margin = 0

        for result in project_closed_results:
            value += result.total_billed_amount
            total_projects_closed_value += result.total_billed_amount
            gross_margin += result.gross_margin

        month_label = get_month_label(start)

        margin_per = gross_margin / value * 100 if value else 0

        backlog_arr = getBacklogSalesOrders(start, end, zar_rate)
        backlog = 0
        for item in backlog_arr:
            backlog += item["uninvoiced_total"]
            total_backlog += item["uninvoiced_total"]

        chart_data.append({
            "month": month_label,
            "value": f"{value:.2f}",
            "margin_per": f"{margin_per:.2f}",
            "backlog": f"{backlog:.2f}"
        })

    # Transform chart_data for stacked chart
    labels = [row["month"] for row in chart_data]

    project_values = [row["value"] for row in chart_data]
    margin_per_values = [row["margin_per"] for row in chart_data]
    backlog_values = [row["backlog"] for row in chart_data]

    data = {
        "title": "Projects",
        "labels": labels,
        "element_id": "projects",
        "type": "single",
        "isReverse": False,
        "total_cards": [
            {
                "title": "Total Closed Projects Value",
                "value": f"{total_projects_closed_value:.2f}"
            }
        ],
        "datasets": [
            {
                "type": "bar",
                "name": "Backlog: Sold but not invoiced (Rand)",
                "values": backlog_values
            },
            {
                "type": "bar",
                "name": "Value (Closed Projects Rand)",
                "values": project_values
            },
            {
                "type": "line",
                "name": "Margin (Closed Projects) %",
                "values": margin_per_values
            },
        ]
    }

    return data

@frappe.whitelist(allow_guest=True)
def get_cost_profit_center_data(start_date, end_date, type_center):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []
    total_cost_center = 0

    for start, end in ranges:
        zar_rate = get_rates(end, "EUR")

        sales_invoice_sql = f"""
        SELECT 
            ts.cost_center, 
            SUM(
                CASE
                    WHEN company = 'Kartoza (Pty) Ltd' THEN
                        base_grand_total
                    ELSE
                        base_grand_total * {zar_rate}
                END
            ) as `total_billed_amount`
            FROM `tabSales Invoice` ts
            WHERE status NOT IN ('Cancelled', 'Draft', 'Return', 'Credit Note Issued')
            AND ts.posting_date BETWEEN '{start}' AND '{end}'
            GROUP BY ts.cost_center
        """

        timesheet_costing_sql = f"""
            SELECT 
                p.cost_center, 
                SUM(tsd.costing_amount) as `total_costing`
            FROM `tabTimesheet Detail` tsd
            JOIN `tabTimesheet` ts ON tsd.parent = ts.name
            LEFT JOIN `tabProject` p ON tsd.project = p.name
                WHERE ts.docstatus = 1
                AND tsd.from_time BETWEEN '{start}' AND '{end}'
            GROUP BY p.cost_center
        """

        timesheet_costing_data = frappe.db.sql(timesheet_costing_sql, as_dict=1, debug=0)
        sales_invoice_data = frappe.db.sql(sales_invoice_sql, as_dict=1, debug=0)

        data_map = {
            'timesheet_costing': {item['cost_center']: item['total_costing'] for item in timesheet_costing_data},
            'sales_invoices': {item['cost_center']: item['total_billed_amount'] for item in sales_invoice_data},
        }

        cost_center_data = frappe.db.sql(f"""
            SELECT
                p.cost_center as `cost_center`,
                p.total_purchase_cost,
                COALESCE(SUM(tpi.base_grand_total), 0) AS total_purchase_invoice,
                COALESCE(SUM(teecd.amount), 0) AS total_expense_claim
                
            FROM `tabProject` p
            LEFT JOIN `tabEmployee Expense Claim` teec ON 
                p.name = teec.project AND teec.approval_status = 'Approved' AND teec.expense_type_parent = 'Purchase'
            LEFT JOIN `tabEmployee Expense Claim Detail` teecd ON 
                teecd.parent = teec.name AND teecd.expense_date BETWEEN '{start}' AND '{end}'
            LEFT JOIN `tabPurchase Invoice` tpi ON 
                p.name = tpi.project AND tpi.posting_date BETWEEN '{start}' AND '{end}'
            LEFT JOIN `tabCost Center` tcc ON p.cost_center = tcc.name
            WHERE
                p.cost_center != ""
                AND tcc.custom_cost_center_type = '{type_center}'
            GROUP BY
                p.cost_center
            ORDER BY
                p.cost_center
        """, as_dict=1, debug=0)

        cost_center_array = []

        for dict in cost_center_data:
            total_costing_amount = data_map['timesheet_costing'].get(dict['cost_center'], 0)
            total_billed_amount = data_map['sales_invoices'].get(dict['cost_center'], 0)
            profit_loss = total_billed_amount - total_costing_amount

            total_cost_center += profit_loss
            cost_center_array.append({
                'cost_center': dict['cost_center'],
                'profit_loss': f"{profit_loss:.2f}",
            })

        month_label = get_month_label(start)

        chart_data.append({
            "month": month_label,
            "cost_center_data": cost_center_array,
        })

    # Transform chart_data for stacked chart
     # Transform chart_data for stacked chart
    labels = [row["month"] for row in chart_data]

    # Initialize a dict to hold profit/loss values per cost center
    cost_center_map = {}

    for row in chart_data:
        month_data = row["cost_center_data"]
        for item in month_data:
            name = item["cost_center"]
            profit_loss = item["profit_loss"]
            if name not in cost_center_map:
                cost_center_map[name] = []
            cost_center_map[name].append(profit_loss)

    data = {
        "title": f"{type_center} Centers",
        "labels": labels,
        "isReverse": False,
        "element_id": f"{type_center}_centers",
        "total_cards": [
            {
                "title": f"Total {type_center} Centre",
                "value": f"{total_cost_center:.2f}"
            }
        ],
        "type": "single",
        "datasets": []
    }

    for name, values in cost_center_map.items():
        data["datasets"].append({
            "type": "bar",
            "name": name,
            "values": values
        })


    return data


@frappe.whitelist(allow_guest=True)
def get_activity_cost_data(start_date, end_date):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []

    total_activity_costs = 0

    activty_sql = """
        SELECT 
            tat.activity_type AS activity_type
        FROM `tabActivity Type` tat
        WHERE disabled = 0
    """
    activity_types = frappe.db.sql(activty_sql, as_dict=True)

    for start, end in ranges:
        zar_rate = get_rates(end, "EUR")

        tiimesheet_sql = """
        SELECT
            activity_type,
            SUM(IFNULL(costing_amount, 0)) AS sum_costing,
            SUM(IFNULL(hours, 0)) AS total_hours,
            SUM(IFNULL(CASE WHEN is_billable = 1 THEN hours ELSE 0 END, 0)) AS sum_billable_hours,
            SUM(IFNULL(CASE WHEN is_billable = 0 THEN hours ELSE 0 END, 0)) AS sum_unbillable_hours
        FROM `tabTimesheet Detail`
        WHERE from_time BETWEEN %s AND %s
        GROUP BY activity_type
        """
        timesheet_data = frappe.db.sql(tiimesheet_sql, (start, end), as_dict=True)
        timesheet_lookup = {(ts["activity_type"]): ts for ts in timesheet_data}

        activity_array = []

        for activity in activity_types:
            key = (activity["activity_type"])
            ts_details = timesheet_lookup.get(
                key, {"sum_costing": 0, "total_hours": 0, "sum_billable_hours": 0, "sum_unbillable_hours": 0},
            )
            total_activity_costs += ts_details['sum_costing']
            activity_array.append({
                'activity': key,
                'cost': f"{ts_details['sum_costing']:.2f}",
            })

        month_label = get_month_label(start)

        chart_data.append({
            "month": month_label,
            "activity_data": activity_array,
        })

    # Transform chart_data for stacked chart
     # Transform chart_data for stacked chart
    labels = [row["month"] for row in chart_data]

    # Initialize a dict to hold profit/loss values per cost center
    activity_map = {}

    for row in chart_data:
        month_data = row["activity_data"]
        for item in month_data:
            name = item["activity"]
            cost = item["cost"]
            if name not in activity_map:
                activity_map[name] = []
            activity_map[name].append(cost)

    data = {
        "title": f"Activity Cost",
        "isReverse": False,
        "labels": labels,
        "element_id": "activity_cost",
        "type": "single",
        "total_cards": [
            {
                "title": f"Total Activity Cost",
                "value": f"{total_activity_costs:.2f}"
            }
        ],
        "datasets": []
    }

    for name, values in activity_map.items():
        # Remove activities with 0 value for all months
        if all(float(v) == 0.0 for v in values):
            continue
        data["datasets"].append({
            "type": "bar",
            "name": name,
            "values": values
        })


    return data

@frappe.whitelist(allow_guest=True)
def get_company_salary_pty(start_date, end_date):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []

    total_salary = 0

    all_departments = set()

    for start, end in ranges:
        timesheets = get_timesheet_data(start, end)
        salary_data = get_salary_slips(start, end)

        # collect departments from both sources
        all_departments.update(ts.department for ts in timesheets if ts.department)
        all_departments.update(s.department for s in salary_data if s.department)

    for start, end in ranges:
        zar_rate = get_rates(end, "EUR")
        timesheets = get_timesheet_data(start, end)
        billing_data = get_billing_data([ts.name for ts in timesheets])
        salary_data = get_salary_slips(start, end)

        final_dict = compute_department_summary(timesheets, billing_data, salary_data, all_departments)

        for final in final_dict:
            if final["department"] == 'Management - K':
                final['total_salary'] += 230000
            total_salary += final['total_salary']

        month_label = get_month_label(start)

        chart_data.append({
            "month": month_label,
            "salary_data": final_dict,
        })

    # Transform chart_data for stacked chart
    labels = [row["month"] for row in chart_data]

    # Initialize a dict to hold profit/loss values per cost center
    salary_map = {}

    for row in chart_data:
        month_data = row["salary_data"]
        for item in month_data:
            name = item["department"]
            cost = item["total_salary"]
            if name not in salary_map:
                salary_map[name] = []
            salary_map[name].append(cost)

    data = {
        "title": f"Total Department Cost",
        "labels": labels,
        "element_id": "salary_cost",
        "isReverse": False,
        "type": "single",
        "total_cards": [
            {
                "title": f"Total Department Costs",
                "value": f"{total_salary:.2f}"
            }
        ],
        "datasets": []
    }

    for name, values in salary_map.items():
        data["datasets"].append({
            "type": "bar",
            "name": name,
            "values": values
        })


    return data

@frappe.whitelist(allow_guest=True)
def get_company_pipeline_pty():

    total_quotes = 0
    sql = f"""
        SELECT 
        CONCAT(tq.customer_name, " (", tq.name, " | ", DATE(tq.creation), ")") AS `quote_name`,
        tq.base_grand_total AS `amount`
        FROM `tabQuotation` tq
        WHERE tq.status in ('Draft', 'Open')
        AND tq.company = 'Kartoza (Pty) Ltd'
        ORDER BY `amount` ASC
    """

    result = frappe.db.sql(sql, as_dict=1, debug=0)
    for obj in result:
        total_quotes += obj["amount"]

    # Show all quote names as legends, and a single label for the chart (e.g., 'Top 10 Quotes')
    label = ["Open Quotes"]
    datasets = []
    for obj in result:
        datasets.append({
            "type": "bar",
            "name": obj["quote_name"],
            "values": [obj["amount"]]
        })

    data = {
        "title": "Pipeline Quotation Kartoza PTY (Draft/Open)",
        "labels": label,
        "element_id": "quote_pty",
        "type": "single",
        "datasets": datasets,
        "total_cards": [
            {
                "title": f"Total Quotes PTY",
                "value": f"{total_quotes:.2f}"
            }
        ],
    }

    return data

@frappe.whitelist(allow_guest=True)
def get_company_pipeline_lda():

    total_quotes = 0
    zar_rate = get_rates(None, "EUR")
    sql = f"""
        SELECT 
        CONCAT(tq.customer_name, " (", tq.name, " | ", DATE(tq.creation), ")") AS `quote_name`,
        SUM(tq.base_grand_total * {zar_rate}) AS `amount`
        FROM `tabQuotation` tq
        WHERE tq.status in ('Draft', 'Open')
        AND tq.company = 'Kartoza Lda'
        GROUP BY tq.name
        ORDER BY `amount` ASC
    """

    result = frappe.db.sql(sql, as_dict=1, debug=0)

    result = frappe.db.sql(sql, as_dict=1, debug=0)
    for obj in result:
        total_quotes += obj["amount"]

    # Show all quote names as legends, and a single label for the chart (e.g., 'Top 10 Quotes')
    label = ["Open Quotes"]
    datasets = []
    for obj in result:
        datasets.append({
            "type": "bar",
            "name": obj["quote_name"],
            "values": [obj["amount"]]
        })

    data = {
        "title": "Pipeline Quotation Kartoza LDA (Draft/Open)",
        "labels": label,
        "isReverse": False,
        "element_id": "quote_lda",
        "type": "single",
        "datasets": datasets,
        "total_cards": [
            {
                "title": f"Total Quotes LDA",
                "value": f"{total_quotes:.2f}"
            }
        ],
    }

    return data

@frappe.whitelist(allow_guest=True)
def get_open_sla():
    chart_data = []
    zar_rate = get_rates(None, "EUR")

    sql = f"""
    SELECT
        COALESCE(so_data.sales_order_amount, 0) AS sales_order_amount,
        COALESCE(si_data.sales_invoice_amount, 0) AS sales_invoice_amount,
        tp.project_name AS project,
        tp.expected_start_date AS start_date,
        tp.expected_end_date AS end_date,
        CASE 
            WHEN LOWER(tp.project_name) LIKE '%sla%' THEN 'SLA'
            WHEN LOWER(tp.project_name) LIKE '%hosting%' THEN 'HOSTING'
            ELSE NULL
        END AS sla_type
    FROM `tabProject` tp

    -- Subquery for Sales Orders
    LEFT JOIN (
        SELECT
            tsoi.custom_project AS project_name,
            SUM(
                CASE 
                    WHEN tso.company = 'Kartoza (Pty) Ltd' THEN tsoi.base_amount
                    ELSE tsoi.base_amount * {zar_rate}
                END
            ) AS sales_order_amount
        FROM `tabSales Order Item` tsoi
        LEFT JOIN `tabSales Order` tso ON tsoi.parent = tso.name
        GROUP BY tsoi.custom_project
    ) AS so_data ON so_data.project_name = tp.name

    -- Subquery for Sales Invoices
    LEFT JOIN (
        SELECT
            tsi.project AS project_name,
            SUM(
                CASE 
                    WHEN tsi.company = 'Kartoza (Pty) Ltd' THEN tsi.base_total
                    ELSE tsi.base_total * {zar_rate}
                END
            ) AS sales_invoice_amount
        FROM `tabSales Invoice` tsi
        WHERE tsi.status = 'Paid'
        GROUP BY tsi.project
    ) AS si_data ON si_data.project_name = tp.name

    WHERE tp.status = 'Open'
    AND (
        LOWER(tp.project_name) LIKE '%sla%' 
        OR LOWER(tp.project_name) LIKE '%hosting%'
    )
    ORDER BY tp.expected_start_date ASC;

    """

    all_sla = frappe.db.sql(sql, as_dict=1, debug=0)

    for sla in all_sla:
        project_label = sla["project"]

        chart_data.append({
            "project": project_label,
            "sales_order_amount": sla["sales_order_amount"],
            "sales_invoice_amount": sla["sales_invoice_amount"],
        })

    # Transform chart_data for stacked chart
    labels = [row["project"] for row in chart_data]

    sales_order_amount_values = [row["sales_order_amount"] for row in chart_data]
    sales_invoice_amount_values = [row["sales_invoice_amount"] for row in chart_data]

    data = {
        "element_id": "open_sla",
        "type": "single",
        "title": "Current open SLA's",
        "labels": labels,
        "isReverse": True,
        "total_cards": [],
        "datasets": [
            {
                "type": "bar",
                "name": "Total Sales Order Amount",
                "values": sales_order_amount_values
            },
            {
                "type": "bar",
                "name": "Total Sales Invoice Amount",
                "values": sales_invoice_amount_values
            }
        ]
    }

    return data

@frappe.whitelist(allow_guest=True)
def get_open_sales_orders():
    chart_data = []

    final_dict = frappe.db.sql("""
    SELECT
        p.name AS project,
        p.status
        FROM `tabProject` p
        WHERE p.status = 'Open'
        GROUP BY p.name
        ORDER BY p.name
    """, as_dict=1, debug=0)

    # Extract project names
    projects = [d['project'] for d in final_dict]

    # Fetch related sales data
    data_map = get_all_data(projects)

    # Enrich final_dict with totals
    for d in final_dict:
        billed = data_map['sales_invoices'].get(d['project'], 0) or 0
        ordered = data_map['sales_orders'].get(d['project'], 0) or 0
        to_be_billed = ordered - billed

        d['total_billed_amount'] = billed
        d['total_billed_sales_order'] = ordered
        d['total_to_be_billed'] = to_be_billed if to_be_billed > 0 else 0

    # Filter only projects that have sales orders
    all_sales_orders = [d for d in final_dict if d['total_billed_sales_order'] > 0]

    for sale_order in all_sales_orders:
        project_label = sale_order["project"]

        chart_data.append({
            "project": project_label,
            "total_billed_amount": sale_order["total_billed_amount"],
            "total_billed_sales_order": sale_order["total_billed_sales_order"],
        })

    # Transform chart_data for stacked chart
    labels = [row["project"] for row in chart_data]

    total_billed_amount_values = [row["total_billed_amount"] for row in chart_data]
    total_billed_sales_order_values = [row["total_billed_sales_order"] for row in chart_data]

    data = {
        "element_id": "open_sales_orders",
        "type": "single",
        "title": "Current Open Sales Orders",
        "labels": labels,
        "isReverse": True,
        "total_cards": [],
        "datasets": [
            {
                "type": "bar",
                "name": "Total Billed Amount",
                "values": total_billed_amount_values
            },
            {
                "type": "bar",
                "name": "Total Billed Sales Order",
                "values": total_billed_sales_order_values
            }
        ]
    }

    return data




