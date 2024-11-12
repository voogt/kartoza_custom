from erpnext.e_commerce.doctype.e_commerce_settings.e_commerce_settings import ECommerceSettings, get_shopping_cart_settings
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import comma_and, flt, unique
import erpnext.e_commerce.doctype.e_commerce_settings.e_commerce_settings as e_commerce_settings
import erpnext.e_commerce.shopping_cart.cart as _cart_settings
import erpnext.selling.doctype.sales_order.sales_order as _sales_order
import redis
from frappe.contacts.doctype.address.address import get_company_address
from frappe.desk.notifications import clear_doctype_notifications
from frappe.model.mapper import get_mapped_doc
from frappe.model.utils import get_fetch_values
from frappe.query_builder.functions import Sum
from frappe.utils import add_days, cint, cstr, flt, get_link_to_form, getdate, nowdate, strip_html
import erpnext.accounts.doctype.payment_request.payment_request as make_payment_request_settings
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
	get_accounting_dimensions,
)

class MultiCurrency(Document):
    def onload(self):
        pass
		

def get_shopping_cart_settings_f():
    
	settings = frappe.get_cached_doc('E Commerce Settings')

	if frappe.cache().get_value('currency') == None:
		frappe.cache().set_value("currency", settings.price_list)
		frappe.cache().set_value("payment_account", settings.payment_gateway_account)

	price_list = frappe.cache().get_value('currency')

	settings.price_list = price_list
	
	return settings

@frappe.whitelist()
def get_cart_quotation_f(doc=None):
	party = _cart_settings.get_party()

	if not doc:
		quotation = _cart_settings._get_cart_quotation(party)
		doc = quotation
		_cart_settings.set_cart_count(quotation)

	addresses = _cart_settings.get_address_docs(party=party)

	if not doc.customer_address and addresses:
		_cart_settings.update_cart_address("billing", addresses[0].name)
	
	cart_settings = frappe.get_cached_doc("E Commerce Settings")

	if frappe.cache().get_value('currency') == None:
		frappe.cache().set_value("currency", cart_settings.price_list)

	price_list = frappe.cache().get_value('currency')

	cart_settings.price_list = price_list

	return {
		"doc": _cart_settings.decorate_quotation_doc(doc),
		"shipping_addresses": _cart_settings.get_shipping_addresses(party),
		"billing_addresses": _cart_settings.get_billing_addresses(party),
		"shipping_rules": _cart_settings.get_applicable_shipping_rules(party),
		"cart_settings": cart_settings,
	}


def apply_cart_settings_f(party=None, quotation=None):
	if not party:
		party = _cart_settings.get_party()
	if not quotation:
		quotation = _cart_settings._get_cart_quotation(party)

	cart_settings = frappe.get_doc("E Commerce Settings")

	if frappe.cache().get_value('currency') == None:
		frappe.cache().set_value("currency", cart_settings.price_list)

	price_list = frappe.cache().get_value('currency')

	cart_settings.price_list = price_list
	# cart_settings.payment_gateway_account = 'Paystack ZAR - USD'

	_cart_settings.set_price_list_and_rate(quotation, cart_settings)

	quotation.run_method("calculate_taxes_and_totals")

	set_taxes_f(quotation, cart_settings)

	_cart_settings._apply_shipping_rule(party, quotation, cart_settings)

def set_taxes_f(quotation, cart_settings):
	"""set taxes based on billing territory"""
	from erpnext.accounts.party import set_taxes

	customer_group = frappe.db.get_value("Customer", quotation.party_name, "customer_group")

	print(f"quotation.price_list_currency over {quotation.price_list_currency}")

	if quotation.price_list_currency != 'ZAR':
		pass
		# quotation.taxes_and_charges = None
  		
	else:
		quotation.taxes_and_charges = set_taxes(
			quotation.party_name,
			"Customer",
			quotation.transaction_date,
			quotation.company,
			customer_group=customer_group,
			supplier_group=None,
			tax_category=quotation.tax_category,
			billing_address=quotation.customer_address,
			shipping_address=quotation.shipping_address_name,
			use_for_shopping_cart=1,
		)
	
		# clear table
		quotation.set("taxes", [])
		
		# append taxes
		quotation.append_taxes_from_master()
	
	print(f"TAXES SETTING {quotation.taxes_and_charges}")
	print(f"TAXES tax_category {quotation.tax_category}")
	print(f"quotation.shipping_address_name {quotation.shipping_address_name}")

@frappe.whitelist()
def make_sales_invoice_f(source_name, target_doc=None, ignore_permissions=False):
	def postprocess(source, target):
		set_missing_values(source, target)
		# Get the advance paid Journal Entries in Sales Invoice Advance
		if target.get("allocate_advances_automatically"):
			target.set_advances()

	def set_missing_values(source, target):
		target.flags.ignore_permissions = True
		target.run_method("set_missing_values")
		target.run_method("set_po_nos")
		target.run_method("calculate_taxes_and_totals")

		if source.company_address:
			target.update({"company_address": source.company_address})
		else:
			# set company address
			target.update(get_company_address(target.company))

		if target.company_address:
			target.update(get_fetch_values("Sales Invoice", "company_address", target.company_address))

		# set the redeem loyalty points if provided via shopping cart
		if source.loyalty_points and source.order_type == "Shopping Cart":
			target.redeem_loyalty_points = 1

		target.debit_to = _sales_order.get_party_account("Customer", source.customer, source.company)

	def update_item(source, target, source_parent):
		target.amount = flt(source.amount) - flt(source.billed_amt)
		target.base_amount = target.amount * flt(source_parent.conversion_rate)
		target.qty = (
			target.amount / flt(source.rate)
			if (source.rate and source.billed_amt)
			else source.qty - source.returned_qty
		)

		if source_parent.project:
			target.cost_center = frappe.db.get_value("Project", source_parent.project, "cost_center")
		if target.item_code:
			item = _sales_order.get_item_defaults(target.item_code, source_parent.company)
			item_group = _sales_order.get_item_group_defaults(target.item_code, source_parent.company)
			cost_center = item.get("selling_cost_center") or item_group.get("selling_cost_center")

			if cost_center:
				target.cost_center = cost_center

	doclist = get_mapped_doc(
		"Sales Order",
		source_name,
		{
			"Sales Order": {
				"doctype": "Sales Invoice",
				"field_map": {
					"party_account_currency": "party_account_currency",
					"payment_terms_template": "payment_terms_template",
				},
				"field_no_map": ["payment_terms_template"],
				"validation": {"docstatus": ["=", 1]},
			},
			"Sales Order Item": {
				"doctype": "Sales Invoice Item",
				"field_map": {
					"name": "so_detail",
					"parent": "sales_order",
				},
				"postprocess": update_item,
				# "condition": lambda doc: doc.qty
				# and (doc.base_amount == 0 or abs(doc.billed_amt) < abs(doc.amount)),
			},
			"Sales Taxes and Charges": {"doctype": "Sales Taxes and Charges", "add_if_empty": True},
			"Sales Team": {"doctype": "Sales Team", "add_if_empty": True},
		},
		target_doc,
		postprocess,
		ignore_permissions=ignore_permissions,
	)

	automatically_fetch_payment_terms = cint(
		frappe.db.get_single_value("Accounts Settings", "automatically_fetch_payment_terms")
	)
	if automatically_fetch_payment_terms:
		doclist.set_payment_schedule()

	return doclist

@frappe.whitelist(allow_guest=True)
def make_payment_request_f(**args):
	"""Make payment request"""

	args = frappe._dict(args)

	ref_doc = frappe.get_doc(args.dt, args.dn)
	
	#get currency
	try:

		currency = ref_doc.currency
		multicurrency_setting = frappe.db.get_all("Multi Currency Settings", filters={
			'enabled': ['=', 1],
			'currency': ['=', currency]
		}, fields='*', order_by="name")

		gateway_account = frappe.get_doc("Payment Gateway Account",multicurrency_setting[0]['payment_gateway_account'])
	except:
		gateway_account = make_payment_request_settings.get_gateway_details(args) or frappe._dict()

	grand_total = make_payment_request_settings.get_amount(ref_doc, gateway_account.get("payment_account"))
	
	if args.loyalty_points and args.dt == "Sales Order":
		from erpnext.accounts.doctype.loyalty_program.loyalty_program import validate_loyalty_points

		loyalty_amount = validate_loyalty_points(ref_doc, int(args.loyalty_points))
		frappe.db.set_value(
			"Sales Order", args.dn, "loyalty_points", int(args.loyalty_points), update_modified=False
		)
		frappe.db.set_value(
			"Sales Order", args.dn, "loyalty_amount", loyalty_amount, update_modified=False
		)
		grand_total = grand_total - loyalty_amount

	bank_account = (
		make_payment_request_settings.get_party_bank_account(args.get("party_type"), args.get("party"))
		if args.get("party_type")
		else ""
	)

	draft_payment_request = frappe.db.get_value(
		"Payment Request",
		{"reference_doctype": args.dt, "reference_name": args.dn, "docstatus": 0},
	)

	existing_payment_request_amount = make_payment_request_settings.get_existing_payment_request_amount(args.dt, args.dn)

	if existing_payment_request_amount:
		grand_total -= existing_payment_request_amount

	if draft_payment_request:
		frappe.db.set_value(
			"Payment Request", draft_payment_request, "grand_total", grand_total, update_modified=False
		)
		pr = frappe.get_doc("Payment Request", draft_payment_request)
	else:
		pr = frappe.new_doc("Payment Request")
		pr.update(
			{
				"payment_gateway_account": gateway_account.get("name"),
				"payment_gateway": gateway_account.get("payment_gateway"),
				"payment_account": gateway_account.get("payment_account"),
				"payment_channel": gateway_account.get("payment_channel"),
				"payment_request_type": args.get("payment_request_type"),
				"currency": ref_doc.currency,
				"grand_total": grand_total,
				"mode_of_payment": args.mode_of_payment,
				"email_to": args.recipient_id or ref_doc.owner,
				"subject": _("Payment Request for {0}").format(args.dn),
				"message": gateway_account.get("message") or make_payment_request_settings.get_dummy_message(ref_doc),
				"reference_doctype": args.dt,
				"reference_name": args.dn,
				"party_type": args.get("party_type") or "Customer",
				"party": args.get("party") or ref_doc.get("customer"),
				"bank_account": bank_account,
			}
		)

		# Update dimensions
		pr.update(
			{
				"cost_center": ref_doc.get("cost_center"),
				"project": ref_doc.get("project"),
			}
		)

		for dimension in get_accounting_dimensions():
			pr.update({dimension: ref_doc.get(dimension)})

		if args.order_type == "Shopping Cart" or args.mute_email:
			pr.flags.mute_email = True

		pr.insert(ignore_permissions=True)
		if args.submit_doc:
			pr.submit()

	if args.order_type == "Shopping Cart":
		frappe.db.commit()
		frappe.local.response["type"] = "redirect"
		frappe.local.response["location"] = pr.get_payment_url()

	if args.return_doc:
		return pr

	return pr.as_dict()

	
# Override methods
# e_commerce_settings.get_shopping_cart_settings = get_shopping_cart_settings_f
# _cart_settings.apply_cart_settings = apply_cart_settings_f
# _cart_settings.get_cart_quotation = get_cart_quotation_f
# _cart_settings.set_taxes = set_taxes_f
# _sales_order.make_sales_invoice = make_sales_invoice_f
# make_payment_request_settings.make_payment_request = make_payment_request_f
