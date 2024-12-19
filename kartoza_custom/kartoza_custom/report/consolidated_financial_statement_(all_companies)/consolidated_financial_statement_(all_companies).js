// Copyright (c) 2024, Kartoza and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Consolidated Financial Statement (All Companies)"] = {
	filters: [
        {
            fieldname: "start_date",
            label: __("Start Date"),
            fieldtype: "Date",
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            reqd: 1
        },
        {
            fieldname: "end_date",
            label: __("End Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1
        },
        {
            fieldname: "currency",
            label: __("Currency"),
            fieldtype: "Select",
            options: ["ZAR", "EUR", "USD"].join("\n"),
            reqd: 1
        }
    ]
};
