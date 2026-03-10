// Copyright (c) 2025, Kartoza and contributors
// For license information, please see license.txt
/* eslint-disable */


frappe.require("assets/kartoza_custom/js/financial_statements.js", function () {
	frappe.query_reports["All Companies Consolidated Financial Report"] = $.extend({}, erpnext.financial_statements);

	erpnext.utils.add_dimensions("All Companies Consolidated Financial Report", 10);

	frappe.query_reports["All Companies Consolidated Financial Report"]["filters"].push({
		fieldname: "include_default_book_entries",
		label: __("Include Default Book Entries"),
		fieldtype: "Check",
		default: 1,
	});
});

frappe.query_reports["Profit and Loss Statement"]["filters"].push({
	fieldname: "include_default_book_entries",
	label: __("Include Default FB Entries"),
	fieldtype: "Check",
	default: 1,
});
