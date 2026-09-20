from django.contrib import messages
from django.shortcuts import redirect, render

from . import imports
from .forms import FileImportForm
from .models import SchoolYear
from .permissions import admin_required

SESSION_STUDENTS_KEY = "uvoz_ucenici_preview"
SESSION_SUBJECTS_KEY = "uvoz_predmeti_preview"


@admin_required
def uvoz_ucenika(request):
    school_years = SchoolYear.objects.filter(is_archived=False)
    preview = request.session.get(SESSION_STUDENTS_KEY)

    if request.method == "POST" and "odustani" in request.POST:
        request.session.pop(SESSION_STUDENTS_KEY, None)
        return redirect("uvoz_ucenika")

    if request.method == "POST" and "potvrdi" in request.POST:
        if not preview:
            messages.error(request, "Nema podataka za potvrdu. Ponovno učitajte datoteku.")
            return redirect("uvoz_ucenika")
        try:
            school_year = SchoolYear.objects.get(id=preview["school_year_id"])
        except SchoolYear.DoesNotExist:
            messages.error(request, "Odabrana školska godina više ne postoji.")
            return redirect("uvoz_ucenika")

        summary = imports.commit_student_rows(preview["rows"], school_year)
        del request.session[SESSION_STUDENTS_KEY]
        messages.success(
            request,
            f"Uvoz završen: dodano {summary['added']}, ažurirano {summary['updated']}, "
            f"preskočeno {summary['skipped']}, grešaka {summary['errors']}.",
        )
        return redirect("uvoz_ucenika")

    if request.method == "POST":
        form = FileImportForm(request.POST, request.FILES)
        school_year_id = request.POST.get("school_year")
        school_year = SchoolYear.objects.filter(id=school_year_id).first()
        if form.is_valid() and school_year:
            rows = imports.parse_student_rows(request.FILES["file"], school_year)
            request.session[SESSION_STUDENTS_KEY] = {
                "rows": rows,
                "school_year_id": school_year.id,
            }
            preview = request.session[SESSION_STUDENTS_KEY]
        else:
            messages.error(request, "Odaberite školsku godinu i ispravnu datoteku.")
            preview = None
    else:
        form = FileImportForm()

    preview_school_year = None
    if preview:
        preview_school_year = SchoolYear.objects.filter(id=preview["school_year_id"]).first()

    return render(
        request,
        "dnevnik/uvoz_ucenika.html",
        {
            "form": form if request.method != "GET" or not preview else FileImportForm(),
            "school_years": school_years,
            "preview": preview["rows"] if preview else None,
            "preview_school_year": preview_school_year,
        },
    )


@admin_required
def uvoz_predmeta(request):
    preview = request.session.get(SESSION_SUBJECTS_KEY)

    if request.method == "POST" and "odustani" in request.POST:
        request.session.pop(SESSION_SUBJECTS_KEY, None)
        return redirect("uvoz_predmeta")

    if request.method == "POST" and "potvrdi" in request.POST:
        if not preview:
            messages.error(request, "Nema podataka za potvrdu. Ponovno učitajte datoteku.")
            return redirect("uvoz_predmeta")
        summary = imports.commit_subject_rows(preview)
        del request.session[SESSION_SUBJECTS_KEY]
        messages.success(
            request,
            f"Uvoz završen: dodano {summary['added']}, preskočeno {summary['skipped']}.",
        )
        return redirect("uvoz_predmeta")

    if request.method == "POST":
        form = FileImportForm(request.POST, request.FILES)
        if form.is_valid():
            rows = imports.parse_subject_rows(request.FILES["file"])
            request.session[SESSION_SUBJECTS_KEY] = rows
            preview = rows
        else:
            preview = None
    else:
        form = FileImportForm()

    return render(
        request,
        "dnevnik/uvoz_predmeta.html",
        {"form": FileImportForm(), "preview": preview},
    )
