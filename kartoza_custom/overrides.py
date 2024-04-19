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

class MultiCurrency(Document):
    def onload(self):
        pass
		

def get_shopping_cart_settings_f():
    
	settings = frappe.get_cached_doc('E Commerce Settings')

	if frappe.cache().get_value('currency') == None:
		frappe.cache().set_value("currency", settings.price_list)

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

	_cart_settings.set_price_list_and_rate(quotation, cart_settings)

	quotation.run_method("calculate_taxes_and_totals")

	_cart_settings.set_taxes(quotation, cart_settings)

	_cart_settings._apply_shipping_rule(party, quotation, cart_settings)


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

	

	
# Override methods
e_commerce_settings.get_shopping_cart_settings = get_shopping_cart_settings_f
_cart_settings.apply_cart_settings = apply_cart_settings_f
_cart_settings.get_cart_quotation = get_cart_quotation_f
_sales_order.make_sales_invoice = make_sales_invoice_f
