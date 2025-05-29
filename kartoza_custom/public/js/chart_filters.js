frappe.after_ajax(async () => {
    try {
        // Run logic only if the URL contains 'dashboard-view'
        if (!window.location.href.includes('dashboard-view')) {
            console.log('Dashboard view not detected in URL. Skipping chart filters initialization.');
            return;
        }

        // Wait until frappe.dashboard.charts is ready
        while (!(frappe.dashboard && Array.isArray(frappe.dashboard.charts) && frappe.dashboard.charts.length > 0)) {
            await new Promise(resolve => setTimeout(resolve, 1000)); // Check every 100ms
        }

        createChartFilters();

        // Wait for all elements with the class `frappe-chart chart` to load in the DOM
        await waitForElement('.frappe-chart.chart');

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
    } catch (error) {
        console.error('Error initializing chart filters:', error);
    }
});


function createChartFilters() {
    try {
        var charts = frappe.utils.parse_array(frappe.dashboard.charts);

        for (var i = 0; i < charts.length; i++) {
            var chart = charts[i];

            var chart_settings = chart.chart_settings;

            // Automatically add start_date and end_date if no filters are found
            if (!chart_settings.filters || Object.keys(chart_settings.filters).length === 0) {
                const now = new Date();

                // First day of previous month
                const firstDayPrevMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);

                // Last day of previous month
                const lastDayPrevMonth = new Date(now.getFullYear(), now.getMonth(), 0);

                chart_settings.filters = {
                    start_date: formatDate(firstDayPrevMonth),
                    end_date: formatDate(lastDayPrevMonth)
                };
            }

            var html = `<div style='margin-right:10px'>${chart.chart_name}:</div>`;
            Object.entries(chart_settings.filters).forEach(([key, value]) => {
                html += `<div style='margin-right:10px'>${formatString(key)}: ${value}</div>`;
            });
            var selector = `[title="${chart.chart_name}"]`;
            const element = document.querySelector(selector);

            if (element) {
                element.innerHTML = html;
            } else {
                console.warn(`Element with selector ${selector} not found.`);
            }
        }
    } catch (error) {
        console.error('Error creating chart filters:', error);
    }
}

function formatDate(date) {
    const year = date.getFullYear();
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const day = date.getDate().toString().padStart(2, '0');
    return `${year}-${month}-${day}`;
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
                reject(new Error(`Timeout waiting for element: ${selector}`));
            }
        }, 500); // check every 500ms
    });
}

function formatString(input) {
    return input
        .split('_') // Split string by underscores
        .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()) // Capitalize each word
        .join(' '); // Join with spaces
}




