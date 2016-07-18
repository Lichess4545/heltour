from .models import *

def generate_pairings(round_, overwrite=False):
    existing_pairings = TeamPairing.objects.filter(round=round_)
    if existing_pairings.count() > 0:
        if overwrite:
            existing_pairings.delete()
        else:
            raise ValueError("The specified round already has pairings.")
    teams = Team.objects.filter(season=round_.season)
    previous_pairings = TeamPairing.objects.filter(round__season=round_.season, round__number__lt=round_.number)
    
    # Run the pairing algorithm
    pairing_system = PlaceholderTeamPairingSystem()
    team_pairings = pairing_system.create_team_pairings(round_, teams, previous_pairings)
    
    # Save the team pairings and create the individual pairings based on the team pairings
    board_count = round_.season.boards
    for team_pairing in team_pairings:
        team_pairing.save()
        for board_number in range(1, board_count + 1):
            white = TeamMember.objects.filter(team=team_pairing.white_team, board_number=board_number).first()
            black = TeamMember.objects.filter(team=team_pairing.black_team, board_number=board_number).first()
            if board_number % 2 == 0:
                white, black = black, white
            if white is not None and black is not None:
                Pairing.objects.create(team_pairing=team_pairing, white=white.player, black=black.player, board_number=board_number)
            else:
                # TODO: Consider how to handle missing players
                # Maybe allow null players in pairings? Or just raise an error
                pass
    
    
class PlaceholderTeamPairingSystem:
    def create_team_pairings(self, round_, teams, previous_pairings):
        # Pair teams in some arbitrary order for testing purposes
        team_pairings = []
        for i in range(int(len(teams) / 2)):
            white_team = teams[i * 2]
            black_team = teams[i * 2 + 1]
            team_pairings.append(TeamPairing(white_team=white_team, black_team=black_team, round=round_))
        return team_pairings