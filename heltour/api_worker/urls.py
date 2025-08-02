from django.urls import path

from heltour.api_worker import views

urlpatterns = [
    path('lichessapi/<path:path>', views.lichess_api_call, name='lichess_api_call'),
    path('watch/', views.watch, name='watch'),
    path('watch/add/', views.watch_add, name='watch_add'),
]
