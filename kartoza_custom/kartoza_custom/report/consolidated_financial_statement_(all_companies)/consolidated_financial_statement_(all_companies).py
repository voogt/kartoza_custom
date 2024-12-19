import frappe
from frappe.utils import flt
import requests

def execute(filters=None):
    columns = get_columns(filters)
    data = get_data(filters)
    return columns, data

def get_columns(filters):
    return [
        {"label": "Account Number", "fieldname": "account_number", "fieldtype": "Data", "width": 120},
        {"label": "Account Name", "fieldname": "account_name", "fieldtype": "Data", "width": 150},
        {"label": "Company", "fieldname": "company", "fieldtype": "Data", "width": 150},
        {"label": f"Debit ({filters.get('currency')})", "fieldname": "debit", "fieldtype": "Float", "width": 100},
        {"label": f"Credit ({filters.get('currency')})", "fieldname": "credit", "fieldtype": "Float", "width": 100},
        {"label": f"Balance ({filters.get('currency')})", "fieldname": "balance", "fieldtype": "Float", "width": 100},
    ]

def get_data(filters):
    if not filters.get("start_date") or not filters.get("end_date"):
        frappe.throw("Please set both Start Date and End Date.")
    if not filters.get("currency"):
        frappe.throw("Please select a Currency.")

    target_currency = filters.get("currency")

    # Get account and company details
    accounts = frappe.get_all("Account", fields=["name", "account_number", "account_name", "company"])
    company_currencies = {
        company.name: company.default_currency
        for company in frappe.get_all("Company", fields=["name", "default_currency"])
    }

    account_map = {acc.name: acc for acc in accounts}

    # Query GL Entries within the date range
    gl_entries = frappe.db.sql("""
        SELECT
            account, company, SUM(debit) as debit, SUM(credit) as credit
        FROM `tabGL Entry`
        WHERE posting_date BETWEEN %(start_date)s AND %(end_date)s
        GROUP BY account, company
    """, filters, as_dict=True)

    data = []
    for entry in gl_entries:
        account = account_map.get(entry.account)
        if account:
            company_currency = company_currencies.get(entry.company)
            debit = convert_currency(entry.debit, company_currency, target_currency, filters)
            credit = convert_currency(entry.credit, company_currency, target_currency, filters)
            balance = flt(debit) - flt(credit)

            data.append({
                "account_number": account.account_number,
                "account_name": account.account_name,
                "company": entry.company,
                "debit": debit,
                "credit": credit,
                "balance": balance,
            })

    # Filter accounts shared across multiple companies
    shared_accounts = [
        acc["account_number"] for acc in data if len(set(d["company"] for d in data if d["account_number"] == acc["account_number"])) > 1
    ]

    return [d for d in data if d["account_number"] in shared_accounts]

import requests

def convert_currency(amount, company_currency, cur, filters):
    
    if company_currency == cur:
        print(f"COMPANY CURR YES {company_currency} to {cur}")
        return amount

    date = filters.get("end_date")
    base_url = "https://api.frankfurter.app"
    latest = "latest"
    conditions = 'base=ZAR&symbols=USD,EUR,CAD'
    
    default = f'{base_url}/{latest}?{conditions}'

    if date:
        api = f'{base_url}/{date}?{conditions}'
    else:
        api = default
    
    try:
        # Use requests to make the GET request
        response = requests.get(api)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)
        r = response.json()  # Parse the JSON response
        
        r = r["rates"]
        
        usd = 1 / r["USD"]
        eur = 1 / r["EUR"]
        cad = 1 / r["CAD"]
        
        if cur == "USD": 
            return usd * amount
        elif cur == "CAD": 
            return cad * amount 
        elif cur == "EUR": 
            return eur * amount
        else: 
            return amount
    except requests.RequestException as e:
        raise Exception(f"Error fetching currency data: {e}")
    except KeyError as e:
        raise Exception(f"Unexpected response structure: {e}")

