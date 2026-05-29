import frappe

def execute():
    field = frappe.get_doc("DocField", {
        "parent": "Travel Itinerary",
        "fieldname": "mode_of_travel"
    })

    options = field.options or ""

    options_list = [o.strip() for o in options.split("\n") if o.strip()]

    if "Own Car" not in options_list:
        options_list.append("Own Car")

        field.options = "\n".join(options_list)
        field.save()