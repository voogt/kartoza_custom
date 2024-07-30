document.addEventListener('DOMContentLoaded', function () {
    if (!getCookie('cookieConsent')) {
        // Inject modal HTML if not already present
        if (!document.getElementById('cookieConsentModal')) {
            var modalHtml = `
                <div class="modal" id="cookieConsentModal">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h4 class="modal-title">Cookie Consent</h4>
                                <button type="button" class="close" data-dismiss="modal">&times;</button>
                            </div>
                            <div class="modal-body">
                                This website uses cookies to ensure you get the best experience.
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-primary" id="acceptCookies">Accept</button>
                            </div>
                        </div>
                    </div>
                </div>`;
            document.body.insertAdjacentHTML('beforeend', modalHtml);
        }

        // Show modal
        $('#cookieConsentModal').modal('show');

        document.getElementById('acceptCookies').onclick = function () {
            setCookie('cookieConsent', 'true', 365);
            $('#cookieConsentModal').modal('hide');
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
