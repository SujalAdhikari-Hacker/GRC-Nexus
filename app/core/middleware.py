"""Apply the logged-in user's timezone preference per request."""
from django.utils import timezone


class UserTimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                pref = getattr(request.user, 'preference', None)
                if pref and pref.timezone:
                    timezone.activate(pref.timezone)
            except Exception:
                pass
        return self.get_response(request)
