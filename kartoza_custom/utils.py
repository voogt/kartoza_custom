from datetime import datetime
import frappe

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
            te.custom_street_number,
            te.custom_street_name,
            te.custom_suburbdistrict,
            te.custom_citytown,
            te.custom_postal_code,
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
            te.status = 'Active'
            AND te.custom_include_payroll_report = 1
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
        ### TODO CALCULATE NUMBER OF PERIODS EMPLOYEE ACTUALLY WORKED
        _3210 = 6
        _3220 = 'N'
        _3213 = employee["custom_street_number"]
        _3214 = employee["custom_street_name"]
        _3215 = employee["custom_suburbdistrict"]
        _3216 = employee["custom_citytown"]
        _3217 = employee["custom_postal_code"]
        ### TODO CHECK whether the postal address is a C/O, (Care of) postal address.
        _3279 = "N"
        ### TODO Check the type of employee bank account (everyone in txt is 0)
        _3240 = 0
        _3288 = 1
        _3026 = 'N'
        _3601 = employee["gross_pay"]
        _3699 = employee["gross_pay"]
        _4102 = employee['paye']
        _4141 = float(employee['emp_uif']) + float(employee['company_uif'])
        _4142 = employee['company_uif']
        _4149 = _4141 + float(_4102) + float(_4142)

        output_lines.append([3010,_3010,3015,_3015,3020,_3020,3025,_3025,3030,_3030,3040,_3040,3050,_3050,3060,_3060,3080,_3080,3100,_3100,3263,_3263,3125,_3125,3135,_3135,3136,_3136,3138,_3138,3146,_3146,3147,_3147,3148,_3148,3149,_3149,3150,_3150,3151,_3151,3160,_3160,3170,_3170,3180,_3180,3190,_3190,3195,_3195,3285,_3285,3200,_3200,3210,_3210,3220,_3220,3213,_3213,3214,_3214,3215,_3215,3216,_3216,3217,_3217,3279,_3279,3240,_3240,3288,_3288,3026,_3026,3601,_3601,3699,_3699,4102,_4102,4141,_4141,4142,_4142,4149,_4149,9999])

        tracker = tracker + 1

    _6010 = tracker + 1

    output_lines.append([6010, _6010, 9999])

    export_lines = []

    for line in output_lines:
        # Format each item in the line
        formatted_line = ','.join(
            f'"{item}"' if not isinstance(item, (int, float)) else str(item)
            for item in line
        )
        export_lines.append(formatted_line)

    # Return the formatted lines
    return '\n'.join(export_lines)



def get_initials(name):
    # Split the first name by spaces
    words = name.split()
    # Get the first letter of each word and join them in uppercase
    initials = ''.join(word[0].upper() for word in words if word)
    return initials

