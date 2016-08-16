from cacheops.query import cached_as, \
                           cached_view_as as _cacheops_cached_view_as, \
                           install_cacheops

# TODO: This should be run automatically by django. I have no idea why it isn't.
install_cacheops()

# Modify the cacheops.cached_view_as decorator to take a "vary_request" lambda
# that allows us to serve different copies of the view to different types of users
# e.g. logged-in vs anonymous users
def cached_view_as(*cva_args, **cva_kwargs):

    vary_request = cva_kwargs.pop('vary_request', None)

    def wrap(func):
        def proxy(request, vary_value, *proxy_args, **proxy_kwargs):
            return func(request, *proxy_args, **proxy_kwargs)

        wrapped_proxy = _cacheops_cached_view_as(*cva_args, **cva_kwargs)(proxy)

        def wrapped(request, *args, **kwargs):
            if vary_request is None:
                return wrapped_proxy(request, None, *args, **kwargs)
            else:
                return wrapped_proxy(request, vary_request(request), *args, **kwargs)

        return wrapped

    return wrap
