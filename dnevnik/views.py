from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Lesson
from .permissions import is_admin


@login_required
def pocetna(request):
    recent_lessons = (
        Lesson.objects.filter(teacher=request.user)
        .select_related("school_class", "subject")
        .order_by("-date", "-period", "-created_at")[:10]
    )
    return render(
        request,
        "dnevnik/pocetna.html",
        {"is_admin": is_admin(request.user), "recent_lessons": recent_lessons},
    )
