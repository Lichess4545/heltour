"""heltour2 URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.9/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import url, include
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from . import views, api, android_app, auth
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import include, path
from django.views.decorators.cache import cache_control

season_urlpatterns = [
    path('summary/', views.SeasonLandingView.as_view(), name='season_landing'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('registration_success/', views.RegistrationSuccessView.as_view(),
        name='registration_success'),
    path('rosters/', views.RostersView.as_view(), name='rosters'),
    path('standings/', views.StandingsView.as_view(), name='standings'),
    path('standings/section/<slug:section>/', views.StandingsView.as_view(),
        name='standings_by_section'),
    path('crosstable/', views.CrosstableView.as_view(), name='crosstable'),
    path('wallchart/', views.WallchartView.as_view(), name='wallchart'),
    path('pairings/', views.PairingsView.as_view(), name='pairings'),
    path('pairings/calendar.ics', views.ICalPairingsView.as_view(), name='pairings_icalendar'),
    path('pairings/team/<int:team_number>/', views.PairingsView.as_view(),
        name='pairings_by_team'),
    path('pairings/team/<int:team_number>/calendar.ics', views.ICalPairingsView.as_view(),
        name='pairings_by_team_icalendar'),
    path('round/<int:round_number>/pairings/', views.PairingsView.as_view(),
        name='pairings_by_round'),
    path('round/<int:round_number>/pairings/team/<int:team_number>/',
        views.PairingsView.as_view(), name='pairings_by_round_team'),
    path('stats/', views.StatsView.as_view(), name='stats'),
    path('dashboard/', staff_member_required(views.LeagueDashboardView.as_view()),
        name='league_dashboard'),
    path('player/', views.UserDashboardView.as_view(), name='user_dashboard'),
    path('player/<str:username>/', views.PlayerProfileView.as_view(),
        name='player_profile'),
    path('team/<int:team_number>/', views.TeamProfileView.as_view(), name='team_profile'),
    path('tv/', cache_control(no_cache=True)(views.TvView.as_view()), name='tv'),
    path('tv/json/', cache_control(no_cache=True)(views.TvJsonView.as_view()), name='tv_json'),
    path('document/<slug:document_tag>/', views.DocumentView.as_view(), name='document'),
    path('request/<slug:req_type>/', views.ModRequestView.as_view(), name='modrequest'),
    path('request/<slug:req_type>/success/', views.ModRequestSuccessView.as_view(),
        name='modrequest_success'),
    path('nominate/', views.NominateView.as_view(), name='nominate'),
    path('nominate/delete/<int:nomination_id>/', views.DeleteNominationView.as_view(),
        name='delete_nomination'),
    path('schedule/edit/', views.ScheduleView.as_view(), name='edit_schedule'),
    path('availability/edit/', views.AvailabilityView.as_view(), name='edit_availability'),
    path('board/<int:board_number>/scores/', views.BoardScoresView.as_view(),
        name='board_scores'),
    path('alternates/', views.AlternatesView.as_view(), name='alternates'),
    path('round/<int:round_number>/alternate/accept/', views.AlternateAcceptView.as_view(),
        name='alternate_accept'),
    path('round/<int:round_number>/alternate/decline/',
        views.AlternateDeclineView.as_view(), name='alternate_decline'),
    path('notifications/', views.NotificationsView.as_view(), name='notifications'),
]

league_urlpatterns = [
    path('', views.LeagueHomeView.as_view(), name='league_home'),
    path('', include(season_urlpatterns)),
    path('season/<slug:season_tag>/',
        include((season_urlpatterns, 'tournament'), 'by_season')),
    path('document/<slug:document_tag>/', views.DocumentView.as_view(), name='document'),
    path('contact/', views.ContactView.as_view(), name='contact'),
    path('contact_success/', views.ContactSuccessView.as_view(), name='contact_success'),
    path('about/', views.AboutView.as_view(), name='about'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('login/<slug:secret_token>/', views.LoginView.as_view(), name='login_with_token'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
]

api_urlpatterns = [
    path('find_pairing/', api.find_pairing, name='find_pairing'),
    path('update_pairing/', api.update_pairing, name='update_pairing'),
    path('get_roster/', api.get_roster, name='get_roster'),
    path('assign_alternate/', api.assign_alternate, name='assign_alternate'),
    path('set_availability/', api.set_availability, name='set_availability'),
    path('get_league_moderators/', api.get_league_moderators, name='get_league_moderators'),
    path('league_document/', api.league_document, name='league_document'),
    path('link_slack/', api.link_slack, name='link_slack'),
    path('get_slack_user_map/', api.get_slack_user_map, name='get_slack_user_map'),
    path('game_warning/', api.game_warning, name='game_warning'),
    path('player_contact/', api.player_contact, name='player_contact'),
    path('get_season_games/', api.get_season_games, name='get_season_games'),
    path('celery_status/', api.celery_status, name='celery_status'),
]

app_urlpatterns = [
    path('event/', android_app.slack_event, name='slack_event'),
    path('register/', android_app.fcm_register, name='fcm_register'),
    path('unregister/', android_app.fcm_unregister, name='fcm_unregister'),
]

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('toggle/darkmode/', views.ToggleDarkModeView.as_view(), name='toggle_darkmode'),
    path('player/<slug:username>/calendar.ics', views.ICalPlayerView.as_view(),
        name='player_icalendar'),
    path('api/', include((api_urlpatterns, 'tournament'), 'api')),
    path('app/', include((app_urlpatterns, 'tournament'), 'app')),
    path('auth/slack/', auth.SlackAuth.as_view(), name='slack_auth'),
    path('auth/lichess/', views.OAuthCallbackView.as_view(), name='lichess_auth'),
    path('auth/lichess/login_failed/', views.LoginFailedView.as_view(), name='login_failed'),
    path('comments/', include('django_comments.urls')),
    path('ckeditor/', include('ckeditor_uploader.urls')),
    path('<slug:league_tag>/', include((league_urlpatterns, 'tournament'), 'by_league')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
