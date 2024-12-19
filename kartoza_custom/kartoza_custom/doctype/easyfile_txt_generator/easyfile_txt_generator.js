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
				const inputFormatB = "YYYY-MM-DD"; // Input format for reference
				const dateObject = new Date(frm.doc.end_date); // Converts the string to a Date object

				// Extract the month (0-based index in JavaScript, so we add 1)
				const month = dateObject.getMonth() + 1;

				let fileName = "";
				const transactionYear = frm.doc.transaction_year // Get the year from the date

				// Check the month and set the file name accordingly
				if (month === 2) {
					fileName = `YE_${transactionYear}.txt`;
				} else if (month === 8) {
					fileName = `Mid_${transactionYear}.txt`;
				}

				const blob = new Blob([r.message], { type: "text/plain" });
				console.log("BLOB", blob)
				const link = document.createElement("a");
				link.href = window.URL.createObjectURL(blob);
				link.download = fileName;
				link.click();
			}
		},
	  });
	}
  });
