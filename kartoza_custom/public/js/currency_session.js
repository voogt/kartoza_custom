$(document).ready(function(){

    $('.address-container').on('DOMSubtreeModified', function(){
        location.reload()
    });

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
            method: "erpnext.e_commerce.shopping_cart.cart.get_cart_quotation", //dotted path to server method
            type: "GET",
            callback: function(r) {
                console.log(r.message.doc)
                // code snippet
                if(r.message.doc.items.length == 0){
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
                }
                else{
                    frappe.throw(("Different currencies in shopping cart is not allowed"))
                }
                
            }
        });

        
    });

   
});