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
from django.conf import settings
from django.conf.urls import url, include
from django.conf.urls.static import static
from . import views, api
from django.contrib.admin.views.decorators import staff_member_required

season_urlpatterns = [
    url(r'^summary/$', views.SeasonLandingView.as_view(), name='season_landing'),
    url(r'^register/$', views.RegisterView.as_view(), name='register'),
    url(r'^registration_success/$', views.RegistrationSuccessView.as_view(), name='registration_success'),
    url(r'^rosters/$', views.RostersView.as_view(), name='rosters'),
    url(r'^standings/$', views.StandingsView.as_view(), name='standings'),
    url(r'^standings/section/(?P<section>[\w-]+)/$', views.StandingsView.as_view(), name='standings_by_section'),
    url(r'^crosstable/$', views.CrosstableView.as_view(), name='crosstable'),
    url(r'^wallchart/$', views.WallchartView.as_view(), name='wallchart'),
    url(r'^pairings/$', views.PairingsView.as_view(), name='pairings'),
    url(r'^pairings/team/(?P<team_number>[0-9]+)/$', views.PairingsView.as_view(), name='pairings_by_team'),
    url(r'^round/(?P<round_number>[0-9]+)/pairings/$', views.PairingsView.as_view(), name='pairings_by_round'),
    url(r'^round/(?P<round_number>[0-9]+)/pairings/team/(?P<team_number>[0-9]+)/$', views.PairingsView.as_view(), name='pairings_by_round_team'),
    url(r'^stats/$', views.StatsView.as_view(), name='stats'),
    url(r'^result/(?P<pairing_id>[0-9]+)/$', views.ResultView.as_view(), name='result'),
    url(r'^dashboard/$', staff_member_required(views.LeagueDashboardView.as_view()), name='league_dashboard'),
    url(r'^player/(?P<username>[\w-]+)/$', views.PlayerProfileView.as_view(), name='player_profile'),
    url(r'^tv/$', views.TvView.as_view(), name='tv'),
    url(r'^document/(?P<document_tag>[\w-]+)/$', views.DocumentView.as_view(), name='document'),
    url(r'^nominate/(?P<secret_token>\w+)/$', views.NominateView.as_view(), name='nominate'),
]

league_urlpatterns = [
    url(r'^$', views.LeagueHomeView.as_view(), name='league_home'),
    url(r'^', include(season_urlpatterns)),
    url(r'^season/(?P<season_tag>[\w-]+)/', include(season_urlpatterns, 'by_season')),
    url(r'^document/(?P<document_tag>[\w-]+)/$', views.DocumentView.as_view(), name='document'),
]

api_urlpatterns = [
    url(r'^find_pairing/$', api.find_pairing, name='find_pairing'),
    url(r'^update_pairing/$', api.update_pairing, name='update_pairing'),
    url(r'^get_roster/$', api.get_roster, name='get_roster'),
    url(r'^assign_alternate/$', api.assign_alternate, name='assign_alternate'),
    url(r'^set_availability/$', api.set_availability, name='set_availability'),
    url(r'^get_league_moderators/$', api.get_league_moderators, name='get_league_moderators'),
    url(r'^league_document/$', api.league_document, name='league_document'),
    url(r'^get_private_url/$', api.get_private_url, name='get_private_url'),
]

urlpatterns = [
    url(r'^$', views.HomeView.as_view(), name='home'),
    url(r'^(?P<league_tag>[\w-]+)/', include(league_urlpatterns, 'by_league')),
    url(r'^api/', include(api_urlpatterns, 'api')),
    url(r'^comments/', include('django_comments.urls')),
    url(r'^ckeditor/', include('ckeditor_uploader.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
