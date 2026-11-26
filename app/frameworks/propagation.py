"""Auto-link a control's mapping to the equivalent requirements in other frameworks.

Compliance is not per-framework in practice: a control that satisfies an ISO
27001 requirement almost always satisfies its counterpart in NIST, CIS, PCI
DSS or the NRB guidelines. When a control is mapped to a requirement, this
module finds the closest counterpart in each other framework (same topic,
highest title similarity) and records it as an ``intersects`` mapping, marked
as auto-linked so a reviewer can confirm or delete it.

Propagation is deliberately one hop and per-framework best match: it proposes
a shortlist, it does not claim that one control satisfies a whole framework.
"""
import re
from contextlib import contextmanager
from threading import local

from django.db import transaction

from .models import FrameworkControl
from .topics import primary_topic

MAX_PER_FRAMEWORK = 1
NOTE = (
    'Auto-linked from {framework} {code} by cross-framework topic match; '
    'review before relying on it.'
)
AUTO_PREFIX = 'Auto-linked from'

# Words too common in requirement titles to prove a match on their own.
_STOPWORDS = {
    'the', 'and', 'for', 'are', 'is', 'of', 'to', 'in', 'an', 'with', 'by',
    'on', 'or', 'be', 'that', 'their', 'its', 'as', 'at', 'from', 'all',
    'other', 'ensure', 'establish', 'maintain', 'implement', 'use', 'using',
    'defined', 'appropriate', 'information', 'security', 'system', 'systems',
    'data', 'management', 'process', 'processes', 'organization',
    'organizational', 'organisation', 'organisational', 'requirement',
    'requirements', 'measure', 'measures', 'including', 'include', 'when',
    'where', 'which', 'this', 'these', 'those', 'such', 'must', 'should',
    'may', 'can', 'not', 'has', 'have', 'was', 'were', 'been', 'into',
    'control', 'controls',
}

_state = local()


def _stem(word):
    return word[:-1] if word.endswith('s') and not word.endswith('ss') else word


def _words(text):
    return {
        _stem(word)
        for word in re.findall(r'[a-z]{3,}', (text or '').lower())
        if word not in _STOPWORDS
    }


@contextmanager
def paused():
    """Suppress propagation while seeding, so seeds stay deterministic."""
    previous = getattr(_state, 'paused', False)
    _state.paused = True
    try:
        yield
    finally:
        _state.paused = previous


def is_paused():
    return getattr(_state, 'paused', False)


def _text(requirement):
    return f'{requirement.title} {requirement.description}'.lower()


def equivalents(requirement, topic=None):
    """Closest requirement per other framework, same topic and shared wording."""
    topic = topic or primary_topic(_text(requirement))
    if topic is None:
        return []

    target_words = _words(requirement.title)
    if not target_words:
        return []

    best = {}
    candidates = (
        FrameworkControl.objects
        .exclude(framework_id=requirement.framework_id)
        .exclude(pk=requirement.pk)
        .select_related('framework')
    )
    for candidate in candidates:
        if primary_topic(_text(candidate)) != topic:
            continue
        shared = target_words & _words(candidate.title)
        if not shared:
            continue
        score = len(shared) / min(len(target_words), len(_words(candidate.title)))
        current = best.get(candidate.framework_id)
        if current is None or score > current[0]:
            best[candidate.framework_id] = (score, candidate)

    return [candidate for _score, candidate in best.values()]


def link(control, requirement, write=True):
    """Create the auto mappings for ``control`` -> ``requirement``'s counterparts.

    ``write=False`` only counts what would be proposed (used by ``--dry-run``).
    """
    from controls.models import ControlFrameworkMapping

    if is_paused():
        return 0

    targets = equivalents(requirement)
    if not targets:
        return 0

    existing = set(
        ControlFrameworkMapping.objects
        .filter(control=control, framework_control__in=targets)
        .values_list('framework_control_id', flat=True)
    )
    note = NOTE.format(
        framework=requirement.framework.name, code=requirement.code,
    )
    rows = [
        ControlFrameworkMapping(
            control=control, framework_control=target,
            relationship='intersects', notes=note,
        )
        for target in targets
        if target.pk not in existing
    ]
    if not rows:
        return 0
    if not write:
        return len(rows)
    with transaction.atomic():
        ControlFrameworkMapping.objects.bulk_create(rows, ignore_conflicts=True)
    return len(rows)


def propagate_mapping(mapping):
    return link(mapping.control, mapping.framework_control)


def propagate_control(control):
    total = 0
    for mapping in control.framework_mappings.select_related('framework_control__framework'):
        total += propagate_mapping(mapping)
    return total
