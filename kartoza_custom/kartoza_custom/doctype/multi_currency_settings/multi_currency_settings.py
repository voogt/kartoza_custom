# Copyright (c) 2024, Kartoza and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import frappe

class MultiCurrencySettings(Document):
	pass

@frappe.whitelist(methods=["GET"], allow_guest=True)
def set_currency_cache(currency):
	frappe.cache().set_value("currency", currency)
	return {"status": 200}

@frappe.whitelist(methods=["GET"], allow_guest=True)
def retrieve_currency_cache():
	price_list = frappe.cache().get_value('currency')
	currency = frappe.db.get_value("Multi Currency Settings", {'price_list': price_list}, ['currency'])
	return currency