frappe.pages['kartoza-dashboard'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Kartoza Dashboard',
        single_column: true
    });

    page.main.html(`
        <div class="flex items-center gap-8">
            <input type="date" id="start_date" value="2024-10-01"  style="margin-right:5px; border-radius:5px"/>
            <input type="date" id="end_date" value="2025-04-30"  style="margin-right:5px; border-radius:5px"/>
            <button id="load-data" class="btn btn-primary btn-sm">Load Chart</button>
        </div>
        <div id="parent-chart"></div>
        
    `);

    loadCSS();
    loadScript();

    // Button event
    document.getElementById("load-data").addEventListener("click", fetchDataAndPlot);
};


function loadCSS() {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = "https://cdn.datatables.net/v/dt/dt-2.3.3/datatables.min.css";
    link.integrity = "sha384-C0ogMvg31Mu1GWzYxEEobPIlBlGbp/DY94Le4M9y/HFd9VGLT1zWL7MErNMsM2x6";
    link.crossOrigin = "anonymous";
    document.head.appendChild(link);
}

function loadScript() {
    const script = document.createElement('script');
    script.src = "https://cdn.datatables.net/v/dt/dt-2.3.3/datatables.min.js";
    script.integrity = "sha384-qyN6ZT87DHLvgCDC+GYE3myTUDGpz3swpW19cYxOh4oa/8GNSGPMteQwbyM6Ot0D";
    script.crossOrigin = "anonymous";
    script.onload = () => console.log("DataTables loaded");
    document.body.appendChild(script);
}



function fetchDataAndPlot() {
    const start_date = document.getElementById("start_date").value;
    const end_date = document.getElementById("end_date").value;

    document.getElementById('parent-chart').innerHTML = ''; // Clear previous charts

    if (!start_date || !end_date) {
        frappe.msgprint("Please select both start and end dates.");
        return;
    }

    var methods = [
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_staff_count',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_utilisation',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_projects_data',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_activity_cost_data',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_company_salary_pty',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_company_pipeline_pty',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_company_pipeline_lda',
    ]

    for (var method of methods) {
        frappe.call({
            method: method,
            args: { start_date, end_date },
            type: 'GET',
            callback: function(r) {
                if (r.message) {
                    drawChart(r.message.labels, r.message.datasets, r.message.title, r.message.element_id, r.message.type);
                } else {
                    frappe.msgprint("No data returned.");
                }
            }
        });
    }

    //cost center data
    frappe.call({
        method: 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_cost_profit_center_data',
        args: { start_date, end_date, type_center:'Cost' },
        type: 'GET',
        callback: function(r) {
            if (r.message) {
                drawChart(r.message.labels, r.message.datasets, r.message.title, r.message.element_id, r.message.type);
            } else {
                frappe.msgprint("No data returned.");
            }
        }
    });

    //profit center data
    frappe.call({
        method: 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_cost_profit_center_data',
        args: { start_date, end_date, type_center:'Profit' },
        type: 'GET',
        callback: function(r) {
            if (r.message) {
                drawChart(r.message.labels, r.message.datasets, r.message.title, r.message.element_id, r.message.type);
            } else {
                frappe.msgprint("No data returned.");
            }
        }
    });
}

function drawChart(labels, datasets, title, element_id, barmode) {
    // Ensure unique element_id for each chart
    const unique_element_id = `${element_id}-${generateRandomId()}`;
    const containerId = `${unique_element_id}-container`;

    // Generate traces for Plotly chart
    const traces = datasets.map(set => ({
        x: labels,
        y: set.values,
        name: set.name,
        type: set.type || 'bar'
    }));

    // Define chart layout
    let layout = {
        legend: {} // default, will be updated conditionally
    };

    if (barmode === 'stack') {
        layout.barmode = 'stack';
    }

    // Adjust legend layout if datasets are more than 8
    if (datasets.length > 8) {
        layout.legend = {
            orientation: 'h',
            x: 0,
            y: 1.2,
            xanchor: 'left',
            yanchor: 'bottom'
        };
        layout.margin = {
            t: 100 // increase top margin to accommodate legend
        };
    }

    // Create a container for the chart and table using insertAdjacentHTML to preserve previous DOM nodes
    const parentElement = document.getElementById('parent-chart');
    parentElement.insertAdjacentHTML('beforeend', `
        <div id="${containerId}" style="margin-bottom: 40px;">
            <h3 style='text-align: center;'>${title}</h3>
            <div id="${unique_element_id}" style="width: 100%; height: 500px;"></div>
            <div id="${unique_element_id}-table" style="margin-top: 20px;"></div>
        </div>
    `);

    // Render the chart
    Plotly.newPlot(unique_element_id, traces, layout);

    // Render the table below the chart
    renderChartTable(labels, datasets, `${unique_element_id}-table`);
}

function generateRandomId(prefix = 'id') {
    // Generate a random string of 8 characters
    const randomStr = Math.random().toString(36).substr(2, 8);
    return `${prefix}-${randomStr}`;
}

function renderChartTable(labels, datasets, tableContainerId) {
    let id = generateRandomId('elem');
    let tableHTML = `<table id='${id}' class="table table-bordered" style="width: 100%; border-collapse: collapse;">`;

    // Header row (months across)
    tableHTML += '<thead><tr><th></th>';  // Empty top-left cell
    labels.forEach(label => {
        tableHTML += `<th>${label}</th>`;
    });
    tableHTML += '</tr></thead><tbody>';

    // Rows for each dataset
    datasets.forEach(set => {
        tableHTML += `<tr><td>${set.name}</td>`;
        set.values.forEach(value => {
            tableHTML += `<td>${value}</td>`;
        });
        tableHTML += '</tr>';
    });

    tableHTML += '</tbody></table>';

    // Inject table
    const container = document.getElementById(tableContainerId);
    if (container) {
        container.innerHTML = tableHTML;
    }

    new DataTable(`#${id}`, {
        lengthChange: false // Remove entries-per-page dropdown
    });
}



