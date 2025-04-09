frappe.ready(() => {
    function addImageWithLink() {
        const headings = document.querySelectorAll("h1");

        for (const heading of headings) {
            if (heading.textContent.trim() === "Blog") {
                // Create an anchor (link) element
                const link = document.createElement("a");
                link.href = "https://kartoza.com/rss.xml";
                link.target = "_blank"; // Open in new tab
                link.rel = "noopener noreferrer";

                // Create an image element
                const img = document.createElement("img");
                img.src = "/assets/kartoza_custom/images/rss-svgrepo-com.svg"; // Replace with your RSS icon
                img.alt = "RSS Feed";
                img.style.marginLeft = "10px";
                img.style.width = "20px";  // Adjust size
                img.style.position = 'absolute';
                img.style.top= '0px'

                // Append image inside link
                link.appendChild(img);

                // Insert link after the heading
                heading.insertAdjacentElement("afterend", link);
                break;
            }
        }
    }

    addImageWithLink();
});
