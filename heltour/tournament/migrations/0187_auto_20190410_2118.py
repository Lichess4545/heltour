# -*- coding: utf-8 -*-
# Generated by Django 1.11.18 on 2019-04-10 21:18
from __future__ import unicode_literals

from django.db import migrations

def old_stuff(season, TPP):
    pass

def new_stuff(season, TPP):

    for pairing in TPP.objects.all():
        if (pairing.team_pairing.white_team.teammember_set.filter(player=pairing.white).exists() or
            pairing.team_pairing.black_team.teammember_set.filter(player=pairing.black).exists()):
            pairing.white_player_team = pairing.team_pairing.white_team
            pairing.black_player_team = pairing.team_pairing.black_team
        elif (pairing.team_pairing.white_team.teammember_set.filter(player=pairing.black).exists() or
              pairing.team_pairing.black_team.teammember_set.filter(player=pairing.white).exists()):
            pairing.black_player_team = pairing.team_pairing.white_team
            pairing.white_player_team = pairing.team_pairing.black_team

        pairing.save()

def old_stuff(season, TPP):
    for pairing in TPP.objects.all():
        if pairing.board_number % 2 == 0:
            pairing.black_player_team = pairing.team_pairing.white_team
            pairing.white_player_team = pairing.team_pairing.black_team
        else:
            pairing.white_player_team = pairing.team_pairing.white_team
            pairing.black_player_team = pairing.team_pairing.black_team

        pairing.save()

def add_team_player_pairing_player_team(apps, schema_editor):
    TeamPlayerPairing = apps.get_model('tournament', 'TeamPlayerPairing')
    Season = apps.get_model('tournament', 'Season')
    for season in Season.objects.all():
        if season.board_set.exists():
            new_stuff(season, TeamPlayerPairing)
        else:
            old_stuff(season, TeamPlayerPairing)

class Migration(migrations.Migration):

    dependencies = [
        ('tournament', '0186_auto_20190410_1959'),
    ]

    operations = [
            migrations.RunPython(add_team_player_pairing_player_team),
    ]
