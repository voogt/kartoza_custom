import json
from warnings import filters
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
from .dashboard_helpers import get_rates, get_month_ranges, get_year_ranges, get_month_label, getBacklogSalesOrders, get_billing_data, get_departments, compute_department_summary_all, get_salary_slips, get_timesheet_data, compute_department_summary, get_all_data, get_profit
from erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement import ( 
    get_data,
    get_period_list
)

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
        "showTotal": False,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "total_cards": [],
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Calculates staff numbers for each month in the selected range:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Opening Count:</b> Employees who joined before the month and are not relieved before the month starts.</li>
                <li><b>New Staff:</b> Employees who joined during the month.</li>
                <li><b>Departures:</b> Employees whose relieving date falls within the month.</li>
                <li><b>Closing Count:</b> Opening count + new staff - departures.</li>
            </ul>
            <span style='color: #888;'>All counts exclude employees with the designation <b>Sub-Contractor</b>.</span>
        </div>
        """,
        "datasets": [
            {
                "type": "bar",
                "name": "Opening Count",
                "unit": "employees",
                "values": opening_values
            },
            {
                "type": "bar",
                "name": "New Staff",
                "unit": "employees",
                "values": new_staff_values
            },
            {
                "type": "bar",
                "name": "Departures",
                "unit": "employees",
                "values": departure_values
            },
            {
                "type": "bar",
                "name": "Closing Count",
                "unit": "employees",
                "values": closing_values
            }
        ]
    }

    return data


@frappe.whitelist(allow_guest=True)
def get_billable_hours(start_date, end_date):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []
    total_external = 0
    total_internal = 0
    total_investment = 0
    total_invoicable_all_staff = 0
    total_uninvoicable_all_staff = 0

    for start, end in ranges:
    
        b = False
        add = frappe.utils.add_to_date
        cur_date = start
        date_range = []
        while b == False:
            date_range.append(f"select '{cur_date}' as date")
            if cur_date == end:
                b = True
                break
            cur_date = add(cur_date, days=1)

        date_range = " union all ".join(date_range)

        util_sql = f"""
        SELECT
            wd.employee_name, 
            wd.name,
            -- totals
            wd.holiday_hours,
            wd.leave_hours,
            SUM(tsd.hours) as `timesheet_hours`,
            SUM(tsd.hours) + wd.holiday_hours + wd.leave_hours as `booked_hours`,
            wd.total_hours as `hours_pm`,
            wd.total_hours - wd.holiday_hours as `total_hours`,
            COALESCE(SUM(tsd.hours)) + wd.holiday_hours + wd.leave_hours - wd.total_hours as `shortage`, 
            SUM(CASE WHEN tsd.is_billable = 0 THEN tsd.hours ELSE 0 END) as `non_billing_hours`,
            -- billable
            SUM(CASE WHEN tsd.project IS NOT NULL AND tsd.is_billable = 1 THEN tsd.hours ELSE 0 END) as `billable_hours`,
            wd.total_hours - wd.holiday_hours - wd.leave_hours as `required_hours`,
            SUM(CASE WHEN tsd.project IS NOT NULL AND tsd.is_billable = 1 THEN tsd.hours ELSE 0 END)
                /
            NULLIF((wd.total_hours - wd.holiday_hours - wd.leave_hours),0) * 100 as `billable_percentage`,
            SUM(tsd.billing_amount) as `billing_rate`,
            SUM(tsd.costing_amount) as `costing_rate`,
            SUM(tsd.billing_amount) - SUM(tsd.costing_amount) as `profit`,

            SUM(CASE WHEN tp.project_type = 'Investment' AND tsd.is_billable = 1 THEN tsd.hours ELSE 0 END) as `investment_hours`,
            SUM(CASE WHEN tp.project_type = 'External' AND tsd.is_billable = 1 THEN tsd.hours ELSE 0 END) as `external_hours`,
            SUM(CASE WHEN tp.project_type = 'Internal' AND tsd.is_billable = 1 THEN tsd.hours ELSE 0 END) as `internal_hours`,
            SUM(CASE WHEN tsd.project IS NULL AND tsd.is_billable = 1 THEN tsd.hours ELSE 0 END) as `no_project_linked_hours`

        FROM (
            SELECT -- wd (aggregated per employee)
                wd.employee_name as `employee_name`,
                wd.name as `name`,
                wd.emp_status as `emp_status`,
                wd.custom_utilization as `custom_utilization`,

                /* compute effective weekday-count in the period (Mon-Fri),
                   adjust for join date if in the middle of the period,
                   then scale by working_days_required_per_week / 5.0,
                   finally multiply by working_hours_required_per_day */
                (
                    (
                        /* total weekdays in period (we count entries from the working_dates union which excludes weekends) */
                        COUNT(CASE WHEN wd.working_dates != '' THEN wd.working_dates END)
                        -
                        /* if employee joined during period, subtract weekdays before their join date */
                        (CASE
                            WHEN '{start}' < wd.date_of_joining AND '{end}' > wd.date_of_joining THEN
                                (
                                    /* weekday-count from {start} up to (date_of_joining - 1) */
                                    5 * (DATEDIFF(wd.date_of_joining, '{start}') DIV 7)
                                    + MID('1234555512344445123333451222234511112345001234550',
                                          7 * WEEKDAY('{start}') + WEEKDAY(wd.date_of_joining) + 1, 1)
                                )
                            WHEN '{end}' < wd.date_of_joining AND '{start}' < wd.date_of_joining THEN
                                /* joined after period */
                                (COUNT(CASE WHEN wd.working_dates != '' THEN wd.working_dates END)) /* will be nulled later by outer logic */
                            ELSE
                                0
                         END)
                    )
                    /* scale weekday-count from a 5-day baseline to employee's required working days */
                    * (COALESCE(wd.working_days_required_per_week, 5) / 5.0)
                    /* multiply by hours per working day */
                ) * COALESCE(wd.working_hours_required_per_day, 8) as `total_hours`,

                /* holiday and leave hours: use employee hours-per-day (fallback to 8) */
                (CASE
                    WHEN '{end}' < wd.date_of_joining AND '{start}' < wd.date_of_joining THEN 0
                    ELSE
                        COUNT(CASE WHEN wd.holiday_dates != '' THEN wd.holiday_dates END)
                    END
                ) * COALESCE(wd.working_hours_required_per_day, 8) as holiday_hours,

                SUM(wd.leave_dates) * COALESCE(wd.working_hours_required_per_day, 8) as `leave_hours`

            FROM ( -- wd detail union (working days / holidays / leave)
                SELECT 
                    emp.employee_name as `employee_name`,
                    emp.name as `name`,
                    emp.status as `emp_status`,
                    tewc.working_hours_required_per_day as `working_hours_required_per_day`,
                    tewc.working_days_required_per_week as `working_days_required_per_week`,
                    emp.custom_utilization as `custom_utilization`,
                    emp.date_of_joining as `date_of_joining`,
                    date_range.date as `working_dates`,
                    '' as `holiday_dates`,
                    '' as `leave_dates`,
                    'Working Days' as `type`
                FROM `tabEmployee` emp
                JOIN (	
                    {date_range}
                ) date_range on WEEKDAY(date_range.date) NOT IN (5,6)  -- keep counting Mon-Fri dates then scale later
                LEFT JOIN `tabEmployee Work Cycle` tewc
                    ON tewc.parent = emp.name
                    AND tewc.applied_from = (
                        SELECT MAX(applied_from)
                        FROM `tabEmployee Work Cycle`
                        WHERE parent = emp.name
                            AND applied_from <= '{start}'
                    )

                UNION ALL -- Holidays
                SELECT
                    emp.employee_name as `employee_name`,
                    emp.name as `name`,
                    emp.status as `emp_status`,
                    tewc2.working_hours_required_per_day as `working_hours_required_per_day`,
                    tewc2.working_days_required_per_week as `working_days_required_per_week`,
                    emp.custom_utilization as `custom_utilization`,
                    emp.date_of_joining as `date_of_joining`,
                    '' as `working_dates`,
                    h.holiday_date as `holiday_dates`,
                    '' as `leave_dates`,
                    'Holiday Days' as `type`
                FROM `tabEmployee` emp
                JOIN `tabHoliday` h ON h.parent = emp.holiday_list
                    AND h.description NOT IN ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday')
                    AND WEEKDAY(h.holiday_date) NOT IN (5,6)
                    AND h.holiday_date >= '{start}'
                    AND h.holiday_date <= '{end}'
                LEFT JOIN `tabEmployee Work Cycle` tewc2
                    ON tewc2.parent = emp.name
                    AND tewc2.applied_from = (
                        SELECT MAX(applied_from)
                        FROM `tabEmployee Work Cycle`
                        WHERE parent = emp.name
                            AND applied_from <= '{start}'
                    )

                UNION ALL -- LEAVE
                SELECT
                    la.employee_name,
                    la.employee,
                    '' as `emp_status`,
                    tewc3.working_hours_required_per_day as `working_hours_required_per_day`,
                    tewc3.working_days_required_per_week as `working_days_required_per_week`,
                    '' as `custom_utilization`,
                    '' as `date_of_joining`,
                    '' as `working_dates`,
                    '' as `holiday_dates`,
                    SUM(
                        CASE
                            WHEN from_date >= '{start}' AND to_date >= '{end}' THEN (
                                /* count weekdays between from_date and {end} */
                                5 * (DATEDIFF('{end}', from_date) DIV 7)
                                + MID('1234555512344445123333451222234511112345001234550', 
                                      7 * WEEKDAY(from_date) + WEEKDAY('{end}') + 1, 1)
                                - (
                                    SELECT COUNT(th.holiday_date)
                                    FROM `tabEmployee` te 
                                    LEFT JOIN `tabHoliday` th 
                                        ON th.parent = te.holiday_list 
                                    WHERE te.employee_name = la.employee_name
                                      AND th.holiday_date >= from_date
                                      AND th.holiday_date <= '{end}'
                                      AND WEEKDAY(th.holiday_date) NOT IN (5,6)
                                )
                            )
                            WHEN from_date <= '{start}' AND to_date >= '{start}' THEN (
                                /* count weekdays between {start} and to_date */
                                5 * (DATEDIFF(to_date, '{start}') DIV 7)
                                + MID('1234555512344445123333451222234511112345001234550',
                                      7 * WEEKDAY('{start}') + WEEKDAY(to_date) + 1, 1)
                                - (
                                    SELECT COUNT(th.holiday_date)
                                    FROM `tabEmployee` te
                                    LEFT JOIN `tabHoliday` th
                                        ON th.parent = te.holiday_list
                                    WHERE te.employee_name = la.employee_name
                                      AND te.status = 'Active'
                                      AND th.holiday_date >= '{start}'
                                      AND th.holiday_date <= to_date
                                      AND WEEKDAY(th.holiday_date) NOT IN (5,6)
                                )
                            )
                            WHEN la.from_date >= '{start}' AND la.to_date <= '{end}' THEN total_leave_days
                            ELSE 0
                        END
                    ) as `leave_dates`,
                    'Leave Days'
                FROM `tabLeave Application` la
                LEFT JOIN `tabEmployee Work Cycle` tewc3
                    ON tewc3.parent = la.employee
                    AND tewc3.applied_from = (
                        SELECT MAX(applied_from)
                        FROM `tabEmployee Work Cycle`
                        WHERE parent = la.employee
                            AND applied_from <= '{start}'
                    )
                WHERE la.status = "Approved" 
                AND la.from_date BETWEEN '{add(start, days=-30)}' AND '{end}'
                GROUP BY employee
            ) wd
            GROUP BY wd.name
            ORDER BY wd.employee_name
        ) wd

        LEFT JOIN `tabTimesheet` ts ON wd.name = ts.employee 
            AND ts.status in ('Submitted', 'Billed')
        LEFT JOIN `tabTimesheet Detail` tsd 
            ON tsd.parent = ts.name
            AND tsd.activity_type NOT REGEXP 'Leave'
            AND tsd.from_time >= '{start} 00:00:00'
            AND tsd.to_time <= '{end} 23:59:59'
        LEFT JOIN `tabProject` tp
            ON tsd.project = tp.name
        WHERE wd.emp_status = (CASE
            WHEN wd.emp_status != 'Active'  AND tsd.hours !=0 AND wd.custom_utilization = '1' THEN wd.emp_status
            WHEN wd.emp_status = 'Active' AND wd.custom_utilization = '1' THEN wd.emp_status
            ELSE NULL
            END
        )
        AND wd.total_hours != 0
        GROUP BY wd.name
        ORDER BY wd.employee_name
        """

        util_results = frappe.db.sql(util_sql, as_dict=True)
        total_capacity_hours = 0
        external = 0
        internal = 0
        investment = 0
        invoicable_all_staff = 0
        uninvoicable_all_staff = 0
        no_project_linked = 0
        holiday_hours = 0

        for util_result in util_results:
            external += util_result.get("external_hours", 0)
            internal += util_result.get("internal_hours", 0)
            investment += util_result.get("investment_hours", 0)
            total_capacity_hours += util_result.get("total_hours", 0)
            no_project_linked += util_result.get("no_project_linked_hours", 0)
            holiday_hours += util_result.get("holiday_hours", 0)
            invoicable_all_staff += util_result.get("billable_hours", 0)
            uninvoicable_all_staff += util_result.get("non_billing_hours", 0)

        capacity_comparison_percent = (
            (invoicable_all_staff / total_capacity_hours) * 100 if total_capacity_hours else 0
        )

        total_invoicable_all_staff += invoicable_all_staff
        total_uninvoicable_all_staff += uninvoicable_all_staff if uninvoicable_all_staff else 0
        total_external += external
        total_internal += internal
        total_investment += investment

        month_label = get_month_label(start)

        chart_data.append({
            "month": month_label,
            "no_project_linked": f"{no_project_linked:.0f}",
            "external": f"{external:.0f}",
            "internal": f"{internal:.0f}",
            "investment": f"{investment:.0f}",
            "capacity_hours": f"{total_capacity_hours:.0f}",
            "holiday_hours": f"{holiday_hours:.0f}",
            "capacity_comparison_percent": f"{capacity_comparison_percent:.0f}"
        })

    # Transform chart_data for stacked chart
    labels = [row["month"] for row in chart_data]

    no_project_linked_values = [row["no_project_linked"] for row in chart_data]
    external_values = [row["external"] for row in chart_data]
    internal_values = [row["internal"] for row in chart_data]
    investment_values = [row["investment"] for row in chart_data]
    capacity_comparison_percent_values = [row["capacity_comparison_percent"] for row in chart_data]
    capacity_hours = [row["capacity_hours"] for row in chart_data]
    holiday_hours = [row["holiday_hours"] for row in chart_data]

    data = {
        "element_id": "billable_hours",
        "isReverse": False,
        "showTotal": False,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "type": "single",
        "title": "Billable Hours",
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Displays billable hours by project type per month:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>No Project Linked:</b> Billable hours not linked to any project.</li>
                <li><b>External/Internal/Investment:</b> Billable hours for each project type.</li>
                <li><b>Capacity Comparison Percent %:</b> (Total billable hours / total capacity hours) × 100.</li>
                <li><b>Capacity Utilisation Staff Hours:</b> Available hours after excluding holidays</li>
                <li><b>Holiday Hours:</b> Hours taken as holidays.</li>
                <li>Only staff with <b>custom_utilization=1</b> are included.</li>
            </ul>
            <span style='color: #888;'>Totals are summed across the selected period.</span>
        </div>
        """,
        "total_cards": [
            {
                "title": "Billable Hours Total",
                "unit": "hours",
                "value": f"{total_invoicable_all_staff:.0f}"
            },
            {
                "title": "Unbillable Hours Total",
                "unit": "hours",
                "value": f"{total_uninvoicable_all_staff:.0f}"
            },
        ],
        "labels": labels,
        "datasets": [
            {
                "type": "bar",
                "name": "No Project Linked",
                "unit": "hours",
                "values": no_project_linked_values
            },
            {
                "type": "bar",
                "name": "External",
                "unit": "hours",
                "values": external_values
            },
            {
                "type": "bar",
                "name": "Internal",
                "unit": "hours",
                "values": internal_values
            },
            {
                "type": "bar",
                "name": "Investment",
                "unit": "hours",
                "values": investment_values
            },
            {
                "type": "bar",
                "name": "Holiday Hours",
                "unit": "hours",
                "values": holiday_hours
            },
            {
                "type": "bar",
                "name": "Capacity Utilisation Staff Hours",
                "unit": "hours",
                "values": capacity_hours
            },
            {
                "type": "line",
                "name": "Capacity Comparison Percent",
                "unit": "percent",
                "values": capacity_comparison_percent_values
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
            "value": f"{value:.0f}",
            "margin_per": f"{margin_per:.0f}",
            "backlog": f"{backlog:.0f}"
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
        "showTotal": True,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Shows project financials per month:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Backlog:</b> Value of sales orders not yet invoiced (uninvoiced total) for the month.<br>
                    <span style='color: #555; font-size: 13px;'>
                        <b>How is backlog calculated?</b><br>
                        For each month, the system collects all sales orders within the month that have not yet been fully invoiced. It sums the <b>uninvoiced_total</b> for each of these sales orders (converted to Rand if needed). This total represents the amount of work sold but not yet invoiced, giving insight into expected future revenue.
                    </span>
                </li>
                <li><b>Value (Closed Projects Rand):</b> Total billed amount for projects completed in the month, converted to Rand if needed.</li>
                <li><b>Margin (Closed Projects) %:</b> (Total billed - total costing) / total billed × 100 for closed projects.</li>
            </ul>
            <span style='color: #888;'>Totals are aggregated for the period.</span>
        </div>
        """,
        "total_cards": [
            {
                "title": "Total Closed Projects Value",
                "unit": "rand",
                "value": f"{total_projects_closed_value:.0f}"
            }
        ],
        "datasets": [
            {
                "type": "bar",
                "name": "Backlog: Sold but not invoiced (Rand)",
                "unit": "rand",
                "values": backlog_values
            },
            {
                "type": "bar",
                "name": "Value (Closed Projects Rand)",
                "unit": "rand",
                "values": project_values
            },
            {
                "type": "line",
                "name": "Margin (Closed Projects) %",
                "unit": "percent",
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
            tsi.cost_center, 
            SUM(
                CASE
                    WHEN ts.company = 'Kartoza (Pty) Ltd' THEN
                        tsi.base_amount
                    ELSE
                        tsi.base_amount * {zar_rate}
                END
            ) as `total_billed_amount`
            FROM `tabSales Invoice` ts
            LEFT JOIN `tabSales Invoice Item` tsi ON tsi.parent = ts.name
            WHERE status NOT IN ('Cancelled', 'Draft', 'Return', 'Credit Note Issued')
            AND ts.posting_date BETWEEN '{start}' AND '{end}'
            GROUP BY tsi.cost_center
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
               tcc.name as `cost_center`
            FROM  `tabCost Center` tcc
            WHERE
              tcc.custom_cost_center_type = '{type_center}'
            ORDER BY
                tcc.name
        """, as_dict=1, debug=0)

        cost_center_array = []

        for dict in cost_center_data:
            
            total_costing_amount = data_map['timesheet_costing'].get(dict['cost_center'], 0)
            total_billed_amount = data_map['sales_invoices'].get(dict['cost_center'], 0)
            profit_loss = total_billed_amount - total_costing_amount

            total_cost_center += profit_loss
            cost_center_array.append({
                'cost_center': dict['cost_center'],
                'profit_loss': f"{profit_loss:.0f}",
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


    # Remove cost centers with 0 for all months
    filtered_cost_center_map = {
        name: values for name, values in cost_center_map.items()
        if any(float(v) != 0.0 for v in values)
    }

    data = {
        "title": f"{type_center} Center True Cost (Profit/Loss)",
        "labels": labels,
        "isReverse": False,
        "showTotal": True,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "element_id": f"{type_center}_centers",
        "help": f"""
        <div style='font-size: 14px;text-align: left'>
            <b>Displays profit/loss per cost center for each month:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Profit/Loss:</b> Total billed amount (from sales invoices) minus total costing (from timesheets) for each center.</li>
                <li>Only centers of the specified type are included.</li>
            </ul>
            <span style='color: #888;'>Totals are summed for the period.</span>
        </div>
        """,
        "total_cards": [],
        "type": "single",
        "datasets": []
    }

    for name, values in filtered_cost_center_map.items():
        data["datasets"].append({
            "type": "bar",
            "name": name,
            "unit": "rand",
            "values": values
        })

    return data


@frappe.whitelist(allow_guest=True)
def get_profit_cost_lost_revenue_data(start_date, end_date, type_center):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []
    total_cost_center = 0

    if type_center == "Profit":
        title = "Opportunity Cost"
    if type_center == "Cost":
        title = "Cost Center Opportunity (Profit/Loss)"

    for start, end in ranges:
        zar_rate = get_rates(end, "EUR")

        sales_invoice_sql = f"""
        SELECT 
            tsi.cost_center, 
            SUM(
                CASE
                    WHEN ts.company = 'Kartoza (Pty) Ltd' THEN
                        tsi.base_amount
                    ELSE
                        tsi.base_amount * {zar_rate}
                END
            ) as `total_billed_amount`
            FROM `tabSales Invoice` ts
            LEFT JOIN `tabSales Invoice Item` tsi ON tsi.parent = ts.name
            WHERE status NOT IN ('Cancelled', 'Draft', 'Return', 'Credit Note Issued')
            AND ts.posting_date BETWEEN '{start}' AND '{end}'
            GROUP BY tsi.cost_center
        """

        timesheet_costing_sql = f"""
            SELECT 
                p.cost_center, 
                SUM(tsd.costing_amount) as `total_costing`,
                SUM(tsd.billing_amount) as `total_timesheet_billing`
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
            'total_timesheet_billing': {item['cost_center']: item['total_timesheet_billing'] for item in timesheet_costing_data},
            'sales_invoices': {item['cost_center']: item['total_billed_amount'] for item in sales_invoice_data},
        }

        cost_center_data = frappe.db.sql(f"""
            SELECT
               tcc.name as `cost_center`
            FROM  `tabCost Center` tcc
            WHERE
              tcc.custom_cost_center_type = '{type_center}'
            ORDER BY
                tcc.name
        """, as_dict=1, debug=0)

        cost_center_array = []

        for dict in cost_center_data:
            total_costing_amount = data_map['timesheet_costing'].get(dict['cost_center'], 0)
            total_billed_amount = data_map['sales_invoices'].get(dict['cost_center'], 0)
            total_timesheet_billing = data_map['total_timesheet_billing'].get(dict['cost_center'], 0)
            profit_loss = total_billed_amount - total_costing_amount
            potential_revenue_total = total_billed_amount - total_timesheet_billing

            if profit_loss < 0:
                total_cost_center += profit_loss
                cost_center_array.append({
                    'cost_center': dict['cost_center'],
                    'profit_loss': f"{potential_revenue_total:.0f}",
                    'billing_rate': f"{total_timesheet_billing:.0f}",
                })
            else:
                cost_center_array.append({
                    'cost_center': dict['cost_center'],
                    'profit_loss': "0",
                    'billing_rate': f"{total_timesheet_billing:.0f}",
                })

        month_label = get_month_label(start)

        chart_data.append({
            "month": month_label,
            "cost_center_data": cost_center_array,
        })

    # Transform chart_data for stacked chart
    labels = [row["month"] for row in chart_data]

    cost_center_map = {}
    billing_rate_map = {}

    for row in chart_data:
        month_data = row["cost_center_data"]
        for item in month_data:
            name = item["cost_center"]
            if name not in cost_center_map:
                cost_center_map[name] = []
                billing_rate_map[name] = []
            cost_center_map[name].append(item["profit_loss"])
            billing_rate_map[name].append(item["billing_rate"])

    # Remove cost centers with 0 for all months
    filtered_cost_center_map = {
        name: values for name, values in cost_center_map.items()
        if any(float(v) != 0.0 for v in values)
    }

    data = {
        "title": title,
        "labels": labels,
        "isReverse": False,
        "showTotal": True,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "element_id": f"{type_center}_centers",
        "help": f"""
        <div style='font-size: 14px;text-align: left'>
            <b>Shows lost revenue (potential profit not realized) for centers with negative profit/loss:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Profit/Loss:</b> For centers with negative profit, shows the difference between total billed and total timesheet billing.</li>
                <li><b>Billing Rate:</b> Total timesheet billing amount for each cost center.</li>
                <li>Only centers of the specified type are included.</li>
            </ul>
            <span style='color: #888;'>Totals are summed for the period.</span>
        </div>
        """,
        "total_cards": [],
        "type": "single",
        "datasets": []
    }

    for name, values in filtered_cost_center_map.items():
        data["datasets"].append({
            "type": "bar",
            "name": name,
            "unit": "rand",
            "values": values
        })
        data["datasets"].append({
            "type": "line",
            "name": f"Billing Rate: {name}",
            "unit": "rand",
            "values": billing_rate_map[name]
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
                'cost': f"{ts_details['sum_costing']:.0f}",
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
        "showTotal": True,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "labels": labels,
        "element_id": "activity_cost",
        "type": "single",
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Displays total cost per activity type for each month:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Cost:</b> Sum of costing amounts from timesheet details for each activity type.</li>
                <li>Only active activity types are included.</li>
            </ul>
            <span style='color: #888;'>Totals are summed for the period.</span>
        </div>
        """,
        "total_cards": [],
        "datasets": []
    }

    for name, values in activity_map.items():
        # Remove activities with 0 value for all months
        if all(float(v) == 0.0 for v in values):
            continue
        data["datasets"].append({
            "type": "bar",
            "name": name,
            "unit": "rand",
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

        # collect departments from both sources, with type check
        all_departments.update(
            ts.department for ts in timesheets
            if hasattr(ts, 'department') and ts.department
        )
        all_departments.update(
            s.department for s in salary_data
            if hasattr(s, 'department') and s.department
        )

    for start, end in ranges:
        zar_rate = get_rates(end, "EUR")
        timesheets = get_timesheet_data(start, end)
        billing_data = get_billing_data([
            ts.name for ts in timesheets
            if hasattr(ts, 'name')
        ])
        salary_data = get_salary_slips(start, end)

        # Filter timesheets to only include objects with a 'department' attribute
        filtered_timesheets = [ts for ts in timesheets if hasattr(ts, 'department')]
        final_dict = compute_department_summary(filtered_timesheets, billing_data, salary_data, all_departments)

        sql_check_management = f"""
            SELECT * 
            FROM `tabSalary Slip` 
            WHERE employee = 'HR-EMP-00001'
            AND posting_date BETWEEN '{start}' AND '{end}'
        """

        check_management = frappe.db.sql(sql_check_management, as_dict=1, debug=0)

        for final in final_dict:
            if final["department"] == 'Management - K':
                if len(check_management) < 1:
                    final['total_salary'] += 240000
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
            salary_map[name].append(f"{cost:.0f}")

    data = {
        "title": f"Total Department Cost Pty",
        "labels": labels,
        "element_id": "salary_cost",
        "isReverse": False,
        "showTotal": True,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "type": "single",
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Shows total salary costs per department for Kartoza (Pty) Ltd per month:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Total Salary:</b> Sum of gross pay on salary slips.</li>
                <li>If no salary slip for 'Management - K', adds a fixed amount.</li>
            </ul>
            <span style='color: #888;'>Totals are summed for the period.</span>
        </div>
        """,
        "total_cards": [],
        "datasets": []
    }

    for name, values in salary_map.items():
        data["datasets"].append({
            "type": "bar",
            "name": name,
            "unit": "rand",
            "values": values
        })


    return data


@frappe.whitelist(allow_guest=True)
def get_company_salary_lda(start_date, end_date):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []

    total_salary = 0

    for start, end in ranges:

        final_dict = [
            {
                "department": "Management - KE",
                "total_salary": 240000 
            },
            {
                "department": "Admin - KE",
                "total_salary": 20000
            }
        ]

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
            salary_map[name].append(f"{cost:.0f}")

    data = {
        "title": f"Total Department Cost Lda",
        "labels": labels,
        "element_id": "salary_cost",
        "isReverse": False,
        "showTotal": True,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "type": "single",
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Shows total salary costs per department for Kartoza Unipessoal Lda per month (Currency ZAR):</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Total Salary:</b> Uses fixed values for each department per month.</li>
            </ul>
            <span style='color: #888;'>Totals are summed for the period.</span>
        </div>
        """,
        "total_cards": [],
        "datasets": []
    }

    for name, values in salary_map.items():
        data["datasets"].append({
            "type": "bar",
            "name": name,
            "unit": "rand",
            "values": values
        })


    return data


@frappe.whitelist(allow_guest=True)
def get_salary_percent_of_sales(start_date, end_date):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []

    total_salary_period = 0
    total_sales_period = 0

    for start, end in ranges:
        zar_rate = get_rates(end, "EUR")

        salary_sql = f"""
            SELECT
                SUM(
                    CASE
                        WHEN company = 'Kartoza (Pty) Ltd' THEN gross_pay
                        ELSE gross_pay * {zar_rate}
                    END
                ) AS total_salary
            FROM `tabSalary Slip`
            WHERE docstatus = 1
            AND posting_date BETWEEN '{start}' AND '{end}'
        """

        sales_sql = f"""
            SELECT
                SUM(
                    CASE
                        WHEN si.company = 'Kartoza (Pty) Ltd' THEN si.base_grand_total
                        ELSE si.base_grand_total * {zar_rate}
                    END
                ) AS total_sales
            FROM (
                SELECT DISTINCT tsi.name, tsi.company, tsi.base_grand_total
                FROM `tabSales Invoice` tsi
                INNER JOIN `tabPayment Entry Reference` per
                    ON per.reference_doctype = 'Sales Invoice'
                    AND per.reference_name = tsi.name
                INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
                WHERE tsi.docstatus = 1
                AND tsi.status NOT IN ('Cancelled', 'Draft', 'Return', 'Credit Note Issued')
                AND pe.docstatus = 1
                AND pe.posting_date BETWEEN '{start}' AND '{end}'
            ) si
        """

        monthly_salary = frappe.db.sql(salary_sql, as_dict=True)[0].get("total_salary") or 0
        monthly_sales = frappe.db.sql(sales_sql, as_dict=True)[0].get("total_sales") or 0

        monthly_salary += 260000 

        salary_percent_of_sales = (monthly_salary / monthly_sales) * 100 if monthly_sales else 0

        total_salary_period += monthly_salary
        total_sales_period += monthly_sales

        month_label = get_month_label(start)
        chart_data.append({
            "month": month_label,
            "salary_percent_of_sales": f"{salary_percent_of_sales:.2f}",
        })

    labels = [row["month"] for row in chart_data]
    salary_percent_values = [row["salary_percent_of_sales"] for row in chart_data]
    period_percent = (total_salary_period / total_sales_period) * 100 if total_sales_period else 0

    data = {
        "title": "Salaries as % of Sales",
        "labels": labels,
        "element_id": "salary_percent_sales",
        "isReverse": False,
        "showTotal": False,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "type": "single",
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Tracks salaries as a percentage of sales month-to-month:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Salaries % of Sales:</b> (Total salaries / total sales invoices) * 100 for each month.</li>
                <li><b>Sales Source:</b> Sales are summed from <b>base_grand_total</b>; for non-Pty companies this value is treated as EUR and converted to ZAR using the monthly EUR rate.</li>
                <li><b>Date Filter:</b> Monthly sales amounts only include sales invoices that have a submitted Payment Entry whose <b>posting_date</b> falls between the selected month start and end dates (the invoice's own posting date is not used).</li>
                <li><b>Invoice Status:</b> Sales invoices with status <b>Cancelled</b>, <b>Draft</b>, <b>Return</b>, and <b>Credit Note Issued</b> are excluded from the calculation.</li>
            </ul>
        </div>
        """,
        "total_cards": [
            {
                "title": "Period Salaries % of Sales",
                "unit": "percent",
                "value": f"{period_percent:.2f}"
            }
        ],
        "datasets": [
            {
                "type": "bar",
                "name": "Salaries % of Sales",
                "unit": "percent",
                "values": salary_percent_values
            }
        ]
    }

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
        ORDER BY `amount` DESC
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
            "unit": "rand",
            "values": [f"{obj['amount']:.0f}"]
        })

    data = {
        "title": "Pipeline Quotation Kartoza Pty (Draft/Open)",
        "labels": label,
        "element_id": "quote_pty",
        "showTotal": True,
        "isReverse": False,
        "type": "single",
        "datasets": datasets,
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Displays open quotations for Kartoza (Pty) Ltd:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Amount:</b> Value of each open quotation (Draft/Open status), grouped by quote name.</li>
            </ul>
            <span style='color: #888;'>Total is the sum of all open quotations.</span>
        </div>
        """,
        "total_cards": [
            {
                "title": f"Total Quotes Pty",
                "unit": "rand",
                "value": f"{total_quotes:.0f}"
            }
        ],
    }

    return data

@frappe.whitelist(allow_guest=True)
def get_company_pipeline_opportunities_pty():

    chart_data = []

    zar_eur_rate = get_rates(None, "EUR")
    zar_usd_rate = get_rates(None, "USD")

    total_opps = 0
    sql = f"""
        SELECT 
        CONCAT(top.customer_name, " (", top.name, " | ", DATE(top.creation), ")") AS `opp_name`,
        (CASE
        WHEN top.currency = 'ZAR' THEN top.opportunity_amount
        WHEN top.currency = 'EUR' THEN top.opportunity_amount * {zar_eur_rate}
        WHEN top.currency = 'USD' THEN top.opportunity_amount * {zar_usd_rate}
        ELSE top.opportunity_amount
        END) AS `amount`,
        top.probability as `probability`
        FROM `tabOpportunity` top
        WHERE top.status in ('Draft', 'Open')
        AND top.company = 'Kartoza (Pty) Ltd'
        ORDER BY `amount` DESC
    """

    result = frappe.db.sql(sql, as_dict=1, debug=0)
    for obj in result:
        total_opps += obj["amount"]

        project_label = obj["opp_name"]

        chart_data.append({
            "project": project_label,
            "amount": f"{obj['amount']:.0f}",
            "probability": f"{obj['probability']:.0f}" if obj.get('probability') else "0",
        })

    # Show all quote names as legends, and a single label for the chart (e.g., 'Top 10 Quotes')
    labels = [row["project"] for row in chart_data]

    total_amount_values = [row["amount"] for row in chart_data]
    total_probability_values = [row["probability"] for row in chart_data]

    data = {
        "title": "Pipeline Opportunity Kartoza Pty (Draft/Open)",
        "labels": labels,
        "isReverse": True,
        "showTotal": True,
        "shouldSplitLongLabels": True,
        "element_id": "quote_pty",
        "type": "single",
        "datasets": [
            {
                "type": "bar",
                "name": "Total Amount",
                "unit": "rand",
                "values": total_amount_values
            },
            {
                "type": "bar",
                "name": "Probability(%)",
                "unit": "percent",
                "values": total_probability_values
            },

        ],
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Displays open opportunities for Kartoza (Pty) Ltd:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Amount:</b> Value of each open opportunity (Draft/Open status), grouped by opportunity name.</li>
            </ul>
            <span style='color: #888;'>Total is the sum of all open opportunities.</span>
        </div>
        """,
        "total_cards": [
            {
                "title": f"Total Opportunities Pty",
                "unit": "rand",
                "value": f"{total_opps:.0f}"
            }
        ],
    }

    return data

@frappe.whitelist(allow_guest=True)
def get_company_pipeline_opportunities_lda():

    chart_data = []

    zar_eur_rate = get_rates(None, "EUR")
    zar_usd_rate = get_rates(None, "USD")

    total_opps = 0
    sql = f"""
        SELECT 
        CONCAT(top.customer_name, " (", top.name, " | ", DATE(top.creation), ")") AS `opp_name`,
        (CASE
        WHEN top.currency = 'ZAR' THEN top.opportunity_amount
        WHEN top.currency = 'EUR' THEN top.opportunity_amount * {zar_eur_rate}
        WHEN top.currency = 'USD' THEN top.opportunity_amount * {zar_usd_rate}
        ELSE top.opportunity_amount
        END) AS `amount`,
        top.probability as `probability`
        FROM `tabOpportunity` top
        WHERE top.status in ('Draft', 'Open')
        AND top.company = 'Kartoza Unipessoal Lda'
        ORDER BY `amount` DESC
    """

    result = frappe.db.sql(sql, as_dict=1, debug=0)
    for obj in result:
        total_opps += obj["amount"]

        project_label = obj["opp_name"]

        chart_data.append({
            "project": project_label,
            "amount": f"{obj['amount']:.0f}",
            "probability": f"{obj['probability']:.0f}" if obj.get('probability') else "0",
        })

    # Show all quote names as legends, and a single label for the chart (e.g., 'Top 10 Quotes')
    labels = [row["project"] for row in chart_data]

    total_amount_values = [row["amount"] for row in chart_data]
    total_probability_values = [row["probability"] for row in chart_data]

    data = {
        "title": "Pipeline Opportunity Kartoza Unipessoal Lda (Draft/Open)",
        "labels": labels,
        "isReverse": True,
        "showTotal": True,
        "shouldSplitLongLabels": True,
        "element_id": "quote_pty",
        "type": "single",
        "datasets": [
            {
                "type": "bar",
                "name": "Total Amount",
                "unit": "rand",
                "values": total_amount_values
            },
            {
                "type": "bar",
                "name": "Probability(%)",
                "unit": "percent",
                "values": total_probability_values
            },

        ],
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Displays open opportunities for Kartoza Unipessoal Lda (Currency ZAR):</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Amount:</b> Value of each open opportunity (Draft/Open status), grouped by opportunity name.</li>
            </ul>
            <span style='color: #888;'>Total is the sum of all open opportunities.</span>
        </div>
        """,
        "total_cards": [
            {
                "title": f"Total Opportunities Lda",
                "unit": "rand",
                "value": f"{total_opps:.0f}"
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
        AND tq.company = 'Kartoza Unipessoal Lda'
        GROUP BY tq.name
        ORDER BY `amount` DESC
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
            "unit": "rand",
            "values": [f"{obj['amount']:.0f}"]
        })

    data = {
        "title": "Pipeline Quotation Kartoza Unipessoal Lda (Draft/Open)",
        "labels": label,
        "isReverse": False,
        "showTotal": True,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "element_id": "quote_lda",
        "type": "single",
        "datasets": datasets,
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Displays open quotations for Kartoza Unipessoal Lda (Currency ZAR):</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Amount:</b> Value of each open quotation (Draft/Open status), converted to Rand if needed, grouped by quote name.</li>
            </ul>
            <span style='color: #888;'>Total is the sum of all open quotations.</span>
        </div>
        """,
        "total_cards": [
            {
                "title": f"Total Quotes Lda",
                "unit": "rand",
                "value": f"{total_quotes:.0f}"
            }
        ],
    }

    return data

@frappe.whitelist(allow_guest=True)
def get_open_sla(service_category=None):
    chart_data = []
    zar_rate = get_rates(None, "EUR")

    if service_category in ("SLA", "Hosting"):
        service_category_filter = f"tp.custom_service_category = '{service_category}'"
    else:
        service_category_filter = "(tp.custom_service_category = 'SLA' OR tp.custom_service_category = 'Hosting')"

    sql = f"""
    SELECT
        COALESCE(so_data.sales_order_amount, 0) AS sales_order_amount,
        COALESCE(si_data.sales_invoice_amount, 0) AS sales_invoice_amount,
        tp.project_name AS project,
        tp.expected_start_date AS start_date,
        tp.expected_end_date AS end_date,
        tp.custom_service_category as sla_type
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
    AND {service_category_filter}
    ORDER BY tp.expected_start_date ASC;

    """

    all_sla = frappe.db.sql(sql, as_dict=1, debug=0)

    for sla in all_sla:
        project_label = sla["project"]

        chart_data.append({
            "project": project_label,
            "sales_order_amount": f"{sla['sales_order_amount']:.0f}",
            "sales_invoice_amount": f"{sla['sales_invoice_amount']:.0f}",
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
        "showTotal": True,
        "shouldSplitLongLabels": False,
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Shows open SLA and hosting projects:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Total Sales Order Amount:</b> Sum of sales order items linked to each project.</li>
                <li><b>Total Sales Invoice Amount:</b> Sum of paid sales invoices linked to each project.</li>
                <li>Projects are filtered by name containing 'sla' or 'hosting' and status 'Open'.</li>
            </ul>
        </div>
        """,
        "total_cards": [],
        "datasets": [
            {
                "type": "bar",
                "name": "Total Sales Order Amount",
                "unit": "rand",
                "values": sales_order_amount_values
            },
            {
                "type": "bar",
                "name": "Total Sales Invoice Amount",
                "unit": "rand",
                "values": sales_invoice_amount_values
            }
        ]
    }

    return data

@frappe.whitelist(allow_guest=True)
def get_open_sales_orders(start_date=None, end_date=None):
    chart_data = []

    total_billed_amount = 0
    total_billed_sales_orders = 0
    total_to_be_billed_all = 0

    date_filter = ""
    if end_date:
        date_filter = f" AND tso.transaction_date <= '{end_date}'"

    final_dict = frappe.db.sql(f"""
        SELECT
            DISTINCT p.name AS project,
            p.status
        FROM `tabProject` p
        INNER JOIN `tabSales Order` tso ON tso.project = p.name
        WHERE tso.docstatus = 1
        AND tso.status NOT IN ('Cancelled')
        AND tso.name NOT IN (
            SELECT reference_name 
            FROM
            `tabComment` tc
            WHERE
                reference_doctype = 'Sales Order'
                AND content = 'Closed'
                AND tc.creation <= %(end_date)s
        )
        {date_filter}
        ORDER BY p.name
    """, {"end_date": end_date}, as_dict=1, debug=0)

    # Extract project names
    projects = [d['project'] for d in final_dict]

    # Fetch related sales data
    data_map = get_all_data(projects, start_date, end_date)
    future_financial_years = data_map.get('future_financial_years', [])
    total_deferred_revenue_by_fy = {fy: 0 for fy in future_financial_years}

    # Enrich final_dict with totals
    for d in final_dict:
        billed = data_map['sales_invoices'].get(d['project'], 0) or 0
        ordered = data_map['sales_orders'].get(d['project'], 0) or 0
        risk_percentages = data_map['risk_percentages'].get(d['project'], 0)
        deferred_revenue_by_fy = data_map.get('deferred_revenues_by_fy', {}).get(d['project'], {})
        total_to_be_billed = ordered - billed

        total_billed_amount += billed
        total_billed_sales_orders += ordered
        total_to_be_billed_all += total_to_be_billed

        d['total_billed_amount'] = billed
        d['total_billed_sales_order'] = ordered
        d['total_to_be_billed'] = total_to_be_billed
        d["risk_percentage"] = risk_percentages

        for fy in future_financial_years:
            fy_value = deferred_revenue_by_fy.get(fy, 0) or 0
            d[f"deferred_revenue_{fy}"] = fy_value
            total_deferred_revenue_by_fy[fy] += fy_value

    # Always show all 3 coming SA financial year columns.
    visible_financial_years = list(future_financial_years)

    # Filter only projects that have sales orders
    all_sales_orders = [d for d in final_dict if d['total_billed_sales_order'] > 0]

    for sale_order in all_sales_orders:
        project_label = sale_order["project"]

        chart_data.append({
            "project": project_label,
            "total_billed_amount": f"{sale_order['total_billed_amount']:.0f}",
            "total_billed_sales_order": f"{sale_order['total_billed_sales_order']:.0f}",
            "total_to_be_billed": f"{sale_order['total_to_be_billed']:.0f}",
            "risk_percentage": f"{sale_order['risk_percentage']:.0f}" if sale_order.get('risk_percentage') else "0",
            "deferred_revenue_by_fy": {
                fy: f"{sale_order.get(f'deferred_revenue_{fy}', 0):.0f}"
                for fy in visible_financial_years
            },
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
        "showTotal": True,
        "shouldSplitLongLabels": False,
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Displays open sales orders by project:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Total Billed Amount:</b> Sum of sales invoices for each open project.</li>
                <li><b>Total Sales Order:</b> Sum of sales orders for each open project.</li>
                <li><b>Total To Be Billed:</b> Sales order total minus billed amount.</li>
                <li><b>Deferred Revenue by SA Financial Year:</b> Future deferred revenue is grouped into South African financial years (April to March) based on invoice due date.</li>
                <li><b>Risk:</b> Green represents low risk or good performance (0-40%), amber represents moderate risk (41-75%), and red represents high risk (76-100%).</li>
            </ul>
            <span style='color: #888;'>Totals are summed for the period.</span>
        </div>
        """,
        "total_cards": [
            {
                "title": f"Total To Be Billed",
                "unit": "rand",
                "value": f"{total_to_be_billed_all:.0f}"
            },
            *[
                {
                    "title": f"Deferred Revenue {fy}",
                    "unit": "rand",
                    "value": f"{total_deferred_revenue_by_fy.get(fy, 0):.0f}"
                }
                for fy in visible_financial_years
            ],
        ],
        "datasets": [
            {
                "type": "bar",
                "name": "Total Billed Amount",
                "unit": "rand",
                "values": total_billed_amount_values,
                "isColorCoded": False
            },
            {
                "type": "bar",
                "name": "Total Sales Order",
                "unit": "rand",
                "values": total_billed_sales_order_values,
                "isColorCoded": False
            },
            {
                "type": "bar",
                "name": "Total To Be Billed",
                "unit": "rand",
                "values": [f"{sale_order['total_to_be_billed']:.0f}" if sale_order.get('total_to_be_billed') else "0" for sale_order in all_sales_orders],
                "isColorCoded": False
            },
            *[
                {
                    "type": "bar",
                    "name": f"Deferred Revenue {fy}",
                    "unit": "rand",
                    "values": [
                        f"{sale_order.get(f'deferred_revenue_{fy}', 0):.0f}"
                        for sale_order in all_sales_orders
                    ],
                    "isColorCoded": False
                }
                for fy in visible_financial_years
            ],
            {
                "type": "line",
                "name": "Risk",
                "unit": "percent",
                "values": [f"{sale_order['risk_percentage']:.0f}" if sale_order.get('risk_percentage') else "0" for sale_order in all_sales_orders],
                "isColorCoded": True
            },

        ]
    }

    return data

@frappe.whitelist(allow_guest=True)
def get_item_wise_annual_sales_pty(start_date, end_date):

    ranges = get_month_ranges(start_date, end_date)
    chart_data = []
    all_item_codes = set()
    all_item_codes_sql = f"""
        SELECT 
            item_code as `item_code`
        FROM `tabSales Invoice Item` tsoi
        LEFT JOIN `tabSales Invoice` tso ON tso.name = tsoi.parent
        WHERE tso.company = 'Kartoza (Pty) Ltd'
        AND tso.posting_date BETWEEN '{start_date}' AND '{end_date}'
        AND tso.status NOT IN ('Cancelled', 'Credit Note Issued', 'Return', 'Draft')
        GROUP BY tsoi.item_code
    """

    all_item_codes_result = frappe.db.sql(all_item_codes_sql, as_dict=1, debug=0)
    for item in all_item_codes_result:
        all_item_codes.add(item["item_code"])
    month_item_data = []

    # First pass: collect all item_codes across all periods
    for start, end in ranges:
        final_dict = frappe.db.sql(f"""
        SELECT 
            item_code as `item_code`,
            SUM(tsoi.base_amount ) as `item_total`
        FROM `tabSales Invoice Item` tsoi
        LEFT JOIN `tabSales Invoice` tso ON tso.name = tsoi.parent
        WHERE tso.company = 'Kartoza (Pty) Ltd'
        AND tso.posting_date BETWEEN '{start}' AND '{end}'
        AND tso.status NOT IN ('Cancelled', 'Credit Note Issued', 'Return', 'Draft')
        GROUP BY tsoi.item_code
        """, as_dict=1, debug=0)
        all_item_codes.update(item["item_code"] for item in final_dict)
        month_item_data.append(final_dict)

    labels = [get_month_label(start) for start, _ in ranges]

    # Second pass: build item_map with 0 for missing item_codes
    item_map = {item_code: [] for item_code in all_item_codes}
    for period_data in month_item_data:
        period_dict = {item["item_code"]: item["item_total"] for item in period_data}
        for item_code in all_item_codes:
            value = period_dict.get(item_code, 0)
            item_map[item_code].append(f"{value:.0f}")

    data = {
        "title": f"Per Item Annual Sales Pty",
        "labels": labels,
        "element_id": "item_wise_annual_sales_pty",
        "isReverse": False,
        "showTotal": True,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "type": "single",
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Displays per item annual sales for Kartoza (Pty) Ltd:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Item Codes:</b> Each bar represents the total sales amount for an item code per month.</li>
                <li><b>Missing Items:</b> If an item code is present in one month but not in another, a value of 0 is shown for the missing month.</li>
                <li><b>Period:</b> Data is grouped and displayed for each month in the selected date range.</li>
                <li><b>Source:</b> Sales Invoice Items for Kartoza (Pty) Ltd, filtered by posting date and document status.</li>
            </ul>
        </div>
        """,
        "total_cards": [],
        "datasets": []
    }

    for name, values in item_map.items():
        data["datasets"].append({
            "type": "bar",
            "name": name,
            "unit": "rand",
            "values": values
        })

    return data 

@frappe.whitelist(allow_guest=True)
def get_item_wise_annual_sales_lda(start_date, end_date):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []
    all_item_codes = set()
    all_item_codes_sql = f"""
        SELECT 
            item_code as `item_code`
        FROM `tabSales Invoice Item` tsoi
        LEFT JOIN `tabSales Invoice` tso ON tso.name = tsoi.parent
        WHERE tso.company = 'Kartoza Unipessoal Lda'
        AND tso.posting_date BETWEEN '{start_date}' AND '{end_date}'
        AND tso.status NOT IN ('Cancelled', 'Credit Note Issued', 'Return', 'Draft')
        GROUP BY tsoi.item_code
    """

    all_item_codes_result = frappe.db.sql(all_item_codes_sql, as_dict=1, debug=0)
    for item in all_item_codes_result:
        all_item_codes.add(item["item_code"])
    month_item_data = []

    zar_eur_rate = get_rates(None, "EUR")

    # First pass: collect all item_codes across all periods
    for start, end in ranges:
        final_dict = frappe.db.sql(f"""
        SELECT 
            item_code as `item_code`,
            SUM(tsoi.base_amount ) * {zar_eur_rate} as `item_total`
        FROM `tabSales Invoice Item` tsoi
        LEFT JOIN `tabSales Invoice` tso ON tso.name = tsoi.parent
        WHERE tso.company = 'Kartoza Unipessoal Lda'
        AND tso.posting_date BETWEEN '{start}' AND '{end}'
        AND tso.status NOT IN ('Cancelled', 'Credit Note Issued', 'Return', 'Draft')
        GROUP BY tsoi.item_code
        """, as_dict=1, debug=0)
        all_item_codes.update(item["item_code"] for item in final_dict)
        month_item_data.append(final_dict)

    labels = [get_month_label(start) for start, _ in ranges]

    # Initialize a dict to hold profit/loss values per cost center
    # Second pass: build item_map with 0 for missing item_codes
    item_map = {item_code: [] for item_code in all_item_codes}
    for period_data in month_item_data:
        period_dict = {item["item_code"]: item["item_total"] for item in period_data}
        for item_code in all_item_codes:
            value = period_dict.get(item_code, 0)
            item_map[item_code].append(f"{value:.0f}")

    data = {
        "title": f"Per Item Annual Sales Lda",
        "labels": labels,
        "element_id": "item_wise_annual_sales_lda",
        "isReverse": False,
        "showTotal": True,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "type": "single",
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Displays per item annual sales for Kartoza Unipessoal Lda:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Item Codes:</b> Each bar represents the total sales amount for an item code per month.</li>
                <li><b>Missing Items:</b> If an item code is present in one month but not in another, a value of 0 is shown for the missing month.</li>
                <li><b>Period:</b> Data is grouped and displayed for each month in the selected date range.</li>
                <li><b>Source:</b> Sales Invoice Items for Kartoza Unipessoal Lda, filtered by posting date and document status.</li>
            </ul>
        </div>
        """,
        "total_cards": [],
        "datasets": []
    }

    for name, values in item_map.items():
        data["datasets"].append({
            "type": "bar",
            "name": name,
            "unit": "rand",
            "values": values
        })


    return data

@frappe.whitelist(allow_guest=True)
def get_sales_analytics_customers_pty(start_date, end_date):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []
    all_customers = set()
    month_item_data = []

    # First pass: collect all item_codes across all periods
    for start, end in ranges:
        final_dict = frappe.db.sql(f"""
        SELECT 
            party_name as `customer`,
            SUM(base_paid_amount) as `paid_amount`
        FROM `tabPayment Entry`
        WHERE payment_type = 'Receive'
        AND company = 'Kartoza (Pty) Ltd'
        AND party_name != ''
        AND posting_date BETWEEN '{start}' AND '{end}'
        GROUP BY party_name
        """, as_dict=1, debug=0)
        all_customers.update(item["customer"] for item in final_dict)
        month_item_data.append(final_dict)

    labels = [get_month_label(start) for start, _ in ranges]

    # Initialize a dict to hold profit/loss values per cost center
    # Second pass: build item_map with 0 for missing item_codes
    customer_map = {customer: [] for customer in all_customers}
    for period_data in month_item_data:
        period_dict = {item["customer"]: item["paid_amount"] for item in period_data}
        for customer in all_customers:
            value = period_dict.get(customer, 0)
            customer_map[customer].append(f"{value:.0f}")

    data = {
        "title": f"Sales Analytics Customers Pty",
        "labels": labels,
        "element_id": "sales_analytics_customers_pty",
        "isReverse": False,
        "showTotal": True,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "type": "single",
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Displays customer payment analytics for Kartoza (Pty) Ltd:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Customer Payments:</b> Shows the total amount paid by each customer during each month in the selected period.</li>
                <li><b>Source:</b> Data is based on Payment Entry records for customers, filtered by company and posting date.</li>
                <li><b>Period:</b> Data is grouped and displayed for each month in the selected date range.</li>
            </ul>
        </div>
        """,
        "total_cards": [],
        "datasets": []
    }

    for name, values in customer_map.items():
        data["datasets"].append({
            "type": "bar",
            "name": name,
            "unit": "rand",
            "values": values
        })


    return data

@frappe.whitelist(allow_guest=True)
def get_sales_analytics_customers_lda(start_date, end_date):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []
    all_customers = set()
    month_item_data = []

    zar_eur_rate = get_rates(None, "EUR")

    # First pass: collect all item_codes across all periods
    for start, end in ranges:
        final_dict = frappe.db.sql(f"""
        SELECT 
            party_name as `customer`,
            SUM(base_paid_amount) * {zar_eur_rate} as `paid_amount`
        FROM `tabPayment Entry`
        WHERE party_type = 'Customer'
        AND company = 'Kartoza Unipessoal Lda'
        AND party_name != ''
        AND posting_date BETWEEN '{start}' AND '{end}'
        GROUP BY party_name
        """, as_dict=1, debug=0)
        all_customers.update(item["customer"] for item in final_dict)
        month_item_data.append(final_dict)

    labels = [get_month_label(start) for start, _ in ranges]

    # Initialize a dict to hold profit/loss values per cost center
    customer_map = {customer: [] for customer in all_customers}
    for period_data in month_item_data:
        period_dict = {item["customer"]: item["paid_amount"] for item in period_data}
        for customer in all_customers:
            value = period_dict.get(customer, 0)
            customer_map[customer].append(f"{value:.0f}")

    data = {
        "title": f"Sales Analytics Customers Lda",
        "labels": labels,
        "element_id": "sales_analytics_customers_lda",
        "isReverse": False,
        "showTotal": True,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "type": "single",
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Displays customer payment analytics for Kartoza Unipessoal Lda:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Customer Payments:</b> Shows the total amount paid by each customer during each month in the selected period.</li>
                <li><b>Source:</b> Data is based on Payment Entry records for customers, filtered by company and posting date.</li>
                <li><b>Period:</b> Data is grouped and displayed for each month in the selected date range.</li>
            </ul>
        </div>
        """,
        "total_cards": [],
        "datasets": []
    }

    for name, values in customer_map.items():
        data["datasets"].append({
            "type": "bar",
            "name": name,
            "unit": "rand",
            "values": values
        })


    return data

@frappe.whitelist(allow_guest=True)
def get_overhead_cost_pty(start_date, end_date):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []

    for start, end in ranges:

        filters = frappe._dict({
            "company": "Kartoza (Pty) Ltd",
            "filter_based_on": "Date Range",
            "period_start_date": start,
            "period_end_date": end,
            "from_fiscal_year": start,
            "to_fiscal_year": end,
            "periodicity": "Monthly",
            "cost_center": [],
            "employee_type": [],
            "business_unit": [],
            "project": [],
            "selected_view": "Report",
            "accumulated_values": 1,
            "include_default_book_entries": 1,
            "prepared_report_name": "1qn7c95eop"
           })

        period_list = get_period_list(
            filters.from_fiscal_year,
            filters.to_fiscal_year,
            filters.period_start_date,
            filters.period_end_date,
            filters.filter_based_on,
            filters.periodicity,
            company="Kartoza (Pty) Ltd",
	    )


        income = get_data(
            "Kartoza (Pty) Ltd",
            "Income",
            "Credit",
            period_list,
            filters=filters,
            accumulated_values=filters.accumulated_values,
            ignore_closing_entries=True,
        )

        expense = get_data(
            "Kartoza (Pty) Ltd",
            "Expense",
            "Debit",
            period_list,
            filters=filters,
            accumulated_values=filters.accumulated_values,
            ignore_closing_entries=True,
	    )

        overhead_fixed = 0
        overhead_variable = 0

        fixed_overhead_accounts = ('5102 - Foreign Exchange Differencee on Salaries', '5104 - Sub-Contrator', '5112 - Domain Registration', '5115 - Hosting', '5117 - Salaries & Wages Non-Admin Staff', '5118 - Insurance as Cost of Sales', '5208 - Accounting Fees', '5232 - Insurance as Expense', '5245 - Rent Paid', '5247 - Salaries & Wages Admin Staff', '5250 - Directors remuneration')

        overhead_variable_accounts = ('5120 - Training', '5122 - Bank Charges as Cost of Sales', '5123 - Exchange Gain/Loss as Cost of Sales', '5207 - Marketing', '5208-01 - Accounting Fees - MST', '5211 - Bank Charges as an Expense', '5217 - Communication', '5219 - Exchange Gain/Loss', '5220 - Gain/Loss on Asset Disposal', '5222 - Computer Expenses', '5223 - Consulting fees', '5241 - Overs and unders', '5242 - Printing & Stationary', '5250 - Travel as an Expense International')
        
        for expense_row in expense:
            print(expense_row)
            account = expense_row.get("account_name")
            if account in fixed_overhead_accounts:
                overhead_fixed += expense_row["total"]
            elif account in overhead_variable_accounts:
                overhead_variable += expense_row["total"]

        total_revenue =  get_profit(
		    income, period_list, filters.company, filters.presentation_currency
	    )

        overhead_variable_cost = overhead_variable
        overhead_fixed_cost = overhead_fixed
        overhead_cost = overhead_fixed_cost + overhead_variable_cost
        overhead_percantage = (overhead_cost / total_revenue) * 100

        month_label = get_month_label(start)

        chart_data.append({
            "month": month_label,
            "overhead_fixed_cost": f"{overhead_fixed_cost:.0f}",
            "overhead_variable_cost": f"{overhead_variable_cost:.0f}",
            "total_revenue": f"{total_revenue:.0f}",
            "overhead_percantage": f"{overhead_percantage:.0f}"
        })

    # Transform chart_data for stacked chart
    labels = [row["month"] for row in chart_data]

    overhead_fixed_cost_values = [row["overhead_fixed_cost"] for row in chart_data]
    overhead_variable_cost_values = [row["overhead_variable_cost"] for row in chart_data]
    total_revenue_values = [row["total_revenue"] for row in chart_data]
    overhead_percantage_values = [row["overhead_percantage"] for row in chart_data]

    data = {
        "element_id": "overhead_cost_pty",
        "type": "single",
        "title": "Overhead Cost Pty",
        "labels": labels,
        "isReverse": False,
        "showTotal": False,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "total_cards": [],
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Displays overhead costs for Kartoza (Pty) Ltd per month:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Overhead Cost:</b> Sum of salary costs for selected overhead departments (PMO, Admin, Management) plus supplier payments for the period.</li>
                <li><b>Total Revenue:</b> Total Income as calculated from income accounts for the period.</li>
                <li><b>Overhead %:</b> Overhead cost as a percentage of total revenue for the period.</li>
            </ul>
            <span style='color: #888;'>Helps track the proportion of overhead costs relative to revenue each month.</span>
        </div>
        """,
        "datasets": [
            {
                "type": "bar",
                "name": "Overhead Fixed Cost",
                "unit": "rand",
                "values": overhead_fixed_cost_values
            },
            {
                "type": "bar",
                "name": "Overhead Variable Cost",
                "unit": "rand",
                "values": overhead_variable_cost_values
            },
            {
                "type": "bar",
                "name": "Total Revenue",
                "unit": "rand",
                "values": total_revenue_values
            },
            {
                "type": "Line",
                "name": "Overhead %",
                "unit": "percent",
                "values": overhead_percantage_values
            }
        ]
    }

    return data

@frappe.whitelist(allow_guest=True)
def get_overhead_cost_lda(start_date, end_date):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []

    zar_eur_rate = get_rates(None, "EUR")

    for start, end in ranges:

        filters = frappe._dict({
            "company": "Kartoza Unipessoal Lda",
            "filter_based_on": "Date Range",
            "period_start_date": start,
            "period_end_date": end,
            "from_fiscal_year": start,
            "to_fiscal_year": end,
            "periodicity": "Monthly",
            "cost_center": [],
            "employee_type": [],
            "business_unit": [],
            "project": [],
            "selected_view": "Report",
            "accumulated_values": 1,
            "include_default_book_entries": 1,
            "prepared_report_name": "1qn7c95eop"
           })

        period_list = get_period_list(
            filters.from_fiscal_year,
            filters.to_fiscal_year,
            filters.period_start_date,
            filters.period_end_date,
            filters.filter_based_on,
            filters.periodicity,
            company="Kartoza Unipessoal Lda",
	    )


        income = get_data(
            "Kartoza Unipessoal Lda",
            "Income",
            "Credit",
            period_list,
            filters=filters,
            accumulated_values=filters.accumulated_values,
            ignore_closing_entries=True,
        )

        expense = get_data(
            "Kartoza Unipessoal Lda",
            "Expense",
            "Debit",
            period_list,
            filters=filters,
            accumulated_values=filters.accumulated_values,
            ignore_closing_entries=True,
	    )

        overhead_fixed = 0
        overhead_variable = 0

        fixed_overhead_accounts = ('5102 - Foreign Exchange Differencee on Salaries', '5104 - Sub-Contrator', '5112 - Domain Registration', '5115 - Hosting', '5125 - Salaries & Wages Non-Admin Staff', '5117 - Insurance as Cost of Sales', '5207 - Accounting Fees', '5231 - Insurance as Expense', '5241 - Rent Paid', '5258 - Salaries & Wages Admin Staff', '5243 - Directors remuneration')

        overhead_variable_accounts = ('5119 - Training', '5121 - Bank Charges as Cost of Sales', '5122 - Exchange Gain/Loss as Cost of Sales', '5206 - Marketing', '5210 - Bank Charges as an Expense', '5216 - Communication', '5218 - Exchange Gain/Loss', '5219 - Gain/Loss on Asset Disposal', '5221 - Computer Expenses', '5222 - Consulting fees', '5238 - Overs and unders', '5239 - Printing & Stationary', '5252 - Travel as an Expense International')
        
        for expense_row in expense:
            print(expense_row)
            account = expense_row.get("account_name")
            if account in fixed_overhead_accounts:
                overhead_fixed += expense_row["total"]
            elif account in overhead_variable_accounts:
                overhead_variable += expense_row["total"]

        total_revenue =  get_profit(
		income, period_list, filters.company, filters.presentation_currency
	    )

        if total_revenue is None or total_revenue == "":
            total_revenue = 0.0
        total_revenue = total_revenue * zar_eur_rate

        overhead_variable_cost = overhead_variable * zar_eur_rate
        overhead_fixed_cost = (overhead_fixed * zar_eur_rate) + 260000
        overhead_cost = overhead_fixed_cost + overhead_variable_cost
        overhead_percantage = (overhead_cost / total_revenue) * 100 if total_revenue else 0.0

        month_label = get_month_label(start)

        chart_data.append({
            "month": month_label,
            "overhead_fixed_cost": f"{overhead_fixed_cost:.0f}",
            "overhead_variable_cost": f"{overhead_variable_cost:.0f}",
            "total_revenue": f"{total_revenue:.0f}",
            "overhead_percantage": f"{overhead_percantage:.0f}"
        })

    # Transform chart_data for stacked chart
    labels = [row["month"] for row in chart_data]

    overhead_fixed_cost_values = [row["overhead_fixed_cost"] for row in chart_data]
    overhead_variable_cost_values = [row["overhead_variable_cost"] for row in chart_data]
    total_revenue_values = [row["total_revenue"] for row in chart_data]
    overhead_percantage_values = [row["overhead_percantage"] for row in chart_data]

    data = {
        "element_id": "overhead_cost_lda",
        "type": "single",
        "title": "Overhead Cost Lda",
        "labels": labels,
        "isReverse": False,
        "showTotal": False,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "total_cards": [],
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Displays overhead costs for Kartoza Unipessoal Lda per month:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Overhead Cost:</b> Sum of salary costs for selected overhead departments (PMO, Admin, Management) plus supplier payments for the period.</li>
                <li><b>Total Revenue:</b> Total Income as calculated from income accounts for the period.</li>
                <li><b>Overhead %:</b> Overhead cost as a percentage of total revenue for the period.</li>
            </ul>
            <span style='color: #888;'>Helps track the proportion of overhead costs relative to revenue each month.</span>
        </div>
        """,
        "datasets": [
            {
                "type": "bar",
                "name": "Overhead Fixed Cost",
                "unit": "rand",
                "values": overhead_fixed_cost_values
            },
            {
                "type": "bar",
                "name": "Overhead Variable Cost",
                "unit": "rand",
                "values": overhead_variable_cost_values
            },
            {
                "type": "bar",
                "name": "Total Revenue",
                "unit": "rand",
                "values": total_revenue_values
            },
            {
                "type": "Line",
                "name": "Overhead %",
                "unit": "percent",
                "values": overhead_percantage_values
            }
        ]
    }

    return data

@frappe.whitelist(allow_guest=True)
def get_project_closed_summary(start_date, end_date):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []
    all_projects= set()
    month_item_data = []

    # First pass: collect all item_codes across all periods
    for start, end in ranges:
        zar_rate = get_rates(end, 'EUR')
        final_dict = frappe.db.sql(f"""
        SELECT
            name as `project_name`,
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
        """, as_dict=1, debug=0)
        all_projects.update(item["project_name"] for item in final_dict)
        month_item_data.append(final_dict)

    labels = [get_month_label(start) for start, _ in ranges]

    # Second pass: build item_map with 0 for missing item_codes
    item_map = {project_name: [] for project_name in all_projects}
    for period_data in month_item_data:
        period_dict = {item["project_name"]: item["total_billed_amount"] for item in period_data}
        for project_name in all_projects:
            value = period_dict.get(project_name, 0)
            item_map[project_name].append(f"{value:.0f}")

    data = {
        "title": f"Project Closed Summary",
        "labels": labels,
        "element_id": "project_closed_summary",
        "isReverse": False,
        "showTotal": True,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "type": "single",
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Displays closed project summaries:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Project Names:</b> Each bar represents the total billed amount for a project that is closed during the period.</li>
                <li><b>Missing Projects:</b> If a project is present in one month but not in another, a value of 0 is shown for the missing month.</li>
                <li><b>Period:</b> Data is grouped and displayed for each month in the selected date range.</li>
                <li><b>Source:</b> Closed projects with their total billed amounts, converted to ZAR if needed, filtered by actual end date.</li>
        </div>
        """,
        "total_cards": [],
        "datasets": []
    }

    for name, values in item_map.items():
        data["datasets"].append({
            "type": "bar",
            "name": name,
            "unit": "rand",
            "values": values
        })

    return data

@frappe.whitelist(allow_guest=True)
def get_tender_summary(start_date, end_date):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []

    for start, end in ranges:
        lost_opportunities_sql = f"""
        SELECT
            COUNT(name) as `count_lost`,
            SUM(
                CASE
                    WHEN currency = 'EUR' THEN
                        opportunity_amount * {get_rates(end, 'EUR')}
                    WHEN currency = 'USD' THEN
                        opportunity_amount * {get_rates(end, 'USD')}
                    WHEN currency = 'GBP' THEN
                        opportunity_amount * {get_rates(end, 'GBP')}
                    ELSE
                        opportunity_amount
                END
            ) as `amount`
            FROM `tabOpportunity` 
            WHERE status IN ('Lost')
            AND creation BETWEEN '{start}' AND '{end}'
        """
        
        lost_quotes_sql = f"""
        SELECT
            COUNT(name) as `count_lost`,
            SUM(
                CASE
                    WHEN company = 'Kartoza Unipessoal Lda' THEN
                        base_total * {get_rates(end, 'EUR')}
                    ELSE
                        base_total
                END
            ) as `amount`
            FROM `tabQuotation` 
            WHERE status IN ('Lost')
            AND transaction_date BETWEEN '{start}' AND '{end}' 
        """

        won_opportunities_sql = f"""
        SELECT
            COUNT(name) as `count_lost`,
            SUM(
                CASE
                    WHEN currency = 'EUR' THEN
                        opportunity_amount * {get_rates(end, 'EUR')}
                    WHEN currency = 'USD' THEN
                        opportunity_amount * {get_rates(end, 'USD')}
                    WHEN currency = 'GBP' THEN
                        opportunity_amount * {get_rates(end, 'GBP')}
                    ELSE
                        opportunity_amount
                END
            ) as `amount`
            FROM `tabOpportunity`
            WHERE status IN ('Converted')
            AND creation BETWEEN '{start}' AND '{end}'
        """
        
        won_quotes_sql = f"""
        SELECT
            COUNT(name) as `count_lost`,
            SUM(
                CASE
                    WHEN company = 'Kartoza Unipessoal Lda' THEN
                        base_total * {get_rates(end, 'EUR')}
                    ELSE
                        base_total
                END
            ) as `amount`
            FROM `tabQuotation` 
            WHERE status IN ('Ordered', 'Partially Ordered')
            AND transaction_date BETWEEN '{start}' AND '{end}' 
        """

        time_sql = f"""
        SELECT 
            SUM(ttd.hours) as `total_hours`,
            SUM(ttd.costing_amount) as `total_costing`
            FROM `tabTask` tt 
            LEFT JOIN `tabTimesheet Detail` ttd ON ttd.task = tt.name
            WHERE LOWER(subject) LIKE '%tender%'
            AND ttd.from_time BETWEEN '{start}' AND '{end}';
        """
        

        lost_quotes = frappe.db.sql(lost_quotes_sql, as_dict=True)
        lost_opportunities = frappe.db.sql(lost_opportunities_sql, as_dict=True)
        won_opportunities = frappe.db.sql(won_opportunities_sql, as_dict=True)
        won_quotes = frappe.db.sql(won_quotes_sql, as_dict=True)
        time_arr = frappe.db.sql(time_sql, as_dict=True)

        month_label = get_month_label(start)

        chart_data.append({
            "month": month_label,
            "lost_quotes_count": f"{(lost_quotes[0]['count_lost'] or 0):.0f}",
            "lost_quotes_amount": f"{(lost_quotes[0]['amount'] or 0):.0f}",
            "won_quotes_count": f"{(won_quotes[0]['count_lost'] or 0):.0f}",
            "won_quotes_amount": f"{(won_quotes[0]['amount'] or 0):.0f}",
            "total_hours": f"{(time_arr[0]['total_hours'] or 0):.0f}",
            "total_costing": f"{(time_arr[0]['total_costing'] or 0):.0f}",
        })

    # Transform chart_data for stacked chart
    labels = [row["month"] for row in chart_data]

    lost_quotes_values = [row["lost_quotes_count"] for row in chart_data]
    lost_quotes_amounts = [row["lost_quotes_amount"] for row in chart_data]
    won_quotes_values = [row["won_quotes_count"] for row in chart_data]
    won_quotes_amounts = [row["won_quotes_amount"] for row in chart_data]
    total_hours_values = [row["total_hours"] for row in chart_data]
    total_costing_values = [row["total_costing"] for row in chart_data]

    data = {
        "element_id": "tender_summary",
        "type": "single",
        "title": "Tender Summary",
        "labels": labels,
        "isReverse": False,
        "showTotal": False,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "total_cards": [],
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Displays summary of tenders (opportunities and quotations) for the selected period:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Lost Quotes Count/Amount:</b> Number and total value of quotations marked as 'Lost' (converted to ZAR if needed).</li>
                <li><b>Won Quotes Count/Amount:</b> Number and total value of quotations marked as 'Ordered' or 'Partially Ordered' (converted to ZAR if needed).</li>
                <li>All amounts are summed for the period and currency conversions are applied where necessary.</li>
                <li>Each bar represents the count or amount for the corresponding category per month.</li>
            </ul>
            <span style='color: #888;'>Helps track tender performance and conversion rates over time.</span>
        </div>
        """,
        "datasets": [
            {
                "type": "bar",
                "name": "Lost Quotes Count",
                "unit": "count",
                "values": lost_quotes_values
            },
            {
                "type": "bar",
                "name": "Lost Quotes Amount",
                "unit": "rand",
                "values": lost_quotes_amounts
            },
            {
                "type": "bar",
                "name": "Won Quotes Count",
                "unit": "count",
                "values": won_quotes_values
            },
            {
                "type": "bar",
                "name": "Won Quotes Amount",
                "unit": "rand",
                "values": won_quotes_amounts
            },
            {
                "type": "bar",
                "name": "Total Tender Hours",
                "unit": "hours",
                "values": total_hours_values
            },
            {
                "type": "bar",
                "name": "Total Tender Costing",
                "unit": "rand",
                "values": total_costing_values
            }
        ]
    }

    return data


@frappe.whitelist(allow_guest=True)
def get_opportunity_trend(start_date, end_date):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []

    for start, end in ranges:
        opp_count_sql = f"""
            SELECT COUNT(name) as `opp_count` 
            FROM `tabOpportunity`
            WHERE creation BETWEEN '{start}' AND '{end}'
        """

        opp_count = frappe.db.sql(opp_count_sql, as_dict=True)[0].opp_count or 0

        month_label = get_month_label(start)

        chart_data.append({
            "month": month_label,
            "opp_count": opp_count
        })

    # Transform chart_data for stacked chart
    labels = [row["month"] for row in chart_data]

    opp_count_values = [row["opp_count"] for row in chart_data]

    data = {
        "element_id": "opportunity_trend",
        "type": "single",
        "title": "Opportunity Trend",
        "labels": labels,
        "isReverse": False,
        "showTotal": False,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "total_cards": [],
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Calculates the number of opportunities created in the selected range</b><br><br>
        </div>
        """,
        "datasets": [
            {
                "type": "bar",
                "name": "Opportunity Count",
                "unit": "count",
                "values": opp_count_values
            },
        ]
    }

    return data


@frappe.whitelist(allow_guest=True)
def get_sales_trend_5_years():
    ranges = get_year_ranges(5)
    chart_data = []

    total_sales_orders = 0
    total_quotes = 0
    total_opportunities = 0

    for start, end in ranges:
        zar_eur_rate = get_rates(end, "EUR")
        zar_usd_rate = get_rates(end, "USD")
        zar_gbp_rate = get_rates(end, "GBP")

        sales_order_sql = f"""
            SELECT SUM(
                CASE
                    WHEN company = 'Kartoza (Pty) Ltd' THEN base_grand_total
                    ELSE base_grand_total * {zar_eur_rate}
                END
            ) as `total`
            FROM `tabSales Order`
            WHERE docstatus = 1
            AND status NOT IN ('Cancelled', 'Closed')
            AND transaction_date BETWEEN '{start}' AND '{end}'
        """

        quotation_sql = f"""
            SELECT SUM(
                CASE
                    WHEN company = 'Kartoza (Pty) Ltd' THEN base_grand_total
                    ELSE base_grand_total * {zar_eur_rate}
                END
            ) as `total`
            FROM `tabQuotation`
            WHERE status != 'Cancelled'
            AND transaction_date BETWEEN '{start}' AND '{end}'
        """

        opportunity_sql = f"""
            SELECT SUM(
                CASE
                    WHEN currency = 'EUR' THEN opportunity_amount * {zar_eur_rate}
                    WHEN currency = 'USD' THEN opportunity_amount * {zar_usd_rate}
                    WHEN currency = 'GBP' THEN opportunity_amount * {zar_gbp_rate}
                    ELSE opportunity_amount
                END
            ) as `total`
            FROM `tabOpportunity`
            WHERE creation BETWEEN '{start}' AND '{end}'
        """

        sales_order_total = frappe.db.sql(sales_order_sql, as_dict=True)[0].total or 0
        quotation_total = frappe.db.sql(quotation_sql, as_dict=True)[0].total or 0
        opportunity_total = frappe.db.sql(opportunity_sql, as_dict=True)[0].total or 0

        total_sales_orders += sales_order_total
        total_quotes += quotation_total
        total_opportunities += opportunity_total

        year_label = start[:4]

        chart_data.append({
            "year": year_label,
            "sales_orders": f"{sales_order_total:.0f}",
            "quotes": f"{quotation_total:.0f}",
            "opportunities": f"{opportunity_total:.0f}",
        })

    labels = [row["year"] for row in chart_data]
    sales_order_values = [row["sales_orders"] for row in chart_data]
    quote_values = [row["quotes"] for row in chart_data]
    opportunity_values = [row["opportunities"] for row in chart_data]

    data = {
        "element_id": "sales_trend_5_years",
        "type": "single",
        "title": "Sales Trend (Last 5 Years)",
        "labels": labels,
        "isReverse": False,
        "showTotal": True,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Shows yearly sales trends for the past 5 years:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Sales Orders:</b> Total value of submitted, non-cancelled sales orders per year, converted to Rand.</li>
                <li><b>Quotes:</b> Total value of non-cancelled quotations per year, converted to Rand.</li>
                <li><b>Opportunities:</b> Total value of opportunities created per year, converted to Rand.</li>
            </ul>
            <span style='color: #888;'>Combines Kartoza (Pty) Ltd and Kartoza Unipessoal Lda. The most recent year is year-to-date.</span>
        </div>
        """,
        "total_cards": [
            {
                "title": "Total Sales Orders (5 Years)",
                "unit": "rand",
                "value": f"{total_sales_orders:.0f}"
            },
            {
                "title": "Total Quotes (5 Years)",
                "unit": "rand",
                "value": f"{total_quotes:.0f}"
            },
            {
                "title": "Total Opportunities (5 Years)",
                "unit": "rand",
                "value": f"{total_opportunities:.0f}"
            },
        ],
        "datasets": [
            {
                "type": "bar",
                "name": "Sales Orders",
                "unit": "rand",
                "values": sales_order_values
            },
            {
                "type": "bar",
                "name": "Quotes",
                "unit": "rand",
                "values": quote_values
            },
            {
                "type": "bar",
                "name": "Opportunities",
                "unit": "rand",
                "values": opportunity_values
            },
        ]
    }

    return data


@frappe.whitelist(allow_guest=True)
def get_timesheet_data(start_date, end_date, type_returned="hours"):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []

    if type_returned == "hours":
        title = "Timesheet Data for Project 'Kartoza Sales' (Hours)"
        help = f"""
            <div style='font-size: 14px;text-align: left'>
                <b>Shows monthly timesheet variance for the 'Kartoza Sales' project grouped by task and activity:</b><br><br>
                <ul style='margin-left: 1em;'>
                    <li><b>Scope:</b> Includes timesheet entries where project = 'Kartoza Sales' within the selected date range.</li>
                    <li><b>Series:</b> Each series the description of the task</li>
                    <li><b>Hours:</b> Total hours per series are included in the table for context (to two decimals).</li>
                </ul>
                <span style='color: #888;'>Data is grouped by month across the selected period.</span>
            </div>
        """
    else:
        title = "Timesheet Data for Project 'Kartoza Sales' (Cost)"
        help = f"""
            <div style='font-size: 14px;text-align: left'>
                <b>Shows monthly timesheet variance for the 'Kartoza Sales' project grouped by task and activity:</b><br><br>
                <ul style='margin-left: 1em;'>
                    <li><b>Scope:</b> Includes timesheet entries where project = 'Kartoza Sales' within the selected date range.</li>
                    <li><b>Series:</b> Each series the description of the task</li>
                    <li><b>Cost:</b> Total cost per series are included in the table for context (to two decimals).</li>
                </ul>
                <span style='color: #888;'>Data is grouped by month across the selected period.</span>
            </div>
        """

    for start, end in ranges:
        timesheet_data = frappe.db.sql(f"""
            SELECT 
                tt.subject as `task`,
                SUM(ttd.hours) as `hours`,
                SUM(ttd.costing_amount) as `costing_amount`,
                SUM(ttd.billing_amount) as `billing_amount`
            FROM `tabTimesheet Detail` ttd
            LEFT JOIN `tabTask` tt on tt.name = ttd.task
            WHERE ttd.project = 'Kartoza Sales'
            AND ttd.creation BETWEEN '{start}' AND '{end}'
            AND tt.subject != ''
            GROUP BY ttd.activity_type, ttd.task 
        """, as_dict=1, debug=0)

        print(f"SQL: {start} to {end} returned {len(timesheet_data)} rows")

        timesheet_array = []

        for dict in timesheet_data:
            
            task = dict['task']
            hours = dict['hours']
            costing_amount = dict['costing_amount']
            billing_amount = dict['billing_amount']
            cost_vs_lost = costing_amount

            timesheet_array.append({
                'task': task,
                'hours': f"{hours:.2f}",
                'cost_vs_lost': f"{cost_vs_lost:.0f}",
            })

        month_label = get_month_label(start)

        chart_data.append({
            "month": month_label,
            "timesheet_data": timesheet_array,
        })


    # Transform chart_data for stacked chart
    labels = [row["month"] for row in chart_data]

    # Collect all unique (task, activity) combinations across all months
    all_names = set()
    month_timesheet_data = []
    for row in chart_data:
        month_data = row["timesheet_data"]
        name_to_item = {}
        for item in month_data:
            name = item["task"]
            all_names.add(name)
            if type_returned == "cost_vs_lost":
                name_to_item[name] = item["cost_vs_lost"]
            else:
                name_to_item[name] = item["hours"]
        month_timesheet_data.append(name_to_item)

    # For each name, build a list of hours per month, filling 0 if missing
    timesheet_map = {name: [] for name in all_names}
    for name in all_names:
        for month_data in month_timesheet_data:
            value = month_data.get(name, "0")
            timesheet_map[name].append(value)

    data = {
        "title": title,
        "labels": labels,
        "isReverse": False,
        "showTotal": True,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "element_id": f"timesheet_data",
        "help": help,
        "total_cards": [],
        "type": "single",
        "datasets": []
    }

    timesheet_unit = "hours" if type_returned == "hours" else "rand"
    for name, values in timesheet_map.items():
        data["datasets"].append({
            "type": "bar",
            "name": name,
            "unit": timesheet_unit,
            "values": values
        })

    return data


@frappe.whitelist(allow_guest=True)
def submit_comment():

    # Accept args from frappe.call (GET or POST)
    data = frappe.local.form_dict or {}

    comment_text = data.get("comment")
    element_id = data.get("element_id")
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    user = frappe.session.user

    if not comment_text or not element_id or not start_date or not end_date:
        return {"success": False, "error": "Missing required fields: comment, element_id, start_date, end_date."}

    # Store comment in Communication doctype
    comm = frappe.get_doc({
        "doctype": "Dashboard Table Comments",
        "table_id": element_id,
        "start_date": start_date,
        "end_date": end_date,
        "comment": comment_text,
        "commented_by": user,
    })
    comm.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "success": True,
        "message": "Comment submitted successfully.",
        "commented_by": user,
        "comment": comment_text,
    }

@frappe.whitelist(allow_guest=True)
def get_comments_for_period(element_id, start_date, end_date):
    """
    Fetch comments for a dashboard table for the selected period using Dashboard Table Comments doctype.
    """
    print(element_id, start_date, end_date)
    filters = {
        "table_id": element_id,
        "start_date": ["=", start_date],
        "end_date": ["=", end_date],
    }
    comments = frappe.get_all(
        "Dashboard Table Comments",
        fields=["name","comment", "commented_by", "start_date", "end_date"],
        filters=filters,
        order_by="creation desc"
    )
    return {"comments": comments}

@frappe.whitelist(allow_guest=True)
def update_comment(comment_id, comment, element_id=None, start_date=None, end_date=None):
    """
    Update the comment text for a given comment ID in Dashboard Table Comments.
    """
    if not comment_id or not comment:
        return {"success": False, "error": "Missing required fields: comment_id, comment."}
    try:
        doc = frappe.get_doc("Dashboard Table Comments", comment_id)
        doc.comment = comment
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return {"success": True, "message": "Comment updated successfully."}
    except Exception as e:
        return {"success": False, "error": str(e)}

@frappe.whitelist(allow_guest=True)
def delete_comment(comment_id, element_id=None, start_date=None, end_date=None):
    """
    Delete a comment by its ID from Dashboard Table Comments.
    """
    if not comment_id:
        return {"success": False, "error": "Missing required field: comment_id."}
    try:
        frappe.delete_doc("Dashboard Table Comments", comment_id, ignore_permissions=True)
        frappe.db.commit()
        return {"success": True, "message": "Comment deleted successfully."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@frappe.whitelist(allow_guest=True)
def get_all_filters():
    """
    Fetch filters.
    """
    filters = frappe.get_all(
        "Kartoza Dashboard Settings",
        fields=["name", "filter_title"],
        order_by="creation desc"
    )

    charts = []
    for row in filters:
        selected_rows = frappe.get_all(
            "Kartoza Dashboard Settings Chart Selection",
            fields=["chart_type"],
            filters={
                "parent": row["name"],
                "parenttype": "Kartoza Dashboard Settings",
                "parentfield": "chart_selection",
            },
            order_by="idx asc"
        )

        charts.append({
            "name": row["name"],
            "filter_title": row["filter_title"],
            "chart_selection": [d.get("chart_type") for d in selected_rows if d.get("chart_type")],
        })

    return {"charts": charts}