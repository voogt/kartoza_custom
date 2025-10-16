import os
import frappe
from frappe.utils import today, add_days, nowdate, get_site_path
from frappe.utils.pdf import get_pdf

def check_passport_expiry():
    """
    Checks Employee passport expiry dates and sends an alert if passport is about to expire.
    """
    # Number of days before expiry to alert
    alert_days = 7
    alert_date = add_days(today(), alert_days)
    
    # Fetch employees with passport expiring within the alert_days
    employees = frappe.get_all(
        "Employee",
        filters={
            "valid_upto": [">=", today()],
            "valid_upto": ["<=", alert_date],
            "status": "Active"
        },
        fields=["name", "employee_name", "valid_upto"]
    )

    # Fallback filter in case the ORM does not handle None values as expected
    employees = [emp for emp in employees if emp.get("valid_upto")]
    
    if not employees:
        return  # Nothing to alert

    for emp in employees:
        #print(f"Employee {emp['employee_name']} (ID: {emp['name']}) has passport expiring on {emp['valid_upto']}")  # For logging purposes
        recipient = "suzanne@kartoza.com"
        message = f"""
        The passport of employee {emp.employee_name} (ID: {emp.name}) is expiring on {emp.valid_upto}.
        Please take necessary action.
        """
        frappe.sendmail(
            recipients=recipient,
            subject="Passport Expiry Alert",
            message=message
        )

def generate_cashflow_report_pdf():

    """
    Generate the Cashflow Forecast report and save it as a CSV file in the public/files/cashflow_reports folder with date in filename.
    """
    from frappe.utils.csvutils import to_csv

    report_name = "Cash Flow Forecast and Project Pipeline"  # Must match the report name exactly
    filters = {}  # Optional: specify filters if your report needs them

    print("Starting Cashflow Forecast report export...")

    try:
        # Get report data
        result_dict = frappe.get_attr("frappe.desk.query_report.run")(report_name, filters)
        columns = result_dict.get("columns")
        data = result_dict.get("result") or result_dict.get("data")

        # Prepare CSV rows
        header = [col.get('label', col.get('fieldname', '')) for col in columns]
        rows = [header]
        for row in data:
            rows.append([row.get(col.get('fieldname', ''), '') for col in columns])

        # Convert to CSV
        csv_data = to_csv(rows)

        # Save file
        today_str = nowdate()
        reports_dir = get_site_path("private", "files")
        os.makedirs(reports_dir, exist_ok=True)
        filename = f"cashflow_forecast_{today_str}.csv"
        filepath = os.path.join(reports_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(csv_data)

        print(f"Cashflow Forecast CSV saved: {filepath}")

        # Attach to Cashflow Forecast Snapshots doctype
        # Save file to File doctype and link to snapshot
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": filename,
            "attached_to_doctype": None,
            "attached_to_name": None,
            "is_private": 1,
            "file_url": f"/private/files/{filename}",
        })
        file_doc.save(ignore_permissions=True)

        snapshot = frappe.get_doc({
            "doctype": "Cashflow Forecast Snapshots",
            "file": file_doc.file_url,
            "created_on": today_str
        })
        snapshot.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        print(f"Error generating Cashflow Forecast CSV: {e}")

