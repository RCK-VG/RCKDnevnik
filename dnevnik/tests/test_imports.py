from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from dnevnik import imports
from dnevnik.models import SchoolClass, SchoolYear, Student, Subject


def csv_file(text, name="ucenici.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8-sig"), content_type="text/csv")


class StudentImportTests(TestCase):
    def setUp(self):
        self.school_year = SchoolYear.objects.create(name="2025./2026.", is_active=True)

    def test_parses_new_students_and_creates_missing_class(self):
        content = "razred;prezime;ime;IP;PP\n1.a;Horvat;Đurđica;da;ne\n1.a;Čović;Šime;ne;ne\n"
        rows = imports.parse_student_rows(csv_file(content), self.school_year)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["action"], "dodaje")
        self.assertEqual(rows[0]["last_name"], "Horvat")
        self.assertEqual(rows[0]["first_name"], "Đurđica")
        self.assertTrue(rows[0]["is_ip"])
        self.assertFalse(rows[0]["is_pp"])

        summary = imports.commit_student_rows(rows, self.school_year)
        self.assertEqual(summary["added"], 2)
        self.assertEqual(SchoolClass.objects.filter(school_year=self.school_year).count(), 1)
        self.assertEqual(Student.objects.count(), 2)

    def test_reimporting_same_file_skips_unchanged_rows(self):
        content = "razred;prezime;ime;IP;PP\n1.a;Horvat;Ana;ne;ne\n"
        rows = imports.parse_student_rows(csv_file(content), self.school_year)
        imports.commit_student_rows(rows, self.school_year)

        rows_again = imports.parse_student_rows(csv_file(content), self.school_year)
        self.assertEqual(rows_again[0]["action"], "preskace")
        summary = imports.commit_student_rows(rows_again, self.school_year)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(Student.objects.count(), 1)

    def test_changed_flags_are_detected_as_update(self):
        content_v1 = "razred;prezime;ime;IP;PP\n1.a;Horvat;Ana;ne;ne\n"
        rows = imports.parse_student_rows(csv_file(content_v1), self.school_year)
        imports.commit_student_rows(rows, self.school_year)

        content_v2 = "razred;prezime;ime;IP;PP\n1.a;Horvat;Ana;da;ne\n"
        rows_v2 = imports.parse_student_rows(csv_file(content_v2), self.school_year)
        self.assertEqual(rows_v2[0]["action"], "azurira")

        summary = imports.commit_student_rows(rows_v2, self.school_year)
        self.assertEqual(summary["updated"], 1)
        student = Student.objects.get()
        self.assertTrue(student.is_ip)

    def test_row_missing_required_field_is_an_error(self):
        content = "razred;prezime;ime;IP;PP\n1.a;;Ana;ne;ne\n"
        rows = imports.parse_student_rows(csv_file(content), self.school_year)
        self.assertEqual(rows[0]["action"], "greska")

    def test_headerless_file_uses_fixed_column_order(self):
        content = "1.b;Novak;Ivan;ne;ne\n"
        rows = imports.parse_student_rows(csv_file(content), self.school_year)
        self.assertEqual(rows[0]["action"], "dodaje")
        self.assertEqual(rows[0]["class_name"], "1.b")


class SubjectImportTests(TestCase):
    def test_parses_and_deduplicates_subjects(self):
        existing = Subject.objects.create(name="Matematika")
        content = "naziv\nMatematika\nHrvatski jezik\nHrvatski jezik\n"
        rows = imports.parse_subject_rows(csv_file(content, "predmeti.csv"))

        self.assertEqual(len(rows), 2)  # duplicate "Hrvatski jezik" line collapsed
        self.assertEqual(rows[0]["action"], "preskace")  # Matematika already exists
        self.assertEqual(rows[1]["action"], "dodaje")

        summary = imports.commit_subject_rows(rows)
        self.assertEqual(summary["added"], 1)
        self.assertEqual(Subject.objects.count(), 2)
        self.assertTrue(Subject.objects.filter(name=existing.name).exists())
