from django.shortcuts import redirect
from django.urls import reverse

# Paths reachable even while a password change is pending. Built lazily
# (not at import time) since urls.py may not be fully loaded yet.
def _allowed_paths():
    return {reverse("promjena_lozinke"), reverse("odjava")}


class ForcePasswordChangeMiddleware:
    """Redirects users with profile.must_change_password to the password
    change screen, until they set their own password.

    NOTE: this runs before the URL resolver has set request.resolver_match
    (resolution happens deeper in the middleware chain), so it compares
    request.path directly instead of relying on resolver_match.url_name.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            profile = getattr(user, "profile", None)
            if profile and profile.must_change_password:
                is_static = request.path.startswith("/static/")
                if request.path not in _allowed_paths() and not is_static:
                    return redirect(reverse("promjena_lozinke"))
        return self.get_response(request)
