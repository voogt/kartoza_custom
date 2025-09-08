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
        <div id="loader-container" style="text-align:center; margin-top:30px;">
            <div id="loader" style="display:none;">
                <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                <span>Loading charts and tables...</span>
            </div>
        </div>
        <div id="parent-cards" class='row'></div>
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
    document.getElementById('parent-cards').innerHTML = ''; // Clear previous cards
    // Show loader
    document.getElementById('loader').style.display = 'inline-block';

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
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_open_sales_orders',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_open_sla',
    ]

    // Helper to chain frappe.call requests sequentially
    function callMethodsSequentially(index) {
        if (index >= methods.length) {
            // After all methods, call cost center
            frappe.call({
                method: 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_cost_profit_center_data',
                args: { start_date, end_date, type_center:'Cost' },
                type: 'GET',
                callback: function(r) {
                    if (r.message) {
                        drawChart(r.message.labels, r.message.datasets, r.message.title, r.message.element_id, r.message.type, r.message.isReverse);
                        addCards(r.message.total_cards);
                    } else {
                        frappe.msgprint("No data returned.");
                    }
                    // After cost center, call profit center
                    frappe.call({
                        method: 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_cost_profit_center_data',
                        args: { start_date, end_date, type_center:'Profit' },
                        type: 'GET',
                        callback: function(r) {
                            if (r.message) {
                                drawChart(r.message.labels, r.message.datasets, r.message.title, r.message.element_id, r.message.type, r.message.isReverse);
                                addCards(r.message.total_cards);
                            } else {
                                frappe.msgprint("No data returned.");
                            }
                            // Hide loader after last chart/table
                            document.getElementById('loader').style.display = 'none';
                        }
                    });
                }
            });
            return;
        }
        frappe.call({
            method: methods[index],
            args: { start_date, end_date },
            type: 'GET',
            callback: function(r) {
                if (r.message) {
                    drawChart(r.message.labels, r.message.datasets, r.message.title, r.message.element_id, r.message.type, r.message.isReverse);
                    if(r.message.total_cards){
                        addCards(r.message.total_cards);
                    }
                } else {
                    frappe.msgprint("No data returned.");
                }
                // Call next method in sequence
                callMethodsSequentially(index + 1);
            }
        });
    }

    // Start the chain
    callMethodsSequentially(0);
}

function addCards(data){
    const parentElement = document.getElementById('parent-cards');
    if (!parentElement) return;

    console.log(data)

    if(data.length > 0){
        data.forEach(card => {
            const cardElement = document.createElement('div');
            cardElement.className = 'card col-md-2';
            cardElement.style.margin = "10px"
            cardElement.innerHTML = `
                <div class="card-header" style="height:60px">${card.title}</div>
                <div class="card-body">${card.value}</div>
            `;
            parentElement.appendChild(cardElement);
        });
    }
}

function drawChart(labels, datasets, title, element_id, barmode, isReverse) {
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



    // Determine if any label is long (e.g., > 12 chars)
    const maxLabelLength = Math.max(...labels.map(l => l.length));
    const shouldRotate = maxLabelLength > 20;

    let layout = {
        legend: {},
        margin: {b: shouldRotate ? 120 : 60, t: 60, l: 60, r: 30},
        xaxis: {
            tickangle: shouldRotate ? -45 : 0,
            automargin: true,
            tickfont: {size: 12},
        },
        yaxis: {
            automargin: true
        }
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
        layout.margin.t = 100; // increase top margin to accommodate legend
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


    // Render the chart without the top toolbar
    Plotly.newPlot(unique_element_id, traces, layout, {displayModeBar: false});

    // Render the table below the chart
    renderChartTable(labels, datasets, `${unique_element_id}-table`, isReverse);
}

function generateRandomId(prefix = 'id') {
    // Generate a random string of 8 characters
    const randomStr = Math.random().toString(36).substr(2, 8);
    return `${prefix}-${randomStr}`;
}

function renderChartTable(labels, datasets, tableContainerId, isReverse) {
    console.log("Rendering table in container:", tableContainerId);
    let id = generateRandomId('elem');
    let tableHTML = `<table id='${id}' class="table table-bordered" style="width: 100%; border-collapse: collapse;">`;

    if(!isReverse){
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
    }
    else{
        // Header row (datasets across)
        tableHTML += '<thead><tr><th></th>';  // Empty top-left cell
        datasets.forEach(set => {
            tableHTML += `<th>${set.name}</th>`;
        });
        tableHTML += '</tr></thead><tbody>';

        // Rows for each month
        labels.forEach(label => {
            tableHTML += `<tr><td>${label}</td>`;
            datasets.forEach(set => {
                tableHTML += `<td>${set.values[labels.indexOf(label)]}</td>`;
            });
            tableHTML += '</tr>';
        });

        tableHTML += '</tbody></table>';
    }

    // Inject table
    const container = document.getElementById(tableContainerId);
    if (container) {
        container.innerHTML = tableHTML;
    }

    new DataTable(`#${id}`, {
        lengthChange: false, // Remove entries-per-page dropdown
        ordering: false      // Disable sorting
    });
}



