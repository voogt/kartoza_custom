frappe.require("assets/kartoza_custom/js/financial_statements.js", function () {
	frappe.query_reports["Kartoza Cash Flow"] = $.extend({}, kartoza_custom.financial_statements);

	erpnext.utils.add_dimensions("Cash Flow", 10);

	// The last item in the array is the definition for Presentation Currency
	// filter. It won't be used in cash flow for now so we pop it. Please take
	// of this if you are working here.

	frappe.query_reports["Kartoza Cash Flow"]["filters"].splice(8, 1);

	frappe.query_reports["Kartoza Cash Flow"]["filters"].push({
		fieldname: "include_default_book_entries",
		label: __("Include Default FB Entries"),
		fieldtype: "Check",
		default: 1,
	});
});