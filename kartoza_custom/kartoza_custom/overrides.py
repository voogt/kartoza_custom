from erpnext.e_commerce.doctype.e_commerce_settings.e_commerce_settings import ECommerceSettings, get_shopping_cart_settings
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import comma_and, flt, unique
import erpnext.e_commerce.doctype.e_commerce_settings.e_commerce_settings as e_commerce_settings
import erpnext.e_commerce.shopping_cart.cart as _cart_settings
import redis


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
	

	
# Override methods
e_commerce_settings.get_shopping_cart_settings = get_shopping_cart_settings_f
_cart_settings.apply_cart_settings = apply_cart_settings_f
_cart_settings.get_cart_quotation = get_cart_quotation_f
