from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from . import exports
from .forms import ExportFilterForm, MatrixExportForm
from .permissions import admin_required, is_admin


@login_required
def izvoz(request):
    return render(request, "dnevnik/izvoz.html", {"is_admin": is_admin(request.user)})


@login_required
def izvoz_prisutnost(request):
    form = MatrixExportForm(request.GET or None)
    if request.GET and form.is_valid():
        data = form.cleaned_data
        return exports.respond_attendance_matrix(
            request.user,
            data["razred"],
            data["predmet"],
            data["datum_od"],
            data["datum_do"],
            data["format"],
        )
    return render(request, "dnevnik/izvoz_prisutnost.html", {"form": form})


@login_required
def izvoz_sazetak(request):
    form = ExportFilterForm(request.GET or None)
    if request.GET and form.is_valid():
        data = form.cleaned_data
        return exports.respond_absence_summary(
            request.user,
            data["razred"],
            data["predmet"],
            data["nastavnik"],
            data["datum_od"],
            data["datum_do"],
            data["format"],
        )
    return render(request, "dnevnik/izvoz_sazetak.html", {"form": form})


@login_required
def izvoz_biljeske(request):
    form = ExportFilterForm(request.GET or None)
    if request.GET and form.is_valid():
        data = form.cleaned_data
        return exports.respond_notes_export(
            request.user,
            data["razred"],
            data["predmet"],
            data["nastavnik"],
            data["datum_od"],
            data["datum_do"],
            data["format"],
        )
    return render(request, "dnevnik/izvoz_biljeske.html", {"form": form})


@admin_required
def izvoz_potpuni(request):
    if request.GET.get("preuzmi"):
        return exports.respond_full_export(request.user)
    return render(request, "dnevnik/izvoz_potpuni.html", {})
