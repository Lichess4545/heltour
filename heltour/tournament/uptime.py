import logging
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache

_start_time = timezone.now()
logger = logging.getLogger(__name__)


class UptimeIndicator(object):
    def __init__(self, name, ping_interval):
        self.name = name
        self.ping_interval = ping_interval

    @property
    def is_up(self):
        value = cache.get(self.name)
        logger.info(f"Checking uptime indicator '{self.name}': {value}")
        return value is True

    @is_up.setter
    def is_up(self, value):
        logger.info(f"Setting uptime indicator '{self.name}' to {value}")
        cache.set(self.name, value, self.ping_interval.total_seconds())

    @property
    def is_down(self):
        logger.info(
            f"Checking uptime indicator '{self.name}' is down: time: {timezone.now()}, start: {_start_time}, interval: {self.ping_interval}"
        )
        return timezone.now() - self.ping_interval > _start_time and not self.is_up


celery = UptimeIndicator("celery_up", ping_interval=timedelta(minutes=15))
