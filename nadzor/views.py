from datetime import datetime, time
from functools import wraps

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils import timezone
from django.utils.timezone import localtime

from dnevnik.exports import _attachment_response, _log_export, _meta_lines, _to_csv
from dnevnik.permissions import is_admin

from .models import ActivityLog
from .services import normalize_name


def can_view_monitoring(user):
    if not user.is_authenticated:
        return False
    if is_admin(user):
        return True
    profile = getattr(user, "profile", None)
    return bool(profile and profile.can_view_monitoring)


def monitoring_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not can_view_monitoring(request.user):
            raise PermissionDenied("Nemate pristup nadzoru računala.")
        return view(request, *args, **kwargs)

    return wrapper


def _choices(field, empty_label):
    values = (
        ActivityLog.objects.exclude(**{field: ""})
        .order_by(field)
        .values_list(field, flat=True)
        .distinct()
    )
    return [("", empty_label)] + [(v, v) for v in values]


class LogFilterForm(forms.Form):
    razred = forms.ChoiceField(label="Razred", required=False)
    ucenik = forms.CharField(label="Ime ili prezime", required=False, max_length=100)
    racunalo = forms.ChoiceField(label="Računalo", required=False)
    vrsta = forms.ChoiceField(label="Vrsta", required=False)
    datum_od = forms.DateField(
        label="Od datuma", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    datum_do = forms.DateField(
        label="Do datuma", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["razred"].choices = _choices("class_name", "Svi razredi")
        self.fields["racunalo"].choices = _choices("computer_name", "Sva računala")
        self.fields["vrsta"].choices = _choices("event_type", "Sve vrste")


def _filtered_logs(form):
    logs = ActivityLog.objects.all()
    if not form.is_valid():
        return logs
    data = form.cleaned_data
    if data["razred"]:
        logs = logs.filter(class_name=data["razred"])
    if data["racunalo"]:
        logs = logs.filter(computer_name=data["racunalo"])
    if data["vrsta"]:
        logs = logs.filter(event_type=data["vrsta"])
    for word in normalize_name(data["ucenik"]).split():
        logs = logs.filter(search_name__contains=word)
    tz = timezone.get_current_timezone()
    if data["datum_od"]:
        logs = logs.filter(received_at__gte=datetime.combine(data["datum_od"], time.min, tz))
    if data["datum_do"]:
        logs = logs.filter(received_at__lte=datetime.combine(data["datum_do"], time.max, tz))
    return logs


def _fmt(dt):
    return localtime(dt).strftime("%d.%m.%Y. %H:%M:%S") if dt else ""


@monitoring_required
def zapisi(request):
    form = LogFilterForm(request.GET or None)
    logs = _filtered_logs(form)

    if request.GET.get("izvoz") == "csv":
        return _csv_response(request, form, logs)

    page_obj = Paginator(logs, 100).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(
        request,
        "nadzor/zapisi.html",
        {
            "form": form,
            "page_obj": page_obj,
            "total": page_obj.paginator.count,
            "querystring": query.urlencode(),
        },
    )


def _csv_response(request, form, logs):
    filters = {k: v for k, v in (form.cleaned_data if form.is_valid() else {}).items() if v}
    _log_export(request.user, "nadzor_racunala", "; ".join(f"{k}={v}" for k, v in filters.items()))
    header = [
        "Vrijeme (server)",
        "Vrijeme (računalo)",
        "Razred",
        "Prezime",
        "Ime",
        "Računalo",
        "Vrsta",
        "Detalji",
    ]
    rows = [
        [
            _fmt(log.received_at),
            _fmt(log.client_time),
            log.class_name,
            log.last_name,
            log.first_name,
            log.computer_name,
            log.event_type,
            log.details,
        ]
        for log in logs.iterator()
    ]
    content = _to_csv(_meta_lines(request.user, "Nadzor računala - zapisi aktivnosti"), header, rows)
    stamp = localtime(timezone.now()).strftime("%Y%m%d_%H%M")
    return _attachment_response(content, f"nadzor_racunala_{stamp}.csv", "text/csv; charset=utf-8")
