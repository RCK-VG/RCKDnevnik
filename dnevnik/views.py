from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .permissions import is_admin


@login_required
def pocetna(request):
    return render(request, "dnevnik/pocetna.html", {"is_admin": is_admin(request.user)})
