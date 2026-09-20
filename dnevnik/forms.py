from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone

from .models import SchoolClass, Subject


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
