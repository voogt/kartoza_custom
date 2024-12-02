# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import add_to_date, flt, get_date_str

from erpnext.accounts.report.financial_statements import get_columns, get_data, get_period_list
from erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement import (
	get_net_profit_loss,
)


def get_mapper_for(mappers, position):
	mapper_list = list(filter(lambda x: x["position"] == position, mappers))
	return mapper_list[0] if mapper_list else []


def get_mappers_from_db():
	return frappe.get_all(
		"Kartoza Cash Flow Mapper",
		fields=[
			"section_name",
			"section_header",
			"section_leader",
			"section_subtotal",
			"section_footer",
			"name",
			"position",
		],
		order_by="position",
	)


def get_accounts_in_mappers(mapping_names):
	cfm = frappe.qb.DocType("Kartoza Cash Flow Mapping")
	cfma = frappe.qb.DocType("Kartoza Cash Flow Mapping Accounts")
	result = (
		frappe.qb.select(
			cfma.name,
			cfm.label,
			cfm.is_working_capital,
			cfm.is_income_tax_liability,
			cfm.is_income_tax_expense,
			cfm.is_finance_cost,
			cfm.is_finance_cost_adjustment,
			cfm.is_asset_purchase,
			cfm.is_asset_sale,
			cfma.account,
		)
		.from_(cfm)
		.join(cfma)
		.on(cfm.name == cfma.parent)
		.where(cfma.parent.isin(mapping_names))
	).run()

	return result

def get_accounts_in_mappers_for_investing(mapping_names):
	cfm = frappe.qb.DocType("Kartoza Cash Flow Mapping")
	cfma = frappe.qb.DocType("Kartoza Cash Flow Mapping Accounts")
	result = (
		frappe.qb.select(
			cfma.name,
			cfm.label,
			cfm.is_asset_purchase,
			cfm.is_asset_sale,
			cfma.account,
		)
		.from_(cfm)
		.join(cfma)
		.on(cfm.name == cfma.parent)
		.where(cfma.parent.isin(mapping_names))
	).run()

	return result


def setup_mappers(mappers):
	cash_flow_accounts = []

	for mapping in mappers:
		mapping["account_types"] = []
		mapping["tax_liabilities"] = []
		mapping["tax_expenses"] = []
		mapping["finance_costs"] = []
		mapping["finance_costs_adjustments"] = []
		mapping["asset_purchases"] = []
		mapping["asset_sales"] = []
		doc = frappe.get_doc("Kartoza Cash Flow Mapper", mapping["name"])
		mapping_names = [item.mapping for item in doc.accounts]

		if not mapping_names:
			continue

		accounts = get_accounts_in_mappers(mapping_names)

		for account in accounts:
			print(f"ACCOUNT IN MAPPER {account}")

		account_types = [
			dict(
				name=account[0],
				account_name=account[9],
				label=account[1],
				is_working_capital=account[2],
				is_income_tax_liability=account[3],
				is_income_tax_expense=account[4],
			)
			for account in accounts
			if not account[3]
		]

		finance_costs_adjustments = [
			dict(
				name=account[0],
				account_name=account[9],
				label=account[1],
				is_finance_cost=account[5],
				is_finance_cost_adjustment=account[6],
			)
			for account in accounts
			if account[6]
		]

		asset_purchases = [
			dict(
				name=account[0],
				account_name=account[9],
				label=account[1],
				is_asset_purchase=account[7],
			)
			for account in accounts
			if account[7]
		]

		asset_sales = [
			dict(
				name=account[0],
				account_name=account[9],
				label=account[1],
				is_asset_purchase=account[8],
			)
			for account in accounts
			if account[8]
		]

		tax_liabilities = [
			dict(
				name=account[0],
				account_name=account[9],
				label=account[1],
				is_income_tax_liability=account[3],
				is_income_tax_expense=account[4],
			)
			for account in accounts
			if account[3]
		]

		tax_expenses = [
			dict(
				name=account[0],
				account_name=account[9],
				label=account[1],
				is_income_tax_liability=account[3],
				is_income_tax_expense=account[4],
			)
			for account in accounts
			if account[4]
		]

		finance_costs = [
			dict(name=account[0], account_name=account[9], label=account[1], is_finance_cost=account[5])
			for account in accounts
			if account[5]
		]

		account_types_labels = sorted(
			set(
				(
					d["label"],
					d["is_working_capital"],
					d["is_income_tax_liability"],
					d["is_income_tax_expense"],
				)
				for d in account_types
			),
			key=lambda x: x[1],
		)

		fc_adjustment_labels = sorted(
			set(
				[
					(d["label"], d["is_finance_cost"], d["is_finance_cost_adjustment"])
					for d in finance_costs_adjustments
					if d["is_finance_cost_adjustment"]
				]
			),
			key=lambda x: x[2],
		)

		unique_liability_labels = sorted(
			set(
				[
					(d["label"], d["is_income_tax_liability"], d["is_income_tax_expense"])
					for d in tax_liabilities
				]
			),
			key=lambda x: x[0],
		)

		unique_expense_labels = sorted(
			set(
				[(d["label"], d["is_income_tax_liability"], d["is_income_tax_expense"]) for d in tax_expenses]
			),
			key=lambda x: x[0],
		)

		unique_finance_costs_labels = sorted(
			set([(d["label"], d["is_finance_cost"]) for d in finance_costs]), key=lambda x: x[0]
		)

		for label in account_types_labels:
			names = [d["account_name"] for d in account_types if d["label"] == label[0]]
			m = dict(label=label[0], names=names, is_working_capital=label[1])
			mapping["account_types"].append(m)

		for label in fc_adjustment_labels:
			names = [d["account_name"] for d in finance_costs_adjustments if d["label"] == label[0]]
			m = dict(label=label[0], names=names)
			mapping["finance_costs_adjustments"].append(m)

		for label in unique_liability_labels:
			names = [d["account_name"] for d in tax_liabilities if d["label"] == label[0]]
			m = dict(label=label[0], names=names, tax_liability=label[1], tax_expense=label[2])
			mapping["tax_liabilities"].append(m)

		for label in unique_expense_labels:
			names = [d["account_name"] for d in tax_expenses if d["label"] == label[0]]
			m = dict(label=label[0], names=names, tax_liability=label[1], tax_expense=label[2])
			mapping["tax_expenses"].append(m)

		for label in unique_finance_costs_labels:
			names = [d["account_name"] for d in finance_costs if d["label"] == label[0]]
			m = dict(label=label[0], names=names, is_finance_cost=label[1])
			mapping["finance_costs"].append(m)

		cash_flow_accounts.append(mapping)

	return cash_flow_accounts


def add_data_for_operating_activities(
	filters, company_currency, profit_data, period_list, light_mappers, mapper, data
):
	has_added_working_capital_header = False
	section_data = []

	data.append(
		{
			"account_name": mapper["section_header"],
			"parent_account": None,
			"indent": 0.0,
			"account": mapper["section_header"],
		}
	)

	if profit_data:
		profit_data.update(
			{"indent": 1, "parent_account": get_mapper_for(light_mappers, position=1)["section_header"]}
		)
		data.append(profit_data)
		section_data.append(profit_data)

		data.append(
			{
				"account_name": mapper["section_leader"],
				"parent_account": None,
				"indent": 1.0,
				"account": mapper["section_leader"],
			}
		)

	for account in mapper["account_types"]:

		if account["is_working_capital"] and not has_added_working_capital_header:
			data.append(
				{
					"account_name": "Movement in working capital",
					"parent_account": None,
					"indent": 1.0,
					"account": "",
				}
			)
			has_added_working_capital_header = True

		if account["label"] == 'Tax Paid':
			account_data = _get_account_tax_based_data(
			filters, account["names"], period_list
		)
		else:
			account_data = _get_account_type_based_data(
				filters, account["names"], period_list, filters.accumulated_values
			)

		if not account["is_working_capital"]:
			
			for key in account_data:
				if key != "total":
					account_data[key] *= -1

		if account_data["total"] != 0:
			print(f"MAPPERSECTION {mapper['section_header']}")
			account_data.update(
				{
					"account_name": account["label"],
					"account": account["names"],
					"indent": 1.0,
					"parent_account": mapper["section_header"],
					"currency": company_currency,
				}
			)
			data.append(account_data)
			section_data.append(account_data)
		
			

	_add_total_row_account(
		data, section_data, mapper["section_subtotal"], period_list, company_currency, indent=1
	)

	# calculate adjustment for tax paid and add to data
	if not mapper["tax_liabilities"]:
		mapper["tax_liabilities"] = [
			dict(label="Income tax paid", names=[""], tax_liability=1, tax_expense=0)
		]

	for account in mapper["tax_liabilities"]:
		tax_paid = calculate_adjustment(
			filters,
			mapper["tax_liabilities"],
			mapper["tax_expenses"],
			filters.accumulated_values,
			period_list,
		)

		if tax_paid:
			tax_paid.update(
				{
					"parent_account": mapper["section_header"],
					"currency": company_currency,
					"account_name": account["label"],
					"indent": 1.0,
				}
			)
			data.append(tax_paid)
			section_data.append(tax_paid)

	if not mapper["finance_costs_adjustments"]:
		mapper["finance_costs_adjustments"] = [dict(label="Interest Paid", names=[""])]

	for account in mapper["finance_costs_adjustments"]:
		interest_paid = calculate_adjustment(
			filters,
			mapper["finance_costs_adjustments"],
			mapper["finance_costs"],
			filters.accumulated_values,
			period_list,
		)

		if interest_paid:
			interest_paid.update(
				{
					"parent_account": mapper["section_header"],
					"currency": company_currency,
					"account_name": account["label"],
					"indent": 1.0,
				}
			)
			data.append(interest_paid)
			section_data.append(interest_paid)

	

	_add_total_row_account(data, section_data, mapper["section_footer"], period_list, company_currency)


def calculate_adjustment(filters, non_expense_mapper, expense_mapper, use_accumulated_values, period_list):
	liability_accounts = [d["names"] for d in non_expense_mapper]
	expense_accounts = [d["names"] for d in expense_mapper]

	non_expense_closing = _get_account_type_based_data(filters, liability_accounts, period_list, 0)

	non_expense_opening = _get_account_type_based_data(
		filters, liability_accounts, period_list, use_accumulated_values, opening_balances=1
	)

	expense_data = _get_account_type_based_data(
		filters, expense_accounts, period_list, use_accumulated_values
	)

	data = _calculate_adjustment(non_expense_closing, non_expense_opening, expense_data)
	return data


def _calculate_adjustment(non_expense_closing, non_expense_opening, expense_data):
	account_data = {}
	for month in non_expense_opening.keys():
		if non_expense_opening[month] and non_expense_closing[month]:
			account_data[month] = (
				non_expense_opening[month] - expense_data[month] + non_expense_closing[month]
			)
		elif expense_data[month]:
			account_data[month] = expense_data[month]

	return account_data


def add_data_for_other_activities(
	filters, company_currency, profit_data, period_list, light_mappers, mapper_list, data
):
	print(f"MAPPERLIST,{mapper_list}\n")
	for mapper in mapper_list:
			
		if mapper['section_name'] == 'Investing Activities':
			section_data = []
			data.append(
				{
					"account_name": mapper["section_header"],
					"parent_account": None,
					"indent": 0.0,
					"account": mapper["section_header"],
				}
			)

			for account in mapper["account_types"]:
				if account["label"] == 'Purchase of fixed Assets':
					account_data = _get_account_asset_based_data(
					filters, account["names"], period_list, 'purchase'
				)
				else:
					account_data = _get_account_type_based_data(
					filters, account["names"], period_list, filters.accumulated_values
				)
					
				try:
					if account_data["total"] != 0:
						account_data.update(
							{
								"account_name": account["label"],
								"account": account["names"],
								"indent": 1,
								"parent_account": mapper["section_header"],
								"currency": company_currency,
							}
						)
						data.append(account_data)
						section_data.append(account_data)
				except:
					print(f"NO TOTAL {account}")

			_add_total_row_account(data, section_data, mapper["section_footer"], period_list, company_currency)
		else:
			section_data = []
			data.append(
				{
					"account_name": mapper["section_header"],
					"parent_account": None,
					"indent": 0.0,
					"account": mapper["section_header"],
				}
			)

			for account in mapper["account_types"]:
				account_data = _get_account_type_based_data(
					filters, account["names"], period_list, filters.accumulated_values
				)
				print(f"ACCOUNTDATA {account_data}")
				try:
					if account_data["total"] != 0:
						account_data.update(
							{
								"account_name": account["label"],
								"account": account["names"],
								"indent": 1,
								"parent_account": mapper["section_header"],
								"currency": company_currency,
							}
						)
						data.append(account_data)
						section_data.append(account_data)
				except:
					print(f"NO TOTAL {account}")

			_add_total_row_account(data, section_data, mapper["section_footer"], period_list, company_currency)


def compute_data(filters, company_currency, profit_data, period_list, light_mappers, full_mapper):
	data = []

	operating_activities_mapper = get_mapper_for(light_mappers, position=1)
	other_mappers = [
		get_mapper_for(light_mappers, position=2),
		get_mapper_for(light_mappers, position=3),
	]

	if operating_activities_mapper:
		add_data_for_operating_activities(
			filters,
			company_currency,
			profit_data,
			period_list,
			light_mappers,
			operating_activities_mapper,
			data,
		)

	if all(other_mappers):
		add_data_for_other_activities(
			filters, company_currency, profit_data, period_list, light_mappers, other_mappers, data
		)

	return data


def execute(filters=None):
	if not filters.periodicity:
		filters.periodicity = "Monthly"
	period_list = get_period_list(
		filters.from_fiscal_year,
		filters.to_fiscal_year,
		filters.period_start_date,
		filters.period_end_date,
		filters.filter_based_on,
		filters.periodicity,
		company='Kartoza (Pty) Ltd',
	)

	mappers = get_mappers_from_db()

	cash_flow_accounts = setup_mappers(mappers)

	# compute net profit / loss
	income = get_data(
		'Kartoza (Pty) Ltd',
		"Income",
		"Credit",
		period_list,
		filters=filters,
		accumulated_values=filters.accumulated_values,
		ignore_closing_entries=True,
		ignore_accumulated_values_for_fy=True,
	)

	expense = get_data(
		'Kartoza (Pty) Ltd',
		"Expense",
		"Debit",
		period_list,
		filters=filters,
		accumulated_values=filters.accumulated_values,
		ignore_closing_entries=True,
		ignore_accumulated_values_for_fy=True,
	)

	net_profit_loss = get_net_profit_loss(income, expense, period_list, 'Kartoza (Pty) Ltd')

	company_currency = frappe.get_cached_value("Company", 'Kartoza (Pty) Ltd', "default_currency")

	data = compute_data(filters, company_currency, net_profit_loss, period_list, mappers, cash_flow_accounts)

	_add_total_row_account(data, data, _("Net Change in Cash"), period_list, company_currency)
	columns = get_columns(filters.periodicity, period_list, filters.accumulated_values, 'Kartoza (Pty) Ltd')

	return columns, data


def _get_account_type_based_data(filters, account_names, period_list, accumulated_values, opening_balances=0):
	if not account_names or not account_names[0] or not isinstance(account_names[0], str):
		# only proceed if account_names is a list of account names
		return {}

	from erpnext.accounts.report.cash_flow.cash_flow import get_start_date

	company = 'Kartoza (Pty) Ltd'
	data = {}
	total = 0
	GLEntry = frappe.qb.DocType("GL Entry")
	Account = frappe.qb.DocType("Account")

	for period in period_list:
		start_date = get_start_date(period, accumulated_values, company)

		account_subquery = (
			frappe.qb.from_(Account)
			.where((Account.name.isin(account_names)) | (Account.parent_account.isin(account_names)))
			.select(Account.name)
			.as_("account_subquery")
		)

		if opening_balances:
			date_info = dict(date=start_date)
			months_map = {"Monthly": -1, "Quarterly": -3, "Half-Yearly": -6}
			years_map = {"Yearly": -1}

			if months_map.get(filters.periodicity):
				date_info.update(months=months_map[filters.periodicity])
			else:
				date_info.update(years=years_map[filters.periodicity])

			if accumulated_values:
				start, end = add_to_date(start_date, years=-1), add_to_date(period["to_date"], years=-1)
			else:
				start, end = add_to_date(**date_info), add_to_date(**date_info)

			start, end = get_date_str(start), get_date_str(end)

		else:
			start, end = start_date if accumulated_values else period["from_date"], period["to_date"]
			start, end = get_date_str(start), get_date_str(end)

		result = (
			frappe.qb.from_(GLEntry)
			.select(Sum(GLEntry.credit) - Sum(GLEntry.debit))
			.where(
				(GLEntry.company == company)
				& (GLEntry.posting_date >= start)
				& (GLEntry.posting_date <= end)
				& (GLEntry.voucher_type != "Period Closing Voucher")
				& (GLEntry.account.isin(account_subquery))
			)
		).run()

		if result and result[0]:
			gl_sum = result[0][0]
		else:
			gl_sum = 0

		total += flt(gl_sum)
		data.setdefault(period["key"], flt(gl_sum))

	data["total"] = total
	return data


def _get_account_asset_based_data(filters, account_names, period_list, type):
	if not account_names or not account_names[0] or not isinstance(account_names[0], str):
		# only proceed if account_names is a list of account names
		return {}

	from erpnext.accounts.report.cash_flow.cash_flow import get_start_date
	total = 0
	company = 'Kartoza (Pty) Ltd'
	data = {}

	for period in period_list:
		start, end = period["from_date"], period["to_date"]
		start, end = get_date_str(start), get_date_str(end)

		if type == 'purchase':
			print(f'account_names {account_names}')
			# Convert list to a comma-separated string for the SQL query
			placeholders = ', '.join([f"'{name}'" for name in account_names])
			print(f"PLACEHOLDER {placeholders}")

			sql = f"""
				SELECT 
					SUM(pi.base_grand_total) as `total`
				FROM 
					`tabPurchase Invoice` pi
				JOIN 
					`tabPurchase Invoice Item` pii
					ON pi.name = pii.parent
				WHERE 
					pii.expense_account IN ({placeholders})
					AND pi.docstatus = 1
					AND pi.status = 'Paid'
					AND pi.posting_date BETWEEN '{start}' AND '{end}'
					AND pi.company = 'Kartoza (Pty) Ltd'
				ORDER BY 
					pi.posting_date DESC;
				"""
			result = frappe.db.sql(sql, as_dict=1, debug=1)

			data.setdefault(period["key"], -flt(result[0]['total']))
			total += -flt(result[0]['total']) 

	data["total"] = total
	return data


def _get_account_tax_based_data(filters, account_names, period_list):
	###TO DO: to get tax paid use account 2608 - Taxation : Balance Sheet - K in gl. (Sum all totals in debit) - (Sum total in credit column if account against is bank account)
	if not account_names or not account_names[0] or not isinstance(account_names[0], str):
		# only proceed if account_names is a list of account names
		return {}

	from erpnext.accounts.report.cash_flow.cash_flow import get_start_date
	total = 0
	company = 'Kartoza (Pty) Ltd'
	data = {}

	for period in period_list:
		start, end = period["from_date"], period["to_date"]
		start, end = get_date_str(start), get_date_str(end)

		sql = f"""
			SELECT 
				SUM(tge.debit - credit) as `total`
			FROM `tabGL Entry` tge
			WHERE tge.account  = '2608 - Taxation : Balance Sheet - K'
			AND tge.against IN ('62483083293 - FNB Business - K', 'SARS', '2606 - Dividends Payable - K, 3009 - Dividends Declared - K')
			AND tge.company = '{company}'
			AND tge.posting_date BETWEEN '{start}' AND '{end}'

		"""

		result = frappe.db.sql(sql, as_dict=1, debug=1)

		data.setdefault(period["key"], flt(result[0]['total']))
		total += flt(result[0]['total']) 

	data["total"] = total
	return data



def _add_total_row_account(out, data, label, period_list, currency, indent=0.0):
	
	total_row = {
		"indent": indent,
		"account_name": "'" + _("{0}").format(label) + "'",
		"account": "'" + _("{0}").format(label) + "'",
		"currency": currency,
	}
	for row in data:
		if row.get("parent_account"):
			for period in period_list:
				total_row.setdefault(period.key, 0.0)
				total_row[period.key] += row.get(period.key, 0.0)

			total_row.setdefault("total", 0.0)
			total_row["total"] += row["total"]

	out.append(total_row)
	out.append({})
