import random

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from dnevnik.models import SchoolClass, SchoolYear, Student, Subject

DEMO_PASSWORD = "Demo1234!"

TEACHERS = [
    ("ana.anic", "Ana", "Anić"),
    ("ivan.ivic", "Ivan", "Ivić"),
    ("marija.maric", "Marija", "Marić"),
    ("petar.peric", "Petar", "Perić"),
    ("iva.ivkovic", "Iva", "Ivković"),
]

SUBJECTS = [
    "Matematika",
    "Hrvatski jezik",
    "Engleski jezik",
    "Informatika",
    "Tjelesna i zdravstvena kultura",
    "Kemija",
    "Fizika",
    "Biologija",
    "Povijest",
    "Geografija",
]

CLASS_NAMES = ["1.a", "1.b", "2.a"]

FIRST_NAMES = [
    "Luka", "Marko", "Ivan", "David", "Filip", "Karlo", "Josip", "Antonio",
    "Ema", "Lucija", "Nika", "Petra", "Mia", "Dora", "Sara", "Tara",
]

LAST_NAMES = [
    "Horvat", "Kovačević", "Babić", "Marić", "Jurić", "Novak", "Vuković",
    "Kovač", "Knežević", "Vidović", "Pavlović", "Matić", "Blažević",
]


class Command(BaseCommand):
    help = "Puni bazu izmišljenim demo podacima za testiranje (NIKAD prave podatke)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--students-per-class",
            type=int,
            default=12,
            help="Broj izmišljenih učenika po razredu (zadano: 12).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(42)
        students_per_class = options["students_per_class"]

        school_year, _ = SchoolYear.objects.get_or_create(
            name="2025./2026.", defaults={"is_active": True}
        )
        SchoolYear.objects.exclude(id=school_year.id).update(is_active=False)
        school_year.is_active = True
        school_year.save(update_fields=["is_active"])

        teacher_users = []
        for username, first_name, last_name in TEACHERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first_name, "last_name": last_name},
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            teacher_users.append(user)

        for name in SUBJECTS:
            Subject.objects.get_or_create(name=name)

        classes = []
        for i, class_name in enumerate(CLASS_NAMES):
            school_class, _ = SchoolClass.objects.get_or_create(
                name=class_name,
                school_year=school_year,
                defaults={"homeroom_teacher": teacher_users[i % len(teacher_users)]},
            )
            classes.append(school_class)

        used_names = set()
        for school_class in classes:
            existing_count = Student.objects.filter(school_class=school_class).count()
            for _ in range(max(0, students_per_class - existing_count)):
                while True:
                    first = rng.choice(FIRST_NAMES)
                    last = rng.choice(LAST_NAMES)
                    key = (school_class.id, first, last)
                    if key not in used_names:
                        used_names.add(key)
                        break
                Student.objects.create(
                    school_class=school_class,
                    first_name=first,
                    last_name=last,
                    is_ip=rng.random() < 0.1,
                    is_pp=rng.random() < 0.05,
                )

        # Plain ASCII on purpose: Windows consoles often default to a legacy
        # codepage (cp1252) that cannot encode Croatian diacritics and would
        # crash this command with UnicodeEncodeError.
        self.stdout.write(self.style.SUCCESS("Demo podaci uspjesno kreirani/azurirani."))
        self.stdout.write(f"Skolska godina: {school_year.name}")
        self.stdout.write(f"Razredi: {', '.join(c.name for c in classes)}")
        self.stdout.write(f"Predmeti: {len(SUBJECTS)}")
        self.stdout.write(
            f"Nastavnici (lozinka za sve: {DEMO_PASSWORD}): "
            + ", ".join(u.username for u in teacher_users)
        )
        self.stdout.write(
            self.style.WARNING(
                "Napomena: svi nastavnicki racuni zahtijevaju promjenu lozinke pri prvoj prijavi."
            )
        )
