frappe.after_ajax(() => {
    // Add a delay to ensure frappe.dashboard.charts is fully populated
    setTimeout(async () => {
        if (frappe.dashboard && Array.isArray(frappe.dashboard.charts) && frappe.dashboard.charts.length > 0) {
            createChartFilters();

            // Wait for all elements with the class `frappe-chart chart` to load in the DOM
            await waitForElement('.frappe-chart.chart');

            // Add listener for chart_settings updates
            const observer = new MutationObserver((mutationsList, observer) => {
                mutationsList.forEach(mutation => {
                    console.log('Mutation detected:', mutation);
                    createChartFilters();
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

    for (var i = 0; i < charts.length; i++) {
        var chart = charts[i];
        console.log('Processing chart:', chart);
        var chart_settings = chart.chart_settings;
        var html = `<div style='margin-right:10px'>${chart.chart_name}:</div>`;
        Object.entries(chart_settings.filters).forEach(([key, value]) => {
            html += `<div style='margin-right:10px'>${formatString(key)}: ${value}</div>`;
        });
        
        console.log('chart', chart)
        var selector = `[title="${chart.chart_name}"]`;
        const element = document.querySelector(selector);

        element.innerHTML = html;
    }
}

function waitForElement(selector, timeout = 5000) {
    return new Promise((resolve, reject) => {
        const startTime = Date.now();

        const interval = setInterval(() => {
            const element = document.querySelector(selector);
            if (element) {
                clearInterval(interval);
                resolve(element);
            } 
        }, 500); // check every 100ms
    });
}

function formatString(input) {
    return input
        .split('_') // Split string by underscores
        .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()) // Capitalize each word
        .join(' '); // Join with spaces
}




