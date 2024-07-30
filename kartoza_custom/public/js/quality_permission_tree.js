console.log("Quality Permission Tree JS Loaded");
frappe.provide("frappe.treeview_settings");


frappe.treeview_settings['Quality Procedure'] = {
    onload: function (treeview) {
        console.log("Treeview settings loaded");

        // Fetch the user roles
        frappe.call({
            method: 'kartoza_custom.overrides.get_user_roles',
            async: false,  // Ensure this call completes before proceeding
            callback: function (data) {
                var roles = data.message;
                console.log("User roles:", roles);
                console.log("TREE VIEW", treeview)

                // Define the query filter based on user roles
                var filters = {};
                
                if (roles.includes('Quality Procedure User')) {
                    // Filter to show only Quality Procedures in 'Policy' group
                    filters.parent_quality_procedure = 'Policy';
                    console.log("Applying filter: ", filters);
                }

                // Apply the filter to the tree view
                treeview.get_query = function () {
                    console.log("Returning filters: ", filters);
                    return {
                        filters: filters
                    };
                };

                // Force reload of the treeview data if possible
                if (treeview && treeview.refresh_data) {
                    treeview.refresh_data();
                }
            },
            error: function (xhr) {
                console.error("API call error:", xhr);
            }
        });
    }
};

// frappe.treeview_settings['Quality Procedure'] = {
//     onload: function (treeview) {
//         // Initialization code
//     },
//     get_tree_nodes: function (node) {
//         return new Promise((resolve, reject) => {
//             frappe.call({
//                 method: 'kartoza_custom.overrides.get_filtered_tree_nodes',
//                 args: {
//                     parent: node ? node.name : null
//                 },
//                 callback: function (response) {
//                     if (response.message) {
//                         resolve(response.message);
//                     } else {
//                         resolve([]);
//                     }
//                 },
//                 error: function (error) {
//                     reject(error);
//                 }
//             });
//         });
//     }
// };





