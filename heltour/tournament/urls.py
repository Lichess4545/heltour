"""heltour2 URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.9/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^$', views.home, name='home'),
    url(r'^register/$', views.register, name='register'),
    url(r'^season/(?P<season_id>[0-9]+)/register/$', views.register_by_season, name='register_by_season'),
    url(r'^registration_success/$', views.registration_success, name='registration_success'),
    url(r'^registration_closed/$', views.registration_closed, name='registration_closed'),
    url(r'^faq/$', views.faq, name='faq'),
    url(r'^rosters/$', views.rosters, name='rosters'),
    url(r'^standings/$', views.standings, name='standings'),
    url(r'^crosstable/$', views.crosstable, name='crosstable'),
    url(r'^pairings/$', views.pairings, name='pairings'),
    url(r'^stats/$', views.stats, name='stats'),
    url(r'^round/(?P<round_number>[0-9]+)/pairings/$', views.pairings_by_round, name='pairings_by_round'),
    url(r'^season/(?P<season_id>[0-9]+)/round/(?P<round_number>[0-9]+)/pairings/$', views.pairings_by_season, name='pairings_by_season'),
]
