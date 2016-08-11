import Queue
import threading

def _run_worker():
    while True:
        _, fn, args = _work_queue.get()
        fn(*args)

_work_queue = Queue.PriorityQueue()
_worker_thread = threading.Thread(target=_run_worker)
_worker_thread.start()

def queue_work(priority, fn, *args):
    _work_queue.put((-priority, fn, args))
