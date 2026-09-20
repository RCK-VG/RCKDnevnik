from django import forms
from django.contrib.auth.forms import AuthenticationForm


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
