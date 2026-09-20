from django.urls import path

from . import views, views_auth, views_import, views_lesson

urlpatterns = [
    path("", views.pocetna, name="pocetna"),
    path("prijava/", views_auth.PrijavaView.as_view(), name="prijava"),
    path("odjava/", views_auth.DnevnikLogoutView.as_view(), name="odjava"),
    path("promjena-lozinke/", views_auth.promjena_lozinke, name="promjena_lozinke"),
    path("uvoz/ucenici/", views_import.uvoz_ucenika, name="uvoz_ucenika"),
    path("uvoz/predmeti/", views_import.uvoz_predmeta, name="uvoz_predmeta"),
    path("sat/novi/", views_lesson.izbor_sata, name="izbor_sata"),
    path("sat/otvori/", views_lesson.otvori_sat, name="otvori_sat"),
    path("sat/<int:pk>/", views_lesson.sat, name="sat"),
]
