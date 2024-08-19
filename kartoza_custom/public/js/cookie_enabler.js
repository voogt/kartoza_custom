document.addEventListener('DOMContentLoaded', function () {
    if (!getCookie('cookieConsent') && !getCookie('cookieDecline')) {
        // Inject banner HTML if not already present
        if (!document.getElementById('cookieConsentBanner')) {
            var bannerHtml = `
                <div id="cookieConsentBanner">
                    <div class="container" style="border:none">
                        <div class="modal-content"  style="border:none">
                            <div class="modal-body" id="modal-cookie" style="border:none"> 
                                <div class="row">
                                    <div class="col-md-2">
                                        <h5 class="modal-title">Cookie Consent</h5>
                                    </div>
                                    <div class='col-md-6'>
                                        <p>This website uses cookies to ensure you get the best experience.</p>
                                    </div>
                                    <div class='col-md-3'>
                                        <div>
                                            <button type="button" class="btn btn-primary" id="acceptCookies">Accept</button>
                                            <button type="button" class="btn btn-primary" id="declineCookies">Decline</button>
                                            <button type="button" class="close" id="closeBanner">&times;</button>
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
            document.getElementById('cookieConsentBanner').style.display = 'none';
        };

        document.getElementById('declineCookies').onclick = function () {
            setCookie('cookieDecline', 'true', 365);
            document.getElementById('cookieConsentBanner').style.display = 'none';
        };

        document.getElementById('closeBanner').onclick = function () {
            document.getElementById('cookieConsentBanner').style.display = 'none';
        };
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