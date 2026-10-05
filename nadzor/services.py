"""Student lookup, sessions and log storage for the computer monitoring
module. Kept free of HTTP so it can be tested directly."""

import base64
import hashlib
import re
import secrets
import unicodedata
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from dnevnik.models import SchoolClass, Student

from .models import ActivityLog, BlockedSite, ComputerSession

MAX_NAME_LEN = 100
MAX_CLASS_LEN = 20
MAX_COMPUTER_LEN = 64
MAX_EVENT_TYPE_LEN = 100
MAX_DETAILS_LEN = 2000

LOGIN_EVENT = "PRIJAVA"
LOGOUT_EVENT = "ODJAVA"
SITE_EVENT = "POSJEĆENA STRANICA"  # event_type the client sends for a visited domain


def normalize_pattern(value):
    """Tidy a disallowed-site entry: lowercase, drop scheme/path and a leading
    www., so "https://www.Roblox.com/games" becomes "roblox.com"."""
    v = (value or "").strip().lower()
    v = re.sub(r"^[a-z]+://", "", v)
    v = v.split("/")[0].split("?")[0].strip()
    if v.startswith("www."):
        v = v[4:]
    return v


def active_block_patterns():
    return [p for p in BlockedSite.objects.filter(is_active=True).values_list("pattern", flat=True) if p]


def domain_is_blocked(domain, patterns=None):
    d = (domain or "").lower()
    pats = active_block_patterns() if patterns is None else patterns
    return any(p in d for p in pats)


def blocked_logs_q(patterns=None):
    """Q selecting visited-site logs that match any disallowed term. Returns a
    never-matching Q when the list is empty."""
    from django.db.models import Q

    pats = active_block_patterns() if patterns is None else patterns
    if not pats:
        return Q(pk__in=[])
    terms = Q()
    for p in pats:
        terms |= Q(details__icontains=p)
    return Q(event_type=SITE_EVENT) & terms

# Files the server offers for client auto-update. Fixed whitelist: never serve
# config.json (holds the key) or the certificate, and never an arbitrary path.
# servis.ps1 + the txt lists live in RCKNadzor; the rest in RCKNadzorProzor.
CLIENT_UPDATE_FILES = (
    "servis.ps1",
    "prozor.ps1",
    "pokreni_prozor.vbs",
    "preskoci_procese.txt",
    "preskoci_domene.txt",
)


def client_bundle():
    """The current client files as {verzija, datoteke:{name:{sha256, sadrzaj}}}.
    'verzija' is a hash of the whole bundle, so any change flips it and clients
    re-download; there is no version number to bump by hand. Returns None if the
    folder is missing."""
    folder = Path(settings.NADZOR_KLIJENT_DIR)
    if not folder.is_dir():
        return None
    files = {}
    combined = hashlib.sha256()
    for name in CLIENT_UPDATE_FILES:
        path = folder / name
        if not path.is_file():
            continue
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        files[name] = {"sha256": digest, "sadrzaj": base64.b64encode(raw).decode("ascii")}
        combined.update(f"{name}:{digest}\n".encode("ascii"))
    if not files:
        return None
    return {"verzija": combined.hexdigest(), "datoteke": files}

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_line(value, max_len):
    """Single-line text: NFC, control chars and newlines removed, runs of
    whitespace collapsed, trimmed and cut to max_len."""
    text = unicodedata.normalize("NFC", str(value or ""))
    text = _CONTROL_CHARS.sub(" ", text)
    text = " ".join(text.split())
    return text[:max_len]


def clean_text(value, max_len):
    """Multi-line text (event details): newlines/tabs kept, other control
    characters removed."""
    text = unicodedata.normalize("NFC", str(value or ""))
    text = _CONTROL_CHARS.sub("", text).strip()
    return text[:max_len]


def normalize_name(value):
    """Comparison key for names: case- and whitespace-insensitive, done in
    Python because SQLite's iexact ignores case only for ASCII letters
    ("ČOLIĆ" would not match "Čolić")."""
    return " ".join(unicodedata.normalize("NFC", str(value or "")).split()).casefold()


def normalize_class(value):
    """"1.c", " 1.C ", "1 .C" all compare equal."""
    return "".join(unicodedata.normalize("NFC", str(value or "")).split()).casefold()


def eligible_classes():
    """Classes of the active school year (or, if none is marked active, of
    all non-archived years) - the only ones offered to and matched from a
    student computer."""
    classes = SchoolClass.objects.filter(school_year__is_active=True)
    if not classes.exists():
        classes = SchoolClass.objects.filter(school_year__is_archived=False)
    return classes


def class_names():
    names = {c.name.strip() for c in eligible_classes()}
    return sorted(names, key=lambda n: normalize_class(n))


def find_students(class_name, first_name, last_name):
    """All non-archived students matching class + first + last name.
    Normally 0 or 1; 2+ means two students with identical names in one
    class, which the caller must treat as ambiguous."""
    wanted_class = normalize_class(class_name)
    class_ids = [c.id for c in eligible_classes() if normalize_class(c.name) == wanted_class]
    if not class_ids:
        return []
    wanted_first, wanted_last = normalize_name(first_name), normalize_name(last_name)
    return [
        s
        for s in Student.objects.filter(school_class_id__in=class_ids, is_archived=False)
        .select_related("school_class")
        if normalize_name(s.first_name) == wanted_first
        and normalize_name(s.last_name) == wanted_last
    ]


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _active_sessions(student, now=None):
    now = now or timezone.now()
    return ComputerSession.objects.filter(
        student=student,
        ended_at__isnull=True,
        last_seen_at__gte=now - timedelta(minutes=settings.NADZOR_AKTIVNOST_MINUTA),
        created_at__gte=now - timedelta(days=settings.NADZOR_TOKEN_DAYS),
    )


def active_session_elsewhere(student, computer_name):
    """An active session of this student on a DIFFERENT computer, or None.
    Active = not logged off and a heartbeat within NADZOR_AKTIVNOST_MINUTA."""
    for session in _active_sessions(student):
        if session.computer_name.casefold() != computer_name.casefold():
            return session
    return None


def start_session(student, computer_name, late=False, already_ended=False):
    """Creates a session and its PRIJAVA log; returns (session, plain token).
    The plain token is only ever returned here - the DB keeps the hash.

    late: a login typed while the server was down and confirmed only now -
    it may overlap other sessions; already_ended closes it right away."""
    now = timezone.now()
    if not late:
        # Logging in again on the same computer replaces the previous session.
        for old in _active_sessions(student, now):
            if old.computer_name.casefold() == computer_name.casefold():
                end_session(old)
    token = secrets.token_urlsafe(32)
    session = ComputerSession.objects.create(
        token_hash=hash_token(token),
        student=student,
        first_name=student.first_name,
        last_name=student.last_name,
        class_name=student.school_class.name,
        computer_name=computer_name,
        ended_at=now if already_ended else None,
    )
    details = "naknadno potvrđena prijava (server nije radio)" if late else ""
    save_logs(session, computer_name, [{"vrsta": LOGIN_EVENT, "detalji": details}])
    return session, token


def end_session(session):
    """Logoff: frees the student to log in on another computer at once."""
    if session.ended_at is not None:
        return
    save_logs(session, session.computer_name, [{"vrsta": LOGOUT_EVENT, "detalji": ""}])
    now = timezone.now()
    ComputerSession.objects.filter(pk=session.pk).update(ended_at=now)
    session.ended_at = now


def heartbeat(session):
    ComputerSession.objects.filter(pk=session.pk).update(last_seen_at=timezone.now())


def session_for_token(token):
    """Valid session for a plain token, else None."""
    if not token or not isinstance(token, str):
        return None
    session = ComputerSession.objects.filter(token_hash=hash_token(token)).first()
    if session is None or not session.is_valid():
        return None
    return session


def parse_client_time(value):
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = parse_datetime(value.strip())
    except ValueError:
        return None
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


class InvalidEvent(ValueError):
    pass


def _build_logs(events, **fields):
    rows = []
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            raise InvalidEvent(f"Zapis {index} nije objekt.")
        event_type = clean_line(event.get("vrsta"), MAX_EVENT_TYPE_LEN)
        if not event_type:
            raise InvalidEvent(f"Zapis {index} nema vrstu događaja.")
        rows.append(
            ActivityLog(
                event_type=event_type,
                details=clean_text(event.get("detalji"), MAX_DETAILS_LEN),
                client_time=parse_client_time(event.get("vrijeme")),
                **fields,
            )
        )
    return rows


def save_logs(session, computer_name, events):
    """Stores events for a session. Each event is a dict with "vrsta"
    (required), "detalji" and "vrijeme" (client ISO time, optional).
    Raises InvalidEvent before saving anything if any event is invalid."""
    rows = _build_logs(
        events,
        session=session,
        student_id=session.student_id,
        first_name=session.first_name,
        last_name=session.last_name,
        class_name=session.class_name,
        computer_name=clean_line(computer_name, MAX_COMPUTER_LEN) or session.computer_name,
        search_name=normalize_name(f"{session.last_name} {session.first_name}"),
    )
    ActivityLog.objects.bulk_create(rows)
    ComputerSession.objects.filter(pk=session.pk).update(last_seen_at=timezone.now())
    return len(rows)


def save_unidentified_logs(computer_name, typed, events):
    """Events from a computer where nobody valid was logged in. `typed` is
    what the student typed in the login window (class/first/last), possibly
    empty; it is kept for the teacher but NOT treated as the student."""
    typed = typed if isinstance(typed, dict) else {}
    first = clean_line(typed.get("ime"), MAX_NAME_LEN)
    last = clean_line(typed.get("prezime"), MAX_NAME_LEN)
    rows = _build_logs(
        events,
        identified=False,
        first_name=first,
        last_name=last,
        class_name=clean_line(typed.get("razred"), MAX_CLASS_LEN),
        computer_name=clean_line(computer_name, MAX_COMPUTER_LEN),
        search_name=normalize_name(f"{last} {first}"),
    )
    ActivityLog.objects.bulk_create(rows)
    return len(rows)
