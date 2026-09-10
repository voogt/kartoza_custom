frappe.pages['kartoza-dashboard'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Kartoza Dashboard',
        single_column: true
    });

    page.main.html(`

        <div class="flex items-center gap-8">
            <input type="date" id="start_date" value=""  style="margin-right:5px; border-radius:5px"/>
            <input type="date" id="end_date" value=""  style="margin-right:5px; border-radius:5px"/>
            <select id="filter-select" style="margin-right:5px; border-radius:5px; min-width:220px; height:31px;">
                <option value="__show_all__">Show All</option>
            </select>
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
    fecthFilters();

    // Button event
    document.getElementById("load-data").addEventListener("click", fetchDataAndPlot);
};

let availableFilters = [];

const KARTOZA_DT_SCRIPT_ID = 'kartoza-jquery-datatables-script';
const KARTOZA_DT_STYLE_ID = 'kartoza-jquery-datatables-style';


function loadCSS() {
    if (document.getElementById(KARTOZA_DT_STYLE_ID)) return;

    const link = document.createElement('link');
    link.id = KARTOZA_DT_STYLE_ID;
    link.rel = 'stylesheet';
    link.href = "https://cdn.datatables.net/v/dt/dt-2.3.3/datatables.min.css";
    link.integrity = "sha384-C0ogMvg31Mu1GWzYxEEobPIlBlGbp/DY94Le4M9y/HFd9VGLT1zWL7MErNMsM2x6";
    link.crossOrigin = "anonymous";
    document.head.appendChild(link);
}

function loadScript() {
    if (!window.__frappeDataTableCtor && window.DataTable) {
        window.__frappeDataTableCtor = window.DataTable;
    }

    const existingScript = document.getElementById(KARTOZA_DT_SCRIPT_ID);
    if (existingScript) return;

    const script = document.createElement('script');
    script.id = KARTOZA_DT_SCRIPT_ID;
    script.src = "https://cdn.datatables.net/v/dt/dt-2.3.3/datatables.min.js";
    script.integrity = "sha384-qyN6ZT87DHLvgCDC+GYE3myTUDGpz3swpW19cYxOh4oa/8GNSGPMteQwbyM6Ot0D";
    script.crossOrigin = "anonymous";
    script.onload = function() {
        // Restore Frappe's DataTable constructor so other report pages keep working.
        if (window.__frappeDataTableCtor) {
            window.DataTable = window.__frappeDataTableCtor;
        }
    };
    document.body.appendChild(script);
}

function fecthFilters(){
    frappe.call({
        method: "kartoza_custom.kartoza_custom.kartoza_dashboard.get_all_filters",
        type: 'GET',
        callback: function(r) {
            const select = document.getElementById("filter-select");
            if (!select) return;

            availableFilters = (r && r.message && Array.isArray(r.message.charts)) ? r.message.charts : [];

            select.innerHTML = '<option value="__show_all__">Show All</option>';

            availableFilters.forEach((filterObj) => {
                if (!filterObj || !filterObj.filter_title) return;
                const option = document.createElement('option');
                option.value = filterObj.filter_title;
                option.textContent = filterObj.filter_title;
                select.appendChild(option);
            });
        },
        error: function(err) {
            frappe.msgprint("Error occurred while fetching filters.");
        }
    });
}


function fetchDataAndPlot() {
    const start_date = document.getElementById("start_date").value;
    const end_date = document.getElementById("end_date").value;
    const selectedFilter = document.getElementById("filter-select")?.value || "__show_all__";

    document.getElementById('parent-chart').innerHTML = ''; // Clear previous charts
    document.getElementById('parent-cards').innerHTML = ''; // Clear previous cards
    // Show loader
    document.getElementById('loader').style.display = 'inline-block';

    if (!start_date || !end_date) {
        frappe.msgprint("Please select both start and end dates.");
        return;
    }

    var methods = [
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_staff_count',
            "title": "Staff Count",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_billable_hours',
            "title": "Billable Hours",
            "args": { start_date, end_date },
        },
        // {
        //     "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_utilisation',
        //     "title": "Utilisation",
        //     "args": { start_date, end_date },
        // },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_projects_data',
            "title": "Projects",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_project_closed_summary',
            "title": "Project Closed Summary",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_activity_cost_data',
            "title": "Activity Cost",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_company_salary_pty',
            "title": "Total Department Cost Pty",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_company_salary_lda',
            "title": "Total Department Cost Lda",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_salary_percent_of_sales',
            "title": "Salaries as % of Sales",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_timesheet_data',
            "title": "Timesheet Data for Project 'Kartoza Sales' (Hours)",
            "args": { start_date, end_date, 'type_returned': "hours" },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_timesheet_data',
            "title": "Timesheet Data for Project 'Kartoza Sales' (Cost vs Lost)",
            "args": { start_date, end_date, 'type_returned': "cost_vs_lost" },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_company_pipeline_pty',
            "title": "Pipeline Quotation Kartoza Pty (Draft/Open)",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_company_pipeline_opportunities_pty',
            "title": "Pipeline Opportunity Kartoza Pty (Draft/Open)",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_company_pipeline_opportunities_lda',
            "title": "Pipeline Opportunity Kartoza Unipessoal Lda (Draft/Open)",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_company_pipeline_lda',
            "title": "Pipeline Quotation Kartoza Unipessoal Lda (Draft/Open)",
            "args": { start_date, end_date },
        },
        
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_open_sales_orders',
            "title": "Current Open Sales Orders",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_open_sla',
            "title": "Current open SLA's",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_item_wise_annual_sales_pty',
            "title": "Per Item Annual Sales Pty",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_item_wise_annual_sales_lda',
            "title": "Per Item Annual Sales Lda",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_sales_analytics_customers_pty',
            "title": "Sales Analytics Customers Pty",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_sales_analytics_customers_lda',
            "title": "Sales Analytics Customers Lda",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_overhead_cost_pty',
            "title": "Overhead Cost Pty",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_overhead_cost_lda',
            "title": "Overhead Cost Lda",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_tender_summary',
            "title": "Proposals Report",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_opportunity_trend',
            "title": "Opportunity Trend",
            "args": { start_date, end_date },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_sales_trend_5_years',
            "title": "Sales Trend (Last 5 Years)",
            "args": {},
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_cost_profit_center_data',
            "title": "Cost Center True Cost (Profit/Loss)",
            "args": { start_date, end_date, "type_center":'Cost' },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_profit_cost_lost_revenue_data',
            "title": "Cost Center Opportunity (Profit/Loss)",
            "args": { start_date, end_date, "type_center":'Cost' },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_cost_profit_center_data',
            "title": "Profit Center True Cost (Profit/Loss)",
            "args": { start_date, end_date, "type_center":'Profit' },
        },
        {
            "method": 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_profit_cost_lost_revenue_data',
            "title": "Profit Center Opportunity (Profit/Loss)",
            "args": { start_date, end_date, "type_center":'Profit' },
        }
    ]

    if (selectedFilter !== "__show_all__") {
        const filterConfig = availableFilters.find((item) => item.filter_title === selectedFilter);
        const selectedTitles = (filterConfig && Array.isArray(filterConfig.chart_selection)) ? filterConfig.chart_selection : [];

        methods = methods.filter((item) => selectedTitles.includes(item.title));

        if (methods.length === 0) {
            document.getElementById('loader').style.display = 'none';
            frappe.msgprint("No charts configured for the selected filter.");
            return;
        }
    }

    // Fire the HTTP request for one method and resolve with its result (no DOM work here).
    // Kept separate from rendering so a batch of these can run concurrently while
    // rendering still happens afterwards in the original array order.
    function fetchMethodData(index) {
        return new Promise((resolve) => {
            frappe.call({
                method: methods[index]["method"],
                args: methods[index]["args"],
                type: 'GET',
                callback: function(r) {
                    resolve(r && r.message);
                },
                error: function() {
                    frappe.msgprint("Error occurred while fetching data.");
                    resolve(null);
                }
            });
        });
    }

    function renderMethodResult(index, message) {
        if (!message) {
            frappe.msgprint("No data returned.");
            return;
        }
        const chartRefs = drawChart(message.labels, message.datasets, message.title, message.element_id, message.type, message.isReverse, message.help, message.shouldSplitLongLabels, message.showTotal);
        if (message.total_cards) {
            addCards(message.total_cards);
        }
        if (methods[index]["title"] === "Billable Hours") {
            setupBillableHoursStaffToggle(chartRefs);
        }
        if (methods[index]["title"] === "Current open SLA's") {
            setupOpenSlaCategoryFilter(chartRefs);
        }
        if (methods[index]["title"] === "Proposals Report") {
            setupTenderSummaryTypeFilter(chartRefs);
        }
    }

    // Run all method calls in fixed-size concurrent batches instead of one at a
    // time. Charts are still drawn in the original top-to-bottom order (each
    // batch is rendered in order once the whole batch resolves), but the
    // network round-trips within a batch overlap instead of queueing serially.
    const CONCURRENCY = 6;
    (async function runInBatches() {
        for (let start = 0; start < methods.length; start += CONCURRENCY) {
            const batchIndexes = [];
            for (let i = start; i < Math.min(start + CONCURRENCY, methods.length); i++) {
                batchIndexes.push(i);
            }
            const batchResults = await Promise.all(batchIndexes.map(fetchMethodData));
            batchIndexes.forEach((index, i) => renderMethodResult(index, batchResults[i]));
        }
        // Hide loader after all calls
        document.getElementById('loader').style.display = 'none';
    })();

}

const addCards = (data) => {
    const parentElement = document.getElementById('parent-cards');
    if (!parentElement) return;

    if(data.length > 0){
        data.forEach(card => {
            const cardElement = document.createElement('div');
            cardElement.className = 'card col-md-2';
            cardElement.style.margin = "10px"
            cardElement.dataset.cardTitle = card.title;
            cardElement.innerHTML = `
                <div class="card-header" style="height:80px">${card.title}</div>
                <div class="card-body">${formatWithUnit(card.value, card.unit)}</div>
            `;
            parentElement.appendChild(cardElement);
        });
    }
}

// Update an already-rendered card's value in place (matched by title)
function updateCardValue(title, value, unit) {
    const parentElement = document.getElementById('parent-cards');
    if (!parentElement) return;
    const cardElement = parentElement.querySelector(`[data-card-title="${CSS.escape(title)}"]`);
    if (!cardElement) return;
    const body = cardElement.querySelector('.card-body');
    if (body) body.innerHTML = formatWithUnit(value, unit);
}

// A 26-color qualitative palette (Plotly Express "Alphabet" set) so charts with
// many datasets (e.g. Activity Cost, with 20+ categories) don't cycle back to
// colors already used by an earlier series in the same chart.
const QUALITATIVE_CHART_COLORS = [
    '#90AD1C', '#3283FE', '#85660D', '#FBE426', '#565656',
    '#1C8356', '#16FF32', '#F7E1A0', '#E2E2E2', '#1CBE4F',
    '#C4451C', '#08306B', '#FE00FA', '#325A9B', '#FEAF16',
    '#F8A19F', '#FA0087', '#F6222E', '#1CFFCE', '#2ED9FF',
    '#B10DA1', '#C075A6', '#FC1CBF', '#B00068', '#782AB6',
    '#AA0DFE',
];

// Render (or re-render in place) the Plotly chart for an existing chart element.
function renderPlot(chartElementId, labels, datasets, barmode, shouldSplitLongLabels) {
    // Some datasets (e.g. Risk) are only meant for the table, not the chart itself
    datasets = datasets.filter(set => !set.excludeFromChart);

    // Determine if any label is long (e.g., > 12 chars)
    const maxLabelLength = Math.max(...labels.map(l => l.length));
    const shouldRotate = maxLabelLength > 20;

    // If rotating, split long labels into two lines and reduce font size
    let processedLabels = labels;
    let tickfontSize = 12;
    if (shouldRotate) {
        processedLabels = labels.map(l => {
            if (shouldSplitLongLabels) {
                let spaceIdx = l.lastIndexOf(' ', 50);
                if (spaceIdx === -1) spaceIdx = l.indexOf(' ', 50);
                if (spaceIdx !== -1) {
                    return l.slice(0, spaceIdx) + '<br>' + l.slice(spaceIdx + 1);
                } else {
                    // No space, just split at 50
                    return l.slice(0, 50) + '<br>' + l.slice(50);
                }
            }
            return l;
        });
        // Move the second line up a bit if <br> is present
        processedLabels = processedLabels.map(lbl => {
            if (typeof lbl === 'string' && lbl.includes('<br>')) {
                // Wrap the second line in a span with negative margin-top
                return lbl.replace(/<br>(.*)/, '<br><span style="display:inline-block; margin-top:-15px;">$1</span>');
            }
            return lbl;
        });
        tickfontSize = 9; // smaller font size for rotated labels
    }

    // Datasets measured as a percentage share a "rand"/count scale with the other
    // bars if plotted on the same axis, which flattens the line into a near-zero
    // strip. Route them to a secondary (right-hand) y-axis so their own scale is used.
    const hasPercentDataset = datasets.some(set => (set.unit || '').toLowerCase() === 'percent');

    // Generate traces for Plotly chart
    const traces = datasets.map((set, index) => {
        const isPercent = (set.unit || '').toLowerCase() === 'percent';
        const color = QUALITATIVE_CHART_COLORS[index % QUALITATIVE_CHART_COLORS.length];
        return {
            x: processedLabels,
            y: set.values,
            name: set.name,
            type: set.type || 'bar',
            yaxis: isPercent ? 'y2' : 'y',
            marker: { color },
            line: { color },
            customdata: set.values.map(v => formatWithUnit(v, set.unit)),
            // Show legend (dataset name) as the title in the hovertemplate
            hovertemplate: `<b>${set.name}</b><br>%{x}: %{customdata}<extra></extra>`
        };
    });

    let layout = {
        legend: {},
        margin: {b: shouldRotate ? 120 : 60, t: 60, l: 60, r: hasPercentDataset ? 60 : 30},
        xaxis: {
            tickangle: shouldRotate ? -45 : 0,
            automargin: true,
            tickfont: {size: tickfontSize},
        },
        yaxis: {
            automargin: true,
            title: { text: "" }
        }
    };

    if (hasPercentDataset) {
        layout.yaxis2 = {
            overlaying: 'y',
            side: 'right',
            automargin: true,
            title: { text: "%" },
            ticksuffix: '%',
            showgrid: false,
            rangemode: 'tozero'
        };
    }

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

    // Render the chart without the top toolbar
    Plotly.newPlot(chartElementId, traces, layout, {displayModeBar: false});
}

function drawChart(labels, datasets, title, element_id, barmode, isReverse, helpText, shouldSplitLongLabels, showTotal) {
    // Ensure unique element_id for each chart
    const unique_element_id = `${element_id}-${generateRandomId()}`;
    const containerId = `${unique_element_id}-container`;
    const tableId = `${unique_element_id}-table`;

    // Create a container for the chart and table using insertAdjacentHTML to preserve previous DOM nodes
    const parentElement = document.getElementById('parent-chart');
    // Add info icon with custom HTML popover if helpText is provided
    let infoIconHTML = '';
    if (helpText) {
        const popoverId = `${containerId}-popover`;
        infoIconHTML = ` <span style="cursor:pointer;position:relative;display:inline-block;" tabindex="0" aria-describedby="${popoverId}" class="info-icon">
            <svg xmlns="http://www.w3.org/2000/svg" height="20px" viewBox="0 -960 960 960" width="20px" fill="#1f1f1f"><path d="M440-280h80v-240h-80v240Zm40-320q17 0 28.5-11.5T520-640q0-17-11.5-28.5T480-680q-17 0-28.5 11.5T440-640q0 17 11.5 28.5T480-600Zm0 520q-83 0-156-31.5T197-197q-54-54-85.5-127T80-480q0-83 31.5-156T197-763q54-54 127-85.5T480-880q83 0 156 31.5T763-763q54 54 85.5 127T880-480q0 83-31.5 156T763-197q-54 54-127 85.5T480-80Zm0-80q134 0 227-93t93-227q0-134-93-227t-227-93q-134 0-227 93t-93 227q0 134 93 227t227 93Zm0-320Z"/></svg>
            <div id="${popoverId}" class="custom-popover" style="display:none; position:absolute; left:25px; top:0; z-index:1000; background:#fff; border:1px solid #ccc; border-radius:6px; box-shadow:0 2px 8px rgba(0,0,0,0.15); padding:14px 18px; min-width:320px; max-width:420px; font-size:14px; color:#222;">
                ${helpText}
            </div>
        </span>`;
    }
    parentElement.insertAdjacentHTML('beforeend', `
        <div id="${containerId}" style="margin-bottom: 80px;">
            <h3 style='text-align: center;'>${title}${infoIconHTML}</h3>
            <div id="${unique_element_id}" style="width: 100%; height: 480px;"></div>
            <div id="${tableId}" style="margin-top: 20px;"></div>
            <hr>
        </div>
    `);

    // Add popover show/hide logic for info icon
    if (helpText) {
        const container = document.getElementById(containerId);
        if (container) {
            const infoIcon = container.querySelector('.info-icon');
            const popover = container.querySelector('.custom-popover');
            if (infoIcon && popover) {
                // Show on hover or focus
                infoIcon.addEventListener('mouseenter', () => { popover.style.display = 'block'; });
                infoIcon.addEventListener('mouseleave', () => { popover.style.display = 'none'; });
                infoIcon.addEventListener('focus', () => { popover.style.display = 'block'; });
                infoIcon.addEventListener('blur', () => { popover.style.display = 'none'; });
            }
        }
    }

    renderPlot(unique_element_id, labels, datasets, barmode, shouldSplitLongLabels);

    // Render the table below the chart
    renderChartTable(labels, datasets, tableId, isReverse, element_id, showTotal);

    return { containerId, chartId: unique_element_id, tableId };
}

function generateRandomId(prefix = 'id') {
    // Generate a random string of 8 characters
    const randomStr = Math.random().toString(36).substr(2, 8);
    return `${prefix}-${randomStr}`;
}

// Add an "Include all staff" checkbox under the Billable Hours chart title,
// and refresh that chart (and its total cards) in place when it's toggled.
function setupBillableHoursStaffToggle(chartRefs) {
    if (!chartRefs) return;
    const container = document.getElementById(chartRefs.containerId);
    const titleEl = container && container.querySelector('h3');
    if (!titleEl) return;

    const toggleWrapper = document.createElement('label');
    toggleWrapper.style.cssText = 'display:block; text-align:center; font-size:13px; font-weight:normal; margin-top:6px; cursor:pointer;';
    toggleWrapper.innerHTML = `<input type="checkbox" id="${chartRefs.chartId}-include-all-staff" style="margin-right:4px;" /> Include all staff (ignore utilization flag) <span id="${chartRefs.chartId}-include-all-staff-spinner" class="spinner-border spinner-border-sm" role="status" aria-hidden="true" style="display:none; margin-left:4px; vertical-align:middle;"></span>`;
    titleEl.insertAdjacentElement('afterend', toggleWrapper);

    toggleWrapper.querySelector('input').addEventListener('change', function() {
        refreshBillableHoursChart(chartRefs, this.checked);
    });
}

function refreshBillableHoursChart(chartRefs, includeAllStaff) {
    const start_date = document.getElementById("start_date").value;
    const end_date = document.getElementById("end_date").value;

    const checkbox = document.getElementById(`${chartRefs.chartId}-include-all-staff`);
    const spinner = document.getElementById(`${chartRefs.chartId}-include-all-staff-spinner`);
    if (checkbox) checkbox.disabled = true;
    if (spinner) spinner.style.display = 'inline-block';

    frappe.call({
        method: 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_billable_hours',
        args: { start_date, end_date, include_all_staff: includeAllStaff ? 1 : 0 },
        type: 'GET',
        callback: function(r) {
            if (!r.message) {
                frappe.msgprint("No data returned.");
                return;
            }
            renderPlot(chartRefs.chartId, r.message.labels, r.message.datasets, r.message.type, r.message.shouldSplitLongLabels);
            renderChartTable(r.message.labels, r.message.datasets, chartRefs.tableId, r.message.isReverse, r.message.element_id, r.message.showTotal);
            (r.message.total_cards || []).forEach(card => updateCardValue(card.title, card.value, card.unit));
        },
        error: function() {
            frappe.msgprint("Error occurred while fetching billable hours data.");
        },
        always: function() {
            if (checkbox) checkbox.disabled = false;
            if (spinner) spinner.style.display = 'none';
        }
    });
}

// Add "All / SLA only / Hosting only" buttons under the Current open SLA's chart title,
// and refresh that chart in place when the selection changes.
function setupOpenSlaCategoryFilter(chartRefs) {
    if (!chartRefs) return;
    const container = document.getElementById(chartRefs.containerId);
    const titleEl = container && container.querySelector('h3');
    if (!titleEl) return;

    const options = [
        { label: 'All', value: '' },
        { label: 'SLA only', value: 'SLA' },
        { label: 'Hosting only', value: 'Hosting' }
    ];

    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'text-align:center; margin-top:6px;';
    wrapper.innerHTML = options.map((opt, idx) => `
        <button type="button" class="btn btn-default btn-xs open-sla-filter-btn" data-value="${opt.value}"
            style="margin:0 3px;${idx === 0 ? 'font-weight:bold;' : ''}">${opt.label}</button>
    `).join('');
    titleEl.insertAdjacentElement('afterend', wrapper);

    wrapper.querySelectorAll('.open-sla-filter-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            wrapper.querySelectorAll('.open-sla-filter-btn').forEach(b => b.style.fontWeight = 'normal');
            this.style.fontWeight = 'bold';
            refreshOpenSlaChart(chartRefs, this.dataset.value);
        });
    });
}

function refreshOpenSlaChart(chartRefs, serviceCategory) {
    frappe.call({
        method: 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_open_sla',
        args: { service_category: serviceCategory },
        type: 'GET',
        callback: function(r) {
            if (!r.message) {
                frappe.msgprint("No data returned.");
                return;
            }
            renderPlot(chartRefs.chartId, r.message.labels, r.message.datasets, r.message.type, r.message.shouldSplitLongLabels);
            renderChartTable(r.message.labels, r.message.datasets, chartRefs.tableId, r.message.isReverse, r.message.element_id, r.message.showTotal);
        },
        error: function() {
            frappe.msgprint("Error occurred while fetching open SLA data.");
        }
    });
}

// Add "All / Opportunities only / Quotes only" buttons under the Proposals Report chart title,
// and refresh that chart in place when the selection changes.
function setupTenderSummaryTypeFilter(chartRefs) {
    if (!chartRefs) return;
    const container = document.getElementById(chartRefs.containerId);
    const titleEl = container && container.querySelector('h3');
    if (!titleEl) return;

    const options = [
        { label: 'All', value: '' },
        { label: 'Opportunities only', value: 'opportunities' },
        { label: 'Quotes only', value: 'quotes' }
    ];

    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'text-align:center; margin-top:6px;';
    wrapper.innerHTML = options.map((opt, idx) => `
        <button type="button" class="btn btn-default btn-xs tender-summary-filter-btn" data-value="${opt.value}"
            style="margin:0 3px;${idx === 0 ? 'font-weight:bold;' : ''}">${opt.label}</button>
    `).join('');
    titleEl.insertAdjacentElement('afterend', wrapper);

    wrapper.querySelectorAll('.tender-summary-filter-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            wrapper.querySelectorAll('.tender-summary-filter-btn').forEach(b => b.style.fontWeight = 'normal');
            this.style.fontWeight = 'bold';
            refreshTenderSummaryChart(chartRefs, this.dataset.value);
        });
    });
}

function refreshTenderSummaryChart(chartRefs, typeFilter) {
    const start_date = document.getElementById("start_date").value;
    const end_date = document.getElementById("end_date").value;

    frappe.call({
        method: 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_tender_summary',
        args: { start_date, end_date, type_filter: typeFilter },
        type: 'GET',
        callback: function(r) {
            if (!r.message) {
                frappe.msgprint("No data returned.");
                return;
            }
            renderPlot(chartRefs.chartId, r.message.labels, r.message.datasets, r.message.type, r.message.shouldSplitLongLabels);
            renderChartTable(r.message.labels, r.message.datasets, chartRefs.tableId, r.message.isReverse, r.message.element_id, r.message.showTotal);
        },
        error: function() {
            frappe.msgprint("Error occurred while fetching tender summary data.");
        }
    });
}

// (Re)initialize the DataTables plugin for a chart table, honoring the pagination toggle.
function initChartDataTable(id, enablePagination) {
    if (!(window.jQuery && window.jQuery.fn && typeof window.jQuery.fn.DataTable === 'function')) return;
    const $ = window.jQuery;
    const $table = $(`#${id}`);
    if ($.fn.DataTable.isDataTable(`#${id}`)) {
        $table.DataTable().destroy();
    }
    const dt = $table.DataTable({
        lengthChange: false,
        ordering: false,
        paging: enablePagination
    });

    // DataTables' own search box class names differ across versions (and it
    // rebuilds its wrapper on every init), so hide it and drive searching
    // from our own input that lives in the controls row next to the toggle.
    $table.closest('.dataTables_wrapper, .dt-container').find('.dataTables_filter, .dt-search').hide();

    const $searchInput = $(`#${id}-search`);
    $searchInput.off('input').on('input', function() {
        dt.search(this.value).draw();
    });
}

function renderChartTable(labels, datasets, tableContainerId, isReverse, element_id, showTotal) {

    const isPercentDataset = (set) => String(set?.name ?? '').includes('%');

    let id = generateRandomId('elem');
    let tableHTML = `<div id="${id}-controls" style="display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:6px;">
        <label style="font-weight:normal;font-size:13px;cursor:pointer;margin:0;"><input type="checkbox" id="${id}-pagination-toggle" checked style="margin-right:4px;" /> Enable pagination</label>
        <label style="font-weight:normal;font-size:13px;margin:0;display:flex;align-items:center;gap:6px;">Search:
            <input type="text" id="${id}-search" style="height:28px;padding:2px 6px;border:1px solid #ccc;border-radius:4px;" />
        </label>
    </div>`;
    tableHTML += `<table id='${id}' class="table table-bordered" style="width: 100%; border-collapse: collapse;">`;

    if(!isReverse){
        // Header row (months across)
        tableHTML += '<thead><tr><th></th>';
        labels.forEach(label => {
            tableHTML += `<th>${label}</th>`;
        });
        tableHTML += '</tr></thead><tbody>';
        // Rows for each dataset
        datasets.forEach(set => {
            tableHTML += `<tr><td>${set.name}</td>`;
            set.values.forEach(value => {
                tableHTML += `<td>${formatWithUnit(value, set.unit)}</td>`;
            });
            tableHTML += '</tr>';
        });
        // Add totals row (sum for each column, excluding datasets with '%' in set.name)
        if (datasets.length > 0 && showTotal) {
            const totalUnit = (datasets.find(set => !isPercentDataset(set)) || {}).unit;
            tableHTML += `<tr style="font-weight:bold;background:#f7f7f7;"><td>Total</td>`;

            for (let i = 0; i < labels.length; i++) {
                let colTotal = 0;

                datasets.forEach(set => {
                    if (!isPercentDataset(set)) {
                        colTotal += Number(set.values[i]) || 0;
                    }
                });

                tableHTML += `<td>${formatWithUnit(colTotal, totalUnit)}</td>`;
            }

            tableHTML += '</tr>';
        }
        tableHTML += '</tbody></table>';
    }
    else{
        // Header row (datasets across)
        tableHTML += '<thead><tr><th></th>';
        datasets.forEach(set => {
            tableHTML += `<th>${set.name}</th>`;
        });
        tableHTML += '</tr></thead><tbody>';
        // Rows for each label
        const deferredRevenueRegex = /^Deferred Revenue (FY\d+)$/;
        labels.forEach((label, labelIdx) => {
            tableHTML += `<tr><td>${escapeHtml(label)}</td>`;
            datasets.forEach(set => {
                if(set.isColorCoded != undefined && set.isColorCoded){
                    if(set.values[labelIdx] >= 0 && set.values[labelIdx] < 41){
                        tableHTML += `<td style="background-color:green"></td>`;
                    }
                    if(set.values[labelIdx] >= 41 && set.values[labelIdx] < 76){
                        tableHTML += `<td style="background-color:yellow"></td>`;
                    }
                    if(set.values[labelIdx] >= 76){
                        tableHTML += `<td style="background-color:red"></td>`;
                    }
                }
                else{
                    const fyMatch = deferredRevenueRegex.exec(set.name || '');
                    if (fyMatch) {
                        tableHTML += `<td class="deferred-revenue-cell" style="cursor:pointer;text-decoration:underline;color:#2490ef;" data-project="${escapeHtmlAttr(label)}" data-fy="${escapeHtmlAttr(fyMatch[1])}" title="Click to view sales orders">${formatWithUnit(set.values[labelIdx], set.unit)}</td>`;
                    } else {
                        tableHTML += `<td>${formatWithUnit(set.values[labelIdx], set.unit)}</td>`;
                    }
                }
            });
            tableHTML += '</tr>';
        });
        // Add totals row (sum for each dataset, exclude if name has '%')
        if (showTotal) {
            let hasNonPercent = datasets.some(set => !isPercentDataset(set));
            if (hasNonPercent) {
                tableHTML += `<tr style="font-weight:bold;background:#f7f7f7;"><td>Total</td>`;
                datasets.forEach(set => {
                    if (!isPercentDataset(set)) {
                        // Sum all values for this dataset
                        let total = set.values.reduce((acc, v) => acc + (Number(v) || 0), 0);
                        tableHTML += `<td>${formatWithUnit(total, set.unit)}</td>`;
                    } else {
                        tableHTML += `<td></td>`;
                    }
                });
                tableHTML += '</tr>';
            }
        }
        tableHTML += '</tbody></table>';
    }

    // Add textarea and submit button below the table
    tableHTML += `<div style="margin-top: 8px;"><label style="font-weight:bold; min-width:70px;">Comment:</label> <textarea id="${element_id}-comment" class="form-control" placeholder="Add comment for this table..." style="width:100%;"></textarea><br><button onclick="submitComment('${element_id}')" type="button" class="btn btn-primary">Submit</button></div><div id="${element_id}-comments-list"></div>`;

    // Inject table
    const container = document.getElementById(tableContainerId);
    if (container) {
        container.innerHTML = tableHTML;
        container.querySelectorAll('.deferred-revenue-cell').forEach(cell => {
            cell.addEventListener('click', function() {
                showDeferredRevenueDialog(this.getAttribute('data-project'), this.getAttribute('data-fy'));
            });
        });
    }


    // Use jQuery DataTables plugin without overriding Frappe's global DataTable constructor.
    // Default is to show all rows at once; the toggle switches to paged mode.
    const paginationToggle = document.getElementById(`${id}-pagination-toggle`);
    if (paginationToggle) {
        paginationToggle.addEventListener('change', function() {
            initChartDataTable(id, this.checked);
        });
    }
    initChartDataTable(id, true);

    const start_date = document.getElementById("start_date").value;
    const end_date = document.getElementById("end_date").value;

    frappe.call({
        method: 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_comments_for_period',
        args: { element_id, start_date, end_date },
        type: 'GET',
        callback: function(r) {
            if (r.message) {
                var comments = r.message["comments"];
                var comment_html = ""

                for(var i = 0; i < comments.length; i++){
                    var c = comments[i];
                    comment_html += `<div style="border:1px solid #ccc; border-radius:6px; padding:10px; margin-top:8px;" id="comment-block-${c.name}">
                        <div style="font-size:12px; color:#555; margin-bottom:6px; display:flex; justify-content:space-between; align-items:center;">
                            <span><strong>${c.commented_by}</strong></span>
                            <span>
                                <button class="btn btn-xs btn-secondary" onclick="editComment('${element_id}', '${c.name}', '${encodeURIComponent(c.comment)}')">Edit</button>
                                <button class="btn btn-xs btn-danger" onclick="deleteComment('${element_id}', '${c.name}')">Delete</button>
                            </span>
                        </div>
                        <div style="font-size:14px; color:#222;" id="comment-content-${c.name}">${c.comment}</div>
                    </div>`;
                }
                const commentsContainer = document.getElementById(`${element_id}-comments-list`);
                if(commentsContainer){
                    commentsContainer.innerHTML = comment_html;
                }
            } 
        }
    });

// --- Global functions for comment editing ---
}

// Edit a comment (show textarea for editing)
function editComment(element_id, comment_id, encodedComment) {
    var commentBlock = document.getElementById(`comment-block-${comment_id}`);
    var commentContent = document.getElementById(`comment-content-${comment_id}`);
    if (!commentBlock || !commentContent) return;
    var comment = decodeURIComponent(encodedComment);
    commentContent.innerHTML = `<textarea id="edit-textarea-${comment_id}" class="form-control" style="width:100%; margin-bottom:6px;">${comment}</textarea>
        <button class='btn btn-primary btn-xs' onclick="updateComment('${element_id}', '${comment_id}')">Save</button>
        <button class='btn btn-secondary btn-xs' onclick="cancelEditComment('${comment_id}', '${encodeURIComponent(comment)}')">Cancel</button>`;
}

// Cancel editing a comment
function cancelEditComment(comment_id, encodedComment) {
    var commentContent = document.getElementById(`comment-content-${comment_id}`);
    if (!commentContent) return;
    var comment = decodeURIComponent(encodedComment);
    commentContent.innerHTML = comment;
}

// Update a comment (send to backend)
function updateComment(element_id, comment_id) {
    var textarea = document.getElementById(`edit-textarea-${comment_id}`);
    if (!textarea) return;
    var newComment = textarea.value.trim();
    if (!newComment) {
        frappe.msgprint("Comment cannot be empty.");
        return;
    }
    const start_date = document.getElementById("start_date").value;
    const end_date = document.getElementById("end_date").value;
    frappe.call({
        method: 'kartoza_custom.kartoza_custom.kartoza_dashboard.update_comment',
        args: { comment_id, comment: newComment, element_id, start_date, end_date },
        callback: function(r) {
            if (r.message && r.message.success) {
                // frappe.msgprint("Comment updated successfully.");
                // Refresh comments list
                refreshComments(element_id, start_date, end_date);
            } else {
                frappe.msgprint("Failed to update comment.");
            }
        }
    });
}

// Delete a comment (send to backend)
function deleteComment(element_id, comment_id) {
    if (!confirm("Are you sure you want to delete this comment?")) return;
    const start_date = document.getElementById("start_date").value;
    const end_date = document.getElementById("end_date").value;
    frappe.call({
        method: 'kartoza_custom.kartoza_custom.kartoza_dashboard.delete_comment',
        args: { comment_id, element_id, start_date, end_date },
        callback: function(r) {
            if (r.message && r.message.success) {
                // frappe.msgprint("Comment deleted successfully.");
                // Refresh comments list
                refreshComments(element_id, start_date, end_date);
            } else {
                frappe.msgprint("Failed to delete comment.");
            }
        }
    });
}

// Refresh comments list for a chart
function refreshComments(element_id, start_date, end_date) {
    frappe.call({
        method: 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_comments_for_period',
        args: { element_id, start_date, end_date },
        type: 'GET',
        callback: function(r) {
            if (r.message) {
                var comments = r.message["comments"];
                var comment_html = "";
                for(var i = 0; i < comments.length; i++){
                    var c = comments[i];
                    comment_html += `<div style=\"border:1px solid #ccc; border-radius:6px; padding:10px; margin-top:8px;\" id=\"comment-block-${c.name}\">`
                        + `<div style=\"font-size:12px; color:#555; margin-bottom:6px; display:flex; justify-content:space-between; align-items:center;\">`
                        + `<span><strong>${c.commented_by}</strong></span>`
                        + `<span>`
                        + `<button class=\"btn btn-xs btn-secondary\" onclick=\"editComment('${element_id}', '${c.name}', '${encodeURIComponent(c.comment)}')\">Edit</button> `
                        + `<button class=\"btn btn-xs btn-danger\" onclick=\"deleteComment('${element_id}', '${c.name}')\">Delete</button>`
                        + `</span></div>`
                        + `<div style=\"font-size:14px; color:#222;\" id=\"comment-content-${c.name}\">${c.comment}</div>`
                        + `</div>`;
                }
                const commentsContainer = document.getElementById(`${element_id}-comments-list`);
                if(commentsContainer){
                    commentsContainer.innerHTML = comment_html;
                }
            }
        }
    });
}
// Escape a value for safe use as HTML text content
function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Escape a value for safe use inside an HTML attribute
function escapeHtmlAttr(value) {
    return escapeHtml(value);
}

// Fetch and show the sales orders/line items behind a deferred revenue cell
function showDeferredRevenueDialog(project, financialYear) {
    if (!project || !financialYear) return;

    const end_date = document.getElementById("end_date").value;

    frappe.dom.freeze('Loading sales order details...');

    frappe.call({
        method: 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_deferred_revenue_sales_orders',
        args: { project, financial_year: financialYear, end_date },
        type: 'GET',
        callback: function(r) {
            const salesOrders = (r.message && r.message.sales_orders) || [];
            renderDeferredRevenueDialog(project, financialYear, salesOrders);
        },
        error: function() {
            frappe.msgprint("Error occurred while fetching sales order details.");
        },
        always: function() {
            frappe.dom.unfreeze();
        }
    });
}

function renderDeferredRevenueDialog(project, financialYear, salesOrders) {
    let bodyHtml = '';

    if (!salesOrders.length) {
        bodyHtml = '<p>No sales orders found for this deferred revenue amount.</p>';
    } else {
        salesOrders.forEach(so => {
            bodyHtml += `
                <div style="margin-bottom:20px;">
                    <h5 style="margin-bottom:8px;">
                        <a href="/app/sales-order/${encodeURIComponent(so.sales_order)}" target="_blank">
                            ${escapeHtml(so.sales_order)}
                        </a>
                    </h5>
                    <table class="table table-bordered" style="width:100%;">
                        <thead>
                            <tr>
                                <th>Item</th>
                                <th>Delivery Date</th>
                                <th>Amount</th>
                            </tr>
                        </thead>
                        <tbody>`;

            so.items.forEach(item => {
                const itemLabel = item.item_name || item.item_code || '';
                bodyHtml += `
                            <tr>
                                <td>${escapeHtml(itemLabel)}</td>
                                <td>${escapeHtml(item.delivery_date || '')}</td>
                                <td>${formatWithUnit(item.amount, 'rand')}</td>
                            </tr>`;
            });

            bodyHtml += `
                            <tr style="font-weight:bold;background:#f7f7f7;">
                                <td colspan="2">Subtotal</td>
                                <td>${formatWithUnit(so.total, 'rand')}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>`;
        });
    }

    const dialog = new frappe.ui.Dialog({
        title: `Deferred Revenue - ${escapeHtml(project)} (${escapeHtml(financialYear)})`,
        size: 'large',
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'deferred_revenue_html',
                options: bodyHtml
            }
        ]
    });
    dialog.show();
}

// Format numbers with spaces as thousands separators, no M/K/B suffixes
function formatNumber(value) {
    if (typeof value === 'number') {
        return value.toLocaleString('en-US').replace(/,/g, ' ');
    }
    let num = Number(value);
    if (!isNaN(num)) {
        return num.toLocaleString('en-US').replace(/,/g, ' ');
    }
    return value;
}

// Append the unit (hours, employees, percent, rand, count) to a formatted number
const UNIT_DISPLAY = {
    rand: { prefix: 'R ' },
    percent: { suffix: '%' },
    hours: { suffix: ' hrs' },
    employees: { suffix: ' employees' },
    count: {}
};

function formatWithUnit(value, unit) {
    const formatted = formatNumber(value);
    const display = UNIT_DISPLAY[unit];
    if (!display) return formatted;
    return `${display.prefix || ''}${formatted}${display.suffix || ''}`;
}

function formatNumberShortHand(value) {
    if (typeof value === 'number') {
        if (Math.abs(value) >= 1e9) {
            return (value/1e9).toFixed(2).replace(/\.00$/, '') + 'B';
        } else if (Math.abs(value) >= 1e6) {
            return (value/1e6).toFixed(2).replace(/\.00$/, '') + 'M';
        } else if (Math.abs(value) >= 1e3) {
            return (value/1e3).toFixed(2).replace(/\.00$/, '') + 'K';
        } else {
            return value.toLocaleString();
        }
    }
    // Try to parse if string
    let num = Number(value);
    if (!isNaN(num)) {
        return formatNumberShortHand(num);
    }
    return value;
}

function submitComment(element_id) {
    const textarea = document.getElementById(`${element_id}-comment`);
    if (textarea) {
        const comment = textarea.value.trim();
        if (!comment) {
            frappe.msgprint("Please enter a comment before submitting.");
            return;
        }
        // Get selected dates
        const start_date = document.getElementById("start_date").value;
        const end_date = document.getElementById("end_date").value;
        // Send comment to server
        frappe.call({
            method: 'kartoza_custom.kartoza_custom.kartoza_dashboard.submit_comment',
            args: { element_id, comment, start_date, end_date },
            callback: function(r) {
                if (r.message && r.message.success) {
                    // frappe.msgprint("Comment submitted successfully.");
                    textarea.value = '';
                    const start_date = document.getElementById("start_date").value;
                    const end_date = document.getElementById("end_date").value;
                    refreshComments(element_id, start_date, end_date);
                } else {
                    frappe.msgprint("Failed to submit comment. Please try again.");
                }
            }
        });
    }
}


