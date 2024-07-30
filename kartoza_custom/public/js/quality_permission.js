frappe.listview_settings['Quality Procedure'] = {
    onload: function (listview) {
        // Call the custom API method to get user roles
        frappe.call({
            method: 'kartoza_custom.overrides.get_user_roles',
            async: false,
            callback: function (data) {
                var roles = data.message;

                // Define the query filter based on user roles
                var filters = {};
                
                if (roles.includes('Quality Manager')) {
                    // No additional filters for Quality Managers
                } else if (roles.includes('Quality Procedure User')) {
                    console.log("ROLES", roles)
                    // Filter for 'Policy' group for Quality Procedure Users
                    filters.parent_quality_procedure = 'Policy';
                }
                // Apply the filter to the list view
                listview.get_query = function () {
                    console.log("GET QUERY")
                    return {
                        filters: filters
                    };
                };
            }
        });
    }
};