from datetime import datetime
app_name = "kartoza_custom"
app_title = "Kartoza Custom"
app_publisher = "Kartoza"
app_description = "Customisation for Kartoza"
app_email = "juanique@kartoza.com"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/kartoza_custom/css/kartoza_custom.css"
app_include_js = [
    f"/assets/kartoza_custom/js/sales_order_override.js?v={datetime.now()}",
]

# include js, css files in header of web template
web_include_css = f"/assets/kartoza_custom/css/main.css?v={datetime.now()}"
web_include_js = [
    f"/assets/kartoza_custom/js/currency_session.js?v={datetime.now()}",
    f"/assets/kartoza_custom/js/cookie_enabler.js?v={datetime.now()}",
    f"/assets/kartoza_custom/js/shopping_cart.js?v={datetime.now()}"
]

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "kartoza_custom/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"Sales Order" : f"public/js/sales_order_override.js?v={datetime.now()}"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "kartoza_custom.utils.jinja_methods",
# 	"filters": "kartoza_custom.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "kartoza_custom.install.before_install"
# after_install = "kartoza_custom.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "kartoza_custom.uninstall.before_uninstall"
# after_uninstall = "kartoza_custom.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "kartoza_custom.utils.before_app_install"
# after_app_install = "kartoza_custom.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "kartoza_custom.utils.before_app_uninstall"
# after_app_uninstall = "kartoza_custom.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "kartoza_custom.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	# "ToDo": "custom_app.overrides.CustomToDo"
    "E Commerce Settings": "kartoza_custom.overrides.MultiCurrency"
}

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"kartoza_custom.tasks.all"
# 	],
# 	"daily": [
# 		"kartoza_custom.tasks.daily"
# 	],
# 	"hourly": [
# 		"kartoza_custom.tasks.hourly"
# 	],
# 	"weekly": [
# 		"kartoza_custom.tasks.weekly"
# 	],
# 	"monthly": [
# 		"kartoza_custom.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "kartoza_custom.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "kartoza_custom.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "kartoza_custom.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["kartoza_custom.utils.before_request"]
# after_request = ["kartoza_custom.utils.after_request"]

# Job Events
# ----------
# before_job = ["kartoza_custom.utils.before_job"]
# after_job = ["kartoza_custom.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"kartoza_custom.auth.validate"
# ]

fixtures = [
    {"doctype": "Moodle Course Settings"},
    {"doctype": "Kartoza Cash Flow Mapping"},
    {"doctype": "Kartoza Cash Flow Mapping Template"},
    {"doctype": "Kartoza Cash Flow Mapper"},
    {"doctype": "Kartoza Cash Flow Mapping Template Details"},
    {"doctype": "Kartoza Cash Flow Mapping Accounts"},
    {"doctype": "Kartoza Reports"},
    {"doctype": "EasyFile txt generator"},
	{
	"doctype": "Report",
	"filters": [["name", "in", ["Kartoza Cash Flow", "Consolidated Financial Statement (All Companies)"]]]
   }
]

website_route_rules = [
	
	{"from_route": "/proforma-quotations", "to_route": "Quotation"},
	{
		"from_route": "/proforma-quotations/<path:name>",
		"to_route": "order_",
		"defaults": {
			"doctype": "Quotation",
			"parents": [{"label": "Quotations", "route": "quotations"}],
		},
	},
	
]
