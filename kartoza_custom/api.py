import json
import frappe
from frappe import whitelist
from frappe import _
from frappe.utils.global_search import search as default_search
from frappe.utils import now_datetime, cint, escape_html
from frappe.model.naming import make_autoname
from frappe.core.doctype.communication.email import make
from frappe.utils.password import remove_encrypted_password, set_encrypted_password, update_password


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
        'name': recipient_name,
        'customer_type': 'Individual',  # Adjust as needed
        'customer_group': 'Individual', # Adjust as needed
        'territory': 'All Territories', # Adjust as needed
        'email_id': recipient_email,
        'mobile_no': contact_phone,
        'tax_id': tax_id,
        'tax_category': "VAT",
        "portal_users": [{"user": frappe.session.user}]
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

@frappe.whitelist()
def acknowledge_procedure(procedure):
    user = frappe.session.user

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

    customer_name = (doc.customer_name or "").strip()
    if not customer_name:
        customer_name = (user.full_name or "").strip()

    if not customer_name and website_user:
        customer_name = website_user.split("@", 1)[0]

    if not customer_name:
        customer_name = "Website Customer"

    doc.customer_name = customer_name

    base_name = customer_name
    new_name = base_name
    i = 1
    while frappe.db.exists("Customer", new_name):
        new_name = f"{base_name}-{i}"
        i += 1

    doc.name = new_name

@frappe.whitelist()
def send_expense_email(docname):
    doc = frappe.get_doc('Employee Expense Claim', docname)

    # Get users with the roles "Expense Approver" or "Expense Manager"
    users = frappe.get_all(
        'Has Role',
        filters={
            'role': ['in', ['Expense Approver', 'Expense Manager']],
            'parenttype': 'User'  
        },
        fields=['parent'],
        distinct=True
    )

    recipients = []
    for user in users:
        username = user.parent

        if username == "Administrator":
            continue  # Skip Administrator

        try:
            user_doc = frappe.get_doc('User', username)
            if user_doc.enabled and user_doc.email:
                recipients.append(user_doc.email)
        except frappe.DoesNotExistError:
            # Silently ignore missing users
            continue
        except Exception:
            # Catch any unexpected issues (e.g. invalid user format)
            continue

    if not recipients:
        return 'No valid recipients found with Expense Approver or Expense Manager role.'
    

    subject = f"{doc.employee_name} has submitted a new Expense Claim"
    message = f"""
        <p>{doc.employee_name} has submitted a new Expense Claim.</p>
        <p>Please review the Expense Claim at 
        <a href='https://erp.kartoza.com/app/employee-expense-claim/{doc.name}'>
        https://erp.kartoza.com/app/employee-expense-claim/{doc.name}</a></p>
    """

    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=message,
        reference_doctype="Employee Expense Claim",
        reference_name=doc.name
    )

    return 'sent'

def _get_or_create_customer_for_user(email: str) -> str:
    """Return the Customer name linked to this email, creating one if none exists."""
    if not email:
        return ""

    # 1. Portal User child table — most direct User → Customer link
    customer = frappe.db.get_value(
        "Portal User",
        {"user": email, "parenttype": "Customer"},
        "parent",
    )
    if customer and frappe.db.exists("Customer", customer):
        return customer

    # 2. Contact Email → Dynamic Link → Customer
    contact = frappe.db.get_value(
        "Contact Email",
        {"email_id": email, "parenttype": "Contact"},
        "parent",
    )
    if contact:
        customer = frappe.db.get_value(
            "Dynamic Link",
            {"parent": contact, "link_doctype": "Customer", "parenttype": "Contact"},
            "link_name",
        )
        if customer and frappe.db.exists("Customer", customer):
            return customer

    # 3. No customer found — create one from the User record
    user_rec = frappe.db.get_value("User", email, ["full_name"], as_dict=True)
    base_name = (user_rec.full_name if user_rec else None) or email.split("@")[0]

    unique_name, i = base_name, 1
    while frappe.db.exists("Customer", unique_name):
        unique_name = f"{base_name} {i}"
        i += 1

    new_customer = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": unique_name,
        "customer_type": "Individual",
        "customer_group": "Individual",
        "territory": "All Territories",
        "portal_users": [{"user": email}],
    })
    new_customer.flags.ignore_permissions = True
    new_customer.insert()

    return new_customer.name


@frappe.whitelist(allow_guest=True)
def create_support_ticket(subject: str, description: str, priority: str = "Medium", raised_by: str = "", attachments=None) -> dict:
    import base64 as _b64
    import os

    subject = (subject or "").strip()
    description = (description or "").strip()
    raised_by = (raised_by or "").strip()

    if not subject:
        frappe.throw(_("Subject is required."))
    if not description:
        frappe.throw(_("Description is required."))
    if priority not in ("Low", "Medium", "High"):
        priority = "Medium"

    customer = _get_or_create_customer_for_user(raised_by)

    issue = frappe.get_doc({
        "doctype": "Issue",
        "subject": escape_html(subject),
        "description": escape_html(description),
        "priority": priority,
        "raised_by": raised_by,
        "customer": customer,
        "via_customer_portal": 1,
    })
    issue.flags.ignore_permissions = True
    if raised_by and frappe.db.exists("User", raised_by):
        issue.owner = raised_by
    issue.insert()

    if attachments:
        if isinstance(attachments, str):
            attachments = json.loads(attachments)

        allowed_ext = {
            ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
            ".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv"
        }
        max_bytes = 10 * 1024 * 1024

        for att in (attachments or []):
            try:
                fname = (att.get("name") or "attachment").strip()
                ext = os.path.splitext(fname)[1].lower()
                if ext not in allowed_ext:
                    continue
                content = _b64.b64decode(att.get("content", ""))
                if len(content) > max_bytes:
                    continue
                from frappe.utils.file_manager import save_file
                save_file(fname=fname, content=content, dt="Issue", dn=issue.name, is_private=0)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "Support Ticket Attachment Error")

    frappe.db.commit()
    return {"name": issue.name}


@frappe.whitelist(allow_guest=True)
def sign_up(email: str, full_name: str, password: str) -> dict:

    user = frappe.db.get("User", {"email": email})
    if user:
        if user.enabled:
            return {"status": 0, "message": _("Already Registered")}
        else:
            return {"status": 0, "message": _("Registered but disabled")}
    else:
        max_signups_allowed_per_hour = cint(frappe.get_system_settings("max_signups_allowed_per_hour") or 300)
        users_created_past_hour = frappe.db.get_creation_count("User", 60)
        if users_created_past_hour >= max_signups_allowed_per_hour:
            frappe.respond_as_web_page(
                _("Temporarily Disabled"),
                _(
                    "Too many users signed up recently, so the registration is disabled. Please try back in an hour"
                ),
                http_status_code=429,
            )

        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": escape_html(full_name),
                "enabled": 1,
                "new_password": '',
                "user_type": "Website User",
            }
        )
        user.flags.ignore_permissions = True
        user.flags.ignore_password_policy = True
        user.flags.no_welcome_mail = True
        user.insert()

        # set default signup role as per Portal Settings
        default_role = frappe.get_single_value("Portal Settings", "default_role")
        if default_role:
            user.add_roles(default_role)

        update_password(user=user.name, pwd=password, logout_all_sessions=0)

        return {"status": 1, "message": _("Registration successful. Please log in to continue.")}
