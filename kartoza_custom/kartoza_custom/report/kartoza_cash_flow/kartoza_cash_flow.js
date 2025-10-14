// frappe.require("assets/erpnext/js/financial_statements.js", function () {
// 	frappe.query_reports["Kartoza Cash Flow"] = $.extend({}, erpnext.financial_statements);

// 	erpnext.utils.add_dimensions("Cash Flow", 10);

// 	// The last item in the array is the definition for Presentation Currency
// 	// filter. It won't be used in cash flow for now so we pop it. Please take
// 	// of this if you are working here.
	

// 	frappe.query_reports["Kartoza Cash Flow"]["filters"].splice(8, 1);
// 	frappe.query_reports["Kartoza Cash Flow"]["filters"].splice(0, 1);

// 	frappe.query_reports["Kartoza Cash Flow"]["filters"].push({
// 		fieldname: "include_default_book_entries",
// 		label: __("Include Default FB Entries"),
// 		fieldtype: "Check",
// 		default: 1,
// 	});
// });

// Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Kartoza Cash Flow"] = $.extend(erpnext.financial_statements, {
	name_field: "section",
	parent_field: "parent_section",
});

erpnext.utils.add_dimensions("Kartoza Cash Flow", 10);

// The last item in the array is the definition for Presentation Currency
// filter. It won't be used in cash flow for now so we pop it. Please take
// of this if you are working here.


var filters_to_remove = ["company", "finance_book", "presentation_currency", "cost_center", "project", "employee_type", "business_unit", "project"];

frappe.query_reports["Kartoza Cash Flow"]["filters"] = frappe.query_reports["Kartoza Cash Flow"]["filters"].filter(function(filter) {
	return filters_to_remove.indexOf(filter.fieldname) === -1;
});

