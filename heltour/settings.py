import os

if 'HELTOUR_ENV' in os.environ and os.environ['HELTOUR_ENV'] == 'STAGING':
    from staging_settings import *
elif 'HELTOUR_ENV' in os.environ and os.environ['HELTOUR_ENV'] == 'LIVE':
    from live_settings import *
else:
    raise Exception('HELTOUR_ENV environment variable not set (should be set in wsgi.py)')
