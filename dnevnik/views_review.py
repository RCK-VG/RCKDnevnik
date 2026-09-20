from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from .forms import ReviewFilterForm
from .models import Attendance, Note, SchoolClass, Student
from .stats import EMPTY_STATS, stats_aggregate_kwargs


def _apply_attendance_filters(qs, form):
    if form.is_valid():
        if form.cleaned_data.get("predmet"):
            qs = qs.filter(lesson__subject=form.cleaned_data["predmet"])
        if form.cleaned_data.get("datum_od"):
            qs = qs.filter(lesson__date__gte=form.cleaned_data["datum_od"])
        if form.cleaned_data.get("datum_do"):
            qs = qs.filter(lesson__date__lte=form.cleaned_data["datum_do"])
    return qs


@login_required
def razredi(request):
    classes = (
        SchoolClass.objects.filter(school_year__is_archived=False)
        .select_related("school_year", "homeroom_teacher")
        .order_by("school_year", "name")
    )
    return render(request, "dnevnik/razredi.html", {"classes": classes})


@login_required
def razred_detalj(request, pk):
    school_class = get_object_or_404(
        SchoolClass.objects.select_related("school_year", "homeroom_teacher"), pk=pk
    )
    filter_form = ReviewFilterForm(request.GET or None)

    students = Student.objects.filter(school_class=school_class, is_archived=False)

    attendance_qs = Attendance.objects.filter(student__school_class=school_class)
    attendance_qs = _apply_attendance_filters(attendance_qs, filter_form)

    stats = attendance_qs.values("student_id").annotate(**stats_aggregate_kwargs())
    stats_by_student = {row["student_id"]: row for row in stats}

    rows = [
        {"student": student, **stats_by_student.get(student.id, EMPTY_STATS)}
        for student in students
    ]

    return render(
        request,
        "dnevnik/razred_detalj.html",
        {"school_class": school_class, "rows": rows, "filter_form": filter_form},
    )


@login_required
def ucenik_profil(request, pk):
    student = get_object_or_404(
        Student.objects.select_related("school_class__school_year"), pk=pk
    )
    filter_form = ReviewFilterForm(request.GET or None)

    attendance_qs = Attendance.objects.filter(student=student).select_related(
        "lesson__subject", "lesson__teacher"
    )
    attendance_qs = _apply_attendance_filters(attendance_qs, filter_form)
    attendance_qs = attendance_qs.order_by("-lesson__date", "-lesson__created_at")

    summary = attendance_qs.aggregate(**stats_aggregate_kwargs())

    notes_qs = Note.objects.filter(student=student, is_archived=False).select_related(
        "lesson__subject", "author"
    )
    if filter_form.is_valid():
        if filter_form.cleaned_data.get("predmet"):
            notes_qs = notes_qs.filter(lesson__subject=filter_form.cleaned_data["predmet"])
        if filter_form.cleaned_data.get("datum_od"):
            notes_qs = notes_qs.filter(lesson__date__gte=filter_form.cleaned_data["datum_od"])
        if filter_form.cleaned_data.get("datum_do"):
            notes_qs = notes_qs.filter(lesson__date__lte=filter_form.cleaned_data["datum_do"])
    notes_qs = notes_qs.order_by("-lesson__date", "-created_at")

    return render(
        request,
        "dnevnik/ucenik_profil.html",
        {
            "student": student,
            "attendance_list": attendance_qs,
            "summary": summary,
            "notes": notes_qs,
            "filter_form": filter_form,
        },
    )
