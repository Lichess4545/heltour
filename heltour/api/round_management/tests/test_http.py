"""HTTP-layer integration coverage lives in schemathesis (run via
``inv preflight`` against a live ``uvicorn heltour.api.main:app``), not
here.

Why not FastAPI's ``TestClient``: the route runs sync DB work via
``sync_to_async(thread_sensitive=True)``, which pins to asgiref's
single worker thread. That thread keeps a psycopg2 connection in its
thread-local store; after ``TestClient.__exit__`` the worker exits but
the connection isn't always closed in time, so postgres still sees the
session when Django tries to ``DROP DATABASE`` at suite teardown and
fails with ``ObjectInUse: is being accessed by other users``.

If we want a TestCase-friendly HTTP harness in the future, the
straightforward fix is a ``tearDownClass`` that runs
``pg_terminate_backend`` on every non-self session on the current
database before Django's runner destroys it. Skipped for now because
schemathesis already exercises every operation against a real running
server, which is closer to production than ``TestClient`` anyway.
"""
