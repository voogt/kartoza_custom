// Copyright (c) 2024, Kartoza and contributors
// For license information, please see license.txt


frappe.ui.form.on('EasyFile txt generator', {
	generate_file: function (frm) {
	  frappe.call({
		method: "kartoza_custom.utils.export_report_to_text",
		args: {
		  start_date: frm.doc.start_date,
		  end_date: frm.doc.end_date,
		  transaction_year: frm.doc.transaction_year
		},
		callback: function(r) {
			if (r.message) {
				const blob = new Blob([r.message], { type: "text/plain" });
				console.log("BLOB", blob)
				const link = document.createElement("a");
				link.href = window.URL.createObjectURL(blob);
				link.download = `EMP501 Reconciliation.txt`;
				link.click();
			}
		},
	  });
	}
  });
