// Function to dynamically add GTM script to the page
function loadGTM() {
    const script = document.createElement('script');
    script.src = 'https://www.googletagmanager.com/gtag/js?id=GTM-K5ZVLM2';
    script.async = true;
    document.head.appendChild(script);

    // // Once the script is loaded, initialize gtag
    // script.onload = function() {
    //     // Initialize gtag function
    //     window.dataLayer = window.dataLayer || [];
    //     function gtag() {
    //         window.dataLayer.push(arguments);
    //     }
    //     gtag('js', new Date());

    //     // Example of using gtag to track pageview
    //     gtag('config', 'GTM-K5ZVLM2');
    // };
}

// Load GTM when the page is ready or as needed

document.addEventListener('DOMContentLoaded', function () {
    loadGTM();
    if (!getCookie('cookieConsent') && !getCookie('cookieDecline')) {
        // Inject banner HTML if not already present
        if (!document.getElementById('cookieConsentBanner')) {
            var bannerHtml = `
                <div id="cookieConsentBanner">
                    <div class="container" style="border:none">
                        <div class="modal-content" style="border:none">
                            <div class="modal-body" id="modal-cookie" style="border:none"> 
                                <button type="button" class="close" id="closeBanner">&times;</button>
                                <div class="row" style="align-items: center;">
                                    <div class="col-md-2 col-sm-12" id="cookie-header">
                                        <h5 class="modal-title">Cookie Consent</h5>
                                    </div>
                                    <div class='col-md-6 col-sm-12' id="cookie-text">
                                        <p style='margin-bottom:0px !important;'> This website uses cookies to ensure you get the best experience.</p>
                                    </div>
                                    <div class='col-md-3 col-sm-12' id="cookie-btn">
                                        <div>
                                            <button type="button" class="btn btn-primary" id="acceptCookies">Accept</button>
                                            <button type="button" class="btn btn-primary" id="declineCookies">Decline</button>
                                            
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>`;
            document.body.insertAdjacentHTML('beforeend', bannerHtml);
        }

        // Show banner
        document.getElementById('cookieConsentBanner').style.display = 'block';

        document.getElementById('acceptCookies').onclick = function () {
            setCookie('cookieConsent', 'true', 365);
            loadGoogleTagManagerGranted();
            document.getElementById('cookieConsentBanner').style.display = 'none';
        };

        document.getElementById('declineCookies').onclick = function () {
            setCookie('cookieDecline', 'true', 365);
            loadGoogleTagManagerDenied();
            document.getElementById('cookieConsentBanner').style.display = 'none';
        };

        document.getElementById('closeBanner').onclick = function () {
            document.getElementById('cookieConsentBanner').style.display = 'none';
        };
    } else if (getCookie('cookieConsent')) {
        loadGoogleTagManagerGranted(); // Load GTM if the user has already accepted cookies
    }
});

function setCookie(name, value, days) {
    var expires = "";
    if (days) {
        var date = new Date();
        date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
        expires = "; expires=" + date.toUTCString();
    }
    document.cookie = name + "=" + (value || "") + expires + "; path=/";
}

function getCookie(name) {
    var nameEQ = name + "=";
    var ca = document.cookie.split(';');
    for (var i = 0; i < ca.length; i++) {
        var c = ca[i];
        while (c.charAt(0) == ' ') c = c.substring(1, c.length);
        if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length, c.length);
    }
    return null;
}

function loadGoogleTagManagerGranted() {
    // Google Tag Manager code insertion
    gtag('consent', 'update', {
        'ad_user_data': 'granted',
        'ad_personalization': 'granted',
        'ad_storage': 'granted',
        'analytics_storage': 'granted'
    });
}

function loadGoogleTagManagerDenied() {
    // Google Tag Manager code insertion
    gtag('consent', 'update', {
        'ad_user_data': 'denied',
        'ad_personalization': 'denied',
        'ad_storage': 'denied',
        'analytics_storage': 'denied'
    });
}
