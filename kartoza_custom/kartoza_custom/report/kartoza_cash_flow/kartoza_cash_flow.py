# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import datetime
import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import add_to_date, flt, get_date_str
from erpnext.accounts.report.financial_statements import get_columns, get_data, get_period_list
from erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement import (
	get_net_profit_loss,
)

from dateutil.relativedelta import relativedelta

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
			"indent": 0,
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
				"indent": 1,
				"account": mapper["section_leader"],
			}
		)

	for account in mapper["account_types"]:

		if account["is_working_capital"] and not has_added_working_capital_header:
			data.append(
				{
					"account_name": "Movement in working capital",
					"account": "Movement in working capital",
					"parent_account": None,
					"indent": 1,
				}
			)
			has_added_working_capital_header = True

		if account["label"] == 'Tax Paid':

			account_structure = _get_account_structure(period_list)
			account_data = account_structure

			income_tax = _get_account_type_based_data(
				filters, ['5300 - Income Tax - K'], period_list, 0
			)

			# Safely handle cases where current or previous fiscal year tax data is missing
			current_tax_list = get_tax_balance_data(period_list, filters, prev=False)
			current_tax_balance_data = current_tax_list[0] if current_tax_list else {}
			prev_tax_list = get_tax_balance_data(period_list, filters, prev=True)
			prev_tax_balance_data = prev_tax_list[0] if prev_tax_list else {}

			total = 0
			for key, value in account_structure.items():
				if key != 'total':
					key_parsed = extract_text_and_year(key)
					opening_balance = prev_tax_balance_data.get(f"{key_parsed['text']}_{key_parsed['year'] - 1}", 0)
					closing_balance = current_tax_balance_data.get(f"{key_parsed['text']}_{key_parsed['year']}", 0)
					diff = (opening_balance - closing_balance) - income_tax.get(key, 0)
					if income_tax[key] != 0:
						account_data[key] = diff
					else:
						account_data[key] = opening_balance
					total = total + account_data[key]
			account_data['total'] = total

		elif account["label"] == 'Dividends Paid':
			# Use standard GL aggregation per period (non-accumulated) for mapped dividend accounts
			account_data = _get_dividends_paid_data(
				filters, account["names"], period_list
			)
		else:
			# Always compute per-period (non-accumulated) values for cash flow rows
			account_data = _get_account_type_based_data(
				filters, account["names"], period_list, 0
			)

		if not account["is_working_capital"]:
			if account["label"] != 'Investment Income':
			# Invert period values for non-working-capital rows
				for key in list(account_data.keys()):
					if key != "total":
						account_data[key] = -flt(account_data.get(key, 0))
				# Recompute total to reflect inverted period values
				account_data["total"] = sum(flt(account_data.get(p["key"], 0)) for p in period_list)

		# Show the row if any period in the selected range has a non-zero value
		has_nonzero_period = any(flt(account_data.get(p["key"], 0)) != 0 for p in period_list)

		if has_nonzero_period or flt(account_data.get("total", 0)) != 0:
			account_data.update(
				{
					"account_name": f"{account['label']} ({', '.join(account['names'])})",
					"account": account['label'],
					"indent": 1,
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
	# if not mapper["tax_liabilities"]:
	# 	mapper["tax_liabilities"] = [
	# 		dict(label="Income tax paid", names=[""], tax_liability=1, tax_expense=0)
	# 	]

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
					"account": account['label'],
					"account_name": f"{account['label']} ({', '.join(account['names'])})",
					"indent": 1,
				}
			)
			data.append(tax_paid)
			section_data.append(tax_paid)

	# if not mapper["finance_costs_adjustments"]:
	# 	mapper["finance_costs_adjustments"] = [dict(label="Interest Paid", names=[""])]

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
					"account": account['label'],
					"account_name": f"{account['label']} ({', '.join(account['names'])})",
					"indent": 1,
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
	total = 0
	for month in non_expense_opening.keys():
		if month == "total":
			continue
		opening = non_expense_opening.get(month, 0) or 0
		closing = non_expense_closing.get(month, 0) or 0
		expense = expense_data.get(month, 0) or 0
		if opening or closing:
			account_data[month] = opening - expense + closing
		elif expense:
			account_data[month] = expense
		else:
			account_data[month] = 0
		total += account_data[month]

	account_data["total"] = total
	return account_data


def add_data_for_other_activities(
	filters, company_currency, profit_data, period_list, light_mappers, mapper_list, data
):
	for mapper in mapper_list:
			
		if mapper['section_name'] == 'Investing Activities':
			section_data = []
			data.append(
				{
					"account_name": mapper["section_header"],
					"parent_account": None,
					"indent": 0,
					"account": mapper["section_header"],
				}
			)

			for account in mapper["account_types"]:
				if account["label"] == 'Purchase of fixed Assets':
					account_data = _get_account_asset_based_data(
					filters, account["names"], period_list, 'purchase'
				)
				else:
					# Always compute per-period (non-accumulated) values
					account_data = _get_account_type_based_data(
					filters, account["names"], period_list, 0
				)
					
				try:
					if account_data["total"] != 0:
						account_data.update(
							{
								"account_name": f"{account['label']} ({', '.join(account['names'])})",
								"account": account['label'],
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
					"indent": 0,
					"account": mapper["section_header"],
				}
			)

			for account in mapper["account_types"]:
				# Always compute per-period (non-accumulated) values
				account_data = _get_account_type_based_data(
					filters, account["names"], period_list, 0
				)
				account_data.update(
					{
						"account_name": f"{account['label']} ({', '.join(account['names'])})",
						"account": account['label'],
						"indent": 1,
						"parent_account": mapper["section_header"],
						"currency": company_currency,
					}
				)
				data.append(account_data)
				section_data.append(account_data)

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

	data = [d for d in data if d]

	return columns, data


def _get_account_type_based_data(filters, account_names, period_list, accumulated_values, opening_balances=0):
	print(f"Getting account type based data for accounts: {account_names}")
	# Normalize account_names into a flat list of non-empty strings
	def _flatten_names(names):
		flat = []
		if not names:
			return flat
		if isinstance(names, str):
			names = [names]
		for n in names:
			if isinstance(n, str):
				if n.strip():
					flat.append(n.strip())
			elif isinstance(n, (list, tuple, set)):
				for m in n:
					if isinstance(m, str) and m.strip():
						flat.append(m.strip())
		# Deduplicate preserving order
		seen = set()
		deduped = []
		for n in flat:
			if n not in seen:
				seen.add(n)
				deduped.append(n)
		return deduped

	account_names = _flatten_names(account_names)
	if not account_names:
		zero = {period["key"]: 0 for period in period_list}
		zero["total"] = 0
		return zero


	from erpnext.accounts.report.cash_flow.cash_flow import get_start_date

	company = 'Kartoza (Pty) Ltd'
	data = {}
	total = 0
	GLEntry = frappe.qb.DocType("GL Entry")
	Account = frappe.qb.DocType("Account")

	# Expand to include all descendant accounts (full tree) for accurate aggregation
	if account_names:
		parents = frappe.db.get_all(
			"Account", filters={"name": ["in", account_names]}, fields=["name", "lft", "rgt"]
		)
		expanded = []
		for p in parents:
			children = frappe.db.get_all(
				"Account",
				filters=[["lft", ">=", p["lft"]], ["rgt", "<=", p["rgt"]]],
				fields=["name"],
			)
			expanded.extend([c["name"] for c in children])
		# Deduplicate while preserving order
		seen = set()
		expanded_names = []
		for n in expanded or account_names:
			if n not in seen:
				seen.add(n)
				expanded_names.append(n)
		account_names = expanded_names

	for period in period_list:
		start_date = get_start_date(period, accumulated_values, company)

		# Build simple IN list from expanded account names
		account_subquery = (
			frappe.qb.from_(Account)
			.where(Account.name.isin(account_names))
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
	# Normalize account names similarly to _get_account_type_based_data
	def _flatten_names(names):
		flat = []
		if not names:
			return flat
		if isinstance(names, str):
			names = [names]
		for n in names:
			if isinstance(n, str):
				if n.strip():
					flat.append(n.strip())
			elif isinstance(n, (list, tuple, set)):
				for m in n:
					if isinstance(m, str) and m.strip():
						flat.append(m.strip())
		# Deduplicate preserving order
		seen = set()
		deduped = []
		for n in flat:
			if n not in seen:
				seen.add(n)
				deduped.append(n)
		return deduped

	account_names = _flatten_names(account_names)
	if not account_names:
		zero = {period["key"]: 0 for period in period_list}
		zero["total"] = 0
		return zero

	total = 0
	company = 'Kartoza (Pty) Ltd'
	data = {}

	for period in period_list:
		start, end = period["from_date"], period["to_date"]
		start, end = get_date_str(start), get_date_str(end)

		if type == 'purchase':
			# Convert list to a comma-separated string for the SQL query
			placeholders = ', '.join([f"'{name}'" for name in account_names])

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
			print("Executing SQL for asset purchase:", sql)
			result = frappe.db.sql(sql, as_dict=1, debug=1)

			row_total = 0
			if result and isinstance(result, list) and result[0] and 'total' in result[0] and result[0]['total'] is not None:
				row_total = flt(result[0]['total'])

			data.setdefault(period["key"], -row_total)
			total += -row_total 

	data["total"] = total
	return data


def _get_account_structure(period_list):
    """
    Return the structure of tax-based data without fetching actual values.
    """
    data = {}
    total = 0

    for period in period_list:
        # Keep the period keys but set values to 0
        data.setdefault(period["key"], 0)

    data["total"] = total
    return data

def _get_account_tax_based_data(filters, account_names, period_list):
	###TO DO: to get tax paid use account 2608 - Taxation : Balance Sheet - K in gl. (Sum all totals in debit) - (Sum total in credit column if account against is bank account)
	# account_names are not strictly required here; compute directly from GL

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
			AND tge.against IN ('62483083293 - FNB Business - K', 'SARS', '2606 - Dividends Payable - K', '3009 - Dividends Declared - K')
			AND tge.company = '{company}'
			AND tge.posting_date BETWEEN '{start}' AND '{end}'

		"""

		result = frappe.db.sql(sql, as_dict=1, debug=1)

		row_total = 0
		if result and isinstance(result, list) and result[0] and 'total' in result[0] and result[0]['total'] is not None:
			row_total = flt(result[0]['total'])

		data.setdefault(period["key"], row_total)
		total += row_total 

	data["total"] = total
	return data


def _get_dividends_paid_data(filters, dividend_account_names, period_list):
	# Sum cash outflows where the bank account is debited/credited and against account is one of provided dividend accounts
	# dividend_account_names can be a list of strings or nested lists; flatten and dedupe
	def _flatten(names):
		flat = []
		if not names:
			return flat
		if isinstance(names, str):
			names = [names]
		for n in names:
			if isinstance(n, str):
				if n.strip():
					flat.append(n.strip())
			elif isinstance(n, (list, tuple, set)):
				for m in n:
					if isinstance(m, str) and m.strip():
						flat.append(m.strip())
		# dedupe preserve order
		seen = set()
		out = []
		for n in flat:
			if n not in seen:
				seen.add(n)
				out.append(n)
		return out

	dividend_accounts = _flatten(dividend_account_names)
	if not dividend_accounts:
		zero = {period["key"]: 0 for period in period_list}
		zero["total"] = 0
		return zero

	company = 'Kartoza (Pty) Ltd'
	data = {}
	total = 0

	# Build IN lists safely
	dividend_in = ", ".join([frappe.db.escape(d) for d in dividend_accounts])

	for period in period_list:
		start, end = get_date_str(period["from_date"]), get_date_str(period["to_date"])
		# We treat dividends paid as cash outflow from bank to dividends accounts.
		# Compute as sum(debit - credit) on the bank account lines where against is in the dividend accounts.

		sql = f"""
			SELECT 
				SUM(tge.credit - tge.debit) AS total
				FROM `tabGL Entry` tge
				JOIN `tabAccount` acc ON acc.name = tge.account
				WHERE tge.account IN ({dividend_in})
				AND (
					tge.against LIKE '%2606 - Dividends Payable - K%'
					OR tge.against LIKE '%3009 - Dividends Declared - K%'
					OR tge.against LIKE '%62483083293 - FNB Business - K%'
					OR tge.against LIKE '%1600 - Loan - Tim Sutton - K%'
					OR tge.against LIKE '%1612 - Loan - Gavin Fleming - K%'
				)
				AND tge.posting_date BETWEEN {frappe.db.escape(start)} AND {frappe.db.escape(end)}
		"""

		res = frappe.db.sql(sql, as_dict=1)
		val = flt(res[0]["total"]) if res and res[0] and res[0]["total"] is not None else 0
		data.setdefault(period["key"], val)
		total += val

	data["total"] = total
	return data



def _add_total_row_account(out, data, label, period_list, currency, indent=0):
	
	total_row = {
		"indent": indent,
		"account_name": _("{0}").format(label),
		"account": _("{0}").format(label),
		"currency": currency,
	}
	for row in data:
		if row.get("parent_account"):
			for period in period_list:
				total_row.setdefault(period.key, 0)
				total_row[period.key] += row.get(period.key, 0)

			total_row.setdefault("total", 0)
			total_row["total"] += row.get("total", 0)

	out.append(total_row)
	out.append({})


def get_tax_balance_data(
	period_list, filters, prev=True
):
	prev_period_list = get_previous_fiscal_year_from_period_list(filters)

	filters_mod = frappe._dict({
		'company': 'Kartoza (Pty) Ltd', 
		'filter_based_on': 'Fiscal Year', 
		'period_start_date': period_list[0]['year_start_date'].strftime('%Y-%m-%d'), 
		'period_end_date': period_list[0]['year_end_date'].strftime('%Y-%m-%d'), 
		'from_fiscal_year': filters.from_fiscal_year, 
		'to_fiscal_year': filters.to_fiscal_year, 
		'periodicity': 'Yearly', 
		'cost_center': [], 
		'employee_type': [], 
		'business_unit': [], 
		'project': [], 
		'selected_view': 'Report', 
		'accumulated_values': 1, 
		'include_default_book_entries': 1})
	
	final_list = None
	if prev:
		final_list = prev_period_list
	else:
		final_list = period_list

	liabilities = get_data(
		filters.company,
		"Liability",
		"Credit",
		final_list,
		only_current_fiscal_year=False,
		filters=filters_mod,
		accumulated_values=1,
	)

	tax_data = []

	for liability in liabilities:
		if liability.get('account') == '2608 - Taxation : Balance Sheet - K':
			tax_data.append(liability)

	return tax_data

def get_previous_fiscal_year_from_period_list(filters):
	print("Getting previous fiscal year period list", filters)
	test = {
		'company': 'Kartoza (Pty) Ltd', 
		'filter_based_on': 'Fiscal Year', 
		'period_start_date': '2025-03-01', 
		'period_end_date': '2026-02-28', 
		'from_fiscal_year': '2022-2023', 
		'to_fiscal_year': '2024-2025', 
		'periodicity': 'Yearly', 
		'cost_center': [], 
		'employee_type': [], 
		'business_unit': [], 
		'project': []
	}

	fiscal_start_year = get_fiscal_year_by_name(filters.from_fiscal_year)
	fiscal_end_year = get_fiscal_year_by_name(filters.to_fiscal_year)

	dt_start = fiscal_start_year.year_start_date
	dt_end = fiscal_end_year.year_end_date

	period_start = dt_start - relativedelta(years=1)
	period_end = subtract_year_adjust_feb(dt_end)

	# Resolve previous fiscal year names by exact boundary dates.
	from_fy_name = get_fiscal_start_year_by_date(period_start.strftime('%Y-%m-%d'))
	to_fy_name = get_fiscal_end_year_by_date(period_end.strftime('%Y-%m-%d'))

	# If the system only has one fiscal year (or boundaries don't match exactly),
	# safely return an empty list to signal "no previous period".
	if not from_fy_name or not to_fy_name:
		return []

	period_list = get_period_list(
		from_fy_name,
		to_fy_name,
		period_start.strftime('%Y-%m-%d'),
		period_end.strftime('%Y-%m-%d'),
		filters.filter_based_on,
		filters.periodicity,
		company='Kartoza (Pty) Ltd',
	)

	return period_list


def get_fiscal_year_by_name(name):
    """
    Fetch the Fiscal Year where a given name falls within its start and end dates.
    """
    fiscal_year = frappe.get_all(
        "Fiscal Year",
        filters={
            "name": ["=", name],
        },
        fields=["name", "year_start_date", "year_end_date"],
        limit_page_length=1
    )
    
    if fiscal_year:
        return fiscal_year[0]
    else:
        return None
	

def get_fiscal_start_year_by_date(date):
    """
    Fetch the Fiscal Year where a given date falls within its start and end dates.
    """
    fiscal_year = frappe.get_all(
        "Fiscal Year",
        filters={
            "year_start_date": ["=", date],
        },
        fields=["name"],
        limit_page_length=1
    )
    
    if fiscal_year:
        return fiscal_year[0]["name"]
    else:
        return None
	

def get_fiscal_end_year_by_date(date):
    """
    Fetch the Fiscal Year where a given date falls within its start and end dates.
    """
    fiscal_year = frappe.get_all(
        "Fiscal Year",
        filters={
            "year_end_date": ["=", date],
        },
        fields=["name"],
        limit_page_length=1
    )
    
    if fiscal_year:
        return fiscal_year[0]["name"]
    else:
        return None
	

def subtract_year_adjust_feb(dt_end):
    # Subtract one year
    new_date = dt_end - relativedelta(years=1)
    
    # If original date is February, adjust for leap year
    if dt_end.month == 2:
        year = new_date.year
        # Check if the new year is a leap year
        if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)):
            new_date = new_date.replace(day=29)
        else:
            new_date = new_date.replace(day=min(new_date.day, 28))
    
    return new_date

def extract_text_and_year(str):
	parts = str.split('_')
	
	if len(parts) == 2 and parts[1].isdigit():
		text, year = parts[0], int(parts[1])
	else:
		text, year = str, None
	return {'text': text, 'year': year}
