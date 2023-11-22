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
from django.conf.urls.static import static
from . import views, api, android_app, auth
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import include, re_path
from django.views.decorators.cache import cache_control

season_urlpatterns = [
    re_path(r'^summary/$', views.SeasonLandingView.as_view(), name='season_landing'),
    re_path(r'^register/$', views.RegisterView.as_view(), name='register'),
    re_path(r'^registration_success/$', views.RegistrationSuccessView.as_view(),
        name='registration_success'),
    re_path(r'^rosters/$', views.RostersView.as_view(), name='rosters'),
    re_path(r'^standings/$', views.StandingsView.as_view(), name='standings'),
    re_path(r'^standings/section/(?P<section>[\w-]+)/$', views.StandingsView.as_view(),
        name='standings_by_section'),
    re_path(r'^crosstable/$', views.CrosstableView.as_view(), name='crosstable'),
    re_path(r'^wallchart/$', views.WallchartView.as_view(), name='wallchart'),
    re_path(r'^pairings/$', views.PairingsView.as_view(), name='pairings'),
    re_path(r'^pairings/calendar.ics$', views.ICalPairingsView.as_view(), name='pairings_icalendar'),
    re_path(r'^pairings/team/(?P<team_number>[0-9]+)/$', views.PairingsView.as_view(),
        name='pairings_by_team'),
    re_path(r'^pairings/team/(?P<team_number>[0-9]+)/calendar.ics$', views.ICalPairingsView.as_view(),
        name='pairings_by_team_icalendar'),
    re_path(r'^round/(?P<round_number>[0-9]+)/pairings/$', views.PairingsView.as_view(),
        name='pairings_by_round'),
    re_path(r'^round/(?P<round_number>[0-9]+)/pairings/team/(?P<team_number>[0-9]+)/$',
        views.PairingsView.as_view(), name='pairings_by_round_team'),
    re_path(r'^stats/$', views.StatsView.as_view(), name='stats'),
    re_path(r'^dashboard/$', staff_member_required(views.LeagueDashboardView.as_view()),
        name='league_dashboard'),
    re_path(r'^player/$', views.UserDashboardView.as_view(), name='user_dashboard'),
    re_path(r'^player/(?P<username>[\w-]+)/$', views.PlayerProfileView.as_view(),
        name='player_profile'),
    re_path(r'^team/(?P<team_number>[0-9]+)/$', views.TeamProfileView.as_view(), name='team_profile'),
    re_path(r'^tv/$', cache_control(no_cache=True)(views.TvView.as_view()), name='tv'),
    re_path(r'^tv/json/$', cache_control(no_cache=True)(views.TvJsonView.as_view()), name='tv_json'),
    re_path(r'^document/(?P<document_tag>[\w-]+)/$', views.DocumentView.as_view(), name='document'),
    re_path(r'^request/(?P<req_type>\w+)/$', views.ModRequestView.as_view(), name='modrequest'),
    re_path(r'^request/(?P<req_type>\w+)/success/$', views.ModRequestSuccessView.as_view(),
        name='modrequest_success'),
    re_path(r'^nominate/$', views.NominateView.as_view(), name='nominate'),
    re_path(r'^nominate/delete/(?P<nomination_id>\w+)/$', views.DeleteNominationView.as_view(),
        name='delete_nomination'),
    re_path(r'^schedule/edit/$', views.ScheduleView.as_view(), name='edit_schedule'),
    re_path(r'^availability/edit/$', views.AvailabilityView.as_view(), name='edit_availability'),
    re_path(r'^board/(?P<board_number>[0-9]+)/scores/$', views.BoardScoresView.as_view(),
        name='board_scores'),
    re_path(r'^alternates/$', views.AlternatesView.as_view(), name='alternates'),
    re_path(r'^round/(?P<round_number>[0-9]+)/alternate/accept/$', views.AlternateAcceptView.as_view(),
        name='alternate_accept'),
    re_path(r'^round/(?P<round_number>[0-9]+)/alternate/decline/$',
        views.AlternateDeclineView.as_view(), name='alternate_decline'),
    re_path(r'^notifications/$', views.NotificationsView.as_view(), name='notifications'),
]

league_urlpatterns = [
    re_path(r'^$', views.LeagueHomeView.as_view(), name='league_home'),
    re_path(r'^', include(season_urlpatterns)),
    re_path(r'^season/(?P<season_tag>[\w-]+)/',
        include((season_urlpatterns, 'tournament'), 'by_season')),
    re_path(r'^document/(?P<document_tag>[\w-]+)/$', views.DocumentView.as_view(), name='document'),
    re_path(r'^contact/$', views.ContactView.as_view(), name='contact'),
    re_path(r'^contact_success/$', views.ContactSuccessView.as_view(), name='contact_success'),
    re_path(r'^about/$', views.AboutView.as_view(), name='about'),
    re_path(r'^login/$', views.LoginView.as_view(), name='login'),
    re_path(r'^login/(?P<secret_token>\w+)/$', views.LoginView.as_view(), name='login_with_token'),
    re_path(r'^logout/$', views.LogoutView.as_view(), name='logout'),
]

api_urlpatterns = [
    re_path(r'^find_pairing/$', api.find_pairing, name='find_pairing'),
    re_path(r'^update_pairing/$', api.update_pairing, name='update_pairing'),
    re_path(r'^get_roster/$', api.get_roster, name='get_roster'),
    re_path(r'^assign_alternate/$', api.assign_alternate, name='assign_alternate'),
    re_path(r'^set_availability/$', api.set_availability, name='set_availability'),
    re_path(r'^get_league_moderators/$', api.get_league_moderators, name='get_league_moderators'),
    re_path(r'^league_document/$', api.league_document, name='league_document'),
    re_path(r'^link_slack/$', api.link_slack, name='link_slack'),
    re_path(r'^get_slack_user_map/$', api.get_slack_user_map, name='get_slack_user_map'),
    re_path(r'^game_warning/$', api.game_warning, name='game_warning'),
    re_path(r'^player_contact/$', api.player_contact, name='player_contact'),
    re_path(r'^get_season_games/$', api.get_season_games, name='get_season_games'),
]

app_urlpatterns = [
    re_path(r'^event/$', android_app.slack_event, name='slack_event'),
    re_path(r'^register/$', android_app.fcm_register, name='fcm_register'),
    re_path(r'^unregister/$', android_app.fcm_unregister, name='fcm_unregister'),
]

urlpatterns = [
    re_path(r'^$', views.HomeView.as_view(), name='home'),
    re_path(r'^toggle/darkmode/$', views.ToggleDarkModeView.as_view(), name='toggle_darkmode'),
    re_path(r'^player/(?P<username>[\w-]+)/calendar.ics$', views.ICalPlayerView.as_view(),
        name='player_icalendar'),
    re_path(r'^api/', include((api_urlpatterns, 'tournament'), 'api')),
    re_path(r'^app/', include((app_urlpatterns, 'tournament'), 'app')),
    re_path(r'^auth/slack/$', auth.SlackAuth.as_view(), name='slack_auth'),
    re_path(r'^auth/lichess/$', views.OAuthCallbackView.as_view(), name='lichess_auth'),
    re_path(r'^comments/', include('django_comments.urls')),
    re_path(r'^ckeditor/', include('ckeditor_uploader.urls')),
    re_path(r'^(?P<league_tag>[\w-]+)/', include((league_urlpatterns, 'tournament'), 'by_league')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
