frappe.ready(function() {
    frappe.call({
        method: 'kartoza_custom.api.get_moodle_course_settings',
        args: {
            item: item
        },
        callback: function(response) {
            console.log(response);
            if (response.message.length != 0) {
                document.getElementById('request-btn').style.display = 'block';
                document.getElementById('contact-btn').style.display = 'none';
                const doc_details = response.message[0];
                $('#request-btn').on('click', function() {
                    // Create a dialog to ask for the email
                    const dialog = new frappe.ui.Dialog({
                        title: 'Request Details',
                        fields: [
                            {
                                label: 'Email',
                                fieldname: 'email',
                                fieldtype: 'Data',
                                reqd: 1,
                                options: 'Email',
                                placeholder: 'Enter your email'
                            }
                        ],
                        primary_action_label: 'Send',
                        primary_action: function(values) {
                            // Validate email
                            if (!values.email) {
                                frappe.msgprint('Please enter a valid email.');
                                return;
                            }
                
                            // Call the server-side method to send email
                            frappe.call({
                                method: 'kartoza_custom.api.send_course_details_email',
                                args: {
                                    email: values.email,
                                    doc_details: doc_details
                                },
                                callback: function(response) {
                                    if (response.message.status === 'success') {
                                        frappe.msgprint(`Email sent successfully to ${values.email}`);
                                        dialog.hide();
                                    } else {
                                        frappe.msgprint('Failed to send email.');
                                    }
                                }
                            });
                        }
                    });
                
                    // Show the dialog
                    dialog.show();
                });
            } else {
                console.log("None found");
            }
        },
        error: function(err) {
            console.error("Error fetching records:", err);
        }
    });
});
