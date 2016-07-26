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
from django.conf.urls import url, include
from . import views, api

season_urlpatterns = [
    url(r'^summary/$', views.season_landing, name='season_landing'),
    url(r'^register/$', views.register, name='register'),
    url(r'^faq/$', views.faq, name='faq'),
    url(r'^rosters/$', views.rosters, name='rosters'),
    url(r'^standings/$', views.standings, name='standings'),
    url(r'^crosstable/$', views.crosstable, name='crosstable'),
    url(r'^pairings/$', views.pairings, name='pairings'),
    url(r'^round/(?P<round_number>[0-9]+)/pairings/$', views.pairings, name='pairings_by_round'),
    url(r'^stats/$', views.stats, name='stats'),
]

league_urlpatterns = [
    url(r'^$', views.league_home, name='league_home'),
    url(r'^registration_success/$', views.registration_success, name='registration_success'),
    url(r'^registration_closed/$', views.registration_closed, name='registration_closed'),
    url(r'^', include(season_urlpatterns)),
    url(r'^season/(?P<season_id>[0-9]+)/', include(season_urlpatterns, 'by_season')),
]

api_urlpatterns = [
    url(r'^find_pairing/$', api.find_pairing, name='find_pairing'),
    url(r'^update_pairing/$', api.update_pairing, name='update_pairing'),
    url(r'^get_roster/$', api.get_roster, name='get_roster'),
]

urlpatterns = [
    url(r'^', include(league_urlpatterns)),
    url(r'^(?P<league_tag>\w+)/', include(league_urlpatterns, 'by_league')),
    url(r'^api/', include(api_urlpatterns, 'api')),
]
