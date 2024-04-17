$(document).ready(function(){

    frappe.call({
        method: "kartoza_custom.kartoza_custom.doctype.multi_currency_settings.multi_currency_settings.retrieve_currency_cache", //dotted path to server method
        type: "GET",
        callback: function(r) {
            // code snippet
            var currency = r.message
            try {
                document.getElementById("dropdownMenuButton").innerText = currency
            } catch (error) {
                
            }
        }
    });

    $('#currencyChange').change(function(){
        selected_value = $("input[name='currency']:checked").val();

        frappe.call({
            method: "kartoza_custom.kartoza_custom.doctype.multi_currency_settings.multi_currency_settings.set_currency_cache", //dotted path to server method
            type: "GET",
            args: {
                "currency": selected_value
            },
            callback: function(r) {
                // code snippet
                console.log(r.message)
                location.reload()
            }
        });
    });
});