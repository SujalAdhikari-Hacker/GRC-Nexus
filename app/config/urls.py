from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView


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

    path('favicon.ico', RedirectView.as_view(url='/static/img/favicon.svg', permanent=True)),
]

# Auth URLs live here rather than in core.urls so the login/logout names stay
# the Django defaults used by LOGIN_URL / LOGOUT_REDIRECT_URL.
urlpatterns += [
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', PostOnlyLogoutView.as_view(), name='logout'),
    path('password-change/', auth_views.PasswordChangeView.as_view(
        template_name='registration/password_change_form.html',
        success_url='/settings/',
    ), name='password_change'),
]

# WhiteNoise serves STATIC_ROOT in production. Uploaded media is served only
# through core.media.download_media, which enforces login + department scoping;
# the raw /media/ mount is intentionally removed so it cannot be bypassed.

