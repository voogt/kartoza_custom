import json
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import frappe
from frappe import whitelist
from frappe import _
from frappe.utils.global_search import search as default_search
from frappe.utils import now_datetime, cint, sbool, escape_html
from frappe.model.naming import make_autoname
from frappe.core.doctype.communication.email import make
from frappe.rate_limiter import rate_limit
from frappe.utils.password import (
    check_password,
    get_password_reset_limit,
    remove_encrypted_password,
    set_encrypted_password,
    update_password as set_user_password,
)
from webshop.webshop.variant_selector.item_variants_cache import ItemVariantsCacheManager


def _build_frontend_password_reset_link(reset_link: str) -> str:
    # Derive the frontend origin from the incoming request's Origin header,
    # falling back to Referer, then the legacy site_config setting.
    origin = None
    request = getattr(frappe.local, "request", None)
    if request:
        raw = request.headers.get("Origin") or request.headers.get("Referer") or ""
        if raw:
            parsed = urlparse(raw)
            if parsed.scheme and parsed.netloc:
                origin = f"{parsed.scheme}://{parsed.netloc}"

    if not origin:
        fallback = (frappe.conf.get("password_reset_frontend_url") or "").strip()
        if fallback:
            parsed = urlparse(fallback)
            origin = f"{parsed.scheme}://{parsed.netloc}"

    if not origin:
        frappe.throw(
            _("Unable to determine the password reset URL."),
            title=_("Configuration Error"),
        )

    reset_query = parse_qs(urlparse(reset_link).query)
    key = (reset_query.get("key") or [""])[0]
    if not key:
        frappe.throw(_("Unable to generate a valid password reset link."))

    return f"{origin}/reset-password/?key={key}"


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=get_password_reset_limit, seconds=60 * 60)
def request_password_reset(email: str) -> str:
    email = (email or "").strip().lower()
    if not email:
        frappe.throw(_("Email is required."))

    response = _("If an account exists for this email address, a password reset link has been sent.")

    try:
        user = frappe.get_doc("User", email)
    except frappe.DoesNotExistError:
        frappe.clear_messages()
        return response

    if user.name == "Administrator" or not user.enabled:
        return response

    user.validate_reset_password()
    reset_link = user._reset_password(send_email=False)
    frontend_link = _build_frontend_password_reset_link(reset_link)
    user.password_reset_mail(frontend_link)

    return response


@frappe.whitelist(allow_guest=True, methods=["POST"])
def confirm_password_reset(key: str, new_password: str) -> dict:
    """Validate a password-reset key and set the new password.

    Called from the /reset-password/ frontend page after the user clicks the
    emailed link and submits the new-password form.
    """
    from datetime import timedelta
    from frappe.utils import get_datetime, now_datetime
    from frappe.utils.data import sha256_hash

    key = (key or "").strip()
    if not key:
        frappe.throw(_("Invalid reset link."))
    if not new_password or len(new_password) < 8:
        frappe.throw(_("Password must be at least 8 characters long."))

    # Frappe stores the SHA-256 hash of the key, not the raw key
    hashed_key = sha256_hash(key)
    user_name = frappe.db.get_value("User", {"reset_password_key": hashed_key}, "name")
    if not user_name:
        frappe.throw(_("This reset link is invalid or has already been used."))

    generated_on = frappe.db.get_value("User", user_name, "last_reset_password_key_generated_on")
    if generated_on:
        expiry = get_datetime(generated_on) + timedelta(hours=24)
        if now_datetime() > expiry:
            frappe.throw(_("This reset link has expired. Please request a new one."))

    set_user_password(user=user_name, pwd=new_password, logout_all_sessions=0)

    # Invalidate the key so it cannot be reused
    frappe.db.set_value("User", user_name, "reset_password_key", "")
    frappe.db.commit()

    return _("Password updated successfully. You can now sign in with your new password.")


# Role granted to every website/portal sign-up (see sign_up below, which reads
# Portal Settings.default_role). Scoping the two_factor_auth flag to this role
# - rather than the "All" role - keeps internal System Manager/desk logins
# unaffected by the website's emailed verification-code requirement.
WEBSITE_LOGIN_ROLE = "Customer"


@frappe.whitelist(methods=["POST"])
def set_two_factor_auth_enabled(enabled=True) -> dict:
    """Turn Frappe's emailed two-factor login code on or off for website users.

    Restricted to System Manager. Intended to be called once at container
    startup by the kartoza-website deployment (see deployment/docker/entrypoint.sh),
    driven by that environment's ENABLE_2FA setting, so each deployment
    environment (prod/dev) controls enforcement without a manual System
    Settings change.
    """
    frappe.only_for("System Manager")
    enabled = 1 if sbool(enabled) else 0

    frappe.db.set_single_value(
        "System Settings",
        {
            "enable_two_factor_auth": enabled,
            "two_factor_method": "Email",
            "otp_issuer_name": "Kartoza",
        },
    )
    frappe.db.set_value("Role", WEBSITE_LOGIN_ROLE, "two_factor_auth", enabled)

    return {"enable_two_factor_auth": enabled}


@frappe.whitelist(methods=['POST'])
def change_email(new_email, current_password):
    """Change the current user's email address.

    Email is the primary key (name) of the Frappe User doctype, so this uses
    rename_doc to cascade updates to all Link fields. Data fields (contact_email
    on open quotations, Contact Email records) are updated manually.
    The session is invalidated afterwards so the user must log in with the new address.
    """
    import re

    user = frappe.session.user
    if user == 'Guest':
        frappe.throw(_("Please login to change your email."), frappe.PermissionError)

    new_email = (new_email or '').strip().lower()
    if not new_email:
        frappe.throw(_("New email address is required."))

    if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', new_email):
        frappe.throw(_("Please enter a valid email address."))

    if new_email == user.lower():
        frappe.throw(_("The new email address is the same as your current one."))

    # Verify identity before making any changes
    try:
        check_password(user, current_password)
    except frappe.AuthenticationError:
        frappe.throw(_("Incorrect password. Please try again."), frappe.AuthenticationError)

    if frappe.db.exists('User', new_email):
        frappe.throw(_("An account with this email address already exists."))

    # Rename the User document — Frappe cascades this to all Link-type fields
    frappe.rename_doc('User', user, new_email, force=True, ignore_permissions=True)

    # Update Data fields that rename_doc does not cascade
    # 1. Open Shopping Cart quotations (contact_email is a plain Data field)
    frappe.db.sql(
        "UPDATE `tabQuotation` SET contact_email = %s WHERE contact_email = %s",
        (new_email, user),
    )
    # 2. Contact Email child table
    frappe.db.sql(
        "UPDATE `tabContact Email` SET email_id = %s WHERE email_id = %s",
        (new_email, user),
    )
    # 3. Sales Orders (contact_email Data field)
    frappe.db.sql(
        "UPDATE `tabSales Order` SET contact_email = %s WHERE contact_email = %s",
        (new_email, user),
    )

    frappe.db.commit()

    # Invalidate the current session — user must log in with the new email
    frappe.local.login_manager.logout()

    return {'new_email': new_email}


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


@frappe.whitelist()
def get_cart_items():
    """Return the current user's active cart with full pricing details.

    Uses the same quotation lookup as the ERPNext Webshop (contact_email +
    order_type = 'Shopping Cart') so the data is always consistent with what
    update_cart / _get_cart_quotation operate on.
    """
    user = frappe.session.user
    if user == 'Guest':
        frappe.throw(_("Please login to view your cart."), frappe.PermissionError)

    # Mirror webshop's _get_cart_quotation filter so we always see the same record.
    quotation_list = frappe.get_all(
        'Quotation',
        fields=['name'],
        filters={
            'contact_email': user,
            'order_type': 'Shopping Cart',
            'docstatus': 0,
        },
        order_by='modified desc',
        limit_page_length=1,
    )

    if not quotation_list:
        return {'items': [], 'total': 0, 'tax_amount': 0, 'grand_total': 0, 'currency': 'USD'}

    quotation = frappe.get_doc('Quotation', quotation_list[0].name)

    items = [
        {
            'item_code': item.item_code,
            'item_name': item.item_name,
            'qty': item.qty,
            'rate': item.rate,
            'amount': item.amount,
        }
        for item in quotation.items
    ]

    return {
        'quotation': quotation.name,
        'items': items,
        'total': quotation.total,
        'tax_amount': quotation.total_taxes_and_charges or 0,
        'grand_total': quotation.grand_total,
        'currency': quotation.currency or 'USD',
    }


@frappe.whitelist()
def remove_from_cart(item_code):
    """Remove a single item from the active cart quotation.

    Uses the same quotation lookup as get_cart_items. When the removed item is
    the last one the quotation is deleted rather than saved, avoiding the
    AttributeError in webshop's update_cart (quotation.name on None).
    """
    user = frappe.session.user
    if user == 'Guest':
        frappe.throw(_("Please login to modify your cart."), frappe.PermissionError)

    quotation_list = frappe.get_all(
        'Quotation',
        fields=['name'],
        filters={
            'contact_email': user,
            'order_type': 'Shopping Cart',
            'docstatus': 0,
        },
        order_by='modified desc',
        limit_page_length=1,
    )

    if not quotation_list:
        return {'success': True, 'empty': True}

    quotation = frappe.get_doc('Quotation', quotation_list[0].name)
    remaining = [item for item in quotation.items if item.item_code != item_code]

    if not remaining:
        quotation.flags.ignore_permissions = True
        quotation.delete()
        return {'success': True, 'empty': True}

    quotation.items = remaining
    quotation.flags.ignore_permissions = True
    quotation.payment_schedule = []
    quotation.save()
    return {'success': True, 'empty': False}


@frappe.whitelist()
def get_checkout_config():
    """Return cart totals, Paystack public key, customer info, and billing addresses for the checkout page."""
    from frappe.contacts.doctype.address.address import get_address_display
    from webshop.webshop.shopping_cart.cart import get_party

    user = frappe.session.user
    if user == 'Guest':
        frappe.throw(_("Please login to proceed to checkout."), frappe.PermissionError)

    # Ensure the user has a linked Customer (creates one via webshop logic if absent).
    party = get_party()
    if not party:
        frappe.throw(_("Could not set up your customer profile. Please contact support."))

    cart = get_cart_items()
    if not cart.get('items'):
        frappe.throw(_("Your cart is empty."))

    company = frappe.db.get_single_value('Webshop Settings', 'company')
    from frappe_paystack.utils import resolve_paystack_settings
    settings = resolve_paystack_settings(company)
    if not settings:
        frappe.throw(_("Payment gateway is not configured. Please contact support."))

    user_doc = frappe.get_doc('User', user)

    # Fetch existing billing addresses linked to this customer.
    billing_addresses = []
    addr_links = frappe.get_all(
        'Dynamic Link',
        filters={'link_doctype': party.doctype, 'link_name': party.name, 'parenttype': 'Address'},
        fields=['parent'],
    )
    if addr_links:
        address_names = [a.parent for a in addr_links]
        addrs = frappe.get_all(
            'Address',
            filters={'name': ['in', address_names], 'address_type': 'Billing'},
            fields=['name', 'address_title', 'address_line1', 'address_line2',
                    'city', 'state', 'pincode', 'country'],
        )
        for addr in addrs:
            addr_doc = frappe.get_doc('Address', addr['name'])
            addr['display'] = get_address_display(addr_doc.as_dict())
            billing_addresses.append(addr)

    # Check if the open quotation already has an address set.
    selected_address = None
    if cart.get('quotation'):
        selected_address = frappe.db.get_value('Quotation', cart['quotation'], 'customer_address') or None

    return {
        'items': cart['items'],
        'total': cart['total'],
        'tax_amount': cart['tax_amount'],
        'grand_total': cart['grand_total'],
        'currency': cart['currency'],
        'paystack_public_key': settings['public_key'],
        'customer_email': user,
        'customer_name': user_doc.full_name or user_doc.first_name or user,
        'billing_addresses': billing_addresses,
        'selected_address': selected_address,
    }


@frappe.whitelist(methods=['POST'])
def save_billing_address(address_line1, city, country,
                         address_line2='', state='', pincode='',
                         address_name=None):
    """Create or update a billing Address and link it to the user's open cart quotation.

    If `address_name` is provided, the existing Address is updated in place and re-linked.
    Otherwise a new Address is created and linked.
    In both cases the quotation's customer_address field is set so ERPNext is consistent.
    """
    from frappe.contacts.doctype.address.address import get_address_display
    from webshop.webshop.shopping_cart.cart import _get_cart_quotation, get_party

    user = frappe.session.user
    if user == 'Guest':
        frappe.throw(_("Please login to save an address."), frappe.PermissionError)

    address_line1 = (address_line1 or '').strip()
    city = (city or '').strip()
    country = (country or '').strip()
    if not address_line1 or not city or not country:
        frappe.throw(_("Address Line 1, City, and Country are required."))

    party = get_party()
    if not party:
        frappe.throw(_("Could not find your customer profile. Please contact support."))

    address_name = (address_name or '').strip() or None

    if address_name and frappe.db.exists('Address', address_name):
        address = frappe.get_doc('Address', address_name)
        address.address_line1 = address_line1
        address.address_line2 = address_line2 or ''
        address.city = city
        address.state = state or ''
        address.pincode = pincode or ''
        address.country = country
        # Ensure the Customer link exists on the address
        linked = any(
            lnk.link_doctype == party.doctype and lnk.link_name == party.name
            for lnk in address.get('links', [])
        )
        if not linked:
            address.append('links', {'link_doctype': party.doctype, 'link_name': party.name})
        address.flags.ignore_permissions = True
        address.save()
    else:
        address = frappe.get_doc({
            'doctype': 'Address',
            'address_title': getattr(party, 'customer_name', None) or party.name,
            'address_type': 'Billing',
            'address_line1': address_line1,
            'address_line2': address_line2 or '',
            'city': city,
            'state': state or '',
            'pincode': pincode or '',
            'country': country,
            'links': [{'link_doctype': party.doctype, 'link_name': party.name}],
        })
        address.flags.ignore_permissions = True
        address.insert()

    address_doc = frappe.get_doc('Address', address.name)
    address_display = get_address_display(address_doc.as_dict())

    # Attach address to the open cart quotation
    quotation = _get_cart_quotation(party=party)
    quotation.customer_address = address.name
    quotation.address_display = address_display
    if not quotation.shipping_address_name:
        quotation.shipping_address_name = address.name

    # Apply 15% VAT for South African billing addresses; clear taxes for all others.
    SA_TAX_TEMPLATE = 'South Africa Tax - K'
    quotation.taxes = []
    if country == 'South Africa':
        if frappe.db.exists('Sales Taxes and Charges Template', SA_TAX_TEMPLATE):
            tax_template = frappe.get_doc('Sales Taxes and Charges Template', SA_TAX_TEMPLATE)
            for tax_row in tax_template.taxes:
                quotation.append('taxes', {
                    'charge_type': tax_row.charge_type,
                    'account_head': tax_row.account_head,
                    'rate': tax_row.rate,
                    'description': tax_row.description or '',
                    'cost_center': tax_row.cost_center or '',
                })
            quotation.taxes_and_charges = SA_TAX_TEMPLATE
        else:
            quotation.taxes_and_charges = ''
    else:
        quotation.taxes_and_charges = ''

    quotation.flags.ignore_permissions = True
    quotation.payment_schedule = []
    quotation.run_method('calculate_taxes_and_totals')
    quotation.save()
    frappe.db.commit()

    return {
        'address_name': address.name,
        'address_display': address_display,
        'total': quotation.total,
        'tax_amount': quotation.total_taxes_and_charges or 0,
        'grand_total': quotation.grand_total,
        'currency': quotation.currency or 'ZAR',
    }


@frappe.whitelist(methods=['POST'])
def initialize_paystack_payment(callback_url):
    """Initialize a Paystack transaction server-side and return the authorization URL.

    Using the redirect flow avoids loading any third-party scripts in the browser,
    which are frequently blocked by ad-blockers and privacy extensions.
    """
    import requests as _requests

    user = frappe.session.user
    if user == 'Guest':
        frappe.throw(_("Please login to proceed to checkout."), frappe.PermissionError)

    cart = get_cart_items()
    if not cart.get('items'):
        frappe.throw(_("Your cart is empty."))

    company = frappe.db.get_single_value('Webshop Settings', 'company')
    from frappe_paystack.utils import resolve_paystack_settings
    settings = resolve_paystack_settings(company)
    if not settings:
        frappe.throw(_("Payment gateway not configured. Please contact support."))

    user_doc = frappe.get_doc('User', user)
    amount_minor = int(round(cart['grand_total'] * 100))

    resp = _requests.post(
        'https://api.paystack.co/transaction/initialize',
        headers={
            'Authorization': f'Bearer {settings["secret_key"]}',
            'Content-Type': 'application/json',
        },
        json={
            'email': user,
            'amount': amount_minor,
            'currency': cart['currency'] or 'ZAR',
            'callback_url': callback_url,
            'metadata': {
                'customer': user_doc.full_name or user,
                'email': user,
            },
        },
        timeout=30,
    )

    if not resp.ok:
        frappe.throw(_("Could not connect to payment gateway. Please try again."))

    data = resp.json()
    if not data.get('status'):
        frappe.throw(_(data.get('message') or 'Payment initialization failed.'))

    return {
        'authorization_url': data['data']['authorization_url'],
        'reference': data['data']['reference'],
        'access_code': data['data']['access_code'],
    }


def _enrol_user_in_moodle_courses(user, sales_order_name, first_name, last_name):
    """Core Moodle enrollment: register/enrol `user` in all auto-enroll items of the Sales Order.

    `first_name` and `last_name` are supplied by the caller so the user can confirm
    or correct them via the registration form before submitting.
    """
    from frappe_paystack.utils import register_user_and_enrol

    sales_order_doc = frappe.get_doc('Sales Order', sales_order_name)

    courses = []
    for item in sales_order_doc.items:
        item_data = frappe.get_doc('Item', item.item_code)
        if item_data.get('custom_auto_enroll_in_moodle') == 1:
            course_id = item_data.get('custom_moodle_course_id')
            token = item_data.get('custom_moodle_web_token')
            if course_id and token:
                courses.append({
                    'course_id': course_id,
                    'token': token,
                    'item_name': item.item_name,
                })

    if not courses:
        return {'all_successful': True, 'courses': []}

    # Reuse an existing log for this Sales Order if one was already created.
    existing_log = frappe.db.get_value('Moodle Enrollment Logs', {'sales_order': sales_order_name}, 'name')
    if existing_log:
        log = frappe.get_doc('Moodle Enrollment Logs', existing_log)
    else:
        log = frappe.get_doc({'doctype': 'Moodle Enrollment Logs', 'sales_order': sales_order_name})
        log.insert(ignore_permissions=True)

    moodle_url = 'https://training.kartoza.com'
    results = []
    all_ok = True

    for course in courses:
        response = register_user_and_enrol(
            moodle_url,
            course['token'],
            user,
            first_name,
            last_name,
            course['course_id'],
        )

        success = response.get('enrollment_succesful', False)
        if not success:
            all_ok = False
            print(f"Moodle registration failed for {user} in course {course['course_id']}: {response}", flush=True)

        log.append('table_details', {
            'name1': f"{first_name} {last_name}".strip(),
            'email': user,
            'course_id': course['course_id'],
            'enrollment_succesful': success,
        })
        results.append({
            'item_name': course['item_name'],
            'course_id': course['course_id'],
            'enrolled': success,
        })

    log.save(ignore_permissions=True)
    frappe.db.commit()

    return {'all_successful': all_ok, 'courses': results}


@frappe.whitelist(methods=['POST'])
def enrol_in_moodle(sales_order, enrollees):
    """Enrol one or more people in Moodle courses for a completed Sales Order.

    `enrollees` is a list of dicts, one per seat:
        [{"item_code": "...", "first_name": "...", "last_name": "...", "email": "..."}, ...]

    Each entry may repeat the same item_code when qty > 1 (multiple places for one course).
    Verifies the Sales Order belongs to the session user before enrolling.
    """
    from frappe_paystack.utils import register_user_and_enrol

    user = frappe.session.user
    if user == 'Guest':
        frappe.throw(_("Please login to enrol."), frappe.PermissionError)

    if isinstance(enrollees, str):
        enrollees = json.loads(enrollees)

    contact_email = frappe.db.get_value('Sales Order', sales_order, 'contact_email')
    if contact_email != user:
        frappe.throw(_("You do not have permission to enrol for this order."), frappe.PermissionError)

    existing_log = frappe.db.get_value('Moodle Enrollment Logs', {'sales_order': sales_order}, 'name')
    if existing_log:
        log = frappe.get_doc('Moodle Enrollment Logs', existing_log)
    else:
        log = frappe.get_doc({'doctype': 'Moodle Enrollment Logs', 'sales_order': sales_order})
        log.insert(ignore_permissions=True)

    moodle_url = 'https://training.kartoza.com'
    all_ok = True
    results = []

    for enrollee in enrollees:
        item_code = (enrollee.get('item_code') or '').strip()
        first_name = (enrollee.get('first_name') or '').strip()
        last_name = (enrollee.get('last_name') or '').strip()
        email = (enrollee.get('email') or '').strip()

        if not first_name or not email:
            all_ok = False
            results.append({'item_code': item_code, 'email': email, 'enrolled': False, 'error': 'Missing required fields'})
            continue

        try:
            item_data = frappe.get_doc('Item', item_code)
            course_id = item_data.get('custom_moodle_course_id')
            token = item_data.get('custom_moodle_web_token')
            item_name = item_data.item_name

            if not course_id or not token:
                all_ok = False
                results.append({'item_code': item_code, 'email': email, 'enrolled': False, 'error': 'Moodle course not configured'})
                continue

            response = register_user_and_enrol(moodle_url, token, email, first_name, last_name, course_id)
            success = response.get('enrollment_succesful', False)
            if not success:
                all_ok = False
                print(f"Moodle registration failed for {email} in course {course_id}: {response}", flush=True)

            log.append('table_details', {
                'name1': f"{first_name} {last_name}".strip(),
                'email': email,
                'course_id': course_id,
                'enrollment_succesful': success,
            })
            results.append({'item_code': item_code, 'item_name': item_name,
                            'first_name': first_name, 'last_name': last_name,
                            'email': email, 'enrolled': success,
                            'course_id': course_id})

        except Exception as e:
            all_ok = False
            frappe.log_error(str(e), f'enrol_in_moodle: failed for {email} in {item_code}')
            results.append({'item_code': item_code, 'email': email, 'enrolled': False, 'error': str(e)})

    log.save(ignore_permissions=True)
    frappe.db.commit()

    return {'all_successful': all_ok, 'results': results}


@frappe.whitelist(methods=['POST'])
def complete_checkout(paystack_reference, currency=None):
    """Verify Paystack payment, convert cart quotation to Sales Order, log the payment."""
    import requests as _requests

    user = frappe.session.user
    if user == 'Guest':
        frappe.throw(_("Please login to complete checkout."), frappe.PermissionError)

    company = frappe.db.get_single_value('Webshop Settings', 'company')
    from frappe_paystack.utils import resolve_paystack_settings
    settings = resolve_paystack_settings(company)
    if not settings:
        frappe.throw(_("Payment gateway not configured."))

    # Verify the payment with Paystack before touching any orders
    verify_url = f'https://api.paystack.co/transaction/verify/{paystack_reference}'
    resp = _requests.get(
        verify_url,
        headers={'Authorization': f'Bearer {settings["secret_key"]}'},
        timeout=30,
    )
    if not resp.ok:
        frappe.throw(_("Could not reach payment gateway. Please contact support."))

    data = resp.json()
    if not data.get('status') or (data.get('data') or {}).get('status') != 'success':
        frappe.throw(_("Payment was not successful. Please try again or contact support."))

    tx = data['data']
    amount_paid = (tx.get('amount') or 0) / 100
    currency_paid = (tx.get('currency') or currency or 'ZAR').upper()

    # Convert quotation → Sales Order (courses are digital; skip address requirement)
    from webshop.webshop.shopping_cart.cart import _get_cart_quotation
    from erpnext.selling.doctype.quotation.quotation import _make_sales_order

    quotation = _get_cart_quotation()
    quotation.company = company
    quotation.flags.ignore_permissions = True
    quotation.payment_schedule = []
    quotation.save()

    fresh_quotation = frappe.get_doc('Quotation', quotation.name)
    fresh_quotation.flags.ignore_permissions = True
    fresh_quotation.submit()

    so_dict = _make_sales_order(fresh_quotation.name, ignore_permissions=True)
    sales_order = frappe.get_doc(so_dict)
    sales_order.payment_schedule = []
    sales_order.flags.ignore_permissions = True
    sales_order.flags.ignore_mandatory = True
    sales_order.insert()
    sales_order.submit()

    # Create a Paystack Payment Log so the webhook reconciler can find it
    log = frappe.get_doc({
        'doctype': 'Paystack Payment Log',
        'company': company,
        'linked_doctype': 'Sales Order',
        'linked_docname': sales_order.name,
        'amount': amount_paid,
        'currency': currency_paid,
        'status': 'Processed',
        'amount_paid': amount_paid,
        'currency_paid': currency_paid,
        'payment_reference': paystack_reference,
        'transaction_id': str(tx.get('id', '')),
        'payment_date': frappe.utils.today(),
        'raw_response': frappe.as_json(tx),
    })
    log.flags.ignore_permissions = True
    log.insert()
    frappe.db.commit()

    # Create and submit a Sales Invoice from the Sales Order
    invoice_name = None
    try:
        from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
        invoice = make_sales_invoice(sales_order.name, ignore_permissions=True)
        invoice.flags.ignore_permissions = True
        invoice.submit()
        if settings.get('capture_payment_entries_automatically'):
            frappe.db.set_value('Sales Invoice', invoice.name, 'status', 'Paid')
        else:
            # Funds are still held by Paystack; leave the invoice Unpaid until a
            # Payment Entry is created manually once the payout reaches the bank.
            frappe.db.set_value('Sales Invoice', invoice.name, 'status', 'Unpaid')
        frappe.db.set_value('Sales Order', sales_order.name, 'status', 'Closed')
        frappe.db.set_value('Sales Order', sales_order.name, 'per_billed', 100)
        frappe.db.commit()
        invoice_name = invoice.name
    except Exception as e:
        frappe.log_error(str(e), 'complete_checkout: Sales Invoice creation failed')

    # Identify items that need Moodle enrollment so the frontend can show the registration form.
    moodle_courses = []
    try:
        for item in sales_order.items:
            item_data = frappe.get_doc('Item', item.item_code)
            if item_data.get('custom_auto_enroll_in_moodle') == 1:
                moodle_courses.append({
                    'item_code': item.item_code,
                    'item_name': item.item_name,
                    'qty': int(item.qty or 1),
                })
    except Exception as e:
        frappe.log_error(str(e), 'complete_checkout: Moodle course check failed')

    user_doc = frappe.get_doc('User', user)
    return {
        'sales_order': sales_order.name,
        'sales_invoice': invoice_name,
        'payment_log': log.name,
        'moodle_courses': moodle_courses,
        'customer_first_name': user_doc.first_name or '',
        'customer_last_name': user_doc.last_name or '',
        'customer_email': user,
    }


@frappe.whitelist()
def get_invoice_pdf(invoice_name):
    """Return a base64-encoded PDF of a Sales Invoice the current user owns."""
    user = frappe.session.user
    if user == 'Guest':
        frappe.throw(_("Please login."), frappe.PermissionError)

    # Verify ownership via the Sales Order that produced this invoice
    so_name = frappe.db.get_value('Sales Invoice Item', {'parent': invoice_name}, 'sales_order')
    if not so_name:
        frappe.throw(_("Invoice not found."), frappe.DoesNotExistError)

    contact_email = frappe.db.get_value('Sales Order', so_name, 'contact_email')
    if contact_email != user:
        frappe.throw(_("You do not have permission to download this invoice."), frappe.PermissionError)

    # as_pdf=True uses Frappe's full PDF pipeline (wkhtmltopdf with correct base URL,
    # CSS resolution, and letterhead) — the same path as the ERPNext print dialog.
    pdf_data = frappe.get_print(
        'Sales Invoice',
        invoice_name,
        print_format='Kartoza Without Timesheet',
        as_pdf=True,
        no_letterhead=0,
    )

    import base64
    return {
        'pdf': base64.b64encode(pdf_data).decode('utf-8'),
        'filename': f'{invoice_name}.pdf',
    }


@frappe.whitelist()
def get_my_orders(page=1, page_size=5, search='', date_from='', date_to=''):
    """Return the current user's submitted Sales Orders with server-side pagination and filtering."""
    user = frappe.session.user
    if user == 'Guest':
        frappe.throw(_("Please login to view your orders."), frappe.PermissionError)

    page = max(1, int(page or 1))
    page_size = min(50, max(1, int(page_size or 5)))
    search = (search or '').strip()
    date_from = (date_from or '').strip()
    date_to = (date_to or '').strip()

    base_filters = [
        ['contact_email', '=', user],
        ['order_type', '=', 'Shopping Cart'],
        ['docstatus', '=', 1],
    ]
    if date_from:
        base_filters.append(['transaction_date', '>=', date_from])
    if date_to:
        base_filters.append(['transaction_date', '<=', date_to])

    # Fetch all matching order names (lightweight — names only, sorted)
    all_names = frappe.get_all(
        'Sales Order',
        filters=base_filters,
        pluck='name',
        order_by='name desc',
    )

    if search:
        search_lower = search.lower()
        name_matched = {n for n in all_names if search_lower in n.lower()}

        item_matched = set()
        if all_names:
            item_matched = set(frappe.get_all(
                'Sales Order Item',
                filters=[
                    ['parent', 'in', all_names],
                    ['item_name', 'like', f'%{search}%'],
                ],
                pluck='parent',
            ))

        matched = name_matched | item_matched
        # Preserve sort order (all_names is already name desc)
        all_names = [n for n in all_names if n in matched]

    total = len(all_names)
    start = (page - 1) * page_size
    page_names = all_names[start:start + page_size]

    orders = []
    for name in page_names:
        order = frappe.db.get_value(
            'Sales Order',
            name,
            ['name', 'transaction_date', 'grand_total', 'currency', 'status'],
            as_dict=True,
        )
        if not order:
            continue

        order['items'] = frappe.get_all(
            'Sales Order Item',
            filters={'parent': name},
            fields=['item_code', 'item_name', 'qty', 'rate', 'amount'],
        )
        order['invoice'] = frappe.db.get_value(
            'Sales Invoice Item',
            {'sales_order': name},
            'parent',
        ) or None

        moodle_items = []
        for item in order['items']:
            try:
                item_doc = frappe.get_cached_doc('Item', item['item_code'])
                if item_doc.get('custom_auto_enroll_in_moodle') == 1:
                    moodle_items.append({
                        'item_code': item['item_code'],
                        'item_name': item['item_name'],
                        'qty': int(item.get('qty') or 1),
                        'course_id': item_doc.get('custom_moodle_course_id') or '',
                    })
            except Exception:
                pass
        order['moodle_items'] = moodle_items

        enrollment_details = []
        log_name = frappe.db.get_value('Moodle Enrollment Logs', {'sales_order': name}, 'name')
        if log_name:
            enrollment_details = frappe.get_all(
                'Moodle Enrollment Details',
                filters={'parent': log_name},
                fields=['name1', 'email', 'course_id', 'enrollment_succesful'],
            )
        order['enrollment_details'] = [dict(d) for d in enrollment_details]

        orders.append(order)

    return {'orders': orders, 'total': total, 'page': page, 'page_size': page_size}


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
def get_countries():
    """Return all country names ordered alphabetically for address dropdowns."""
    return frappe.get_all(
        'Country',
        fields=['country_name'],
        order_by='country_name asc',
        limit_page_length=300,
    )


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


@frappe.whitelist(allow_guest=True)
def get_free_courses():
    """Return all Moodle courses available for free self-registration (zero_rated = 1)."""
    return frappe.get_all(
        'Moodle Course Settings',
        filters={'zero_rated': 1},
        fields=['item', 'course_link'],
    )


@frappe.whitelist(allow_guest=True)
def self_register_free_course(item_code, email):
    """Self-register a user for a free (zero-rated) Moodle course.

    Looks up Moodle Course Settings for the given item, confirms it is free
    (zero_rated = 1), then emails the enrollment key and course link to the
    provided address. Duplicate registrations for the same course + email are
    rejected to prevent key leakage via repeated requests.
    """
    from frappe.utils import validate_email_address

    item_code = (item_code or "").strip()
    email = (email or "").strip()

    if not item_code or not email:
        frappe.throw(_("Item code and email address are required."))

    if not validate_email_address(email):
        frappe.throw(_("Please provide a valid email address."))

    settings = frappe.get_all(
        'Moodle Course Settings',
        filters={'item': item_code, 'zero_rated': 1},
        fields=['item', 'enrollment_key', 'course_link'],
        limit=1,
    )

    if not settings:
        frappe.throw(_("This course is not available for free self-registration."))

    course = settings[0]

    already_registered = frappe.db.exists(
        'Moodle Course Email Requests',
        {'course': item_code, 'email': email, 'email_sent': 1},
    )
    if already_registered:
        return {
            "status": "already_registered",
            "message": _("You have already registered for this course. Please check your inbox for the enrollment details."),
        }

    course_name = frappe.db.get_value('Item', item_code, 'item_name') or item_code
    subject = f"Your Free Course Access: {course_name}"
    message = f"""
        <p>Thank you for registering for <strong>{course_name}</strong>!</p>
        <p>You can access the course at the link below. Use the enrollment key when prompted.</p>
        <table style="margin: 1rem 0; border-collapse: collapse;">
            <tr>
                <td style="padding: 0.4rem 1rem 0.4rem 0; font-weight: 600;">Course Link:</td>
                <td><a href="{course.get('course_link')}">{course.get('course_link')}</a></td>
            </tr>
            <tr>
                <td style="padding: 0.4rem 1rem 0.4rem 0; font-weight: 600;">Enrollment Key:</td>
                <td><code>{course.get('enrollment_key')}</code></td>
            </tr>
        </table>
        <p>If you have any questions, please <a href="https://kartoza.com/contact-us/">contact us</a>.</p>
        <p>Happy learning!<br>The Kartoza Team</p>
    """

    frappe.sendmail(
        recipients=email,
        subject=subject,
        message=message,
        sender="Kartoza <notifications@erpnext.com>",
        now=True,
    )

    frappe.get_doc({
        'doctype': 'Moodle Course Email Requests',
        'course': item_code,
        'email': email,
        'email_sent': 1,
    }).insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "status": "success",
        "message": _(
            "Enrollment details have been sent to {0}. "
            "Please check your inbox (and spam folder) for the course link and enrollment key."
        ).format(email),
    }


@frappe.whitelist()
def get_next_employee_number(company):
    company_abbr = "GEN"
    
    if company == "Kartoza Unipessoal Lda":
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
def send_expense_email(docname, doctype):
    doc = frappe.get_doc(doctype, docname)

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
    
    if doctype == 'Travel Request':
        doc_url = 'travel-request'
    elif doctype == 'Employee Expense Claim':
        doc_url = 'employee-expense-claim'
    

    subject = f"{doc.employee_name} has submitted a new Expense Claim"
    message = f"""
        <p>{doc.employee_name} has submitted a new Expense Claim.</p>
        <p>Please review the Expense Claim at 
        <a href='https://erp.kartoza.com/app/{doc_url}/{doc.name}'>
        https://erp.kartoza.com/app/{doc_url}/{doc.name}</a></p>
    """

    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=message,
        reference_doctype=doctype,
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

        set_user_password(user=user.name, pwd=password, logout_all_sessions=0)

        return {"status": 1, "message": _("Registration successful. Please log in to continue.")}


@frappe.whitelist(allow_guest=True)
def get_attributes_and_values(item_code):
    """Return variant attribute data as a JSON-serializable list.

    Example:
    [
        {
            "name": "Introduction to QGIS Course-11 - 13 August 2026-ONLINE",
            "item_code": "INTRO-QGIS-ONLINE-2026-08-11",
            "variants": {"Schedule": "11 - 13 August 2026", "Venue": "ONLINE"},
            "prices": [
                {"price_list": "Standard Selling", "price_list_rate": 1299, "currency": "ZAR", "uom": "Nos"}
            ]
        }
    ]
    """
    item_code = (item_code or "").strip()
    if not item_code:
        return []

    # Accept either internal Item name or human-readable item_name from the client.
    template_code = item_code
    if not frappe.db.exists("Item", template_code):
        template_code = frappe.db.get_value(
            "Item",
            {"item_name": item_code, "has_variants": 1},
            "name",
        )

    if not template_code:
        return []

    is_template = bool(frappe.db.get_value("Item", template_code, "has_variants"))

    item_cache = ItemVariantsCacheManager(template_code)
    item_variants_data = item_cache.get_item_variants_data() or []

    variant_codes = set()
    variant_meta = {}

    for variant_code, attribute, attribute_value in item_variants_data:
        variant_codes.add(variant_code)
        attr_key = (attribute or "").strip()
        value = (attribute_value or "").strip()
        if not attr_key or not value:
            continue

        meta = variant_meta.setdefault(variant_code, {})
        # Keep all variant attributes instead of hardcoding specific keys.
        if attr_key in meta and meta[attr_key] != value:
            existing = meta[attr_key]
            if isinstance(existing, list):
                if value not in existing:
                    existing.append(value)
            else:
                meta[attr_key] = [existing, value]
        else:
            meta[attr_key] = value

    # If the selected item is a template, only keep active variants.
    if is_template:
        active_variant_codes = set(
            frappe.get_all(
                "Item",
                filters={"variant_of": template_code, "disabled": 0},
                pluck="name",
            )
        )
        if variant_codes:
            variant_codes = variant_codes.intersection(active_variant_codes)
        else:
            variant_codes = active_variant_codes

    if not variant_codes:
        variant_filters = {"variant_of": template_code}
        if is_template:
            variant_filters["disabled"] = 0

        variant_codes = set(
            frappe.get_all(
                "Item",
                filters=variant_filters,
                pluck="name",
            )
        )
        if not variant_codes and not is_template:
            variant_codes = {template_code}

    item_meta = frappe.get_meta("Item")
    has_website_image = bool(item_meta.get_field("website_image"))
    has_website_description = bool(item_meta.get_field("website_description"))

    item_fields = ["name", "item_name", "image", "description"]
    if has_website_image:
        item_fields.append("website_image")
    if has_website_description:
        item_fields.append("website_description")

    items = frappe.get_all(
        "Item",
        filters={"name": ["in", list(variant_codes)]},
        fields=item_fields,
        order_by="item_name asc",
    )

    item_codes = [item.get("name") for item in items if item.get("name")]
    price_rows = []
    if item_codes:
        price_rows = frappe.get_all(
            "Item Price",
            filters={"item_code": ["in", item_codes]},
            fields=["item_code", "price_list", "price_list_rate", "currency", "uom"],
            order_by="item_code asc, price_list asc",
        )

    prices_by_item = {}
    for row in price_rows:
        code = row.get("item_code")
        if not code:
            continue

        prices_by_item.setdefault(code, []).append({
            "price_list": row.get("price_list"),
            "price_list_rate": row.get("price_list_rate"),
            "currency": row.get("currency"),
            "uom": row.get("uom"),
        })

    response = []
    for item in items:
        item_name = item.get("name")
        full_name = (item.get("item_name") or item.get("name") or "").strip()
        meta = variant_meta.get(item_name, {})
        image = item.get("image") or (item.get("website_image") if has_website_image else None)
        description = item.get("description") or (
            item.get("website_description") if has_website_description else None
        )

        response.append({
            "name": full_name,
            "item_code": item_name,
            "image": image,
            "description": description,
            "variants": meta,
            "prices": prices_by_item.get(item_name, []),
        })

    return response


@frappe.whitelist(allow_guest=True)
def get_active_items_with_variants():
    """Return all active items and include variants for template items."""
    item_meta = frappe.get_meta("Item")
    has_website_image = bool(item_meta.get_field("website_image"))
    has_website_description = bool(item_meta.get_field("website_description"))

    item_fields = [
        "name",
        "item_name",
        "has_variants",
        "variant_of",
        "image",
        "description",
    ]
    if has_website_image:
        item_fields.append("website_image")
    if has_website_description:
        item_fields.append("website_description")

    items = frappe.get_all(
        "Item",
        filters={"disabled": 0},
        fields=item_fields,
        order_by="item_name asc",
    )

    template_codes = [item.get("name") for item in items if item.get("has_variants")]

    variants_by_template = {}
    if template_codes:
        variants = frappe.get_all(
            "Item",
            filters={
                "disabled": 0,
                "variant_of": ["in", template_codes],
            },
            fields=item_fields,
            order_by="item_name asc",
        )

        for variant in variants:
            parent = variant.get("variant_of")
            if not parent:
                continue

            variants_by_template.setdefault(parent, []).append(
                {
                    "item_code": variant.get("name"),
                    "name": (variant.get("item_name") or variant.get("name") or "").strip(),
                    "image": variant.get("image")
                    or (variant.get("website_image") if has_website_image else None),
                    "description": variant.get("description")
                    or (variant.get("website_description") if has_website_description else None),
                }
            )

    response = []
    for item in items:
        item_code = item.get("name")
        is_template = bool(item.get("has_variants"))

        response.append(
            {
                "item_code": item_code,
                "name": (item.get("item_name") or item_code or "").strip(),
                "is_template": is_template,
                "variant_of": item.get("variant_of"),
                "image": item.get("image") or (item.get("website_image") if has_website_image else None),
                "description": item.get("description")
                or (item.get("website_description") if has_website_description else None),
                "variants": variants_by_template.get(item_code, []) if is_template else [],
            }
        )

    return response