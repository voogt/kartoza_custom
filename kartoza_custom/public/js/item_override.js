if (erpnext && erpnext.ProductList) {
    class CustomProductList extends erpnext.ProductList {
        // Override the make method
        get_primary_button(item, settings) {
            return `
                    <a href="/${item.route || "#"}">
                        <div class="btn btn-sm btn-explore-variants btn mb-0 mt-0">
                            ${__("Explore")}
                        </div>
                    </a>
                `;
        }
    }

    // Replace the original class with the custom one
    erpnext.ProductList = CustomProductList;
}