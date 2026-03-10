frappe.after_ajax(() => {
    if (frappe.session.user === "Guest") return;

    frappe.call("kartoza_custom.api.get_unacknowledged_procedure").then(r => {
        const procedures = r.message;
        if (!procedures || procedures.length === 0) return;

        procedures.forEach(procedure => {
            const dialog = new frappe.ui.Dialog({
                title: `Please Acknowledge Procedure`,
                fields: [
                    {
                        fieldtype: 'HTML',
                        options: `<div style="max-height:300px; overflow:auto">
                                    <strong>${procedure.title}</strong><br><br>
                                    ${procedure.content}
                                  </div>`
                    }
                ],
                primary_action_label: 'Acknowledge',
                primary_action: () => {
                    frappe.call('kartoza_custom.api.acknowledge_procedure', {
                        procedure: procedure.name
                    }).then(() => {
                        frappe.msgprint('Thank you for acknowledging.');
                        dialog.hide();
                    });
                }
            });

            dialog.show();
        });
    });
});
