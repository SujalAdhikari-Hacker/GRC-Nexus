"""Authorised media downloads.

Uploaded evidence and policy documents must never be served straight off
``/media/`` — that bypasses department scoping and lets anyone who can guess a
path read another team's evidence. Every download goes through
:func:`download_media`, which only serves a file when the requesting user can
see a record that references it.
"""
import os
import posixpath

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import FileResponse, Http404


def _safe_rel_path(path):
    """Normalise a media path or return None if it escapes MEDIA_ROOT."""
    if not path:
        return None
    path = path.replace('\\', '/')
    normalised = posixpath.normpath(path)
    if normalised.startswith(('/', '..')) or normalised in ('.', ''):
        return None
    return normalised


def _candidate_querysets(user):
    """Yield (queryset, file_field_name) pairs the user may read from."""
    from audits.models import EvidenceItem
    from controls.models import ControlEvidence
    from policies.models import Policy

    if user.is_superuser:
        yield Policy.objects.all(), 'document'
        yield ControlEvidence.objects.all(), 'file'
        yield EvidenceItem.objects.all(), 'attachment'
        return

    dept_id = getattr(user, 'department_id', None)
    if not dept_id:
        return

    from .mixins import scope_queryset

    yield scope_queryset(Policy.objects.all(), user), 'document'
    yield ControlEvidence.objects.filter(
        Q(control__owner_dept_id=dept_id) | Q(control__is_shared=True)
    ), 'file'
    yield scope_queryset(EvidenceItem.objects.all(), user), 'attachment'


def _serve(rel_path):
    full_path = os.path.join(settings.MEDIA_ROOT, rel_path)
    if not os.path.isfile(full_path):
        raise Http404('File not found')
    # Guard against symlink escapes.
    real_root = os.path.realpath(settings.MEDIA_ROOT)
    if not os.path.realpath(full_path).startswith(real_root):
        raise Http404('File not found')
    return FileResponse(
        open(full_path, 'rb'),
        as_attachment=False,
        filename=posixpath.basename(rel_path),
    )


@login_required
def download_media(request, path):
    """Serve an uploaded file only to users who can see a record referencing it."""
    rel_path = _safe_rel_path(path)
    if rel_path is None:
        raise Http404('Invalid path')
    for queryset, field in _candidate_querysets(request.user):
        if queryset.filter(**{field: rel_path}).exists():
            return _serve(rel_path)
    raise Http404('File not found')
