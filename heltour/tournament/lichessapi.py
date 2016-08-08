import requests
import time

def api_json_request(url):
    time.sleep(2)
    r = requests.get(url)
    if r.status_code == 200:
        return r.json()
    elif r.status_code == 429:
        time.sleep(60)
    else:
        time.sleep(2)
    # Retry once
    return requests.get(url).json()

def get_user_classical_rating_and_games_played(lichess_username):
    url = "https://en.lichess.org/api/user/%s" % lichess_username
    result = api_json_request(url)
    classical = result["perfs"]["classical"]
    return (classical["rating"], classical["games"])
