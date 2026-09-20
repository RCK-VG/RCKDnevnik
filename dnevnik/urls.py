from django.urls import path

from . import views, views_auth, views_backup, views_export, views_import, views_lesson, views_review

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
    path("razredi/", views_review.razredi, name="razredi"),
    path("razredi/<int:pk>/", views_review.razred_detalj, name="razred_detalj"),
    path("ucenici/<int:pk>/", views_review.ucenik_profil, name="ucenik_profil"),
    path("izvoz/", views_export.izvoz, name="izvoz"),
    path("izvoz/prisutnost/", views_export.izvoz_prisutnost, name="izvoz_prisutnost"),
    path("izvoz/sazetak/", views_export.izvoz_sazetak, name="izvoz_sazetak"),
    path("izvoz/biljeske/", views_export.izvoz_biljeske, name="izvoz_biljeske"),
    path("izvoz/potpuni/", views_export.izvoz_potpuni, name="izvoz_potpuni"),
    path("backup/preuzmi/", views_backup.preuzmi_backup, name="preuzmi_backup"),
]
