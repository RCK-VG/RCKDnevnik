from datetime import datetime, time
from functools import wraps

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import localtime

from dnevnik.exports import _attachment_response, _log_export, _meta_lines, _to_csv
from dnevnik.permissions import is_admin

from . import services
from .models import ActivityLog, BlockedSite
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
    ucionica = forms.ChoiceField(label="Učionica", required=False)
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
    samo_nedopustene = forms.BooleanField(label="Samo nedopuštene stranice", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ucionica"].choices = services.classroom_choices()
        self.fields["razred"].choices = _choices("class_name", "Svi razredi")
        self.fields["racunalo"].choices = _choices("computer_name", "Sva računala")
        self.fields["vrsta"].choices = _choices("event_type", "Sve vrste")


def _filtered_logs(form):
    logs = ActivityLog.objects.all()
    if not form.is_valid():
        return logs
    data = form.cleaned_data
    if data.get("ucionica"):
        logs = services.filter_by_classroom(logs, data["ucionica"])
    if data["razred"]:
        logs = logs.filter(class_name=data["razred"])
    if data["racunalo"]:
        logs = logs.filter(computer_name=data["racunalo"])
    if data["vrsta"]:
        logs = logs.filter(event_type=data["vrsta"])
    if data.get("samo_nedopustene"):
        logs = logs.filter(services.blocked_logs_q())
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
    pats = services.active_block_patterns()
    for log in page_obj:
        log.blocked = log.event_type == services.SITE_EVENT and services.domain_is_blocked(log.details, pats)
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
            "has_blocklist": bool(pats),
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
        "Identificiran",
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
            "da" if log.identified else "ne",
        ]
        for log in logs.iterator()
    ]
    content = _to_csv(_meta_lines(request.user, "Nadzor računala - zapisi aktivnosti"), header, rows)
    stamp = localtime(timezone.now()).strftime("%Y%m%d_%H%M")
    return _attachment_response(content, f"nadzor_racunala_{stamp}.csv", "text/csv; charset=utf-8")


# --------------------------------------------------------------------------
# Nedopuštene stranice: the teacher's own list, and a report of violations.
# --------------------------------------------------------------------------


@monitoring_required
def blokirane(request):
    """Manage the list of disallowed sites (add / delete / import from CSV)."""
    if request.method == "POST":
        action = request.POST.get("akcija")
        if action == "dodaj":
            pattern = services.normalize_pattern(request.POST.get("izraz"))
            category = (request.POST.get("kategorija") or "").strip()[:50]
            if pattern:
                _, created = BlockedSite.objects.get_or_create(
                    pattern=pattern, defaults={"category": category}
                )
                messages.success(request, f"Dodano: {pattern}" if created else f"Već postoji: {pattern}")
            else:
                messages.error(request, "Upiši domenu ili izraz.")
        elif action == "obrisi":
            BlockedSite.objects.filter(pk=request.POST.get("id")).delete()
        elif action == "uvoz" and request.FILES.get("datoteka"):
            added = _import_blocked_csv(request.FILES["datoteka"])
            messages.success(request, f"Uvezeno novih: {added}.")
        return redirect("nadzor_blokirane")

    return render(
        request,
        "nadzor/blokirane.html",
        {"stavke": BlockedSite.objects.all()},
    )


def _import_blocked_csv(uploaded):
    """Each line's first column is a domain/keyword; a second column (optional)
    is a category. A header row named like 'domena' is skipped."""
    try:
        text = uploaded.read().decode("utf-8-sig")
    except (UnicodeDecodeError, AttributeError):
        return 0
    added = 0
    for raw in text.splitlines():
        parts = [c.strip() for c in raw.replace(";", ",").split(",")]
        pattern = services.normalize_pattern(parts[0])
        if not pattern or pattern in ("domena", "izraz", "domena ili izraz"):
            continue
        category = parts[1][:50] if len(parts) > 1 else ""
        _, created = BlockedSite.objects.get_or_create(pattern=pattern, defaults={"category": category})
        added += int(created)
    return added


class ViolationFilterForm(forms.Form):
    ucionica = forms.ChoiceField(label="Učionica", required=False)
    razred = forms.ChoiceField(label="Razred", required=False)
    datum_od = forms.DateField(
        label="Od datuma", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    datum_do = forms.DateField(
        label="Do datuma", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ucionica"].choices = services.classroom_choices()
        self.fields["razred"].choices = _choices("class_name", "Svi razredi")


def _violation_logs(form):
    logs = ActivityLog.objects.filter(services.blocked_logs_q())
    if form.is_valid():
        data = form.cleaned_data
        if data.get("ucionica"):
            logs = services.filter_by_classroom(logs, data["ucionica"])
        if data["razred"]:
            logs = logs.filter(class_name=data["razred"])
        tz = timezone.get_current_timezone()
        if data["datum_od"]:
            logs = logs.filter(received_at__gte=datetime.combine(data["datum_od"], time.min, tz))
        if data["datum_do"]:
            logs = logs.filter(received_at__lte=datetime.combine(data["datum_do"], time.max, tz))
    return logs


def _summarize_violations(logs):
    """Group hits per student: count, distinct domains, last time."""
    by_student = {}
    for log in logs.order_by("-received_at").iterator():
        key = (log.class_name, log.last_name, log.first_name, log.identified)
        row = by_student.get(key)
        if row is None:
            row = by_student[key] = {
                "class_name": log.class_name,
                "last_name": log.last_name,
                "first_name": log.first_name,
                "identified": log.identified,
                "count": 0,
                "domains": set(),
                "last": log.received_at,
            }
        row["count"] += 1
        row["domains"].add(log.details)
        row["last"] = max(row["last"], log.received_at)
    result = sorted(by_student.values(), key=lambda r: r["count"], reverse=True)
    for r in result:
        r["domains"] = sorted(r["domains"])
    return result


@monitoring_required
def prekrsaji(request):
    if not services.active_block_patterns():
        return render(request, "nadzor/prekrsaji.html", {"nema_popisa": True})

    form = ViolationFilterForm(request.GET or None)
    logs = _violation_logs(form)

    if request.GET.get("izvoz") == "csv":
        return _violations_csv(request, logs)

    rows = _summarize_violations(logs)
    query = request.GET.copy()
    query.pop("izvoz", None)
    return render(
        request,
        "nadzor/prekrsaji.html",
        {"form": form, "rows": rows, "total": sum(r["count"] for r in rows), "querystring": query.urlencode()},
    )


def _violations_csv(request, logs):
    _log_export(request.user, "nadzor_prekrsaji", "")
    header = ["Razred", "Prezime", "Ime", "Broj posjeta", "Zadnji put", "Domene"]
    rows = [
        [
            r["class_name"],
            r["last_name"],
            r["first_name"],
            r["count"],
            _fmt(r["last"]),
            ", ".join(r["domains"]),
        ]
        for r in _summarize_violations(logs)
    ]
    content = _to_csv(_meta_lines(request.user, "Nadzor računala - nedopuštene stranice"), header, rows)
    stamp = localtime(timezone.now()).strftime("%Y%m%d_%H%M")
    return _attachment_response(content, f"nadzor_prekrsaji_{stamp}.csv", "text/csv; charset=utf-8")
