import json
import frappe
from frappe import whitelist
from frappe import _
from frappe.utils.global_search import search as default_search
from frappe.utils import now_datetime
from frappe.model.naming import make_autoname
from frappe.core.doctype.communication.email import make

@frappe.whitelist(allow_guest=True)
def get_project_sla_overview_table():

    # Step 1: Get all open projects in one query
    sql = f"""
    SELECT 
        tp.name as `project`,
        tp.company as `company`,
        tp.expected_time as `expected_time`,
        tp.actual_time as `consumed_time`,
        tp.percent_complete as `actual_progress`,
        tp.expected_end_date as `due_date`,
        tp.total_costing_amount as `total_costing`
    FROM tabProject AS tp
    LEFT JOIN `tabEmployee` te ON te.user_id = tp.project_lead
    WHERE tp.status = 'Open'
    GROUP BY tp.project_name
    """
    final_arr = frappe.db.sql(sql, as_dict=1, debug=0)

    # Step 2: Get all billable hours for these projects in one query
    project_names = [row['project'] for row in final_arr if row['project']]
    if project_names:
        placeholders = ','.join([f"%({i})s" for i in range(len(project_names))])
        timesheet_sql = f"""
            SELECT 
                ttd.project as project,
                ROUND(COALESCE(SUM(CASE WHEN ttd.is_billable = 1 THEN ttd.hours ELSE 0 END), 0), 2) as billable_hours
            FROM `tabTimesheet` tt
            LEFT JOIN `tabTimesheet Detail` ttd ON ttd.parent = tt.name
            WHERE ttd.project IN ({placeholders})
            AND ttd.docstatus = 1
            AND ttd.task != ''
            AND tt.status = 'Submitted'
            GROUP BY ttd.project
        """
        params = {str(i): name for i, name in enumerate(project_names)}
        timesheet_data = frappe.db.sql(timesheet_sql, params, as_dict=1, debug=0)
        timesheet_map = {row['project']: row['billable_hours'] for row in timesheet_data}
    else:
        timesheet_map = {}

    # Step 3: Get all sales order totals for these projects in one query
    sales_sql = f"""
        SELECT 
            tso.project as project,
            SUM(tso.base_total) as base_total
        FROM `tabSales Order` tso
        WHERE tso.status NOT IN ('Cancelled', 'Return', 'Credit Note Issued', 'Draft')
        AND tso.project IN ({placeholders})
        GROUP BY tso.project
    """
    sales_data = frappe.db.sql(sales_sql, params, as_dict=1, debug=0)
    sales_map = {row['project']: row['base_total'] for row in sales_data}

    # Step 4: Map timesheet and sales order data to projects and calculate fields
    for arr in final_arr:
        project = arr["project"]
        expected_time = arr.get('expected_time') or 0
        billable_hours = timesheet_map.get(project, 0)
        billable_hours_percent = (billable_hours / expected_time * 100) if expected_time else 0
        if billable_hours_percent > 100:
            billable_hours_percent = 100 - billable_hours_percent
        arr['billable_hours'] = billable_hours
        arr['billable_hours_percent'] = billable_hours_percent
        arr['billable_hours_left'] = expected_time - billable_hours

        actual_progress = arr.get('actual_progress') or 0
        arr['progress_status'] = ''
        if actual_progress > billable_hours_percent:
            arr["progress_status"] = 'On Track'
        elif actual_progress < (billable_hours_percent + billable_hours_percent * 0.10):
            arr["progress_status"] = 'Warning'
        elif actual_progress >= (billable_hours_percent + (billable_hours_percent * 0.10)):
            arr["progress_status"] = 'Critical'

        sales_order_total = sales_map.get(project, 0)
        if arr.get('company') != 'Kartoza (Pty) Ltd':
            sales_order_total = convertEURToRand(sales_order_total or 0)
        arr['total_sales_amount_via_sales_order'] = sales_order_total
        denominator = arr['total_sales_amount_via_sales_order'] or 0
        numerator = arr.get('total_costing') or 0
        arr['budget_used'] = (numerator / denominator) * 100 if denominator else 0
        arr['budget_status'] = ''
        if denominator > numerator:
            arr['budget_status'] = 'Profit'
        elif denominator < numerator:
            arr['budget_status'] = 'Loss'

    data = {
        "element_id": "project_sla_overview",
        "title": "Project/SLA Overview Table",
        "labels": [
            "Project", 
            "Company",
            "Expected Time", 
            "Consumed Time", 
            "Billable Hours", 
            "Billable Hours %",
            "Billable Hours Left",
            "Actual Progress",
            "Status",
            "Due Date",
            "Total Sales Amount (via Sales Order)",
            "Total Costing",
            "Budget Used",
            "Status"
        ],
        "help": """
        
        """,
        "datasets": final_arr,
        "type": "table",
    }

    return data


@frappe.whitelist(allow_guest=True)
def get_task_drill_down_table():

    # Step 1: Get all open project tasks in one query
    sql = f"""
    SELECT 
        tp.name as `project`,
        tt.name as `milestone`,
        tt.expected_time as `expected_time`,
        tt.actual_time as `consumed_time`,
        tt.exp_end_date as `exp_end_date`
    FROM tabProject AS tp 
    LEFT JOIN tabTask tt ON tp.project_name = tt.project
    WHERE tp.status = 'Open'
    AND tt.name IS NOT NULL
    """
    final_arr = frappe.db.sql(sql, as_dict=1, debug=0)

    # Step 2: Get all billable hours for these tasks in one query
    task_names = [row['milestone'] for row in final_arr if row['milestone']]
    if task_names:
        placeholders = ','.join([f"%({i})s" for i in range(len(task_names))])
        timesheet_sql = f"""
            SELECT 
                ttd.task as task,
                ROUND(COALESCE(SUM(CASE WHEN ttd.is_billable = 1 THEN ttd.hours ELSE 0 END), 0), 2) as billable_hours
            FROM `tabTimesheet` tt
            LEFT JOIN `tabTimesheet Detail` ttd ON ttd.parent = tt.name
            WHERE ttd.task IN ({placeholders})
            AND ttd.docstatus = 1
            AND ttd.task != ''
            AND tt.status = 'Submitted'
            GROUP BY ttd.task
        """
        params = {str(i): name for i, name in enumerate(task_names)}
        timesheet_data = frappe.db.sql(timesheet_sql, params, as_dict=1, debug=0)
        timesheet_map = {row['task']: row['billable_hours'] for row in timesheet_data}
    else:
        timesheet_map = {}

    # Step 3: Map timesheet data to tasks and calculate fields
    for arr in final_arr:
        task = arr["milestone"]
        expected_time = arr.get('expected_time') or 0
        billable_hours = timesheet_map.get(task, 0)
        billable_hours_percent = (billable_hours / expected_time * 100) if expected_time else 0
        if billable_hours_percent > 100:
            billable_hours_percent = 100 - billable_hours_percent
        arr['billable_hours'] = billable_hours
        arr['billable_hours_percent'] = billable_hours_percent
        arr['billable_hours_left'] = expected_time - billable_hours
        arr['task_status'] = ''
        if expected_time > billable_hours:
            arr["task_status"] = 'Under'
        elif expected_time < billable_hours:
            arr["task_status"] = 'Over'

    data = {
        "element_id": "task_drill_down",
        "title": "Task Drill-down Table",
        "labels": [
            "Project", 
            "Milestone",
            "Expected Time", 
            "Consumed Time", 
            "Billable Hours", 
            "Billable Hours %",
            "Billable Hours Left",
            "Status",
            "Due Date",
        ],
        "help": """
        
        """,
        "datasets": final_arr,
        "type": "table",
    }

    return data

@frappe.whitelist(allow_guest=True)
def project_time_overview_chart():
    sql = f""" 
    SELECT 
        tp.name as `project`,
        tp.expected_time as `expected_time`,
        tp.actual_time as `consumed_time` ,
        '' as `billable_hours`
    FROM tabProject AS tp 
    WHERE tp.status = 'Open'
    GROUP BY tp.project_name 
    """

    projects = frappe.db.sql(sql, as_dict=1, debug=0)
    chart_data = []

    for project in projects:

        timesheet_details = getTimesheetDetail(project["project"])

        # Coalesce numeric values and guard against None/zero divisions
        billable_hours = (timesheet_details.get('billable_hours') or 0)

        chart_data.append({
            "project": project['project'],
            "consumed_time": project['consumed_time'],
            "billable_hours": billable_hours,
            "expected_time": project['expected_time'],
        })

    # Transform chart_data for stacked chart
    labels = [row["project"] for row in chart_data]

    consumed_time_values = [row["consumed_time"] for row in chart_data]
    billable_hours_values = [row["billable_hours"] for row in chart_data]
    expected_time_values = [row["expected_time"] for row in chart_data]

    data = {
        "element_id": "project_time_overview",
        "type": "chart",
        "title": "Project Graph: Time Overview",
        "labels": labels,
        "isReverse": False,
        "showTotal": False,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "help": """
        """,
        "datasets": [
            {
                "type": "bar",
                "name": "Consumed Time",
                "values": consumed_time_values
            },
            {
                "type": "bar",
                "name": "Billable Hours",
                "values": billable_hours_values
            },
            {
                "type": "bar",
                "name": "Expected Time",
                "values": expected_time_values
            }
        ]
    }

    return data


@frappe.whitelist(allow_guest=True)
def project_performance_overview_chart():
    sql = f""" 
    SELECT 
        tp.name as `project`,
        tp.expected_time as `expected_time`,
        tp.actual_time as `consumed_time` ,
        '' as `billable_hours`,
        tp.percent_complete as `project_progress`
    FROM tabProject AS tp 
    WHERE tp.status = 'Open'
    GROUP BY tp.project_name 
    """

    projects = frappe.db.sql(sql, as_dict=1, debug=0)
    chart_data = []

    for project in projects:

        timesheet_details = getTimesheetDetail(project["project"])

        # Coalesce numeric values and guard against None/zero divisions
        billable_hours = (timesheet_details.get('billable_hours') or 0)

        chart_data.append({
            "project": project['project'],
            "consumed_time": (project['consumed_time'] / project['expected_time'] * 100),
            "billable_hours": (billable_hours / project["expected_time"] * 100),
            "project_progress": project['project_progress'],
        })

    # Transform chart_data for stacked chart
    labels = [row["project"] for row in chart_data]

    consumed_time_values = [row["consumed_time"] for row in chart_data]
    billable_hours_values = [row["billable_hours"] for row in chart_data]
    project_progress_values = [row["project_progress"] for row in chart_data]

    data = {
        "element_id": "project_performance_overview",
        "type": "chart",
        "title": "Project Graph: Performance Metrics",
        "labels": labels,
        "isReverse": False,
        "showTotal": False,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "help": """
        """,
        "datasets": [
            {
                "type": "bar",
                "name": "Consumed Time (%)",
                "values": consumed_time_values
            },
            {
                "type": "bar",
                "name": "Hours used (%)",
                "values": billable_hours_values
            },
            {
                "type": "bar",
                "name": "Project Progress (%)",
                "values": project_progress_values
            }
        ]
    }

    return data

        
def getAllSalesOrders(project):
    if "'" in project:
        project = project.replace("'", "''")

    sql = """
    SELECT 
        SUM(tso.base_total) as base_total
    FROM `tabSales Order` tso
    WHERE tso.status NOT IN ('Cancelled', 'Return', 'Credit Note Issued', 'Draft')
    AND (tso.project = %(project)s OR tso.name IN (
        SELECT parent FROM `tabSales Order Item` WHERE custom_project = %(project)s
    ))
    """

    data_orders = frappe.db.sql(sql, {"project": project}, as_dict=1, debug=0)

    # Return a numeric value instead of a dict; default to 0 when None
    if data_orders and isinstance(data_orders[0], dict):
        return data_orders[0].get('base_total') or 0
    return 0
    

def getTimesheetDetail(project):
    if "'" in project:
        project = project.replace("'", "''")
    sql = """
        SELECT 
            ROUND(COALESCE(SUM(
                CASE
                    WHEN ttd.is_billable = 1 THEN
                        ttd.hours
                    ELSE
                     0
                END
            ), 0), 2) as `billable_hours`,
            ROUND(COALESCE(SUM(costing_amount), 0), 2) as `total_costing_timesheet`,
            ROUND(COALESCE(SUM(billing_amount), 0), 2) as `total_billable_amount`,
            tt.currency as `currency`,
            tt.exchange_rate as `exchange_rate`
        FROM `tabTimesheet` tt
        LEFT JOIN `tabTimesheet Detail` ttd ON ttd.parent = tt.name
        WHERE ttd.project = %(project)s
        AND ttd.docstatus = 1
        AND ttd.task != ''
        AND tt.status = 'Submitted'
    """
    data = frappe.db.sql(sql,{"project": project}, as_dict=1, debug=0)
    
    return data[0]

def getTimesheetDetailTask(task):
    sql = """
        SELECT 
            ROUND(COALESCE(SUM(
                CASE
                    WHEN ttd.is_billable = 1 THEN
                        ttd.hours
                    ELSE
                     0
                END
            ), 0), 2) as `billable_hours`
        FROM `tabTimesheet` tt
        LEFT JOIN `tabTimesheet Detail` ttd ON ttd.parent = tt.name
        WHERE ttd.task = %(task)s
        AND ttd.docstatus = 1
        AND ttd.task != ''
        AND tt.status = 'Submitted'
    """
    data = frappe.db.sql(sql,{"task": task}, as_dict=1, debug=0)
    
    return data[0]
    
    
def convertEURToRand(num):
    # Guard against None
    if not num:
        return 0
    sql = f"""
        WITH exchange_rates AS (
            SELECT terra.current_exchange_rate AS exchange_rate
            FROM `tabExchange Rate Revaluation` AS terr
            JOIN `tabExchange Rate Revaluation Account` AS terra
            ON terra.parent = terr.name
            WHERE terr.company = 'Kartoza (Pty) Ltd'
              AND terra.account_currency = 'EUR'
              AND terra.account = '1303 - Debtors EURO - K'
            ORDER BY terr.name DESC
        )
        SELECT 
            CASE 
                WHEN (SELECT exchange_rate FROM exchange_rates LIMIT 1) = 0 
                THEN (SELECT exchange_rate FROM exchange_rates LIMIT 1 OFFSET 1) 
                ELSE (SELECT exchange_rate FROM exchange_rates LIMIT 1) 
            END AS exchange_rate;
    """
    
    res = frappe.db.sql(sql, as_dict=1, debug=0)
    exchange_rate = (res[0]['exchange_rate'] if res and res[0].get('exchange_rate') else 0) or 0
    if not exchange_rate:
        return num  # Fallback to original number if no exchange rate found
    
    # Multiply instead of divide to convert EUR → Rand
    return num * exchange_rate

