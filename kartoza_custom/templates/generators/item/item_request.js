frappe.ready(function() {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Moodle Course Settings',
            fields: ['item', 'enrollment_key', 'course_link'],
            filters: {
                item: item,
                zero_rated: 1
            }
        },
        callback: function(response) {
            if (response && response.message) {
                document.getElementById('request-btn').style.display = 'block'
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
                
                            const doc_details = response.message; // If this script runs within a form, else fetch details separately
                
                            // Send email with details from Doctype
                            frappe.call({
                                method: 'frappe.core.doctype.communication.email.make',
                                args: {
                                    recipients: values.email,
                                    subject: `Details for ${doc_details.item}`,
                                    content: `<p>Here are the details you requested:</p>
                                              <p>Course Enrollment key: ${doc_details.enrollment_key}</p>
                                              <p>Course Link: ${doc_details.course_link}</p>`,
                                    doctype: doc_details.item,
                                    name: doc_details.item, // Assuming the 'name' field holds the identifier
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