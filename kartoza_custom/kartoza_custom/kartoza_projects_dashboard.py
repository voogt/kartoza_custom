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

# Get distinct project managers
@frappe.whitelist()
def get_project_managers():

    sql = """
        SELECT DISTINCT
            tp.project_lead AS user_id,
            u.full_name
        FROM tabProject tp
        LEFT JOIN tabUser u ON u.name = tp.project_lead
        WHERE tp.status = 'Open'
        AND tp.project_lead IS NOT NULL
        AND tp.project_lead != ''
        AND tp.project_lead LIKE '%@kartoza.com'
        ORDER BY u.full_name
    """

    data = frappe.db.sql(sql, as_dict=True)

    return [
        {
            "label": row["full_name"] or row["user_id"],
            "value": row["user_id"]
        }
        for row in data
    ]

# Time Overview Chart
@frappe.whitelist(allow_guest=True)
def project_time_overview_chart(
    size_group="small",
    project_name=None,
    project_manager=None,
    start_date=None,
    end_date=None
):

    filters = ["tp.status = 'Open'"]
    params = {}

    # Filters

    if project_name:
        filters.append("tp.name LIKE %(project_name)s")
        params["project_name"] = f"%{project_name}%"

    if project_manager:
        filters.append("tp.project_lead = %(project_manager)s")
        params["project_manager"] = project_manager

    if start_date:
        filters.append("tp.expected_start_date >= %(start_date)s")
        params["start_date"] = start_date

    if end_date:
        filters.append("tp.expected_end_date <= %(end_date)s")
        params["end_date"] = end_date

    # Size Group Logic

    if size_group == "small":
        filters.append("COALESCE(tp.expected_time,0) <= 100")

    elif size_group == "medium":
        filters.append("COALESCE(tp.expected_time,0) > 100 AND COALESCE(tp.expected_time,0) <= 200")

    elif size_group == "large":
        filters.append("COALESCE(tp.expected_time,0) > 200 AND COALESCE(tp.expected_time,0) <= 500")

    elif size_group == "very_large":
        filters.append("COALESCE(tp.expected_time,0) > 500")

    where_clause = " AND ".join(filters)

    # Project Query

    sql = f"""
        SELECT 
            tp.name as project,
            COALESCE(tp.expected_time,0) as expected_time,
            COALESCE(tp.actual_time,0) as consumed_time
        FROM tabProject tp
        WHERE {where_clause}
        ORDER BY tp.expected_time ASC
    """

    projects = frappe.db.sql(sql, params, as_dict=1)

    project_names = [row['project'] for row in projects]

    # Timesheet Query

    if project_names:
        placeholders = ','.join([f"%({i})s" for i in range(len(project_names))])

        timesheet_sql = f"""
            SELECT 
                ttd.project,
                ROUND(COALESCE(SUM(
                    CASE WHEN ttd.is_billable = 1 THEN ttd.hours ELSE 0 END
                ),0),2) as billable_hours
            FROM `tabTimesheet` tt
            LEFT JOIN `tabTimesheet Detail` ttd ON ttd.parent = tt.name
            WHERE ttd.project IN ({placeholders})
            AND ttd.docstatus = 1
            AND tt.status = 'Submitted'
            GROUP BY ttd.project
        """

        ts_params = {str(i): name for i, name in enumerate(project_names)}
        timesheet_data = frappe.db.sql(timesheet_sql, ts_params, as_dict=1)
        timesheet_map = {row['project']: row['billable_hours'] for row in timesheet_data}
    else:
        timesheet_map = {}

    # Build Data

    labels = []
    consumed_values = []
    billable_values = []
    expected_values = []

    for project in projects:
        labels.append(project["project"])
        consumed_values.append(project["consumed_time"])
        billable_values.append(timesheet_map.get(project["project"], 0))
        expected_values.append(project["expected_time"])

    return {
        "element_id": "project_time_overview",
        "type": "chart",
        "title": f"Project Time Overview ({size_group.replace('_',' ').title()})",
        "labels": labels,
        "datasets": [
            {"type": "bar", "name": "Consumed Time", "values": consumed_values},
            {"type": "bar", "name": "Billable Hours", "values": billable_values},
            {"type": "bar", "name": "Expected Time", "values": expected_values}
        ]
    }

# Performance Overview Chart
@frappe.whitelist(allow_guest=True)
def project_performance_overview_chart(
    page=1,
    page_size=10,
    project_name=None,
    project_manager=None,
    start_date=None,
    end_date=None
):

    page = int(page)
    page_size = int(page_size)
    offset = (page - 1) * page_size

    filters = ["tp.status = 'Open'"]
    params = {}

    # Apply Filters

    if project_name:
        filters.append("tp.name LIKE %(project_name)s")
        params["project_name"] = f"%{project_name}%"

    if project_manager:
        filters.append("tp.project_lead = %(project_manager)s")
        params["project_manager"] = project_manager

    if start_date:
        filters.append("tp.expected_start_date >= %(start_date)s")
        params["start_date"] = start_date

    if end_date:
        filters.append("tp.expected_end_date <= %(end_date)s")
        params["end_date"] = end_date

    where_clause = " AND ".join(filters)    

    # Total Count (With Filters)
    
    count_sql = f"""
        SELECT COUNT(*) as total
        FROM tabProject tp
        WHERE {where_clause}
    """

    total_projects = frappe.db.sql(count_sql, params, as_dict=1)[0]["total"]

    # Step 1: Get Paginated Projects

    sql = f"""
        SELECT 
            tp.name as project,
            tp.expected_time,
            tp.actual_time as consumed_time,
            tp.percent_complete as project_progress
        FROM tabProject tp
        WHERE {where_clause}
        ORDER BY tp.name
        LIMIT %(page_size)s OFFSET %(offset)s
    """

    params.update({
        "page_size": page_size,
        "offset": offset
    })

    projects = frappe.db.sql(sql, params, as_dict=1)

    # Step 2: Get all billable hours for these projects in one query
    project_names = [row['project'] for row in projects if row['project']]
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

    # Step 3: Build chart data
    chart_data = []
    for project in projects:
        expected_time = project['expected_time'] or 0
        consumed_time_pct = (project['consumed_time'] / expected_time * 100) if expected_time else 0
        billable_hours = timesheet_map.get(project['project'], 0)
        billable_hours_pct = (billable_hours / expected_time * 100) if expected_time else 0
        chart_data.append({
            "project": project['project'],
            "consumed_time": consumed_time_pct,
            "billable_hours": billable_hours_pct,
            "project_progress": project['project_progress'],
        })

    # Transform for chart
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
        "help": "",
        "datasets": [
            {
                "type": "bar",
                "name": "Consumed Time",
                "values": consumed_time_values
            },
            {
                "type": "bar",
                "name": "Hours used",
                "values": billable_hours_values
            },
            {
                "type": "bar",
                "name": "Project Progress",
                "values": project_progress_values
            }
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_projects": total_projects,
            "total_pages": (total_projects + page_size - 1) // page_size
        }
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

