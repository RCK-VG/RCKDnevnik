from django.urls import path

from . import api, views

urlpatterns = [
    path("api/nadzor/v1/razredi/", api.razredi, name="nadzor_api_razredi"),
    path("api/nadzor/v1/prijava/", api.prijava, name="nadzor_api_prijava"),
    path("api/nadzor/v1/zapisi/", api.zapisi, name="nadzor_api_zapisi"),
    path("api/nadzor/v1/zivost/", api.zivost, name="nadzor_api_zivost"),
    path("api/nadzor/v1/odjava/", api.odjava, name="nadzor_api_odjava"),
    path("nadzor/", views.zapisi, name="nadzor_zapisi"),
]
