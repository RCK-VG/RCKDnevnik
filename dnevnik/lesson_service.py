"""Business logic for saving a Nastavni sat screen: attendance + notes,
with an audit trail (history) for every change.

Kept out of views.py so it can be unit tested without going through HTTP.
"""

from . import constants
from .models import Attendance, AttendanceHistory, Note, NoteHistory
from .permissions import can_edit_note, can_set_justified


def save_attendance(lesson, student, status, justified_raw, user):
    """Creates or updates the Attendance row for one student on one lesson.

    justified_raw: "true", "false" or anything else (treated as "unknown").
    Only applied when status is "odsutan" AND the user is allowed to set it
    (homeroom teacher of the class, or admin) - otherwise the previous
    value (or None) is kept, silently ignoring the attempted change.
    """
    if status not in dict(constants.ATTENDANCE_STATUS_CHOICES):
        status = constants.ATTENDANCE_PRESENT

    requested_justified = {"true": True, "false": False}.get(justified_raw)
    allowed_to_set_justified = can_set_justified(user, lesson.school_class)

    attendance, created = Attendance.objects.get_or_create(
        lesson=lesson,
        student=student,
        defaults={
            "status": status,
            "justified": (
                requested_justified
                if status == constants.ATTENDANCE_ABSENT and allowed_to_set_justified
                else None
            ),
            "updated_by": user,
        },
    )
    if created:
        return attendance

    new_justified = attendance.justified
    if status != constants.ATTENDANCE_ABSENT:
        new_justified = None
    elif allowed_to_set_justified:
        new_justified = requested_justified

    changed = attendance.status != status or attendance.justified != new_justified
    if changed:
        AttendanceHistory.objects.create(
            attendance=attendance,
            status=attendance.status,
            justified=attendance.justified,
            changed_by=user,
        )
        attendance.status = status
        attendance.justified = new_justified
        attendance.updated_by = user
        attendance.save()

    return attendance


def save_note(lesson, student, text, user):
    """Creates, updates or archives the note for (lesson, student) - student
    may be None for the lesson's general note.

    Only the note's original author (or an admin) may change it; if someone
    else attempts to, the change is silently ignored (the caller should
    avoid rendering an editable field for such notes in the first place).
    """
    text = (text or "").strip()
    existing = (
        Note.objects.filter(lesson=lesson, student=student, is_archived=False)
        .order_by("-created_at")
        .first()
    )

    if existing is None:
        if text:
            return Note.objects.create(lesson=lesson, student=student, author=user, text=text)
        return None

    if not can_edit_note(user, existing):
        return existing

    if not text:
        if existing.text:
            NoteHistory.objects.create(note=existing, text=existing.text, edited_by=user)
        existing.is_archived = True
        existing.save(update_fields=["is_archived", "updated_at"])
        return existing

    if text != existing.text:
        NoteHistory.objects.create(note=existing, text=existing.text, edited_by=user)
        existing.text = text
        existing.save(update_fields=["text", "updated_at"])

    return existing
