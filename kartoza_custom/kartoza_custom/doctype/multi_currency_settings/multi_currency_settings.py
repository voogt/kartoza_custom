# Copyright (c) 2024, Kartoza and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import frappe

class MultiCurrencySettings(Document):
	pass

@frappe.whitelist(methods=["GET"], allow_guest=True)
def set_currency_cache(currency):
	print(f"CURRENT Curency {currency}")
	payment_account = frappe.db.get_value("Multi Currency Settings", {'price_list': currency}, ['payment_gateway_account'])
	frappe.cache().set_value("currency", currency)
	frappe.cache().set_value("payment_account", payment_account)
	return {"status": 200}

@frappe.whitelist(methods=["GET"], allow_guest=True)
def retrieve_currency_cache():
	price_list = frappe.cache().get_value('currency')
	currency = frappe.db.get_value("Multi Currency Settings", {'price_list': price_list}, ['currency'])
	return currency

@frappe.whitelist(methods=["GET"], allow_guest=True)
def retrieve_payment_account_cache():
	payment_account = frappe.cache().get_value('payment_account')
	return payment_account