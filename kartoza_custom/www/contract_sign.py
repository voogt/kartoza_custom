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
def sign_contract(name: str, signee: str, signature: str):
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

    # Generate signed PDF with signature block and attach to Contract
    try:
        signed_on_str = format_datetime(doc.signed_on)
        contract_terms_html = doc.contract_terms or ""
        signee_safe = escape_html(signee)
        signature_img = signature  # data URL

        html = f"""
        <html>
        <head>
            <meta charset='utf-8'>
            <style>
                body {{ font-family: Inter, Arial, Helvetica, sans-serif; font-size: 12px; color: #111; }}
                h1,h2,h3 {{ margin: 0 0 12px 0; }}
                .section {{ margin-bottom: 18px; }}
                .terms {{ margin-top: 12px; }}
                .sig-block {{ margin-top: 28px; border-top: 1px solid #ccc; padding-top: 12px; }}
                .sig-row {{ display: flex; gap: 24px; align-items: flex-end; }}
                .sig-box {{ border: 1px solid #ddd; border-radius: 4px; padding: 8px; min-height: 100px; min-width: 300px; }}
                .sig-meta {{ margin-top: 8px; font-size: 11px; color: #555; }}
                img.signature {{ max-height: 120px; max-width: 100%; }}
            </style>
        </head>
        <body>
            <div class='section'>
                <h2>Contract {escape_html(doc.name)}</h2>
                <div>Party: {escape_html(frappe.utils.cstr(doc.party_name))}</div>
            </div>
            <div class='terms section'>
                {contract_terms_html}
            </div>
            <div class='sig-block section'>
                <div class='sig-row'>
                    <div class='sig-box'>
                        <img class='signature' src='{signature_img}' alt='Signature'>
                    </div>
                </div>
                <div class='sig-meta'>
                    Signed by: {signee_safe} on {escape_html(signed_on_str)}
                </div>
            </div>
        </body>
        </html>
        """

        pdf_bytes = get_pdf(html)
        file_name = f"Contract-{doc.name}-Signed.pdf"
        file_doc = save_file(file_name, pdf_bytes, "Contract", doc.name, is_private=1)
        attachment_url = file_doc.file_url

        # Send notification email to signee and company signer (if any)
        try:
            recipients = []
            recipients.append('juanique@kartoza.com')
                    

            if recipients:
                subject = f"Contract {doc.name} signed"
                message = (
                    f"<p>The contract <b>{escape_html(doc.name)}</b> has been signed by <b>{signee_safe}</b> on {escape_html(signed_on_str)}.</p>"
                    f"<p>You can view it in ERPNext or download the attached PDF.</p>"
                )
                frappe.sendmail(
                    recipients=recipients,
                    subject=subject,
                    message=message,
                    attachments=[{"fname": file_name, "fcontent": pdf_bytes}],
                    reference_doctype="Contract",
                    reference_name=doc.name,
                )
        except Exception:
            # Ignore email failures
            pass
    except Exception as e:
        attachment_url = None

    frappe.db.commit()
    return {
        "status": "ok",
        "message": "Contract signed",
        "signed_on": format_datetime(doc.signed_on),
        "attachment_url": attachment_url,
    }
