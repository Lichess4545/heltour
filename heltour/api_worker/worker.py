import json
import queue
import threading
import time
from datetime import timedelta

import websocket
from django.utils import timezone


def _run_worker():
    while True:
        _, fn, args = _work_queue.get()
        try:
            fn(*args)
        # FIXME: unlogged naked exception == footgun!
        except Exception:
            pass


_work_queue = queue.PriorityQueue()
_worker_thread = threading.Thread(target=_run_worker)
_worker_thread.daemon = True
_worker_thread.start()


def queue_work(priority, fn, *args):
    _work_queue.put((-priority, fn, args))


def _run_socket():
    global _websocket
    last_start = None
    fallback = 2
    while True:
        try:
            if last_start is not None and last_start > timezone.now() - timedelta(
                seconds=10
            ):
                time.sleep(fallback)
                fallback = fallback * 2
                if fallback > 120:
                    fallback = 120
            else:
                fallback = 2
            last_start = timezone.now()

            _websocket = websocket.create_connection(
                "wss://socket.lichess.org/api/socket"
            )
            with _games_lock:
                for game_id in list(_games.keys()):
                    _start_watching(game_id)
            while True:
                msg = json.loads(_websocket.recv())
                if msg["t"] == "fen":
                    with _games_lock:
                        game_id = msg["d"]["id"]
                        if game_id in _games:
                            _games[game_id] = msg
        # FIXME: unlogged naked exception == footgun
        except Exception:
            continue


def _start_watching(game_id):
    try:
        _websocket.send(json.dumps({"t": "startWatching", "d": game_id}))
    # FIXME: unlogged naked exception == footgun
    except Exception:
        pass


_websocket = None
_games = {}
_games_lock = threading.Lock()
_socket_thread = threading.Thread(target=_run_socket)
_socket_thread.daemon = True
_socket_thread.start()


def watch_games(game_ids):
    with _games_lock:
        game_id_set = set(game_ids)
        for game_id in set(_games.keys()) - game_id_set:
            del _games[game_id]
        for game_id in game_id_set - set(_games.keys()):
            _games[game_id] = None
            _start_watching(game_id)
        return [_games[game_id] for game_id in game_ids]


def add_watch(game_id):
    with _games_lock:
        if game_id not in _games:
            _games[game_id] = None
            _start_watching(game_id)
