import frappe
from datetime import datetime, timedelta
import calendar
import requests

def get_rates(date, cur):
    base_url = "https://api.frankfurter.app"
    latest = "latest"

    # We want to convert FROM EUR TO ZAR, so base=EUR and symbols=ZAR
    conditions = f'base=EUR&symbols=ZAR'

    api = f'{base_url}/{date}?{conditions}' if date else f'{base_url}/{latest}?{conditions}'

    try:
        response = requests.get(api)
        response.raise_for_status()  # Raise error for bad status codes
        r = response.json()["rates"]

        # Now r["ZAR"] is the value of 1 EUR in ZAR
        if cur == "EUR":
            return r["ZAR"]
        else:
            return 0
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

    data_invoice_item = frappe.db.sql(sql_invoice_item, {"sales_order": sales_order, "zar_rate": zar_rate, "end_date": end_date}, as_dict=1, debug=1)

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

    data_orders = frappe.db.sql(sql, {"zar_rate": zar_rate, "start_date": start_date, "end_date": end_date}, as_dict=1, debug=1)

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
    }, as_dict=1, debug=1) or []

def get_departments(company):
    return [
        d.name for d in frappe.get_all(
            "Department",
            filters={'company': company},
            fields=["name"]
        )
        if d.name
    ]

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

def get_all_data(projects):
    # Escape single quotes for all projects
    projects_str = "', '".join([project.replace("'", "''") for project in projects])

    # Query timesheet costing for all projects
    sales_invoice_sql = f"""
        SELECT ts.project, SUM(base_grand_total) as `total_billed_amount`
        FROM `tabSales Invoice` ts
        WHERE status NOT IN ('Cancelled', 'Draft', 'Return', 'Credit Note Issued')
        AND project IN ('{projects_str}')
        GROUP BY ts.project
    """
    
    sales_order_sql = f"""
        SELECT tso.project, SUM(base_grand_total) as `total_sales_order_amount`
        FROM `tabSales Order` tso
        WHERE status NOT IN ('Cancelled', 'Draft', 'Return', 'Credit Note Issued')
        AND project IN ('{projects_str}')
        GROUP BY tso.project
    """
    
    sales_invoice_data = frappe.db.sql(sales_invoice_sql, as_dict=1, debug=1)
    sales_order_data = frappe.db.sql(sales_order_sql, as_dict=1, debug=1)

    return {
        'sales_invoices': {item['project']: item['total_billed_amount'] for item in sales_invoice_data},
        'sales_orders': {item['project']: item['total_sales_order_amount'] for item in sales_order_data},
    }
