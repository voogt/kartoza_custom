import frappe
from frappe.utils import now_datetime, format_datetime, escape_html
from frappe.utils.pdf import get_pdf
from frappe.utils.file_manager import save_file


def get_context(context):
    name = frappe.form_dict.get("name")
    if not name:
        frappe.throw("Missing contract name in URL")

    if not frappe.db.exists("Contract", name):
        raise frappe.PageDoesNotExistError

    doc = frappe.get_doc("Contract", name)

    user = frappe.get_doc("User", doc.party_user)

    if doc.party_user != frappe.session.user:
        frappe.throw("You are not authorized to sign this contract", frappe.PermissionError)

    context.contract_name = name
    context.already_signed = bool(doc.is_signed)
    context.signed_on = doc.signed_on
    context.contract_terms = doc.contract_terms
    context.party_user = user.full_name or user.email

    # basic meta
    context.meta_title = f"Sign Contract {name}"
    context.no_cache = True


@frappe.whitelist(allow_guest=True)
def sign_contract(name: str, signee: str, signature: str, location_signed: str = None, date_signed: str = None) -> dict:
    """
    Accept signature data (base64 PNG) and mark Contract signed.
    """
    if not name:
        frappe.throw("Missing contract name")
    if not signee:
        frappe.throw("Please enter your full name")
    if not signature or not signature.startswith("data:image/png;base64,"):
        frappe.throw("Invalid signature data")

    doc = frappe.get_doc("Contract", name)

    # Prevent re-signing
    if doc.is_signed:
        return {"status": "already_signed", "message": "Contract already signed"}

    # Update fields
    doc.signee = signee
    # store the drawn signature in the standard Signature field
    doc.set("custom_signee_party", signature)
    doc.signed_on = now_datetime()
    doc.custom_location_signed_customer = location_signed
    doc.custom_date_signed_customer = date_signed
    doc.ip_address = (
        frappe.local.request_ip or getattr(getattr(frappe.local, "request", None), "remote_addr", None)
        if hasattr(frappe.local, "request")
        else None
    )
    doc.is_signed = 1

    # persist ignoring permissions (customer may be Guest)
    doc.flags.ignore_permissions = True
    doc.save()

    # Submit if possible
    try:
        doc.submit()
    except Exception:
        # If submit fails due to permissions, keep as saved (signed)
        pass

    # Send notification email to signee and company signer (if any)
    try:
        recipients = []
        recipients.append('juanique@kartoza.com')

        signed_on_str = format_datetime(doc.signed_on)
        contract_terms_html = doc.contract_terms or ""
        signee_safe = escape_html(signee)
        signature_img = signature  # data URL
        location_signed_safe = escape_html(location_signed or "")
        date_signed_safe = escape_html(date_signed or "")
                

        if recipients:
            subject = f"Contract {doc.name} signed"
            message = (
                f"<p>The contract <b>{escape_html(doc.name)}</b> has been signed by <b>{signee_safe}</b> on {escape_html(signed_on_str)}.</p>"
                f"<p>You can view it in ERPNext</p>"
            )
            frappe.sendmail(
                recipients=recipients,
                subject=subject,
                message=message,
                attachments=[],
                reference_doctype="Contract",
                reference_name=doc.name,
            )
    except Exception:
        # Ignore email failures
        pass

    frappe.db.commit()

    request = frappe.local.request
    return {
        "status": "ok",
        "message": "Contract signed",
        "signed_on": format_datetime(doc.signed_on),
        "attachment_url": f"/api/method/frappe.utils.print_format.download_pdf?doctype=Contract&name={doc.name}&format=Contract%20PDF&no_letterhead=0&letterhead=Kartoza&settings=%7B%7D&_lang=en",
    }
