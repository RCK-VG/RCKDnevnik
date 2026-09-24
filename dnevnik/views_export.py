from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from . import exports
from .forms import ExportFilterForm, MatrixExportForm
from .models import ClassSubject
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
    # For the "Preuzmi i otvori Gmail" button: theory teacher e-mail per
    # class+subject, so the browser can fill in the recipient without a
    # round trip. Only rows with an e-mail address are useful here.
    theory_map = {
        f"{cs.school_class_id}-{cs.subject_id}": {
            "name": cs.theory_teacher_name,
            "email": cs.theory_teacher_email,
        }
        for cs in ClassSubject.objects.exclude(theory_teacher_email="")
    }
    return render(
        request,
        "dnevnik/izvoz_prisutnost.html",
        {
            "form": form,
            "theory_map": theory_map,
            "sender_name": request.user.get_full_name() or request.user.username,
        },
    )


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
