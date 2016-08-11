from django.conf.urls import url
import views

urlpatterns = [
    url(r'^lichessapi/(?P<path>.+)/$', views.lichess_api_call, name='lichess_api_call'),
]
