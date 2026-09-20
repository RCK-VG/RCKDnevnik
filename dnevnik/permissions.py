from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def is_admin(user):
    return user.is_active and (user.is_staff or user.is_superuser)


def admin_required(view_func):
    """Like @user_passes_test(is_admin), but returns 403 Forbidden for a
    logged-in non-admin user instead of redirecting to the login page
    (which would be misleading - they ARE logged in, just not allowed)."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_admin(request.user):
            raise PermissionDenied("Ova stranica je dostupna samo administratoru.")
        return view_func(request, *args, **kwargs)

    return wrapper


def can_edit_lesson(user, lesson):
    return is_admin(user) or lesson.teacher_id == user.id


def can_edit_note(user, note):
    return is_admin(user) or note.author_id == user.id


def can_set_justified(user, school_class):
    return is_admin(user) or school_class.homeroom_teacher_id == user.id
