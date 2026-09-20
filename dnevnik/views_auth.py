from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LogoutView
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from . import auth_throttle
from .forms import DnevnikAuthenticationForm


class PrijavaView(View):
    template_name = "dnevnik/login.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("pocetna")
        return render(request, self.template_name, {"form": DnevnikAuthenticationForm()})

    def post(self, request):
        username = request.POST.get("username", "").strip()

        if username and auth_throttle.is_locked_out(username):
            messages.error(
                request,
                "Previše neuspjelih pokušaja prijave. Pokušajte ponovno za nekoliko minuta.",
            )
            return render(request, self.template_name, {"form": DnevnikAuthenticationForm()})

        form = DnevnikAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            auth_throttle.record_attempt(username, successful=True)
            auth_login(request, form.get_user())
            return redirect("pocetna")

        if username:
            auth_throttle.record_attempt(username, successful=False)
        return render(request, self.template_name, {"form": form})


class DnevnikLogoutView(LogoutView):
    next_page = "prijava"


@login_required
def promjena_lozinke(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            user.profile.must_change_password = False
            user.profile.save(update_fields=["must_change_password"])
            from django.contrib.auth import update_session_auth_hash

            update_session_auth_hash(request, user)
            messages.success(request, "Lozinka je uspješno promijenjena.")
            return redirect("pocetna")
    else:
        form = PasswordChangeForm(request.user)

    forced = getattr(request.user, "profile", None) and request.user.profile.must_change_password
    return render(
        request,
        "dnevnik/promjena_lozinke.html",
        {"form": form, "forced": forced},
    )
