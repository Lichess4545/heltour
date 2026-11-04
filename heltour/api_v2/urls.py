from django.urls import path

from heltour.api_v2 import views

app_name = "api_v2"

urlpatterns = [
    path("leagues/", views.LeaguesView.as_view(), name="leagues"),
    path("leagues/<slug:tag>/", views.LeagueView.as_view(), name="league"),
]
