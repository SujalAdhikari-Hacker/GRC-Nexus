from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from core.login_view import ThrottledLoginView


class PostOnlyLogoutView(auth_views.LogoutView):
    """Sign-out must be a POST (CSRF-protected), never a GET.

    Django 4.2 still answers GET /logout/, which lets a third-party page log
    the user out with a bare <img>/link. Restrict it to POST.
    """

    http_method_names = ['post', 'options']


urlpatterns = [
    path('admin/', admin.site.urls),

    # Auth
    path('', include('core.urls')),
    path('assets/', include('assets.urls')),
    path('risks/', include('risks.urls')),
    path('controls/', include('controls.urls')),
    path('policies/', include('policies.urls')),
    path('vendors/', include('vendors.urls')),
    path('frameworks/', include('frameworks.urls')),
    path('vulnerabilities/', include('vulnerabilities.urls')),
    path('kris/', include('kris.urls')),
    path('audits/', include('audits.urls')),
    path('threat-intel/', include('threatintel.urls')),
    path('tickets/', include('tickets.urls')),
    path('incidents/', include('incidents.urls')),

    path('favicon.ico', RedirectView.as_view(url='/static/img/favicon.svg', permanent=True)),
]

# Auth URLs live here rather than in core.urls so the login/logout names stay
# the Django defaults used by LOGIN_URL / LOGOUT_REDIRECT_URL.
urlpatterns += [
    path('login/', ThrottledLoginView.as_view(
        template_name='registration/login.html'), name='login'),
    path('logout/', PostOnlyLogoutView.as_view(), name='logout'),
    path('password-change/', auth_views.PasswordChangeView.as_view(
        template_name='registration/password_change_form.html',
        success_url='/settings/',
    ), name='password_change'),
]

# WhiteNoise serves STATIC_ROOT in production. Uploaded media is served only
# through core.media.download_media, which enforces login + department scoping;
# the raw /media/ mount is intentionally removed so it cannot be bypassed.


# ---------------------------------------------------------------------------
# Custom error handlers
#
# With DEBUG=False Django already renders 404.html / 403.html / 500.html
# automatically. These handlers add the attempted path (and any permission
# message) to the context so the pages can explain *why* access was denied —
# most denials in GRC Nexus are cross-department access attempts.
# ---------------------------------------------------------------------------

def handler403(request, exception=None):
    from django.shortcuts import render
    return render(request, '403.html', {
        'message': str(exception) if exception else '',
        'request_path': request.path,
    }, status=403)


def handler404(request, exception=None):
    from django.shortcuts import render
    return render(request, '404.html', {'request_path': request.path}, status=404)


def handler500(request):
    from django.shortcuts import render
    return render(request, '500.html', status=500)

