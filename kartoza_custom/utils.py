from datetime import datetime
import frappe
from dateutil.relativedelta import relativedelta
from collections import defaultdict
from frappe.utils.global_search import search as default_search
import requests
from frappe.utils import flt
from kartoza_custom.country_codes import country_codes
from frappe.utils import now_datetime
import re
import unicodedata

def get_country_code_by_name(country_name):
    try:
        country = frappe.get_doc("Country", country_name)
        return country.code.upper()
    except frappe.DoesNotExistError:
        frappe.throw(f"Country '{country_name}' not found.")
    except Exception as e:
        frappe.throw(f"An error occurred: {str(e)}")

def is_approx_six_or_twelve_months_apart(date1_str, date2_str):
    date1 = datetime.strptime(date1_str, "%Y-%m-%d")
    date2 = datetime.strptime(date2_str, "%Y-%m-%d")

    delta_days = abs((date2 - date1).days)
    months = delta_days / 30.44  # average month length

    if 5.5 <= months <= 6.5:
        return '02'
    if 11.5 <= months <= 12.5:
        return '03'
    
def is_valid_sa_id(id_number: str) -> bool:
    if len(id_number) != 13 or not id_number.isdigit():
        return False

    # Check valid date
    try:
        birth_date = datetime.strptime(id_number[:6], "%y%m%d")
    except ValueError:
        return False

    # Luhn algorithm
    def luhn_checksum(number):
        digits = list(map(int, number))
        sum_ = 0
        alt = False
        for i in range(len(digits) - 1, -1, -1):
            d = digits[i]
            if alt:
                d *= 2
                if d > 9:
                    d -= 9
            sum_ += d
            alt = not alt
        return sum_ % 10 == 0

    return luhn_checksum(id_number)
    
def normalize_text(text):
    # Step 1: Normalize and remove accents
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ASCII', 'ignore').decode('utf-8')
    
    # Step 2: Remove special characters (keep only alphanumerics and spaces)
    text = re.sub(r'[^A-Za-z0-9 ]+', '', text)
    
    return text

def normalize_number(number):
    number = str(number).strip()
    if number.startswith('+27'):
        return '0' + number[3:]
    elif number.startswith('27'):
        return '0' + number[2:]
    return number

@frappe.whitelist()
def update_exchange_rate_and_amount():
    """
    Update exchange rate and opportunity amount for all opportunities
    if the company currency differs from the opportunity currency using Frankfurter API.
    """
    opportunities = frappe.get_all(
        "Opportunity",
        fields=["name", "company", "currency", "opportunity_amount"],
        filters={"status": ["!=", "Closed"]}
    )
    
    for opp in opportunities:
        # Fetch the Opportunity document
        doc = frappe.get_doc("Opportunity", opp.name)
        
        # Get company currency
        company_currency = frappe.db.get_value("Company", doc.company, "default_currency")

        # Ensure currencies are present
        if not company_currency or not doc.currency:
            frappe.throw(f"Company currency or Opportunity currency is missing for Opportunity {doc.name}.")

        # If the currencies are the same, no need to update
        if company_currency == doc.currency:
            continue

        # Fetch the exchange rate from Frankfurter API
        api_url = f"https://api.frankfurter.app/latest?from={company_currency}&to={doc.currency}"
        response = requests.get(api_url)

        if response.status_code != 200:
            frappe.throw(f"Failed to fetch exchange rate for Opportunity {doc.name}. Please try again later.")

        # Extract the exchange rate
        exchange_rate = response.json().get("rates", {}).get(doc.currency)
        if not exchange_rate:
            frappe.throw(f"Exchange rate not found for {company_currency} to {doc.currency} for Opportunity {doc.name}.")

        # Update the exchange rate and recalculate the opportunity amount
        doc.conversion_rate = flt(exchange_rate)
        doc.base_opportunity_amount = flt(doc.opportunity_amount) * flt(exchange_rate)

        # Save the updated fields
        try:
            doc.flags.ignore_validate_update_after_submit = True
            doc.save()
        except:
            pass


@frappe.whitelist()
def export_report_to_text(start_date, end_date, transaction_year):

    # Define the input and output date formats
    input_format = "%d/%m/%Y"
    input_format_b = "%Y-%m-%d"
    output_format_ymd = "%Y%m%d"  # CCYYMM format
    output_format_ym = "%Y%m" 

    start = start_date
    end = end_date
    employer_paye_num = 7580786665
    certifcate_num_period = "31/08/2025"

    date_object_start = datetime.strptime(start, input_format_b)
    date_object_end = datetime.strptime(end, input_format_b)

    recon_period = is_approx_six_or_twelve_months_apart(start, end)
    
    certificate_num_transaction_date = datetime.strptime(end, input_format_b).strftime(output_format_ym)
    
    #add int to end of this for employee certificate_num
    certificate_num = f"{employer_paye_num}{certificate_num_transaction_date}VIPL0000000"

    period_recon = datetime.strptime(end, input_format_b).strftime(output_format_ym)

    output_lines = []

    employer_details = [2010,"Kartoza (Pty) Ltd", 2015, "LIVE", 2020, employer_paye_num, 2022,"L580786665", 2024,"U580786665",2025,"Rian",2036,"Myburgh",2026,"0219811979",2027,"rian@mstgroup.co.za",2028,"ERPNext",2029,"ERPNext",2030,transaction_year,2031,period_recon,2081,"ZA",2037,"N",2063,"2",2064,"Fir Street Block B",2065,"North Park",2066,"Observatory",2080,7925,2082,46510,9999 ]
    
    output_lines.append(employer_details)

    sql = f"""
        SELECT 
            te.name as `employee`, 
            te.first_name as `first_name`, 
            te.last_name as `last_name`, 
            te.date_of_birth as `date_of_birth`, 
            te.date_of_joining as `date_of_joining`,
            te.tax_payroll_number as `tax_payroll_number`,
            te.company_email as `company_email`, 
            te.personal_email as `personal_email`,
            te.cell_number as `cell_number`,
            te.id_number as `id_number`, 
            te.passport_number as `passport_number`, 
            te.current_address as `current_address`,
            te.custom_unit_number,
            te.custom_complex,
            te.custom_street_number,
            te.custom_street_name,
            te.custom_suburbdistrict,
            te.custom_citytown,
            te.custom_postal_code,
            te.status as `employee_status`,
            te.relieving_date,
            te.custom_earns_prescribed_minimum_wage,
            te.custom_earns_national_minimum_wage,
            te.custom_employee_qualifies_for_eti,
            te.custom_special_economic_zone,
            te.custom_designated_industry,
            te.custom_connected_person,
            te.custom_domestic_worker,
            te.custom_labour_broker,
            te.custom_independent_contractor,
            te.custom_employed_1_october_2013,
            te.custom_id_number_or_asylum_seeker_permit,
            thl.custom_country_code as `custom_country_code`,
            te.custom_country_of_issue as `custom_country_of_issue`,
            -- Subquery for gross pay
            (SELECT 
                COALESCE(SUM(tss.gross_pay), 0) as `gross_pay`
            FROM 
                `tabSalary Slip` tss 
            WHERE 
                tss.employee = te.employee 
                AND tss.posting_date BETWEEN '{start}' AND '{end}'
            ) AS gross_pay,
            -- Subquery for PAYE
            (SELECT 
                COALESCE(SUM(tsd.amount), 0)
            FROM 
                `tabSalary Slip` tss
            INNER JOIN 
                `tabSalary Detail` tsd ON tss.name = tsd.parent
            WHERE 
                tss.employee = te.employee 
                AND tsd.salary_component = '4102 PAYE'
                AND tss.posting_date BETWEEN '{start}' AND '{end}'
            ) AS paye,
            -- Subquery for Employee UIF contributions
            (SELECT 
                COALESCE(SUM(tsd.amount), 0 )
            FROM 
                `tabSalary Slip` tss
            INNER JOIN 
                `tabSalary Detail` tsd ON tss.name = tsd.parent
            WHERE 
                tss.employee = te.employee 
                AND tsd.salary_component = '4141 UIF Employee and Employer Contributions'
                AND tss.posting_date BETWEEN '{start}' AND '{end}'
            ) AS emp_uif,
            -- Subquery for Company UIF contributions
            (SELECT 
                COALESCE(SUM(tcc.amount), 0 )
            FROM 
                `tabSalary Slip` tss
            INNER JOIN 
                `tabCompany Contribution` tcc ON tss.name = tcc.parent
            WHERE 
                tss.employee = te.employee 
                AND tcc.salary_component = '4141 UIF Employee and Employer Contributions'
                AND tss.posting_date BETWEEN '{start}' AND '{end}'
            ) AS company_uif
        FROM 
            `tabEmployee` te
        LEFT JOIN 
            `tabHoliday List` thl ON te.holiday_list = thl.name
        WHERE 
            te.custom_include_payroll_report = 1
            AND te.date_of_joining <= '{start}'
            AND EXISTS (
                SELECT 1 FROM `tabSalary Slip` tss
                WHERE tss.employee = te.name
                AND tss.posting_date BETWEEN '{start}' AND '{end}'
            )
    """


    employee_dict = frappe.db.sql(sql, as_dict=True)
    tracker = 0

    _6020 = 0

    for employee in employee_dict:
        tracker += 1
        formatted_tracker = f"{tracker:03d}"
        _3010 = f"{certificate_num}{formatted_tracker}"
        _3135 = employee["cell_number"].replace('+', '').replace(' ', '').replace('-', '')

        if employee["custom_country_of_issue"] != None:
            country_code = get_country_code_by_name(employee["custom_country_of_issue"])
            _3151 = country_code
            _3075 = country_codes.get(country_code) 
        else:
            _3075 = country_codes.get(employee["custom_country_code"])
            _3151 = employee["custom_country_code"]

        
        if _3075 == 'ZAF':
            _3015 = "IRP5"
            _4102 = employee['paye']
            _3135 = normalize_number(_3135)
            
        else:
            _3015 = 'IT3(a)'
            _4102 = 0
            _3135 = f"00{_3135}"

        
        
        _3020 = 'A'
        _3025 = transaction_year
        _3030 = normalize_text(employee["last_name"])
        _3040 = normalize_text(employee["first_name"])
        _3050 = get_initials(employee["first_name"])
        _3060 = employee["id_number"]
        _3070 = employee["id_number"] if employee["id_number"] != None else employee["passport_number"].replace(' ', '')
        _3080 = str(employee["date_of_birth"]).replace('-', '')
        _3100 = employee["tax_payroll_number"]
        _3263 = 46510
        _3125 = employee['company_email'] if employee['company_email'] != None else employee['personal_email']
        _3136 = _3135
        _3138 = _3135
        _3144 = employee["custom_unit_number"]
        _3145 = employee["custom_complex"]
        _3146 = employee["custom_street_number"]
        _3147 = employee["custom_street_name"]
        _3148 = employee["custom_suburbdistrict"]
        _3149 = employee["custom_citytown"]
        _3150 = employee["custom_postal_code"]
        _3151 = _3151
        _3160 = employee["employee"]
        _3170 = datetime.strptime(start, input_format_b).strftime(output_format_ymd)
        _3180 = datetime.strptime(end, input_format_b).strftime(output_format_ymd)
        _3190 = datetime.strptime(str(employee['date_of_joining']), input_format_b).strftime(output_format_ymd)
        _3195 = "N"
        _3285 = _3151
        _3200 = 12

        if employee["employee_status"] == 'Active':
            joining_obj = datetime.strptime(str(employee["date_of_joining"]), input_format_b)
            if joining_obj < date_object_start:
                _3210 = 6
            elif joining_obj > date_object_start:
                _3210 = (joining_obj.year - date_object_start.year) * 12 + (joining_obj.month - date_object_start.month)
        else:
            if employee["relieving_date"] and employee['relieving_date'] != None:
                relieve_obj = datetime.strptime(str(employee["relieving_date"]), input_format_b)
                if relieve_obj > date_object_start and relieve_obj < date_object_end:
                    _3210 = (date_object_end.year - relieve_obj.year) * 12 + (date_object_end.month - relieve_obj.month)

        _3220 = 'N'
        _3213 = employee["custom_street_number"]
        _3214 = employee["custom_street_name"]
        _3215 = employee["custom_suburbdistrict"]
        _3216 = employee["custom_citytown"]
        _3217 = employee["custom_postal_code"]
        _3279 = "N"
        _3240 = 0
        _3288 = 1
        _3601 = int(employee["gross_pay"])
        _3699 = int(employee["gross_pay"])
        
        _4141 = float(employee['emp_uif']) + float(employee['company_uif'])
        _4142 = employee['company_uif']
        _4149 = round(_4141 + float(_4102) + float(_4142), 2)
        _4150 = '02'

        if employee["custom_employee_qualifies_for_eti"] == 1:
            _3026 = 'Y'
            _3015 = 'IT3(a)'

            sql = f"""
                SELECT 
                    tss.posting_date,
                    2000 AS `Minimum_monthly_wage`,
                    160 AS `Actual_Hours_per_Month`,
                    COALESCE(tsd.amount, 0) AS `Actual_monthly_wage`,
                    COALESCE(tsd.amount, 0) AS `ETI_Remuneration`,
                    COALESCE(cast(tss.custom_monthly_eti as decimal(10,2)), 0) AS `calculated_incentive`
                FROM tabEmployee te 
                LEFT JOIN `tabSalary Slip` tss 
                    ON te.employee = tss.employee 
                LEFT JOIN `tabSalary Detail` tsd
                    ON tsd.parent = tss.name
                LEFT JOIN `tabTimesheet` tt
                    ON tt.employee  = tss.employee 
                WHERE te.employee = '{employee['employee']}'
                AND tsd.salary_component = '3601 Taxable Income Basic'
                AND tss.status = 'Submitted'
                AND tss.posting_date BETWEEN '{start_date}' AND '{end_date}'
                GROUP BY tss.posting_date, tsd.amount, tss.custom_monthly_eti;

            """
            _eti_dict = frappe.db.sql(sql, as_dict=1, debug=1)

            output_lines.append([
                3010,_3010,
                3015,_3015,
                4150,_4150,
                3020,_3020,
                3025,_3025,
                3030,_3030,
                3040,_3040,
                3050,_3050,
                3060,_3060,
                3075,_3075,
                3080,_3080,
                3100,_3100,
                3263,_3263,
                3125,_3125,
                3135,_3135,
                3136,_3136,
                3138,_3138,
                3144,_3144,
                3145,_3145,
                3146,_3146,
                3147,_3147,
                3148,_3148,
                3149,_3149,
                3150,_3150,
                3151,_3151,
                3160,_3160,
                3170,_3170,
                3180,_3180,
                3190,_3190,
                3195,_3195,
                3285,_3285,
                3200,_3200,
                3210,_3210,
                3220,_3220,
                3213,_3213,
                3214,_3214,
                3215,_3215,
                3216,_3216,
                3217,_3217,
                3279,_3279,
                3240,_3240,
                3288,_3288,
                3026,_3026,
                3601,_3601,
                3699,_3699,
                4141,_4141,
                4142,_4142,
                4149,_4149])
            
            # if employee["custom_employee_qualifies_for_eti"] == 1:
            #     output_lines.append([4150,_4150])
            
            _4118 = 0
            _7004 = []
            _7006 = []
            _7002 = []
            _7003 = []
            _7005 = []
            _7007 = []
            _7008 = []

            # Group entries in eti_dict by month and year
            eti_grouped_by_month = defaultdict(list)
            for eti in _eti_dict:
                _4118 = _4118 + eti['calculated_incentive']
                posting_date_obj = datetime.strptime(str(eti['posting_date']), input_format_b)
                month_year_key = (posting_date_obj.year, posting_date_obj.month)
                eti_grouped_by_month[month_year_key].append(eti)

            current_date = date_object_start
            num_track = 0
            
            while current_date <= date_object_end:
                month_str = f"{current_date.month:02d}"  # formats with leading zero
                _7006.append(month_str)
                month_year_key = (current_date.year, current_date.month)

                if month_year_key in eti_grouped_by_month:
                    # Process all ETI entries for the current month
                    for eti in eti_grouped_by_month[month_year_key]:
                        _7007.append(eti['Actual_Hours_per_Month'])
                        _7002.append(eti['Actual_monthly_wage'])
                        _7008.append(eti['Minimum_monthly_wage'])
                        _7005.append(1)
                        _7003.append(float(eti['Actual_Hours_per_Month']) / float(eti['Actual_Hours_per_Month']))
                        _7004.append(eti['calculated_incentive'])
                else:
                    # No entries for the current month
                    _7007.append(0)
                    _7002.append(0)
                    _7008.append(0)
                    _7005.append(0)
                    _7003.append(0)
                    _7004.append(0)

                num_track += 1
                current_date += relativedelta(months=1)

            output_lines.append([4118, _4118,])

            for i in range(num_track):
                output_lines.append([7006, _7006[i], 7002, _7002[i], 7003, _7003[i], 7004, _7004[i], 7005, _7005[i], 7007, _7007[i], 7008, _7008[i],])

            output_lines.append(9999)
            

        elif employee["custom_employee_qualifies_for_eti"] == 0:
            _3026 = 'N'
            if employee["id_number"] == '6610070015086':
                _3015 = 'IRP5'
        
            output_lines.append([
                3010,_3010,
                3015,_3015,
                3020,_3020,
                3025,_3025,
                3030,_3030,
                3040,_3040,
                3050,_3050,
                3075,_3075,
                3080,_3080,
                
                3263,_3263,
                3125,_3125,
                3135,_3135,
                3136,_3136,
                3138,_3138,
                3144,_3144,
                3145,_3145,
                3146,_3146,
                3147,_3147,
                3148,_3148,
                3149,_3149,
                3150,_3150,
                3151,_3151,
                3160,_3160,
                3170,_3170,
                3180,_3180,
                3190,_3190,
                3285,_3285,
                3200,_3200,
                3210,_3210,
                3213,_3213,
                3214,_3214,
                3215,_3215,
                3216,_3216,
                3217,_3217,
                3279,_3279,
                3240,_3240,
                3288,_3288,
                3026,_3026,
                3601,_3601,
                3699,_3699,
                4141,_4141,
                4142,_4142,
                4149,_4149,
                ])
            
            if _3075 != 'ZAF':
                if employee["id_number"] != '6610070015086':
                    output_lines.append(
                        [
                            4150,_4150,
                            3070,_3070
                        ]
                    )
                elif employee["id_number"] == '6610070015086':
                    output_lines.append(
                        [   
                            3070,_3070,
                            3195,_3195,
                            3220,_3220,
                            4102,_4102,
                            3060,_3060,
                            3100,_3100
                        ]
                    )
            else:
                output_lines.append(
                    [
                        3195,_3195,
                        3220,_3220,
                        4102,_4102,
                        3060,_3060,
                        3100,_3100
                    ]
                )
                
            output_lines.append(9999)

        

    _6010 = tracker + 1

    output_lines.append([6010, _6010, 9999])

    result = []
    current_line = []

    for sublist in output_lines:
        # Ensure sublist is a list
        if isinstance(sublist, (int, float, str)):
            sublist = [sublist]

        for item in sublist:
            if item == 9999:
                # Add the current line with 9999
                current_line.append(item)
                result.append(",".join(map(str, current_line)))
                current_line = []  # Reset for the next line
            else:
                current_line.append(item)

    # Add any remaining items in the current line
    if current_line:
        result.append(",".join(map(str, current_line)))

    for i, item in enumerate(result):
        array = item.split(",")
        updated_array = []
        for j, val in enumerate(array):
            if str(val) == "0" or str(val) == "0.0":
                if array[j - 1 ] != "3240" and array[j - 1] != '7005':
                    formatted_val = f"0.00"
                    updated_array.append(formatted_val)
                else:
                    updated_array.append(val)
            elif val == "None":
                updated_array.append(f'"{val}"')
            elif array[j - 1] == "3070":
                updated_array.append(f'"{val}"')
            elif is_number(val):
                if array[j - 1] == "3200" or array[j - 1] == "3210" or array[j - 1] == "7007":
                    formatted_val = f"{int(val):.4f}"
                    if val == "6":
                        formatted_val = f"0{formatted_val}"
                    updated_array.append(formatted_val)
                elif array[j - 1] == "4141" or array[j - 1] == "4142" or array[j - 1] == '7002' or array[j - 1] == '7003' or array[j - 1] == '7008' or array[j - 1] == '7004':
                    formatted_val = f"{float(val):.2f}"
                    updated_array.append(formatted_val)
                else:
                    updated_array.append(val)
            else:
                updated_array.append(f'"{val}"')
        result[i] = updated_array

    return "\n".join([",".join(map(str, row)) for row in result])

def is_number(val):
    try:
        float(val)
        return True
    except ValueError:
        return False

def get_initials(name):
    # Split the first name by spaces
    words = name.split()
    # Get the first letter of each word and join them in uppercase
    initials = ''.join(word[0].upper() for word in words if word)
    return initials


