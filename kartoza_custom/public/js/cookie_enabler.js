// Function to dynamically add GTM script to the page
function loadGTM(callback) {
    const script = document.createElement('script');
    script.src = 'https://www.googletagmanager.com/gtag/js?id=G-Q0PPBT1N7V';
    script.async = true;

    // Initialize gtag after the script has loaded
    script.onload = function () {
        window.dataLayer = window.dataLayer || [];
        function gtag() {
            window.dataLayer.push(arguments);
        }
        window.gtag = gtag; // Make gtag globally accessible
        gtag('js', new Date());
        gtag('config', 'G-Q0PPBT1N7V');

        if (typeof callback === 'function') {
            callback(); // Trigger the callback after gtag is initialized
        }
    };

    document.head.appendChild(script);
}

function loadGoogleTagManagerGranted() {
    if (typeof gtag === 'function') {
        gtag('consent', 'update', {
            'ad_user_data': 'granted',
            'ad_personalization': 'granted',
            'ad_storage': 'granted',
            'analytics_storage': 'granted'
        });
    } else {
        console.error('gtag is not defined yet.');
    }
}

function loadGoogleTagManagerDenied() {
    if (typeof gtag === 'function') {
        gtag('consent', 'update', {
            'ad_user_data': 'denied',
            'ad_personalization': 'denied',
            'ad_storage': 'denied',
            'analytics_storage': 'denied'
        });
    } else {
        console.error('gtag is not defined yet.');
    }
}

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

// Load GTM when the page is ready or as needed
document.addEventListener('DOMContentLoaded', function () {
    if (!getCookie('cookieConsent') && !getCookie('cookieDecline')) {
        // Inject banner HTML if not already present
        if (!document.getElementById('cookieConsentBanner')) {
            const bannerHtml = `
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
                                        <p style='margin-bottom:0px !important;'>This website uses cookies to ensure you get the best experience.</p>
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
            loadGTM(loadGoogleTagManagerGranted); // Ensure GTM script is loaded before calling granted function
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
        loadGTM(loadGoogleTagManagerGranted); // Ensure GTM script is loaded before calling granted function
    }
});


