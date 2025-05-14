import json
import frappe
from frappe import whitelist
from frappe import _
from frappe.utils.global_search import search as default_search
from frappe.utils import now_datetime
from frappe.model.naming import make_autoname


@frappe.whitelist(allow_guest=True)
def get_latest_quotation_items():
    # Fetch the latest Quotation for the current user (customer)
    user = frappe.session.user
    quotation = frappe.db.get_value('Quotation', 
                                    filters={'owner': user, 'docstatus': 0},  # Draft status (docstatus = 0)
                                    order_by='creation desc')  # Get the most recent Quotation

    if not quotation:
        frappe.throw(_("No active quotation found for the current user."))

    # Fetch the Quotation Items linked to this Quotation
    items = frappe.get_all('Quotation Item',
                           filters={'parent': quotation},
                           fields=['item_code', 'item_name', 'qty', 'rate'])

    return {'quotation': quotation, 'items': items}

import frappe

@frappe.whitelist(allow_guest=True)
def get_or_create_customer(recipient_name, recipient_email, contact_phone, tax_id):
    # Check if customer exists
    customer = frappe.db.get_value('Customer', {'customer_name': recipient_name}, 'name')

    if customer:
        return {'customer_name': customer}

    # If customer does not exist, create a new customer
    new_customer = frappe.get_doc({
        'doctype': 'Customer',
        'customer_name': recipient_name,
        'customer_type': 'Individual',  # Adjust as needed
        'customer_group': 'Individual', # Adjust as needed
        'territory': 'All Territories', # Adjust as needed
        'email_id': recipient_email,
        'mobile_no': contact_phone,
        'tax_id': tax_id,
        'tax_category': "VAT"
    })
    new_customer.flags.ignore_permissions = True
    new_customer.insert()
    frappe.db.commit()
    
    return {'customer_name': new_customer.name}

@frappe.whitelist(allow_guest=True)
def get_moodle_course_settings(item):
    return frappe.get_list(
        'Moodle Course Settings',
        fields=['item', 'enrollment_key', 'course_link'],
        filters={'item': item, 'zero_rated': 1}
    )

@frappe.whitelist(allow_guest=True)
def send_course_details_email(email, doc_details):
    try:
        # Parse doc_details if it's a JSON string
        if isinstance(doc_details, str):
            doc_details = json.loads(doc_details)
        
        subject = f"Details for {doc_details.get('item')}"
        message = f"""
            <p>Here are the details you requested:</p>
            <p>Course Enrollment key: {doc_details.get('enrollment_key')}</p>
            <p>Course Link: {doc_details.get('course_link')}</p>
            <p>Please access the course as a guest.</p>
        """

        # Send the email
        frappe.sendmail(
            recipients=email,
            subject=subject,
            message=message,
            sender="Kartoza <notifications@erpnext.com>",
            now=True
        )

        email_doc = frappe.get_doc({
            "doctype": "Moodle Course Email Requests",
            "course": doc_details.get('item'),
            "email": email,
            "email_sent": 1  
        })
        
        # Insert the document into the database
        email_doc.insert(ignore_permissions=True)  # Ignore permissions if running as admin
        
        # Commit the transaction
        frappe.db.commit()

        return {"status": "success", "message": _(f"""Email being sent to {email}. Please allow a few minutes for the email to reach your inbox. If it doesn't appear after a while, kindly check your spam folder or contact us for assistance.""")}
    
    except Exception as e:
        frappe.throw(_(f"Unable to send email. Please try again later. {e}"))


@frappe.whitelist()
def get_next_employee_number(company):
    print("COMPANY", company)
    company_abbr = "GEN"
    
    if company == "Kartoza Lda":
        company_abbr = "LDA"

    # Fetch the last assigned number safely
    latest_employee = frappe.db.sql("""
        SELECT name FROM `tabEmployee`
        WHERE naming_series LIKE %s
        ORDER BY name DESC
        LIMIT 1
    """, ('HR-EMP-%'), as_dict=True)

    if latest_employee:
        latest_number = int(latest_employee[0]['name'].split('-')[-1]) + 1
    else:
        latest_number = 1  # Start numbering from 1 if no previous record exists

    new_series = f'HR-EMP-{str(latest_number).zfill(5)}'
    print("NEW SERIES", new_series)
    
    # Double-check to prevent duplication
    if frappe.db.exists("Employee", new_series):
        frappe.throw(f"Duplicate Employee ID {new_series} detected. Please retry.")

    return new_series

def get_qpp_fields():
    meta = frappe.get_meta("Quality Procedure Process")
    return [f"{df.fieldname} ({df.fieldtype})" for df in meta.fields]


@frappe.whitelist()
def get_unacknowledged_procedure():
    user = frappe.session.user
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not employee:
        return []

    procedures = frappe.get_all(
        "Quality Procedure",
        filters={"custom_mandatory_to_acknowledge": 1, "custom_status": "Published"},
        fields=["name", "quality_procedure_name"],
        order_by="modified desc"
    )

    unacknowledged = []
    for procedure in procedures:
        exists = frappe.db.exists("User Procedure Acknowledgment", {
            "employee": employee,
            "quality_procedure": procedure["name"]
        })
        if not exists:
            doc = frappe.get_doc("Quality Procedure", procedure["name"])
            steps = [row.process_description for row in doc.processes if row.process_description]
            content_html = "<br>".join(steps)
            unacknowledged.append({
                "name": doc.name,
                "title": doc.quality_procedure_name,
                "content": content_html
            })

    return unacknowledged


# @frappe.whitelist()
# def get_unacknowledged_procedure():
#     user = frappe.session.user

#     employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
#     if not employee:
#         return None
#     # if "Employee" not in frappe.get_roles(user):
#     #     return None

#     procedures = frappe.get_all(
#         "Quality Procedure",
#         filters={"custom_mandatory_to_acknowledge": 1, "custom_status": "Published"},
#         order_by="modified desc",
#         limit=1,
#         fields=["name", "quality_procedure_name"]
#     )

#     if not procedures:
#         return None

#     procedure = procedures[0]

#     # Check if already acknowledged
#     exists = frappe.db.exists("User Procedure Acknowledgment", {
#         "employee": employee,
#         "quality_procedure": procedure["name"]
#     })

#     if exists:
#         return None

#     doc = frappe.get_doc("Quality Procedure", procedure["name"])

#     # Combine all step descriptions
#     steps = [row.process_description for row in doc.processes if row.process_description]

#     content_html = "<br>".join(steps)

#     return {
#         "name": doc.name,
#         "title": doc.quality_procedure_name,
#         "content": content_html
#     }

@frappe.whitelist()
def acknowledge_procedure(procedure):
    user = frappe.session.user

    print("PROCEDURE", procedure)

    if not procedure:
        frappe.throw(_("No procedure specified."))

    # Find employee linked to current user
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not employee:
        frappe.throw(_("No Employee record linked to this user."))

    # Check if the acknowledgment already exists
    exists = frappe.db.exists("User Procedure Acknowledgment", {
        "employee": employee,
        "quality_procedure": procedure
    })

    if exists:
        frappe.msgprint(_("You have already acknowledged this procedure."))
        return

    # Insert acknowledgment record
    frappe.get_doc({
        "doctype": "User Procedure Acknowledgment",
        "employee": employee,
        "quality_procedure": procedure,
        "accepted_on": now_datetime()
    }).insert(ignore_permissions=True)


def before_insert_customer(doc, method):
    website_user = frappe.session.user

    if website_user in ("Administrator", "Guest"):
        return

    user = frappe.get_doc("User", website_user)
    if user.user_type == "System User":
        return

    # Set customer_name to username
    doc.customer_name = user.full_name

    # Slugify full name
    base_name = user.full_name

    # Ensure unique name
    new_name = base_name
    i = 1
    while frappe.db.exists("Customer", new_name):
        new_name = f"{base_name}-{i}"
        i += 1

    # Change docname before saving
    doc.name = new_name