from django.urls import path

from heltour.api_v2 import views

app_name = "api_v2"

urlpatterns = [
    path("leagues/", views.LeaguesView.as_view(), name="leagues"),
    path("leagues/<slug:tag>/", views.LeagueView.as_view(), name="league"),
    path("leagues/<slug:tag>/rounds/", views.RoundsView.as_view(), name="rounds"),
    path(
        "leagues/<slug:tag>/rounds/<int:round_id>/",
        views.RoundView.as_view(),
        name="round",
    ),
]
