import urllib.parse

from django.http import HttpResponseBadRequest


class RejectNullMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if "\0" in urllib.parse.unquote(request.get_full_path()):
            return HttpResponseBadRequest()
        return self.get_response(request)
