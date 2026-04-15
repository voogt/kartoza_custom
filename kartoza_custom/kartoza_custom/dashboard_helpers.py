import frappe
from datetime import datetime, timedelta
import calendar
import requests
from frappe import _
from frappe.utils import flt

def get_rates(date, cur):
    base_url = "https://api.frankfurter.dev/v1/latest"

    # We want to convert FROM EUR TO ZAR, so base=EUR and symbols=ZAR
    conditions = f'base={cur}'

    api =  f'{base_url}?{conditions}'

    try:
        response = requests.get(api)
        response.raise_for_status()  # Raise error for bad status codes
        r = response.json()["rates"]

        return r["ZAR"]
    except (requests.RequestException, KeyError) as e:
        print(f"Error fetching exchange rate: {e}")
        return 0
    

def get_month_ranges(start_date_str, end_date_str):
    """
    Generate a list of month ranges between two dates.
    """
    
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

    current = start_date.replace(day=1)

    month_ranges = []

    while current <= end_date:
        #Get the last day of the current month
        last_day = calendar.monthrange(current.year, current.month)[1]
        month_start = current
        month_end = current.replace(day=last_day)

        #Adjust the month_end if it exceeds the input range
        if month_start < start_date:
            month_start = start_date
        if month_end > end_date:
            month_end = end_date
        
        month_ranges.append((month_start.strftime('%Y-%m-%d'), month_end.strftime('%Y-%m-%d')))

        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1, day=1)
        else:
            current = current.replace(month=current.month + 1, day=1)
    
    return month_ranges


def get_month_label(date_str):
    date = datetime.strptime(date_str, '%Y-%m-%d')
    year = date.year
    month = date.month
    month_name = datetime(year, month, 1).strftime('%B')

    return f"{month_name}-{year}"


def getTotalInvoicesProject(sales_order, end_date, zar_rate):
    
    sql_invoice_item = """
        SELECT 
            ROUND(COALESCE(SUM(
            CASE
                WHEN company = 'Kartoza (Pty) Ltd' THEN
                    tsii.base_amount
                ELSE
                    tsii.base_amount * %(zar_rate)s
            END
            ), 0), 2) as `base_total`
        FROM 
            `tabSales Invoice Item` tsii
        LEFT JOIN 
            `tabSales Invoice` tsi on tsii.parent = tsi.name
        WHERE 
            tsi.status NOT IN ('Cancelled', 'Return', 'Credit Note Issued', 'Draft')
            AND tsii.sales_order = %(sales_order)s
            AND tsi.posting_date <= %(end_date)s
    """

    data_invoice_item = frappe.db.sql(sql_invoice_item, {"sales_order": sales_order, "zar_rate": zar_rate, "end_date": end_date}, as_dict=1, debug=0)

    if len(data_invoice_item) > 0:
        return data_invoice_item[0]["base_total"]
    
    return 0


def getAllSalesOrdersProject(start_date, end_date, zar_rate):

    sql = """
    SELECT 
        name as `sales_order`,
        ROUND(COALESCE((
        CASE
            WHEN company = 'Kartoza (Pty) Ltd' THEN
                tso.base_total
            ELSE
                tso.base_total *  %(zar_rate)s
        END
        ), 0), 2) as `base_total`
    FROM `tabSales Order` tso
    WHERE tso.status NOT IN ('Cancelled', 'Return', 'Credit Note Issued', 'Draft')
    AND tso.creation <= %(end_date)s
    AND tso.name NOT IN (
        SELECT reference_name 
        FROM
        `tabComment` tc
        WHERE
            reference_doctype = 'Sales Order'
            AND content = 'Closed'
            AND tc.creation <= %(end_date)s
    )
    """

    data_orders = frappe.db.sql(sql, {"zar_rate": zar_rate, "start_date": start_date, "end_date": end_date}, as_dict=1, debug=0)

    if len(data_orders) > 0:
        return data_orders
    
    return 0

def getBacklogSalesOrders(start_date, end_date, zar_rate):
    sql = """
    SELECT
        tso.name AS sales_order,
        tso.transaction_date,
        ROUND(
            COALESCE((
                CASE
                    WHEN tso.company = 'Kartoza (Pty) Ltd' THEN tso.base_total
                    ELSE tso.base_total * %(zar_rate)s
                END
            ), 0), 2
        ) AS sales_order_total,

        ROUND(
            COALESCE((
                SELECT SUM(
                    CASE
                        WHEN tsi.company = 'Kartoza (Pty) Ltd' THEN tsii.base_amount
                        ELSE tsii.base_amount * %(zar_rate)s
                    END
                )
                FROM `tabSales Invoice Item` tsii
                INNER JOIN `tabSales Invoice` tsi
                        ON tsii.parent = tsi.name
                WHERE tsii.sales_order = tso.name
                AND tsi.status NOT IN ('Cancelled', 'Return', 'Credit Note Issued', 'Draft')
                AND tsi.posting_date <= %(end_date)s
            ), 0), 2
        ) AS invoiced_total,

        ROUND(
            COALESCE((
                CASE
                    WHEN tso.company = 'Kartoza (Pty) Ltd' THEN tso.base_total
                    ELSE tso.base_total * %(zar_rate)s
                END
            ), 0), 2)
        - ROUND(
            COALESCE((
                SELECT SUM(
                    CASE
                        WHEN tsi.company = 'Kartoza (Pty) Ltd' THEN tsii.base_amount
                        ELSE tsii.base_amount * %(zar_rate)s
                    END
                )
                FROM `tabSales Invoice Item` tsii
                INNER JOIN `tabSales Invoice` tsi
                        ON tsii.parent = tsi.name
                WHERE tsii.sales_order = tso.name
                AND tsi.status NOT IN ('Cancelled', 'Return', 'Credit Note Issued', 'Draft')
                AND tsi.posting_date <= %(end_date)s
            ), 0), 2
        ) AS uninvoiced_total

    FROM `tabSales Order` tso
    WHERE tso.status NOT IN ('Cancelled', 'Return', 'Credit Note Issued', 'Draft')
    AND tso.transaction_date <= %(end_date)s
    AND tso.project IS NOT NULL
    AND tso.project != ''
    AND tso.name NOT IN (
        SELECT reference_name 
        FROM
        `tabComment` tc
        WHERE
            reference_doctype = 'Sales Order'
            AND content = 'Closed'
            AND tc.creation <= %(end_date)s
    )
    HAVING uninvoiced_total > 0;

    """
    return frappe.db.sql(sql, {
        "zar_rate": zar_rate,
        "start_date": start_date,
        "end_date": end_date
    }, as_dict=1, debug=0) or []

def get_departments(company):
    return [
        d.name for d in frappe.get_all(
            "Department",
            filters={'company': company},
            fields=["name"]
        )
        if d.name
    ]

def compute_department_summary_all(timesheets, billing_data, salary_data, all_departments):
    # Convert salary data to dict for quick lookup
    salary_map = {s.department: s.total_salary for s in salary_data}

    department_summary = {}

    # Initialize all departments with zeros
    for dept in all_departments:
        department_summary[dept] = {
            'total_costing_amount': 0,
            'total_billing_amount': 0,
            'total_salary': 0
        }

    for ts in timesheets:
        dept = ts.department
        if not dept:
            continue

        costing = ts.total_costing_amount or 0
        billing = billing_data.get(ts.name, 0)

        if dept not in department_summary:
            department_summary[dept] = {
                'total_costing_amount': 0,
                'total_billing_amount': 0,
                'total_salary': 0
            }

        department_summary[dept]['total_costing_amount'] = department_summary[dept]['total_costing_amount'] + costing
        department_summary[dept]['total_billing_amount'] = department_summary[dept]['total_billing_amount'] + billing

    for dept, salary in salary_map.items():
        if dept not in department_summary:
            department_summary[dept] = {
                'total_costing_amount': 0,
                'total_billing_amount': 0,
                'total_salary': 0
            }
        department_summary[dept]['total_salary'] = salary

    return [{"department": dept, **vals} for dept, vals in department_summary.items()]

def get_timesheet_data(start_date, end_date):
    return frappe.db.sql("""
        SELECT name, department, total_costing_amount
        FROM `tabTimesheet`
        WHERE start_date BETWEEN %s AND %s
    """, (start_date, end_date), as_dict=True)

def get_salary_slips(start_date, end_date):
    return frappe.db.sql("""
        SELECT 
            department,
            SUM(gross_pay) AS total_salary
        FROM `tabSalary Slip` tss 
        WHERE posting_date BETWEEN %s AND %s
        GROUP BY department
    """, (start_date, end_date), as_dict=True)

def get_billing_data(timesheet_names):
    if not timesheet_names:
        return {}
    
    format_strings = ','.join(['%s'] * len(timesheet_names))
    rows = frappe.db.sql(f"""
        SELECT time_sheet, SUM(billing_amount) as billing_amount
        FROM `tabSales Invoice Timesheet` tsit
        LEFT JOIN `tabSales Invoice` tsi ON tsit.parent = tsi.name
        WHERE tsi.status = 'Paid'
        AND time_sheet IN ({format_strings})
        GROUP BY time_sheet
    """, tuple(timesheet_names), as_dict=True)

    return {row.time_sheet: row.billing_amount for row in rows}

def compute_department_summary(timesheets, billing_data, salary_data, all_departments):
    # Convert salary data to dict for quick lookup
    salary_map = {s.department: s.total_salary for s in salary_data if s.department}

    department_summary = {}
    for ts in timesheets:
        dept = ts.department
        if dept is None:  # skip null departments early
            continue

        if dept not in department_summary:
            department_summary[dept] = {
                'total_salary': 0
            }

    # Add salary information
    for dept, salary in salary_map.items():
        if dept not in department_summary:
            department_summary[dept] = {
                'total_salary': 0
            }
        department_summary[dept]['total_salary'] = salary

    # Ensure all known departments are present (pad with 0 if missing)
    for dept in all_departments:
        if dept not in department_summary:
            department_summary[dept] = {
                'total_salary': 0
            }

    return [
        {"department": dept, **vals}
        for dept, vals in department_summary.items()
        if dept is not None
    ]

def get_sa_financial_year_label(date_value):
    """Return South Africa financial-year label (April to March) as FYYYYY."""
    if not date_value:
        return None

    if isinstance(date_value, datetime):
        date_obj = date_value.date()
    elif isinstance(date_value, str):
        date_obj = datetime.strptime(date_value.split(" ")[0], "%Y-%m-%d").date()
    else:
        date_obj = date_value

    fy_year = date_obj.year + 1 if date_obj.month >= 4 else date_obj.year
    return f"FY{fy_year}"

def get_all_data(projects, start_date=None, end_date=None):
    if not projects:
        return {
            'sales_invoices': {},
            'sales_orders': {},
            'risk_percentages': {},
            'deferred_revenues': {},
            'deferred_revenues_by_fy': {},
            'future_financial_years': [],
        }
    
    zar_eur_rate = get_rates(None, "EUR")

    # Escape single quotes for all projects
    projects_str = "', '".join([project.replace("'", "''") for project in projects])

    sales_invoice_date_filter = ""
    sales_order_date_filter = ""
    future_payment_date_filter = ""
    sales_order_comment_filter = ""

    if start_date and end_date:
        sales_invoice_date_filter = f" AND ts.posting_date BETWEEN '{start_date}' AND '{end_date}'"
    if end_date:
        sales_order_date_filter = f" AND tso.transaction_date <= '{end_date}'"
        future_payment_date_filter = f"""
            AND (
                (tps.name IS NOT NULL AND tps.due_date > '{end_date}')
                OR
                (tps.name IS NULL AND tsi.due_date > '{end_date}')
            )
        """
        sales_order_comment_filter = f"""
            AND tso.name NOT IN (
                SELECT reference_name 
                FROM
                `tabComment` tc
                WHERE
                    reference_doctype = 'Sales Order'
                    AND content = 'Closed'
                    AND tc.creation <= '{end_date}'
            )
        """
    else:
        future_payment_date_filter = """
            AND (
                (tps.name IS NOT NULL AND tps.due_date > CURDATE())
                OR
                (tps.name IS NULL AND tsi.due_date > CURDATE())
            )
        """

    # Query timesheet costing for all projects
    sales_invoice_sql = f"""
        SELECT ts.project, 
        SUM(CASE
            WHEN company = 'Kartoza (Pty) Ltd' THEN ts.base_grand_total
            ELSE ts.base_grand_total * {zar_eur_rate}
            END
        ) as `total_billed_amount`
        FROM `tabSales Invoice` ts
        WHERE status NOT IN ('Cancelled', 'Draft', 'Return', 'Credit Note Issued')
        AND project IN ('{projects_str}')
        {sales_invoice_date_filter}
        GROUP BY ts.project
    """
    
    sales_order_sql = f"""
        SELECT tso.project, 
        SUM(CASE
            WHEN company = 'Kartoza (Pty) Ltd' THEN tso.base_grand_total
            ELSE tso.base_grand_total * {zar_eur_rate}
            END
        ) as `total_sales_order_amount`,
        tso.custom_risk_percentage_ as `risk_percentage`
        FROM `tabSales Order` tso
        WHERE tso.docstatus = 1
        AND tso.status NOT IN ('Closed')
        AND project IN ('{projects_str}')
        {sales_order_date_filter}
        {sales_order_comment_filter}
        GROUP BY tso.project
    """
    
    deferred_revenue_sql = f"""
        SELECT
        tso.project,
        tsi.delivery_date as due_date,
        SUM(
            CASE
                WHEN company = 'Kartoza (Pty) Ltd' THEN tsi.base_net_amount
                ELSE tsi.base_net_amount * {zar_eur_rate}
            END
        ) as `deferred_revenue`
        FROM `tabSales Order Item` tsi
        LEFT JOIN `tabSales Order` tso ON tsi.parent = tso.name
        WHERE tso.status NOT IN ('Cancelled', 'Draft', 'Return', 'Credit Note Issued')
        AND tso.project IN ('{projects_str}')
        AND tsi.delivery_date > '{end_date}'
        GROUP BY tso.project, due_date
    """

    sales_invoice_data = frappe.db.sql(sales_invoice_sql, as_dict=1, debug=0)
    sales_order_data = frappe.db.sql(sales_order_sql, as_dict=1, debug=0)
    deferred_revenue_data = frappe.db.sql(deferred_revenue_sql, as_dict=1, debug=0)

    deferred_revenue_totals = {}
    deferred_revenue_by_fy = {}
    future_financial_years = set()

    # Always expose a rolling future FY horizon so table columns are stable
    # even when no schedule rows exist yet for a specific future year.
    if end_date:
        anchor_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    else:
        anchor_date = datetime.now().date()

    anchor_fy_year = anchor_date.year + 1 if anchor_date.month >= 4 else anchor_date.year
    for i in range(1, 4):
        future_financial_years.add(f"FY{anchor_fy_year + i}")

    for row in deferred_revenue_data:
        project = row.get('project')
        due_date = row.get('due_date')
        amount = row.get('deferred_revenue') or 0

        if not project:
            continue

        deferred_revenue_totals[project] = deferred_revenue_totals.get(project, 0) + amount

        fy_label = get_sa_financial_year_label(due_date)
        if not fy_label:
            continue

        future_financial_years.add(fy_label)
        if project not in deferred_revenue_by_fy:
            deferred_revenue_by_fy[project] = {}
        deferred_revenue_by_fy[project][fy_label] = deferred_revenue_by_fy[project].get(fy_label, 0) + amount

    sorted_financial_years = sorted(
        future_financial_years,
        key=lambda fy: int(fy.replace("FY", ""))
    )

    return {
        'sales_invoices': {item['project']: item['total_billed_amount'] for item in sales_invoice_data},
        'sales_orders': {item['project']: item['total_sales_order_amount'] for item in sales_order_data},
        'risk_percentages': {item['project']: item['risk_percentage'] for item in sales_order_data if item['risk_percentage'] is not None},
        'deferred_revenues': deferred_revenue_totals,
        'deferred_revenues_by_fy': deferred_revenue_by_fy,
        'future_financial_years': sorted_financial_years,
    }

def get_profit(income, period_list, company, currency=None, consolidated=False):
	total = 0
	net_profit_loss = {
		"account_name": "'" + _("Profit for the year") + "'",
		"account": "'" + _("Profit for the year") + "'",
		"warn_if_negative": True,
		"currency": currency or frappe.get_cached_value("Company", company, "default_currency"),
	}

	has_value = False

	for period in period_list:
		key = period if consolidated else period.key

		# Only calculate income
		total_income = flt(income[-2][key], 3) if income else 0

		net_profit_loss[key] = total_income

		if net_profit_loss[key]:
			has_value = True

		total += flt(net_profit_loss[key])
		net_profit_loss["total"] = total

	if has_value:
		return net_profit_loss['total']