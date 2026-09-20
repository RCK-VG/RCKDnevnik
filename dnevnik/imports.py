"""CSV/Excel import helpers for students and subjects.

Each parse_* function returns a list of plain dicts describing what would
happen on commit (add / update / skip / error), so the view can show a
preview before anything is written to the database.
"""

import csv
import io

import openpyxl

TRUE_VALUES = {"da", "d", "1", "true", "istina", "x", "yes"}


def _to_bool(value):
    return str(value).strip().lower() in TRUE_VALUES


def _read_rows_from_upload(uploaded_file):
    """Returns a list of row lists (raw cell strings) from a .csv or .xlsx file."""
    name = uploaded_file.name.lower()
    if name.endswith(".xlsx"):
        workbook = openpyxl.load_workbook(uploaded_file, data_only=True)
        sheet = workbook.active
        rows = []
        for raw_row in sheet.iter_rows(values_only=True):
            rows.append(["" if cell is None else str(cell).strip() for cell in raw_row])
        return rows

    raw_bytes = uploaded_file.read()
    for encoding in ("utf-8-sig", "cp1250", "latin-1"):
        try:
            text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw_bytes.decode("utf-8", errors="replace")

    sample = text[:2048]
    delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [[cell.strip() for cell in row] for row in reader if any(cell.strip() for cell in row)]


def parse_student_rows(uploaded_file, school_year):
    """Parses a student import file.

    Expected columns (header names, order does not matter, case-insensitive):
    razred, prezime, ime, ip, pp
    """
    from .models import SchoolClass, Student

    rows = _read_rows_from_upload(uploaded_file)
    if not rows:
        return []

    header = [cell.lower() for cell in rows[0]]
    expected = {"razred", "prezime", "ime", "ip", "pp"}
    if expected.issubset(set(header)):
        data_rows = rows[1:]
        col_index = {col: header.index(col) for col in expected}
    else:
        # No recognizable header: assume fixed column order as in the spec.
        data_rows = rows
        col_index = {"razred": 0, "prezime": 1, "ime": 2, "ip": 3, "pp": 4}

    existing_classes = {
        c.name.strip().lower(): c
        for c in SchoolClass.objects.filter(school_year=school_year)
    }
    existing_students = {
        (s.school_class_id, s.first_name.strip().lower(), s.last_name.strip().lower()): s
        for s in Student.objects.filter(school_class__school_year=school_year)
    }
    classes_to_create = set()

    results = []
    for line_number, row in enumerate(data_rows, start=2):

        def cell(key):
            idx = col_index.get(key)
            return row[idx].strip() if idx is not None and idx < len(row) else ""

        class_name = cell("razred")
        last_name = cell("prezime")
        first_name = cell("ime")
        is_ip = _to_bool(cell("ip"))
        is_pp = _to_bool(cell("pp"))

        if not class_name or not last_name or not first_name:
            results.append(
                {
                    "line": line_number,
                    "action": "greska",
                    "message": "Nedostaje razred, ime ili prezime.",
                    "class_name": class_name,
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_ip": is_ip,
                    "is_pp": is_pp,
                }
            )
            continue

        class_key = class_name.strip().lower()
        school_class = existing_classes.get(class_key)
        new_class = school_class is None
        if new_class:
            classes_to_create.add(class_name)

        student_key = (
            school_class.id if school_class else f"NEW:{class_key}",
            first_name.strip().lower(),
            last_name.strip().lower(),
        )
        existing = existing_students.get(student_key) if school_class else None

        if existing:
            changed = existing.is_ip != is_ip or existing.is_pp != is_pp
            action = "azurira" if changed else "preskace"
        else:
            action = "dodaje"

        results.append(
            {
                "line": line_number,
                "action": action,
                "message": "Novi razred bit će stvoren." if new_class else "",
                "class_name": class_name,
                "first_name": first_name,
                "last_name": last_name,
                "is_ip": is_ip,
                "is_pp": is_pp,
                "existing_id": existing.id if existing else None,
            }
        )

    return results


def commit_student_rows(parsed_rows, school_year):
    """Writes previously parsed rows (parse_student_rows output) to the database."""
    from .models import SchoolClass, Student

    added = updated = skipped = errors = 0
    class_cache = {}

    for row in parsed_rows:
        if row["action"] == "greska":
            errors += 1
            continue

        class_name = row["class_name"]
        class_key = class_name.strip().lower()
        school_class = class_cache.get(class_key)
        if school_class is None:
            try:
                school_class = SchoolClass.objects.get(
                    school_year=school_year, name__iexact=class_name
                )
            except SchoolClass.DoesNotExist:
                school_class = SchoolClass.objects.create(
                    school_year=school_year, name=class_name
                )
            class_cache[class_key] = school_class

        if row["action"] == "dodaje":
            Student.objects.create(
                school_class=school_class,
                first_name=row["first_name"],
                last_name=row["last_name"],
                is_ip=row["is_ip"],
                is_pp=row["is_pp"],
            )
            added += 1
        elif row["action"] == "azurira":
            Student.objects.filter(id=row["existing_id"]).update(
                is_ip=row["is_ip"], is_pp=row["is_pp"]
            )
            updated += 1
        else:
            skipped += 1

    return {"added": added, "updated": updated, "skipped": skipped, "errors": errors}


def parse_subject_rows(uploaded_file):
    """Parses a subject import file: a single column of subject names,
    with or without a header ('naziv' / 'predmet')."""
    from .models import Subject

    rows = _read_rows_from_upload(uploaded_file)
    if not rows:
        return []

    header = [cell.lower() for cell in rows[0]]
    if header and header[0] in ("naziv", "predmet", "ime", "name"):
        data_rows = rows[1:]
    else:
        data_rows = rows

    existing = {s.name.strip().lower(): s for s in Subject.objects.all()}
    seen = set()
    results = []
    for line_number, row in enumerate(data_rows, start=2):
        name = row[0].strip() if row else ""
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        action = "preskace" if key in existing else "dodaje"
        results.append({"line": line_number, "action": action, "name": name})

    return results


def commit_subject_rows(parsed_rows):
    from .models import Subject

    added = skipped = 0
    for row in parsed_rows:
        if row["action"] == "dodaje":
            if not Subject.objects.filter(name__iexact=row["name"]).exists():
                Subject.objects.create(name=row["name"])
            added += 1
        else:
            skipped += 1
    return {"added": added, "skipped": skipped}
