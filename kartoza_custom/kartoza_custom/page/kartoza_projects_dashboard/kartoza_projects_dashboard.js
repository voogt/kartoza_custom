// Pagination state for Project Performance chart
let performanceChartState = {
    page: 1,
    page_size: 10,
    total_pages: 1
};

frappe.pages['kartoza-projects-dashboard'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Kartoza Projects Dashboard',
		single_column: true
	});

	page.main.html(`

        <div id="loader-container" style="text-align:center; margin-top:30px;">
            <div id="loader" style="display:none;">
                <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                <span id="loader-text" style="margin-left:8px;"></span>
            </div>
        </div>
        <div id="parent-chart"></div>
        
    `);

    loadCSS();
    loadScript();
    fetchDataAndPlot();             // Load all normal charts
    fetchPerformanceChart();        // Load performance chart
}

// Load external resources
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

// Simple loader controls
function setLoader(visible, text) {
    const loader = document.getElementById("loader");
    const textEl = document.getElementById("loader-text");
    if (loader) loader.style.display = visible ? 'inline-flex' : 'none';
    if (typeof text === 'string' && textEl) textEl.textContent = text;
}

// Fetch generic charts
function fetchDataAndPlot() {
    document.getElementById('parent-chart').innerHTML = ''; // Clear previous charts
    // Show loader and keep it visible until all requests complete

    var methods = [
		'kartoza_custom.kartoza_custom.kartoza_projects_dashboard.project_time_overview_chart',
        'kartoza_custom.kartoza_custom.kartoza_projects_dashboard.get_project_sla_overview_table',
		'kartoza_custom.kartoza_custom.kartoza_projects_dashboard.get_task_drill_down_table'
    ]

    const total = methods.length;
    let inflight = 0;
    let completed = 0;

    const updateLoaderText = () => setLoader(true, `Loading ${completed}/${total}…`);
    // initialize loader
    updateLoaderText();

    for (var i = 0; i < methods.length; i++){
        inflight++;
        updateLoaderText();
		frappe.call({
			method: methods[i],
			args: {},
			type: 'GET',
			callback: function(r) {
				if (r.message) {
					if(r.message.type == 'table'){
						renderChartTable(r.message.labels, r.message.datasets, false, r.message.element_id, r.message.title)
					}
					else{
						drawChart(r.message.labels, r.message.datasets, r.message.title, r.message.element_id, 'single', r.message.shouldSplitLongLabels,);
					}
				} else {
					frappe.msgprint("No data returned.");
				}
                // finalize one request
                inflight--; completed++;
                if (inflight <= 0) {
                    setLoader(false, '');
                } else {
                    updateLoaderText();
                }
			}
            , error: function() {
                // on error, still account for completion
                inflight--; completed++;
                if (inflight <= 0) {
                    setLoader(false, '');
                } else {
                    updateLoaderText();
                }
            }
		});
	}
}

// Fetch performance chart (paginated)
function fetchPerformanceChart() {

    frappe.call({
        method: 'kartoza_custom.kartoza_custom.kartoza_projects_dashboard.project_performance_overview_chart',
        args: {
            page: performanceChartState.page,
            page_size: performanceChartState.page_size,
            project_name: document.getElementById("filter-project-name")?.value || "",
            project_manager: document.getElementById("filter-project-manager")?.value || "",
            start_date: document.getElementById("filter-start-date")?.value || "",
            end_date: document.getElementById("filter-end-date")?.value || ""
        },
        callback: function(r) {

            if (!r.message) {
                frappe.msgprint("No performance data returned.");
                return;
            }

            const data = r.message;

            if (data.pagination) {
                performanceChartState.total_pages = data.pagination.total_pages;
            }

            drawPerformanceChart(
                data.labels,
                data.datasets,
                data.title
            );
        }
    });
}

// Draw performance chart
function drawPerformanceChart(labels, datasets, title) {
    const parentElement = document.getElementById('parent-chart');
    let container = document.getElementById("performance-chart-container");

    if (!container) {
        parentElement.insertAdjacentHTML('beforeend', `
            <div id="performance-chart-container" style="margin-bottom: 80px;">
                <h3 id="performance-chart-title" style='text-align: center;'></h3>

                <div style="display:flex; gap:10px; justify-content:center; flex-wrap:wrap; margin-bottom:20px;">
                    <input type="text" id="filter-project-name" placeholder="Project Name" class="form-control" style="width:200px;">
                    <input type="text" id="filter-project-manager" placeholder="Project Manager" class="form-control" style="width:200px;">
                    <input type="date" id="filter-start-date" class="form-control" style="width:180px;">
                    <input type="date" id="filter-end-date" class="form-control" style="width:180px;">
                    <button id="apply-filters-btn" class="btn btn-primary btn-sm">Apply</button>
                </div>

                <div style="text-align:center; margin-bottom:15px;">
                    <button id="prev-page-btn" class="btn btn-sm btn-secondary">Previous</button>
                    <span id="performance-page-indicator" style="margin:0 15px;"></span>
                    <button id="next-page-btn" class="btn btn-sm btn-secondary">Next</button>
                </div>

                <div id="performance-chart"></div>
                <hr>
            </div>
        `);

        container = document.getElementById("performance-chart-container");
    }

    const titleEl = document.getElementById("performance-chart-title");
    if (titleEl) {
        titleEl.textContent = title;
    }

    const prevBtn = document.getElementById("prev-page-btn");
    const nextBtn = document.getElementById("next-page-btn");
    const pageIndicator = document.getElementById("performance-page-indicator");

    if (prevBtn) {
        prevBtn.disabled = performanceChartState.page <= 1;
    }
    if (nextBtn) {
        nextBtn.disabled = performanceChartState.page >= performanceChartState.total_pages;
    }
    if (pageIndicator) {
        pageIndicator.textContent = `Page ${performanceChartState.page} of ${performanceChartState.total_pages}`;
    }
    
    // Labels
    const traces = datasets.map(set => ({
        x: labels,
        y: set.values,
        name: set.name,
        type: 'bar',
        hovertemplate: "%{fullData.name}: %{y:.1f}%<extra></extra>"
    }));

    // Labels Layout
    const layout = {
        barmode: 'group',
        hovermode: 'x unified',
        margin: { b: 150, t: 60, l: 80, r: 40 },
        xaxis: {
            tickangle: -30,
            automargin: true
        },
        yaxis: {
            ticksuffix: "%",
            tickformat: ".0f",
            range: [0, 110]
        }
    };

    Plotly.newPlot("performance-chart", traces, layout, {displayModeBar: false});

    document.getElementById("apply-filters-btn").onclick = function() {
        performanceChartState.page = 1;
        fetchPerformanceChart();
    };

    document.getElementById("prev-page-btn").onclick = function() {
        if (performanceChartState.page > 1) {
            performanceChartState.page--;
            fetchPerformanceChart();
        }
    };

    document.getElementById("next-page-btn").onclick = function() {
        if (performanceChartState.page < performanceChartState.total_pages) {
            performanceChartState.page++;
            fetchPerformanceChart();
        }
    };
}

// Draw generic charts
function drawChart(labels, datasets, title, element_id, barmode, shouldSplitLongLabels) {
    // Ensure unique element_id for each chart
    const unique_element_id = `${element_id}-${generateRandomId()}`;
    const containerId = `${unique_element_id}-container`;

	const parentElement = document.getElementById('parent-chart');

	parentElement.insertAdjacentHTML('beforeend', `
        <div id="${containerId}" style="margin-bottom: 80px;">
            <h3 style='text-align: center;'>${title}</h3>
            <div id="${unique_element_id}" style="margin-top: 20px;"></div>
            <hr>
        </div>
    `);

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
    // Render the chart without the top toolbar
    Plotly.newPlot(unique_element_id, traces, layout, {displayModeBar: false});
}

function generateRandomId(prefix = 'id') {
    // Generate a random string of 8 characters
    const randomStr = Math.random().toString(36).substr(2, 8);
    return `${prefix}-${randomStr}`;
}

// Table renderer
function renderChartTable(labels, datasets, showTotal, element_id, title) {

	const unique_element_id = `${element_id}-${generateRandomId()}`;
    const containerId = `${unique_element_id}-container`;
	const parentElement = document.getElementById('parent-chart');

	parentElement.insertAdjacentHTML('beforeend', `
        <div id="${containerId}" style="margin-bottom: 80px;">
            <h3 style='text-align: center;'>${title}</h3>
            <div id="${unique_element_id}-table" style="margin-top: 20px;"></div>
            <hr>
        </div>
    `);

    let id = generateRandomId('elem');
    let tableHTML = `<table id='${id}' class="table table-bordered" style="width: 100%; border-collapse: collapse;">`;

	// Header row (datasets across)
	tableHTML += '<thead><tr>';
	labels.forEach(label => {
		tableHTML += `<th>${label}</th>`;
	});
	tableHTML += '</tr></thead><tbody>';
	// Rows for each label
	datasets.forEach((dataset) => {
		tableHTML += `<tr>`;
		for (let key in dataset) {
			if (dataset.hasOwnProperty(key)) {
				tableHTML += `<td>${formatNumber(dataset[key])}</td>`;
			}
		}
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

    // Inject table
    const container = document.getElementById(`${unique_element_id}-table`);
    if (container) {
        container.innerHTML = tableHTML;
    }

    // Initialize DataTable
    const dt = new DataTable(`#${id}`, {
        lengthChange: false,
        ordering: false
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


