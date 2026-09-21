from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone

from . import constants
from .models import SchoolClass, Subject

FORMAT_CHOICES = [("xlsx", "Excel (.xlsx)"), ("csv", "CSV (za Excel, ; razdjelnik)")]


class TeacherChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        return user.get_full_name() or user.username


class DnevnikAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="Korisničko ime",
        widget=forms.TextInput(attrs={"autofocus": True, "class": "form-control"}),
    )
    password = forms.CharField(
        label="Lozinka",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )


class FileImportForm(forms.Form):
    file = forms.FileField(
        label="Datoteka (CSV ili Excel)",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,.xlsx"}),
    )


class ReviewFilterForm(forms.Form):
    predmet = forms.ModelChoiceField(
        label="Predmet",
        queryset=Subject.objects.filter(is_archived=False),
        required=False,
        empty_label="Svi predmeti",
    )
    datum_od = forms.DateField(
        label="Od datuma", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    datum_do = forms.DateField(
        label="Do datuma", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )


class LessonFilterForm(forms.Form):
    razred = forms.ModelChoiceField(
        label="Razred",
        queryset=SchoolClass.objects.select_related("school_year").order_by(
            "school_year", "name"
        ),
        required=False,
        empty_label="Svi razredi",
    )
    predmet = forms.ModelChoiceField(
        label="Predmet", queryset=Subject.objects.all(), required=False, empty_label="Svi predmeti"
    )
    nastavnik = TeacherChoiceField(
        label="Nastavnik",
        queryset=get_user_model().objects.filter(is_active=True).order_by("last_name", "first_name"),
        required=False,
        empty_label="Svi nastavnici",
    )
    datum_od = forms.DateField(
        label="Od datuma", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    datum_do = forms.DateField(
        label="Do datuma", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )


class MatrixExportForm(forms.Form):
    razred = forms.ModelChoiceField(
        label="Razred",
        queryset=SchoolClass.objects.select_related("school_year").order_by(
            "school_year", "name"
        ),
    )
    predmet = forms.ModelChoiceField(
        label="Predmet",
        queryset=Subject.objects.all(),
        required=False,
        empty_label="Svi predmeti",
    )
    datum_od = forms.DateField(
        label="Od datuma", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    datum_do = forms.DateField(
        label="Do datuma", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    format = forms.ChoiceField(label="Format", choices=FORMAT_CHOICES, initial="xlsx")


class ExportFilterForm(forms.Form):
    razred = forms.ModelChoiceField(
        label="Razred",
        queryset=SchoolClass.objects.select_related("school_year").order_by(
            "school_year", "name"
        ),
        required=False,
        empty_label="Svi razredi",
    )
    predmet = forms.ModelChoiceField(
        label="Predmet", queryset=Subject.objects.all(), required=False, empty_label="Svi predmeti"
    )
    nastavnik = TeacherChoiceField(
        label="Nastavnik",
        queryset=get_user_model().objects.filter(is_active=True).order_by("last_name", "first_name"),
        required=False,
        empty_label="Svi nastavnici",
    )
    datum_od = forms.DateField(
        label="Od datuma", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    datum_do = forms.DateField(
        label="Do datuma", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    format = forms.ChoiceField(label="Format", choices=FORMAT_CHOICES, initial="xlsx")


class LessonPickerForm(forms.Form):
    razred = forms.ModelChoiceField(
        label="Razred",
        queryset=SchoolClass.objects.filter(
            school_year__is_archived=False
        ).select_related("school_year"),
        empty_label="Odaberite razred",
    )
    predmet = forms.ModelChoiceField(
        label="Predmet",
        queryset=Subject.objects.filter(is_archived=False),
        empty_label="Odaberite predmet",
    )
    datum = forms.DateField(
        label="Datum",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    grupa = forms.ChoiceField(
        label="Grupa",
        choices=[("", "Cijeli razred")] + list(constants.GROUP_CHOICES),
        required=False,
    )
