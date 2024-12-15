from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

_start_time = timezone.now()


class UptimeIndicator(object):
    def __init__(self, name, ping_interval):
        self.name = name
        self.ping_interval = ping_interval

    @property
    def is_up(self):
        return cache.get(self.name) is True

    @is_up.setter
    def is_up(self, value):
        cache.set(self.name, value, self.ping_interval.total_seconds())

    @property
    def is_down(self):
        return timezone.now() - self.ping_interval > _start_time and not self.is_up


celery = UptimeIndicator("celery_up", ping_interval=timedelta(minutes=15))
