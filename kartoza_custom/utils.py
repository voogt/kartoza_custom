from datetime import datetime
import frappe
from dateutil.relativedelta import relativedelta
from collections import defaultdict

@frappe.whitelist()
def export_report_to_text(start_date, end_date, transaction_year):

    # Define the input and output date formats
    input_format = "%d/%m/%Y"
    input_format_b = "%Y-%m-%d"
    output_format = "%Y%m"  # CCYYMM format

    start = start_date
    end = end_date
    employer_paye_num = 7580786665
    certifcate_num_period = "31/08/2025"

    date_object_start = datetime.strptime(start, input_format_b)
    date_object_end = datetime.strptime(end, input_format_b)
    
    certificate_num_transaction_date = datetime.strptime(certifcate_num_period, input_format).strftime(output_format)
    
    #add int to end of this for employee certificate_num
    certificate_num = f"{employer_paye_num}{certificate_num_transaction_date}VIPL000100000"

    period_recon = datetime.strptime(end, input_format_b).strftime(output_format)

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
               COALESCE( SUM(tcc.amount), 0 )
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
    """

    employee_dict = frappe.db.sql(sql, as_dict=True)
    tracker = 1

    _6020 = 0

    for employee in employee_dict:
        _3010 = f"{certificate_num}{tracker}"
        
        if employee["custom_country_code"] == 'ZA':
            _3015 = "IRP5"
        else:
            _3015 = 'IT3(a)'

        
        _3020 = 'A'
        _3025 = transaction_year
        _3030 = employee["last_name"]
        _3040 = employee["first_name"]
        _3050 = get_initials(employee["first_name"])
        _3060 = employee["id_number"]
        _3080 = str(employee["date_of_birth"]).replace('-', '')
        _3100 = employee["tax_payroll_number"]
        _3263 = 46510
        _3125 = employee['company_email']
        _3135 = employee["cell_number"]
        _3136 = employee["cell_number"]
        _3138 = employee["cell_number"]
        _3144 = employee["custom_unit_number"]
        _3145 = employee["custom_complex"]
        _3146 = employee["custom_street_number"]
        _3147 = employee["custom_street_name"]
        _3148 = employee["custom_suburbdistrict"]
        _3149 = employee["custom_citytown"]
        _3150 = employee["custom_postal_code"]
        _3151 = employee["custom_country_code"]
        _3160 = employee["employee"]
        _3170 = datetime.strptime(start, input_format_b).strftime(output_format)
        _3180 = datetime.strptime(end, input_format_b).strftime(output_format)
        _3190 = datetime.strptime(str(employee['date_of_joining']), input_format_b).strftime(output_format)
        _3195 = "N"
        _3285 = employee["custom_country_code"]
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
        _3601 = employee["gross_pay"]
        _3699 = employee["gross_pay"]
        _4102 = employee['paye']
        _4141 = float(employee['emp_uif']) + float(employee['company_uif'])
        _4142 = employee['company_uif']
        _4149 = _4141 + float(_4102) + float(_4142)
        if employee["custom_employee_qualifies_for_eti"] == 1:
            _3026 = 'Y'
            _4150 = '02'

            sql = f"""
                SELECT 
                    tss.posting_date,
                    COALESCE(tsd.amount, 0) AS `Minimum_monthly_wage`,
                    SUM(COALESCE(tt.total_hours, 0)) AS `Actual_Hours_per_Month`,
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
                3020,_3020,
                3025,_3025,
                3030,_3030,
                3040,_3040,
                3050,_3050,
                3060,_3060,
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
                4102,_4102,
                4141,_4141,
                4142,_4142,
                4149,_4149])

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
                print(f"ETIDICT {eti}")
                _4118 = _4118 + eti['calculated_incentive']
                posting_date_obj = datetime.strptime(str(eti['posting_date']), input_format_b)
                month_year_key = (posting_date_obj.year, posting_date_obj.month)
                eti_grouped_by_month[month_year_key].append(eti)

            current_date = date_object_start
            num_track = 0
            
            while current_date <= date_object_end:
                _7006.append(current_date.month)
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
        
            output_lines.append([
                3010,_3010,
                3015,_3015,
                3020,_3020,
                3025,_3025,
                3030,_3030,
                3040,_3040,
                3050,_3050,
                3060,_3060,
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
                4102,_4102,
                4141,_4141,
                4142,_4142,
                4149,_4149,
                9999])

        tracker = tracker + 1

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
                result.append(", ".join(map(str, current_line)))
                current_line = []  # Reset for the next line
            else:
                current_line.append(item)

    # Add any remaining items in the current line
    if current_line:
        result.append(", ".join(map(str, current_line)))

    return "\n".join(result)


def get_initials(name):
    # Split the first name by spaces
    words = name.split()
    # Get the first letter of each word and join them in uppercase
    initials = ''.join(word[0].upper() for word in words if word)
    return initials

