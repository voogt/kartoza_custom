import frappe
from frappe import whitelist

@frappe.whitelist()
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

@frappe.whitelist()
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
    
    new_customer.insert()
    frappe.db.commit()
    
    return {'customer_name': new_customer.name}

@frappe.whitelist()
def get_moodle_course_settings(item):
    return frappe.get_list(
        'Moodle Course Settings',
        fields=['item', 'enrollment_key', 'course_link'],
        filters={'item': item, 'zero_rated': 1}
    )