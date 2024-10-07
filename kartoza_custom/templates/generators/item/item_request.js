frappe.ready(function() {
    frappe.call({
        method: 'kartoza_custom.api.get_moodle_course_settings',
        args: {
            item: item
        },
        callback: function(response) {
            console.log(response)
            if (response.message.length != 0) {
                document.getElementById('request-btn').style.display = 'block'
                document.getElementById('contact-btn').style.display = 'none'
                const doc_details = response.message;
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
                
                
                            // Send email with details from Doctype
                            frappe.call({
                                method: 'frappe.core.doctype.communication.email.sendmail',
                                args: {
                                    recipients: values.email,
                                    subject: `Details for ${doc_details[0].item}`,
                                    content: `<p>Here are the details you requested:</p>
                                              <p>Course Enrollment key: ${doc_details[0].enrollment_key}</p>
                                              <p>Course Link: ${doc_details[0].course_link}</p>`,
                                    doctype: 'Moodle Course Settings',
                                    name: doc_details[0].item, // Assuming the 'name' field holds the identifier
                                    send_email: 1
                                },
                                callback: function(response) {
                                    if (!response.exc) {
                                        frappe.msgprint(`Email sent successfully to ${values.email}`);
                                        dialog.hide();
                                    }
                                }
                            });
                        }
                    });
                
                    // Show the dialog
                    dialog.show();
                });
            } else {
                console.log("None found")
            }
        },
        error: function(err) {
            console.error("Error fetching records:", err);
        }
    });

    
});