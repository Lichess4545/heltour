#!/usr/bin/env python
# cache-test marker v2: warm-run reuse test (safe to remove)
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("HELTOUR_ENV", "prod")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "heltour.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
