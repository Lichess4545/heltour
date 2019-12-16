from heltour import settings

if not settings.TESTING:
    from cacheops.query import cached_as as _cacheops_cached_as, \
        cached_view_as as _cacheops_cached_view_as, \
        install_cacheops

    # TODO: This should be run automatically by django. I have no idea why it isn't.
    install_cacheops()


def cached_as(*ca_args, **ca_kwargs):
    def wrap(func):
        if settings.DEBUG or settings.TESTING:
            # Disable caching during testing
            return func

        wrapped_func = _cacheops_cached_as(*ca_args, **ca_kwargs)(func)

        def wrapped(*args, **kwargs):
            return wrapped_func(*args, **kwargs)

        return wrapped

    return wrap
