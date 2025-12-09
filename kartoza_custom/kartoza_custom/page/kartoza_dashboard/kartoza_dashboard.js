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
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_billable_hours',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_utilisation',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_projects_data',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_activity_cost_data',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_company_salary_pty',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_company_salary_lda',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_company_pipeline_pty',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_company_pipeline_opportunities_pty',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_company_pipeline_opportunities_lda',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_company_pipeline_lda',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_open_sales_orders',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_open_sla',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_item_wise_annual_sales_pty',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_item_wise_annual_sales_lda',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_sales_analytics_customers_pty',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_sales_analytics_customers_lda',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_overhead_cost_pty',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_overhead_cost_lda',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_project_closed_summary',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_tender_summary',
        'kartoza_custom.kartoza_custom.kartoza_dashboard.get_opportunity_trend',
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
                        drawChart(r.message.labels, r.message.datasets, r.message.title, r.message.element_id, r.message.type, r.message.isReverse, r.message.help, r.message.shouldSplitLongLabels, r.message.showTotal);
                        addCards(r.message.total_cards);
                    } else {
                        frappe.msgprint("No data returned.");
                    }
                    // After cost center, call profit center
                    frappe.call({
                        method: 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_profit_cost_lost_revenue_data',
                        args: { start_date, end_date, type_center:'Cost' },
                        type: 'GET',
                        callback: function(r) {
                            if (r.message) {
                                drawChart(r.message.labels, r.message.datasets, r.message.title, r.message.element_id, r.message.type, r.message.isReverse, r.message.help, r.message.shouldSplitLongLabels, r.message.showTotal);
                                addCards(r.message.total_cards);
                            } else {
                                frappe.msgprint("No data returned.");
                            }
                            // Hide loader after last chart/table
                            frappe.call({
                                method: 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_cost_profit_center_data',
                                args: { start_date, end_date, type_center:'Profit' },
                                type: 'GET',
                                callback: function(r) {
                                    if (r.message) {
                                        drawChart(r.message.labels, r.message.datasets, r.message.title, r.message.element_id, r.message.type, r.message.isReverse, r.message.help, r.message.shouldSplitLongLabels, r.message.showTotal);
                                        addCards(r.message.total_cards);
                                    } else {
                                        frappe.msgprint("No data returned.");
                                    }
                                    // Hide loader after last chart/table
                                    frappe.call({
                                        method: 'kartoza_custom.kartoza_custom.kartoza_dashboard.get_profit_cost_lost_revenue_data',
                                        args: { start_date, end_date, type_center:'Profit' },
                                        type: 'GET',
                                        callback: function(r) {
                                            if (r.message) {
                                                drawChart(r.message.labels, r.message.datasets, r.message.title, r.message.element_id, r.message.type, r.message.isReverse, r.message.help, r.message.shouldSplitLongLabels, r.message.showTotal);
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
                    drawChart(r.message.labels, r.message.datasets, r.message.title, r.message.element_id, r.message.type, r.message.isReverse, r.message.help, r.message.shouldSplitLongLabels, r.message.showTotal);
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

const addCards = (data) => {
    const parentElement = document.getElementById('parent-cards');
    if (!parentElement) return;

    if(data.length > 0){
        data.forEach(card => {
            const cardElement = document.createElement('div');
            cardElement.className = 'card col-md-2';
            cardElement.style.margin = "10px"
            cardElement.innerHTML = `
                <div class="card-header" style="height:80px">${card.title}</div>
                <div class="card-body">${formatNumber(card.value)}</div>
            `;
            parentElement.appendChild(cardElement);
        });
    }
}

function drawChart(labels, datasets, title, element_id, barmode, isReverse, helpText, shouldSplitLongLabels, showTotal) {
    // Ensure unique element_id for each chart
    const unique_element_id = `${element_id}-${generateRandomId()}`;
    const containerId = `${unique_element_id}-container`;

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

    // Generate traces for Plotly chart
    const traces = datasets.map(set => ({
        x: processedLabels,
        y: set.values,
        name: set.name,
        type: set.type || 'bar',
        customdata: set.values.map(v => formatNumber(v)),
        // Show legend (dataset name) as the title in the hovertemplate
        hovertemplate: `<b>${set.name}</b><br>%{x}: %{customdata}<extra></extra>`
    }));

    let layout = {
        legend: {},
        margin: {b: shouldRotate ? 120 : 60, t: 60, l: 60, r: 30},
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
            <div id="${unique_element_id}-table" style="margin-top: 20px;"></div>
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

    // Render the chart without the top toolbar
    Plotly.newPlot(unique_element_id, traces, layout, {displayModeBar: false});

    // Render the table below the chart
    renderChartTable(labels, datasets, `${unique_element_id}-table`, isReverse, element_id, showTotal);
}

function generateRandomId(prefix = 'id') {
    // Generate a random string of 8 characters
    const randomStr = Math.random().toString(36).substr(2, 8);
    return `${prefix}-${randomStr}`;
}

function renderChartTable(labels, datasets, tableContainerId, isReverse, element_id, showTotal) {

    let id = generateRandomId('elem');
    let tableHTML = `<table id='${id}' class="table table-bordered" style="width: 100%; border-collapse: collapse;">`;

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
                tableHTML += `<td>${formatNumber(value)}</td>`;
            });
            tableHTML += '</tr>';
        });
        // Add totals row (sum for each column, excluding datasets with '%' in set.name)
        if (datasets.length > 0 && showTotal) {
            tableHTML += `<tr style="font-weight:bold;background:#f7f7f7;"><td>Total</td>`;

            for (let i = 0; i < labels.length; i++) {
                let colTotal = 0;

                datasets.forEach(set => {
                    if (!set.name.includes('%')) {
                        colTotal += Number(set.values[i]) || 0;
                    }
                });

                tableHTML += `<td>${formatNumber(colTotal)}</td>`;
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
        labels.forEach((label, labelIdx) => {
            tableHTML += `<tr><td>${label}</td>`;
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
                    tableHTML += `<td>${formatNumber(set.values[labelIdx])}</td>`;
                }
            });
            tableHTML += '</tr>';
        });
        // Add totals row (sum for each dataset, exclude if name has '%')
        if (showTotal) {
            let hasNonPercent = datasets.some(set => !set.name.includes('%'));
            if (hasNonPercent) {
                tableHTML += `<tr style="font-weight:bold;background:#f7f7f7;"><td>Total</td>`;
                datasets.forEach(set => {
                    if (!set.name.includes('%')) {
                        // Sum all values for this dataset
                        let total = set.values.reduce((acc, v) => acc + (Number(v) || 0), 0);
                        tableHTML += `<td>${formatNumber(total)}</td>`;
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
    }


    // Initialize DataTable
    const dt = new DataTable(`#${id}`, {
        lengthChange: false,
        ordering: false
    });

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
                    comment_html += `<div style="border:1px solid #ccc; border-radius:6px; padding:10px; margin-top:8px;">
                        <div style="font-size:12px; color:#555; margin-bottom:6px;">
                            <strong>${c.commented_by}</strong>
                        </div>
                        <div style="font-size:14px; color:#222;">${c.comment}</div>
                    </div>`;
                }

                const commentsContainer = document.getElementById(`${element_id}-comments-list`);
                if(commentsContainer){
                    commentsContainer.innerHTML = comment_html;
                }
            } 
        }
    });
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
                    frappe.msgprint("Comment submitted successfully.");
                    textarea.value = '';
                    var comments = r.message["comments"];
                    var comment_html = ""

                    comment_html += `<div style="border:1px solid #ccc; border-radius:6px; padding:10px; margin-top:8px;">
                        <div style="font-size:12px; color:#555; margin-bottom:6px;">
                            <strong>${r.message.commented_by}</strong>
                        </div>
                        <div style="font-size:14px; color:#222;">${r.message.comment}</div>
                    </div>`;

                    const commentsContainer = document.getElementById(`${element_id}-comments-list`);
                    if(commentsContainer){
                        commentsContainer.innerHTML += comment_html;
                    }
                } else {
                    frappe.msgprint("Failed to submit comment. Please try again.");
                }
            }
        });
    }
}


