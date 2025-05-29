frappe.after_ajax(() => {
    // Add a delay to ensure frappe.dashboard.charts is fully populated
    setTimeout(() => {
        if (frappe.dashboard && Array.isArray(frappe.dashboard.charts) && frappe.dashboard.charts.length > 0) {
            createChartFilters();

            // Add listener for chart_settings updates
            const observer = new MutationObserver((mutationsList, observer) => {
                mutationsList.forEach(mutation => {
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
    // const containers = document.querySelectorAll('.widget-subtitle');

    for (var i = 0; i < charts.length; i++) {
        var chart = charts[i];
        console.log('Processing chart:', chart);
        var chart_settings = chart.chart_settings;
        var html = `<div style='margin-right:10px'>${chart.chart_name}:</div>`;
        Object.entries(chart_settings.filters).forEach(([key, value]) => {
            html += `<div style='margin-right:10px'>${formatString(key)}: ${value}</div>`;
        });
        // const element = document.querySelector(`[title="${chart.chart_name}"]`);
        // try {
        //     element.innerHTML = html;
        // } catch (error) {
            
        // }
        const selector = `[title="${chart.chart_name}"]`;

        waitForElement(selector, 5000)
            .then(element => {
                element.innerHTML = html;
            })
            .catch(error => {
                console.error(error);
            });
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
            } else if (Date.now() - startTime > timeout) {
                clearInterval(interval);
                reject(new Error("Element not found within timeout"));
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




