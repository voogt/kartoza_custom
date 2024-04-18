frappe.ui.form.on("Sales Order", {
	
	onload_post_render(frm) {
		console.log(frm)
		if(frm.doc.status !== 'Closed') {
			if(frm.doc.status !== 'On Hold') {
				if(flt(frm.doc.per_delivered, 6) >= 100 || flt(frm.doc.per_billed) >= 100){
					frm.add_custom_button(__('Sales Invoice'), () => make_sales_invoice(), __('Create'));
				}
				
			}
		}
		
		function make_sales_invoice(){
			console.log(frm)
			frappe.model.open_mapped_doc({
				method: "erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice",
				frm: frm
			})
		}
		
    },
});

