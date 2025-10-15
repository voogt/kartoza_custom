import frappe
from frappe.utils import today, add_days

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
