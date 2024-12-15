from django.urls import path

from . import views

urlpatterns = [
    path("lichessapi/<path:path>", views.lichess_api_call, name="lichess_api_call"),
    path("watch/", views.watch, name="watch"),
    path("watch/add/", views.watch_add, name="watch_add"),
]
