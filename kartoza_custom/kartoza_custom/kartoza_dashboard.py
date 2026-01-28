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
from .dashboard_helpers import get_rates, get_month_ranges, get_month_label, getBacklogSalesOrders, get_billing_data, get_departments, compute_department_summary_all, get_salary_slips, get_timesheet_data, compute_department_summary, get_all_data, get_profit
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
                "values": opening_values
            },
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
    add = frappe.utils.add_to_date

    for start, end in ranges:
        print("START:", start)
        print("END:", end)
        b = False
        cur_date = start
        date_range = []
        while b == False:
            date_range.append(f"select '{cur_date}' as date")
            if cur_date == end:
                b = True
                break
            cur_date = add(cur_date, days=1)

        date_range = " union all ".join(date_range)
        #p(f"{date_range}") 
        sql = f"""
        SELECT
            wd.employee_name, 
            wd.name,
            -- totals
            wd.holiday_hours,
            wd.leave_hours,
            SUM(tsd.hours) as `timesheet_hours`,
            SUM(tsd.hours) + wd.holiday_hours + wd.leave_hours as `booked_hours`,
            wd.total_hours as `hours_pm`,
            wd.total_hours - wd.holiday_hours - wd.leave_hours as `total_hours`,
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

            SUM(CASE WHEN tp.project_type = 'Investment' THEN tsd.hours ELSE 0 END) as `investment_hours`,
            SUM(CASE WHEN tp.project_type = 'External' THEN tsd.hours ELSE 0 END) as `external_hours`,
            SUM(CASE WHEN tp.project_type = 'Internal' THEN tsd.hours ELSE 0 END) as `internal_hours`

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

        results = frappe.db.sql(sql, as_dict=True)

        booked_hours = 0
        total_hours = 0
        staff_total = 0

        for result in results:
            booked_hours += 0 if result.get("billable_hours") is None else result.get("billable_hours")
            total_hours += 0 if result.get("total_hours") is None else result.get("total_hours")
            staff_total += 1

        invoicable_hours_staff_median = total_hours / staff_total if staff_total else 0
        utilisation_percent = (booked_hours / total_hours) * 100 if total_hours else 0

        month_label = get_month_label(start)

        chart_data.append({
            "month": month_label,
            "invoicable_hours_staff_median": f"{invoicable_hours_staff_median:.0f}",
            "utilisation_percent": f"{utilisation_percent:.0f}"
        })

    # Transform chart_data for stacked chart
    labels = [row["month"] for row in chart_data]

    invoicable_hours_staff_median_values = [row["invoicable_hours_staff_median"] for row in chart_data]
    utilisation_percent_values = [row["utilisation_percent"] for row in chart_data]

    data = {
        "element_id": "utilisation",
        "isReverse": False,
        "showTotal": True,
        "shouldSplitLongLabels": False,
        "isLegendReverse": False,
        "type": "single",
        "title": "Utilisation",
        "total_cards": [],
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Shows staff utilisation per month:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Invoicable Hours Staff:</b> Median of total available hours per staff, considering working days, holidays, and approved leave.</li>
                <li><b>Utilisation %:</b> (Total booked(billable) hours / total available hours) × 100.</li>
                <li><b>Booked hours:</b> Includes timesheet, holiday, and leave hours.</li>
                <li>Only staff with <b>custom_utilization=1</b> are included.</li>
            </ul>
        </div>
        """,
        "labels": labels,
        "datasets": [
            {
                "type": "bar",
                "name": "Invoicable Hours Staff",
                "values": invoicable_hours_staff_median_values
            },
            {
                "type": "line",
                "name": "Utilisation %",
                "values": utilisation_percent_values
            },
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
    total_no_project_linked = 0
    total_invoicable_all_staff = 0
    total_uninvoicable_all_staff = 0

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
                        WHEN p.project_type IN ('External', 'Internal', 'Investment') AND tsd.is_billable = 1 
                        THEN tsd.hours
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

        invoicable_sql = f"""
            SELECT 
                SUM(
                    CASE 
                        WHEN is_billable = 1 THEN hours
                        ELSE 0
                    END
                ) AS `invoicable_all_staff`
            FROM `tabTimesheet Detail` tsd
            WHERE tsd.from_time >= '{start} 00:00:00'
            AND tsd.to_time <= '{end} 23:59:59' 
        """

        uninvoicable_sql = f"""
            SELECT 
                SUM(
                    CASE 
                        WHEN is_billable = 0 THEN hours
                        ELSE 0
                    END
                ) AS `uninvoicable_all_staff`
            FROM `tabTimesheet Detail` tsd
            WHERE tsd.from_time >= '{start} 00:00:00'
            AND tsd.to_time <= '{end} 23:59:59' 
        """

        invoicable_all_staff = frappe.db.sql(invoicable_sql, as_dict=True)[0]["invoicable_all_staff"]
        uninvoicable_all_staff = frappe.db.sql(uninvoicable_sql, as_dict=True)[0]["uninvoicable_all_staff"]
        total_invoicable_all_staff += invoicable_all_staff if invoicable_all_staff else 0
        total_uninvoicable_all_staff += uninvoicable_all_staff if uninvoicable_all_staff else 0

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
            "no_project_linked": f"{no_project_linked:.0f}",
            "external": f"{external:.0f}",
            "internal": f"{internal:.0f}",
            "investment": f"{investment:.0f}",
            "invoicable_all_staff": f"{invoicable_all_staff:.0f}"
        })

    # Transform chart_data for stacked chart
    labels = [row["month"] for row in chart_data]

    no_project_linked_values = [row["no_project_linked"] for row in chart_data]
    external_values = [row["external"] for row in chart_data]
    internal_values = [row["internal"] for row in chart_data]
    investment_values = [row["investment"] for row in chart_data]
    invoicable_all_staff_values = [row["invoicable_all_staff"] for row in chart_data]

    data = {
        "element_id": "billable_hours",
        "isReverse": False,
        "showTotal": True,
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
                <li><b>Invoicable All Staff:</b> All billable hours, regardless of project link.</li>
            </ul>
            <span style='color: #888;'>Totals are summed across the selected period.</span>
        </div>
        """,
        "total_cards": [
            {
                "title": "Billable Hours Total",
                "value": f"{total_invoicable_all_staff:.0f}"
            },
            {
                "title": "Unbillable Hours Total",
                "value": f"{total_uninvoicable_all_staff:.0f}"
            },
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
            },
            {
                "type": "bar",
                "name": "Invoicable All Staff",
                "values": invoicable_all_staff_values
            },
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
                "value": f"{total_projects_closed_value:.0f}"
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
            "values": values
        })

    return data


@frappe.whitelist(allow_guest=True)
def get_profit_cost_lost_revenue_data(start_date, end_date, type_center):
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
                })
            else:
                cost_center_array.append({
                    'cost_center': dict['cost_center'],
                    'profit_loss': "0",
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
        "title": f"{type_center} Center Lost Opportunity (Profit/Loss)",
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
            <b>Shows total salary costs per department for Kartoza Lda per month (Currency ZAR):</b><br><br>
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
                "values": total_amount_values
            },
            {
                "type": "bar",
                "name": "Probability(%)",
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
        AND top.company = 'Kartoza Lda'
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
        "title": "Pipeline Opportunity Kartoza Lda (Draft/Open)",
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
                "values": total_amount_values
            },
            {
                "type": "bar",
                "name": "Probability(%)",
                "values": total_probability_values
            },
            
        ],
        "help": """
        <div style='font-size: 14px;text-align: left'>
            <b>Displays open opportunities for Kartoza Lda (Currency ZAR):</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Amount:</b> Value of each open opportunity (Draft/Open status), grouped by opportunity name.</li>
            </ul>
            <span style='color: #888;'>Total is the sum of all open opportunities.</span>
        </div>
        """,
        "total_cards": [
            {
                "title": f"Total Opportunities Lda",
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
        AND tq.company = 'Kartoza Lda'
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
            "values": [f"{obj['amount']:.0f}"]
        })

    data = {
        "title": "Pipeline Quotation Kartoza Lda (Draft/Open)",
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
            <b>Displays open quotations for Kartoza Lda (Currency ZAR):</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Amount:</b> Value of each open quotation (Draft/Open status), converted to Rand if needed, grouped by quote name.</li>
            </ul>
            <span style='color: #888;'>Total is the sum of all open quotations.</span>
        </div>
        """,
        "total_cards": [
            {
                "title": f"Total Quotes Lda",
                "value": f"{total_quotes:.0f}"
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
            WHEN LOWER(tp.project_name) REGEXP '(^|[[:space:]])sla([[:space:]]|$)' THEN 'SLA'
            WHEN LOWER(tp.project_name) REGEXP '(^|[[:space:]])hosting([[:space:]]|$)' THEN 'HOSTING'
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
        LOWER(tp.project_name) REGEXP '(^|[[:space:]])sla([[:space:]]|$)'
        OR LOWER(tp.project_name) REGEXP '(^|[[:space:]])hosting([[:space:]]|$)'
    )
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

    total_billed_amount = 0
    total_billed_sales_orders = 0
    total_to_be_billed_all = 0

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
        risk_percentages = data_map['risk_percentages'].get(d['project'], 0)
        total_to_be_billed = ordered - billed

        total_billed_amount += billed
        total_billed_sales_orders += ordered
        total_to_be_billed_all += total_to_be_billed

        d['total_billed_amount'] = billed
        d['total_billed_sales_order'] = ordered
        d['total_to_be_billed'] = total_to_be_billed
        d["risk_percentage"] = risk_percentages

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
                <li><b>Risk:</b> Green represents low risk or good performance (0-40%), amber represents moderate risk (41-75%), and red represents high risk (76-100%).</li>
            </ul>
            <span style='color: #888;'>Totals are summed for the period.</span>
        </div>
        """,
        "total_cards": [
            {
                "title": f"Total To Be Billed",
                "value": f"{total_to_be_billed_all:.0f}"
            },
        ],
        "datasets": [
            {
                "type": "bar",
                "name": "Total Billed Amount",
                "values": total_billed_amount_values,
                "isColorCoded": False
            },
            {
                "type": "bar",
                "name": "Total Sales Order",
                "values": total_billed_sales_order_values,
                "isColorCoded": False
            },
            {
                "type": "bar",
                "name": "Total To Be Billed",
                "values": [f"{sale_order['total_to_be_billed']:.0f}" if sale_order.get('total_to_be_billed') else "0" for sale_order in all_sales_orders],
                "isColorCoded": False
            },
            {
                "type": "line",
                "name": "Risk",
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
        WHERE tso.company = 'Kartoza Lda'
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
        WHERE tso.company = 'Kartoza Lda'
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
            <b>Displays per item annual sales for Kartoza Lda:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Item Codes:</b> Each bar represents the total sales amount for an item code per month.</li>
                <li><b>Missing Items:</b> If an item code is present in one month but not in another, a value of 0 is shown for the missing month.</li>
                <li><b>Period:</b> Data is grouped and displayed for each month in the selected date range.</li>
                <li><b>Source:</b> Sales Invoice Items for Kartoza Lda, filtered by posting date and document status.</li>
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
        AND company = 'Kartoza Lda'
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
            <b>Displays customer payment analytics for Kartoza Lda:</b><br><br>
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
            "values": values
        })


    return data

@frappe.whitelist(allow_guest=True)
def get_overhead_cost_pty(start_date, end_date):
    ranges = get_month_ranges(start_date, end_date)
    chart_data = []

    for start, end in ranges:
        overhead_cost_salaries_sql = f"""
            SELECT 
                SUM(tss.total_cost) as `total_cost`
            FROM `tabSalary Slip` tss
            LEFT JOIN `tabEmployee` te ON te.name = tss.employee
            WHERE te.department IN ('PMO - K', 'PMO - KE', 'Admin - K', 'Admin - KE', 'Management - K', 'Management - KE')
            AND tss.posting_date BETWEEN '{start}' AND '{end}'
        """

        overhead_cost_insurance_sql = f"""
            SELECT 
                SUM(base_paid_amount) as `total_cost`
            FROM `tabPayment Entry` te
            LEFT JOIN `tabSupplier` ts ON ts.name = te.party
            WHERE payment_type = 'Pay'
            AND company = 'Kartoza (Pty) Ltd'
            AND ts.supplier_group = 'Insurance'
            AND posting_date BETWEEN '{start}' AND '{end}'
        """

        overhead_cost_supplier_sql = f"""
            SELECT 
                SUM(base_paid_amount) as `total_cost`
            FROM `tabPayment Entry` te
            LEFT JOIN `tabSupplier` ts ON ts.name = te.party
            WHERE payment_type = 'Pay'
            AND company = 'Kartoza (Pty) Ltd'
            AND ts.supplier_group NOT IN ('Insurance')
            AND posting_date BETWEEN '{start}' AND '{end}'
        """

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

        total_revenue =  get_profit(
		income, period_list, filters.company, filters.presentation_currency
	    )

        overhead_cost_salaries = frappe.db.sql(overhead_cost_salaries_sql, as_dict=True)[0].total_cost or 0
        overhead_cost_supplier = frappe.db.sql(overhead_cost_supplier_sql, as_dict=True)[0].total_cost or 0
        overhead_cost_insurance = frappe.db.sql(overhead_cost_insurance_sql, as_dict=True)[0].total_cost or 0
        overhead_variable_cost = overhead_cost_supplier
        overhead_fixed_cost = overhead_cost_salaries + overhead_cost_insurance
        overhead_cost = overhead_cost_salaries + overhead_cost_supplier + overhead_cost_insurance
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
                "values": overhead_fixed_cost_values
            },
            {
                "type": "bar",
                "name": "Overhead Variable Cost",
                "values": overhead_variable_cost_values
            },
            {
                "type": "bar",
                "name": "Total Revenue",
                "values": total_revenue_values
            },
            {
                "type": "Line",
                "name": "Overhead %",
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

        overhead_cost_insurance_sql = f"""
            SELECT 
                SUM(base_paid_amount) * {zar_eur_rate} as `total_cost`
            FROM `tabPayment Entry` te
            LEFT JOIN `tabSupplier` ts ON ts.name = te.party
            WHERE payment_type = 'Pay'
            AND company = 'Kartoza Lda'
            AND ts.supplier_group = 'Insurance'
            AND posting_date BETWEEN '{start}' AND '{end}'
        """

        overhead_cost_supplier_sql = f"""
            SELECT 
                SUM(base_paid_amount) * {zar_eur_rate} as `total_cost`
            FROM `tabPayment Entry` te
            LEFT JOIN `tabSupplier` ts ON ts.name = te.party
            WHERE payment_type = 'Pay'
            AND company = 'Kartoza Lda'
            AND ts.supplier_group NOT IN ('Insurance')
            AND posting_date BETWEEN '{start}' AND '{end}'
        """

        filters = frappe._dict({
            "company": "Kartoza Lda",
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
            company="Kartoza Lda",
	    )


        income = get_data(
            "Kartoza Lda",
            "Income",
            "Credit",
            period_list,
            filters=filters,
            accumulated_values=filters.accumulated_values,
            ignore_closing_entries=True,
        )

        total_revenue =  get_profit(
		income, period_list, filters.company, filters.presentation_currency
	    )

        if total_revenue is None or total_revenue == "":
            total_revenue = 0.0
        total_revenue = total_revenue * zar_eur_rate

        overhead_cost_salaries = 260000
        overhead_cost_supplier = frappe.db.sql(overhead_cost_supplier_sql, as_dict=True)[0].total_cost or 0
        overhead_cost_insurance = frappe.db.sql(overhead_cost_insurance_sql, as_dict=True)[0].total_cost or 0
        overhead_variable_cost = overhead_cost_supplier
        overhead_fixed_cost = overhead_cost_salaries + overhead_cost_insurance
        overhead_cost = overhead_cost_salaries + overhead_cost_supplier + overhead_cost_insurance
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
            <b>Displays overhead costs for Kartoza Lda per month:</b><br><br>
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
                "values": overhead_fixed_cost_values
            },
            {
                "type": "bar",
                "name": "Overhead Variable Cost",
                "values": overhead_variable_cost_values
            },
            {
                "type": "bar",
                "name": "Total Revenue",
                "values": total_revenue_values
            },
            {
                "type": "Line",
                "name": "Overhead %",
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
        period_dict = {item["project_name"]: item["gross_margin"] for item in period_data}
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
                <li><b>Project Names:</b> Each bar represents the total gross margin for a project that is closed during the period.</li>
                <li><b>Missing Projects:</b> If a project is present in one month but not in another, a value of 0 is shown for the missing month.</li>
                <li><b>Period:</b> Data is grouped and displayed for each month in the selected date range.</li>
                <li><b>Source:</b> Closed projects with their gross margins, converted to ZAR if needed, filtered by actual end date.</li>
        </div>
        """,
        "total_cards": [],
        "datasets": []
    }

    for name, values in item_map.items():
        data["datasets"].append({
            "type": "bar",
            "name": name,
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
                    WHEN company = 'Kartoza Lda' THEN
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
                    WHEN company = 'Kartoza Lda' THEN
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
            "lost_opportunities_count": f"{(lost_opportunities[0]['count_lost'] or 0):.0f}",
            "lost_opportunities_amount": f"{(lost_opportunities[0]['amount'] or 0):.0f}",
            "lost_quotes_count": f"{(lost_quotes[0]['count_lost'] or 0):.0f}",
            "lost_quotes_amount": f"{(lost_quotes[0]['amount'] or 0):.0f}",
            "won_opportunities_count": f"{(won_opportunities[0]['count_lost'] or 0):.0f}",
            "won_opportunities_amount": f"{(won_opportunities[0]['amount'] or 0):.0f}",
            "won_quotes_count": f"{(won_quotes[0]['count_lost'] or 0):.0f}",
            "won_quotes_amount": f"{(won_quotes[0]['amount'] or 0):.0f}",
            "total_hours": f"{(time_arr[0]['total_hours'] or 0):.0f}",
            "total_costing": f"{(time_arr[0]['total_costing'] or 0):.0f}",
        })

    # Transform chart_data for stacked chart
    labels = [row["month"] for row in chart_data]

    lost_opportunities_values = [row["lost_opportunities_count"] for row in chart_data]
    lost_opportunities_amounts = [row["lost_opportunities_amount"] for row in chart_data]
    lost_quotes_values = [row["lost_quotes_count"] for row in chart_data]
    lost_quotes_amounts = [row["lost_quotes_amount"] for row in chart_data]
    won_opportunities_values = [row["won_opportunities_count"] for row in chart_data]
    won_opportunities_amounts = [row["won_opportunities_amount"] for row in chart_data]
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
                <li><b>Lost Opportunities Count/Amount:</b> Number and total value of opportunities marked as 'Lost' (converted to ZAR if needed).</li>
                <li><b>Lost Quotes Count/Amount:</b> Number and total value of quotations marked as 'Lost' (converted to ZAR if needed).</li>
                <li><b>Won Opportunities Count/Amount:</b> Number and total value of opportunities marked as 'Converted' (converted to ZAR if needed).</li>
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
                "name": "Lost Opportunities Count",
                "values": lost_opportunities_values
            },
            {
                "type": "bar",
                "name": "Lost Opportunities Amount",
                "values": lost_opportunities_amounts
            },
            {
                "type": "bar",
                "name": "Lost Quotes Count",
                "values": lost_quotes_values
            },
            {
                "type": "bar",
                "name": "Lost Quotes Amount",
                "values": lost_quotes_amounts
            },
            {
                "type": "bar",
                "name": "Won Opportunities Count",
                "values": won_opportunities_values
            },
            {
                "type": "bar",
                "name": "Won Opportunities Amount",
                "values": won_opportunities_amounts
            },
            {
                "type": "bar",
                "name": "Won Quotes Count",
                "values": won_quotes_values
            },
            {
                "type": "bar",
                "name": "Won Quotes Amount",
                "values": won_quotes_amounts
            },
            {
                "type": "bar",
                "name": "Total Tender Hours",
                "values": total_hours_values
            },
            {
                "type": "bar",
                "name": "Total Tender Costing",
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
                "values": opp_count_values
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
    else:
        title = "Timesheet Data for Project 'Kartoza Sales' (Cost vs Lost)"

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
        "help": f"""
        <div style='font-size: 14px;text-align: left'>
            <b>Shows monthly timesheet variance for the 'Kartoza Sales' project grouped by task and activity:</b><br><br>
            <ul style='margin-left: 1em;'>
                <li><b>Scope:</b> Includes timesheet entries where project = 'Kartoza Sales' within the selected date range.</li>
                <li><b>Series:</b> Each series the description of the task</li>
                <li><b>Hours:</b> Total hours per series are included in the table for context (to two decimals).</li>
            </ul>
            <span style='color: #888;'>Data is grouped by month across the selected period.</span>
        </div>
        """,
        "total_cards": [],
        "type": "single",
        "datasets": []
    }

    for name, values in timesheet_map.items():
        data["datasets"].append({
            "type": "bar",
            "name": name,
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
