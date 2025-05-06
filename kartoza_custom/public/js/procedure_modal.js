frappe.after_ajax(() => {
    if (frappe.session.user === "Guest") return;
  
    
    frappe.call("kartoza_custom.api.get_unacknowledged_procedure").then(r => {
        const procedure = r.message;
        if (!procedure) return;
        console.log("PROCEDURE", procedure)
        frappe.msgprint({
            title: `Please Acknowledge Procedure`,
            message: `<div style="max-height:300px; overflow:auto"> ${procedure.title} ${procedure.content}</div>`,
            indicator: 'orange',
            primary_action: {
                label: 'Acknowledge',
                action() {
                    frappe.call('kartoza_custom.api.acknowledge_procedure', {
                        procedure: procedure.title
                    }).then(() => {
                        frappe.msgprint('Thank you for acknowledging.');
                        dialog.hide();
                    });
                }
            }
        });
    });

});
  