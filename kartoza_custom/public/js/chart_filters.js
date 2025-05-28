frappe.after_ajax(() => {
    // Add a delay to ensure frappe.dashboard.charts is fully populated
    setTimeout(() => {
        if (frappe.dashboard && Array.isArray(frappe.dashboard.charts) && frappe.dashboard.charts.length > 0) {
            createChartFilters();

            // Add listener for chart_settings updates
            const observer = new MutationObserver((mutationsList, observer) => {
                mutationsList.forEach(mutation => {
                    createChartFilters();
                    console.log('Mutation detected:', mutation);
                });
            });
            
            // Select all elements with the class `frappe-chart chart`
            document.querySelectorAll('.frappe-chart.chart').forEach(el => {
                observer.observe(el, {
                    childList: true,        // Listen for added/removed children
                    subtree: true,          // Listen deeply within the node
                    attributes: true,       // Listen for attribute changes
                    characterData: true     // Listen for text content changes
                });
            });
        } 
    }, 1000); // Delay of 100ms
});

function createChartFilters(){
    var charts = frappe.utils.parse_array(frappe.dashboard.charts);
    const containers = document.querySelectorAll('.widget-subtitle');

    for (var i = 0; i < charts.length; i++) {
        var chart = charts[i];
        var chart_settings = chart.chart_settings;
        var html = ``;
        Object.entries(chart_settings.filters).forEach(([key, value]) => {
            html += `<div>${formatString(key)}: ${value}</div>`;
        });
        containers[i].innerHTML = '';
        containers[i].innerHTML += html;
    }
}

function formatString(input) {
    return input
        .split('_') // Split string by underscores
        .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()) // Capitalize each word
        .join(' '); // Join with spaces
}




