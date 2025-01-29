import json
import frappe
from frappe import whitelist
from frappe import _
from frappe.utils.global_search import search as default_search


def custom_global_search(search_text, start=0, limit=10):
    # Get default global search results
    print(f"FIRED OFF")
    results = default_search(search_text, start, limit)

    # Query Website Items
    website_items = frappe.db.sql(
        """
        SELECT
            name AS value, item_name AS label, description AS description
        FROM
            `tabWebsite Item`
        WHERE
            item_name LIKE %(query)s
            OR description LIKE %(query)s
        LIMIT %(limit)s OFFSET %(start)s
        """,
        {"query": f"%{search_text}%", "start": start, "limit": limit},
        as_dict=True,
    )

    # Append Website Items to the results
    results.extend(
        [{
            "title": item["label"],
            "route": f"/{item['value']}",
            "content": item["description"],
        } for item in website_items]
    )

    return results

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