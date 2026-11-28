"""Template filters that respect the user's date/time format preference."""
from django import template

register = template.Library()


def _get_format(context, key, default):
    """Extract a preference from the template context, with fallbacks."""
    try:
        # The context processors add user_date_format / user_time_format
        return context.get(key) or default
    except Exception:
        return default


@register.simple_tag(takes_context=True)
def userdate(context, value):
    """Format a date using the user's preferred date format."""
    if not value:
        return '—'
    fmt = _get_format(context, 'user_date_format', 'Y-m-d')
    try:
        # Django's date filter handles both date/datetime objects and format tokens
        from django.template.defaultfilters import date as date_filter
        return date_filter(value, fmt)
    except Exception:
        return str(value)


@register.simple_tag(takes_context=True)
def userdatetime(context, value):
    """Format a datetime using the user's preferred date + time format."""
    if not value:
        return '—'
    d_fmt = _get_format(context, 'user_date_format', 'Y-m-d')
    t_fmt = _get_format(context, 'user_time_format', 'H:i')
    fmt = f'{d_fmt} {t_fmt}'
    try:
        from django.template.defaultfilters import date as date_filter
        return date_filter(value, fmt)
    except Exception:
        return str(value)


@register.simple_tag(takes_context=True)
def usertime(context, value):
    """Format just the time using the user's preferred time format."""
    if not value:
        return '—'
    fmt = _get_format(context, 'user_time_format', 'H:i')
    try:
        from django.template.defaultfilters import date as date_filter
        return date_filter(value, fmt)
    except Exception:
        return str(value)


@register.simple_tag(takes_context=True)
def querystring(context, **kwargs):
    """Rebuild the current query string with the given overrides.

    Used by pagination so page links keep active filters. Pass a value of
    ``None``/``''`` to drop a key.
    """
    request = context.get('request')
    if request is None:
        from django.http import QueryDict
        return QueryDict('', mutable=True).urlencode()
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value in (None, ''):
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()
