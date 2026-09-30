"""JSON API used by the student-computer client (klijent/servis.ps1, which
runs as SYSTEM on every student PC).

Every endpoint requires the X-API-Key header (settings.NADZOR_API_KEY). The
key only unlocks these endpoints - never reading any logs back. See
nadzor/services.py for the data side."""

import hmac
import json
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import services

MAX_BODY_BYTES = 512 * 1024
MAX_EVENTS_PER_REQUEST = 200
FAILED_LOGIN_WINDOW_SECONDS = 10 * 60


def _json(data, status=200):
    # Explicit charset: Windows PowerShell 5.1 otherwise decodes as Latin-1.
    return JsonResponse(data, status=status, content_type="application/json; charset=utf-8")


def _error(message, status):
    return _json({"greska": message}, status=status)


def api_key_required(view):
    @csrf_exempt
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        expected = settings.NADZOR_API_KEY
        if not expected:
            return _error("Nadzor računala nije uključen na serveru (NADZOR_API_KEY).", 503)
        given = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8")):
            return _error("Neispravan API ključ.", 403)
        return view(request, *args, **kwargs)

    return wrapper


def _read_json(request):
    if len(request.body) > MAX_BODY_BYTES:
        return None, _error("Zahtjev je prevelik.", 413)
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, _error("Tijelo zahtjeva mora biti JSON u UTF-8.", 400)
    if not isinstance(data, dict):
        return None, _error("Tijelo zahtjeva mora biti JSON objekt.", 400)
    return data, None


def _client_ip(request):
    # Behind Caddy the real address is in X-Forwarded-For. It can be spoofed
    # by a client talking to gunicorn directly - acceptable, the limit is
    # only against casual name guessing, not a security control.
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")


def _failed_login_key(request):
    return f"nadzor:prijava:{_client_ip(request)}"


@require_GET
@api_key_required
def razredi(request):
    """Class names only - never student names."""
    return _json({"razredi": services.class_names()})


@require_GET
@api_key_required
def klijent(request):
    """Current client files, so the service can update itself (no more USB per
    change). Read-only: it never accepts uploads, and serves only the fixed
    whitelist in services.CLIENT_UPDATE_FILES (never the key or certificate)."""
    bundle = services.client_bundle()
    if bundle is None:
        return _error("Datoteke klijenta nisu dostupne na serveru.", 503)
    return _json(bundle)


@require_POST
@api_key_required
def prijava(request):
    key = _failed_login_key(request)
    if cache.get(key, 0) >= settings.NADZOR_PRIJAVA_MAX_POKUSAJA:
        return _error("Previše neuspjelih prijava s ovog računala. Pokušaj za nekoliko minuta.", 429)

    data, error = _read_json(request)
    if error:
        return error

    class_name = services.clean_line(data.get("razred"), services.MAX_CLASS_LEN)
    first_name = services.clean_line(data.get("ime"), services.MAX_NAME_LEN)
    last_name = services.clean_line(data.get("prezime"), services.MAX_NAME_LEN)
    computer = services.clean_line(data.get("racunalo"), services.MAX_COMPUTER_LEN)
    if not (class_name and first_name and last_name and computer):
        return _error("Potrebni su razred, ime, prezime i naziv računala.", 400)

    # "naknadno": login typed while the server was down, confirmed now by
    # the client. It is not checked for duplicates (the moment has passed);
    # "zavrsena" means the Windows session already ended meanwhile.
    late = data.get("naknadno") is True
    already_ended = late and data.get("zavrsena") is True

    matches = services.find_students(class_name, first_name, last_name)
    if not matches:
        cache.add(key, 0, FAILED_LOGIN_WINDOW_SECONDS)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, FAILED_LOGIN_WINDOW_SECONDS)
        return _error("Učenik nije pronađen. Provjeri razred, ime i prezime.", 404)
    if len(matches) > 1:
        return _json(
            {"greska": "U razredu postoji više učenika s istim imenom - javi se nastavniku.", "kod": "isto_ime"},
            status=409,
        )

    student = matches[0]
    if not late:
        other = services.active_session_elsewhere(student, computer)
        if other is not None:
            return _json(
                {
                    "greska": (
                        f"{student.first_name} {student.last_name} ({student.school_class.name}) "
                        f"već je prijavljen/a na računalu {other.computer_name}. "
                        "Ako to nisi ti, javi se nastavniku."
                    ),
                    "kod": "vec_prijavljen",
                    "racunalo": other.computer_name,
                },
                status=409,
            )
    session, token = services.start_session(student, computer, late=late, already_ended=already_ended)
    return _json(
        {
            "token": token,
            "ucenik": f"{student.first_name} {student.last_name}",
            "razred": student.school_class.name,
        }
    )


def _session_from_body(request):
    data, error = _read_json(request)
    if error:
        return None, None, error
    session = services.session_for_token(data.get("token"))
    if session is None:
        return data, None, _error("Neispravan ili istekao token - potrebna je ponovna prijava.", 401)
    return data, session, None


@require_POST
@api_key_required
def zivost(request):
    """Heartbeat while the student is logged in (keeps the session active
    for the duplicate-login check)."""
    data, session, error = _session_from_body(request)
    if error:
        return error
    if session.ended_at is not None:
        return _error("Ova prijava je završena.", 401)
    services.heartbeat(session)
    return _json({"ok": True})


@require_POST
@api_key_required
def odjava(request):
    """Student logged off Windows: ends the session so they can log in on
    another computer straight away."""
    data, session, error = _session_from_body(request)
    if error:
        return error
    services.end_session(session)
    return _json({"ok": True})


@require_POST
@api_key_required
def zapisi(request):
    """Accepts one event ({"vrsta", "detalji", "vrijeme"} at the top level)
    or many ({"zapisi": [...]}, used when flushing the offline queue).

    With a token the events belong to that login. Without one, the body must
    say {"neidentificiran": {...what was typed, maybe empty...}} and the
    events are stored as unidentified (nobody valid was logged in)."""
    data, error = _read_json(request)
    if error:
        return error

    unidentified = "neidentificiran" in data and not data.get("token")
    session = None
    if not unidentified:
        session = services.session_for_token(data.get("token"))
        if session is None:
            return _error("Neispravan ili istekao token - potrebna je ponovna prijava.", 401)
    elif not services.clean_line(data.get("racunalo"), services.MAX_COMPUTER_LEN):
        return _error("Potreban je naziv računala.", 400)

    if "zapisi" in data:
        events = data["zapisi"]
        if not isinstance(events, list):
            return _error("'zapisi' mora biti lista.", 400)
    else:
        events = [data]
    if not events:
        return _error("Nema zapisa.", 400)
    if len(events) > MAX_EVENTS_PER_REQUEST:
        return _error(f"Najviše {MAX_EVENTS_PER_REQUEST} zapisa po zahtjevu.", 413)

    try:
        if unidentified:
            count = services.save_unidentified_logs(
                data.get("racunalo"), data.get("neidentificiran"), events
            )
        else:
            count = services.save_logs(session, data.get("racunalo"), events)
    except services.InvalidEvent as exc:
        return _error(str(exc), 400)
    return _json({"primljeno": count}, status=201)
