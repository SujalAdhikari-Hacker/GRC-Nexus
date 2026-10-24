"""Enrolment, verification and recovery for TOTP multi-factor auth."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .mfa import (
    build_otpauth_uri, generate_backup_codes, generate_secret,
    normalize_backup_code, verify_totp,
)
from .models import UserMFA

MFA_FAIL_LIMIT = 5
MFA_FAIL_WINDOW = 5 * 60


def _safe_next(request):
    candidate = (
        request.POST.get('next')
        or request.GET.get('next')
        or request.session.get('mfa_next')
    )
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return reverse('core:dashboard')


def _consume_backup_code(mfa, code):
    normalized = normalize_backup_code(code)
    if not normalized:
        return False
    for index, hashed in enumerate(list(mfa.backup_codes or [])):
        if check_password(normalized, hashed):
            remaining = list(mfa.backup_codes)
            remaining.pop(index)
            mfa.backup_codes = remaining
            mfa.save(update_fields=['backup_codes'])
            return True
    return False


@login_required
@never_cache
def mfa_setup(request):
    mfa, _ = UserMFA.objects.get_or_create(
        user=request.user, defaults={'secret': generate_secret()}
    )
    if not mfa.secret:
        mfa.secret = generate_secret()
        mfa.save(update_fields=['secret'])

    if request.method == 'POST' and not mfa.enabled:
        code = request.POST.get('code', '')
        if verify_totp(mfa.secret, code):
            codes = generate_backup_codes()
            mfa.enabled = True
            mfa.confirmed_at = timezone.now()
            mfa.backup_codes = [
                make_password(normalize_backup_code(c)) for c in codes
            ]
            mfa.save()
            request.session['mfa_verified'] = True
            messages.success(
                request,
                'Two-factor authentication is now enabled. Store the backup '
                'codes somewhere safe — they will not be shown again.',
            )
            return render(
                request, 'core/mfa_backup_codes.html', {'codes': codes}
            )
        messages.error(
            request,
            'That verification code was not valid. Check your authenticator '
            'app and try again.',
        )

    uri = build_otpauth_uri(
        mfa.secret, request.user.get_username(), settings.MFA_ISSUER
    )
    return render(request, 'core/mfa_setup.html', {
        'mfa': mfa,
        'otpauth_uri': uri,
        'secret': mfa.secret,
    })


@login_required
@require_POST
@never_cache
def mfa_disable(request):
    mfa = getattr(request.user, 'mfa', None)
    if not mfa or not mfa.enabled:
        messages.info(request, 'Two-factor authentication is not enabled.')
        return redirect('core:settings')

    if not request.user.check_password(request.POST.get('password', '')):
        messages.error(
            request,
            'To disable two-factor authentication, enter your password and a '
            'current authenticator or backup code.',
        )
        return redirect('core:mfa_setup')

    code = request.POST.get('code', '')
    # Only consume a single-use backup code after the password check succeeds;
    # otherwise a wrong-password request could burn a valid recovery code.
    if not (verify_totp(mfa.secret, code) or _consume_backup_code(mfa, code)):
        messages.error(
            request,
            'To disable two-factor authentication, enter your password and a '
            'current authenticator or backup code.',
        )
        return redirect('core:mfa_setup')

    mfa.delete()
    request.session['mfa_verified'] = True
    messages.success(request, 'Two-factor authentication has been disabled.')
    return redirect('core:settings')


@login_required
@require_POST
@never_cache
def mfa_regenerate_backup_codes(request):
    mfa = getattr(request.user, 'mfa', None)
    if not mfa or not mfa.enabled:
        messages.info(request, 'Enable two-factor authentication first.')
        return redirect('core:mfa_setup')
    if not request.user.check_password(request.POST.get('password', '')):
        messages.error(request, 'Password is incorrect.')
        return redirect('core:mfa_setup')
    if not verify_totp(mfa.secret, request.POST.get('code', '')):
        messages.error(request, 'Enter a current authenticator code.')
        return redirect('core:mfa_setup')

    codes = generate_backup_codes()
    mfa.backup_codes = [make_password(normalize_backup_code(c)) for c in codes]
    mfa.save(update_fields=['backup_codes'])
    messages.success(request, 'New backup codes generated. Store them safely.')
    return render(request, 'core/mfa_backup_codes.html', {'codes': codes})


@login_required
@never_cache
def mfa_verify(request):
    mfa = getattr(request.user, 'mfa', None)
    if not mfa or not mfa.enabled:
        request.session['mfa_verified'] = True
        return redirect(_safe_next(request))
    if request.session.get('mfa_verified', False):
        return redirect(_safe_next(request))

    fail_key = f'grc:mfa-fails:{request.user.pk}'
    locked = cache.get(fail_key, 0) >= MFA_FAIL_LIMIT
    if request.method == 'POST':
        if locked:
            messages.error(
                request,
                'Too many incorrect codes. Wait a few minutes and try again.',
            )
            return render(
                request, 'core/mfa_verify.html',
                {'next': _safe_next(request), 'locked': True},
                status=429,
            )
        code = request.POST.get('code', '')
        if verify_totp(mfa.secret, code) or _consume_backup_code(mfa, code):
            cache.delete(fail_key)
            request.session['mfa_verified'] = True
            request.session.cycle_key()
            mfa.last_used_at = timezone.now()
            mfa.save(update_fields=['last_used_at'])
            return redirect(_safe_next(request))

        cache.add(fail_key, 0, MFA_FAIL_WINDOW)
        try:
            cache.incr(fail_key)
        except ValueError:
            cache.set(fail_key, 1, MFA_FAIL_WINDOW)
        if cache.get(fail_key, 0) >= MFA_FAIL_LIMIT:
            messages.error(
                request,
                'Too many incorrect codes. Wait a few minutes and try again.',
            )
            return render(
                request, 'core/mfa_verify.html',
                {'next': _safe_next(request), 'locked': True},
                status=429,
            )
        messages.error(
            request,
            'That code was not valid. Check the code and try again, or use a '
            'backup code.',
        )

    return render(request, 'core/mfa_verify.html', {
        'next': _safe_next(request),
        'locked': cache.get(fail_key, 0) >= MFA_FAIL_LIMIT,
    })
