from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from . import constants, lesson_service
from .forms import LessonPickerForm
from .models import Lesson, Student
from .permissions import can_edit_lesson, can_edit_note, can_set_justified

VALID_GROUP_LABELS = {code for code, _ in constants.GROUP_CHOICES}


def _clean_group_label(raw):
    return raw if raw in VALID_GROUP_LABELS else ""


@login_required
def izbor_sata(request):
    form = LessonPickerForm()
    return render(request, "dnevnik/sat_izbor.html", {"form": form})


@login_required
def otvori_sat(request):
    data = request.POST if request.method == "POST" else request.GET
    form = LessonPickerForm(data)
    if not form.is_valid():
        messages.error(request, "Odaberite razred, predmet i ispravan datum.")
        return redirect("izbor_sata")

    school_class = form.cleaned_data["razred"]
    subject = form.cleaned_data["predmet"]
    date = form.cleaned_data["datum"]
    group_label = _clean_group_label(form.cleaned_data.get("grupa", ""))

    lesson = Lesson.objects.filter(
        school_class=school_class, subject=subject, date=date, teacher=request.user
    ).first()
    if lesson:
        return _redirect_to_sat(lesson.id, group_label)

    if request.method == "POST":
        lesson = _save_lesson(request, None, school_class, subject, date, group_label)
        return _redirect_to_sat(lesson.id, group_label)

    return _render_sat_screen(request, None, school_class, subject, date, group_label)


@login_required
def sat(request, pk):
    """Any logged-in teacher may VIEW any lesson (per spec: no restriction
    by class/subject); only the lesson's own teacher or an admin may EDIT
    (save) it - enforced below, on the POST path only."""
    lesson = get_object_or_404(
        Lesson.objects.select_related("school_class", "subject", "teacher"), pk=pk
    )
    can_edit = can_edit_lesson(request.user, lesson)

    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied("Ne možete uređivati tuđi nastavni sat.")
        group_label = _clean_group_label(request.POST.get("grupa", ""))
        _save_lesson(request, lesson, lesson.school_class, lesson.subject, lesson.date, group_label)
        return _redirect_to_sat(lesson.id, group_label)

    group_label = _clean_group_label(request.GET.get("grupa", ""))
    return _render_sat_screen(
        request, lesson, lesson.school_class, lesson.subject, lesson.date, group_label, can_edit
    )


def _redirect_to_sat(lesson_id, group_label):
    url = reverse("sat", kwargs={"pk": lesson_id})
    if group_label:
        url += f"?grupa={group_label}"
    return redirect(url)


def _group_students(school_class, group_label):
    students = Student.objects.filter(school_class=school_class, is_archived=False)
    if group_label:
        students = students.filter(group_label=group_label)
    return students


def _save_lesson(request, lesson, school_class, subject, date, group_label):
    topic = request.POST.get("tema", "").strip()

    if lesson is None:
        lesson = Lesson.objects.create(
            school_class=school_class,
            subject=subject,
            teacher=request.user,
            date=date,
            topic=topic,
        )
    elif lesson.topic != topic:
        lesson.topic = topic
        lesson.save(update_fields=["topic", "updated_at"])

    # Only touch students in the selected group - attendance/notes already
    # recorded for the rest of the class (the other group) must stay as-is.
    students = _group_students(school_class, group_label)
    for student in students:
        status = request.POST.get(f"status_{student.id}", constants.ATTENDANCE_PRESENT)
        justified_raw = request.POST.get(f"justified_{student.id}", "")
        lesson_service.save_attendance(lesson, student, status, justified_raw, request.user)

        note_text = request.POST.get(f"note_{student.id}", "")
        lesson_service.save_note(lesson, student, note_text, request.user)

    general_text = request.POST.get("opca_biljeska", "")
    lesson_service.save_note(lesson, None, general_text, request.user)

    messages.success(request, "Sat je spremljen.")
    return lesson


def _note_context(note, user, can_edit_overall):
    if note is None:
        return {"text": "", "editable": can_edit_overall, "author": None, "updated_at": None}
    return {
        "text": note.text,
        "editable": can_edit_overall and can_edit_note(user, note),
        "author": note.author,
        "updated_at": note.updated_at,
    }


def _render_sat_screen(request, lesson, school_class, subject, date, group_label="", can_edit=True):
    from .models import Attendance, Note

    students = _group_students(school_class, group_label)

    attendance_by_student = {}
    notes_by_student = {}
    general_note = None

    if lesson is not None:
        attendance_by_student = {
            a.student_id: a for a in Attendance.objects.filter(lesson=lesson)
        }
        notes_by_student = {
            n.student_id: n
            for n in Note.objects.filter(lesson=lesson, is_archived=False, student__isnull=False)
        }
        general_note = (
            Note.objects.filter(lesson=lesson, student__isnull=True, is_archived=False)
            .order_by("-created_at")
            .first()
        )

    rows = []
    for student in students:
        attendance = attendance_by_student.get(student.id)
        rows.append(
            {
                "student": student,
                "status": attendance.status if attendance else constants.ATTENDANCE_PRESENT,
                "justified": attendance.justified if attendance else None,
                "note": _note_context(notes_by_student.get(student.id), request.user, can_edit),
            }
        )

    if lesson is not None:
        save_url = reverse("sat", kwargs={"pk": lesson.id})
    else:
        save_url = reverse("otvori_sat")

    has_groups = Student.objects.filter(
        school_class=school_class, is_archived=False
    ).exclude(group_label="").exists()

    context = {
        "lesson": lesson,
        "is_new": lesson is None,
        "school_class": school_class,
        "subject": subject,
        "date": date,
        "rows": rows,
        "general_note": _note_context(general_note, request.user, can_edit),
        "can_edit": can_edit,
        "can_set_justified": can_edit and can_set_justified(request.user, school_class),
        "save_url": save_url,
        "status_choices": constants.ATTENDANCE_STATUS_CHOICES,
        "attendance_present": constants.ATTENDANCE_PRESENT,
        "attendance_absent": constants.ATTENDANCE_ABSENT,
        "attendance_late": constants.ATTENDANCE_LATE,
        "group_label": group_label,
        "group_choices": constants.GROUP_CHOICES,
        "has_groups": has_groups,
    }
    return render(request, "dnevnik/sat.html", context)
