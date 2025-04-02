"""
Some team rating utils shared between create_teams and admin.py
"""


# -------------------------------------------------------------------------------
def squared_diff(a, b):
    return (a - b) ** 2


# -------------------------------------------------------------------------------
def variance(mean, xs):
    return sum([squared_diff(mean, x) for x in xs]) / len(xs)


# -------------------------------------------------------------------------------
def team_rating_variance(teams):
    means = [team.get_mean() for team in teams]
    league_mean = sum(means) / len(teams)
    return variance(league_mean, means)


# -------------------------------------------------------------------------------
def team_rating_range(teams):
    means = [team.get_mean() for team in teams]
    return max(means) - min(means)
