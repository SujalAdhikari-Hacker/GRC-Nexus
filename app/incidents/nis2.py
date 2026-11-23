"""NIS2 Article 23 incident clock — pure functions, no database.

Art. 23(4) requires a significantly affected entity to file three reports
after becoming aware of an incident:

* early warning            within 24 hours
* incident notification    within 72 hours
* final report             within one month (30 days)

Every phase is anchored on ``detected_at`` — the moment the organisation
became aware. The final report is legally tied to the submission of the
notification, not to detection; anchoring it on detection can only make the
deadline earlier, never later, so the clock stays conservative if a report was
filed late.

States per phase: ``pending`` → ``due_soon`` (two hours out) → ``breached``,
or ``submitted`` once a timestamp is recorded. Keeping this module free of
Django imports lets the formula be tested and reproduced by hand.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

EARLY_WARNING_HOURS = 24
NOTIFICATION_HOURS = 72
FINAL_REPORT_DAYS = 30
PRE_DEADLINE_ALERT_HOURS = 2

PHASE_CHOICES = [
    ('early_warning', 'Early warning (24 h)'),
    ('notification', 'Incident notification (72 h)'),
    ('final_report', 'Final report (30 days)'),
]
PHASE_LABELS = dict(PHASE_CHOICES)
PHASE_ORDER = tuple(phase for phase, _label in PHASE_CHOICES)

# Model field that records when each report was filed.
SUBMISSION_FIELDS = {
    'early_warning': 'nis2_early_warning_submitted_at',
    'notification': 'nis2_notification_submitted_at',
    'final_report': 'nis2_final_report_submitted_at',
}

STATE_LABELS = {
    'pending': 'Pending',
    'due_soon': 'Due soon',
    'breached': 'Breached',
    'submitted': 'Submitted',
}
STATE_BADGES = {
    'pending': 'bg-secondary',
    'due_soon': 'bg-warning text-dark',
    'breached': 'bg-danger',
    'submitted': 'bg-success',
}


@dataclass(frozen=True)
class PhaseClock:
    """One Article 23 obligation and where it stands right now."""

    phase: str
    label: str
    due_at: datetime
    submitted_at: datetime | None
    state: str
    remaining: timedelta

    @property
    def state_label(self):
        return STATE_LABELS[self.state]

    @property
    def badge_css(self):
        return STATE_BADGES[self.state]

    @property
    def submitted_late(self):
        """True when the report landed after the legal deadline."""
        return self.submitted_at is not None and self.submitted_at > self.due_at

    @property
    def remaining_label(self):
        """Human duration until (or past) the deadline."""
        seconds = int(self.remaining.total_seconds())
        minutes = abs(seconds) // 60
        days, rest = divmod(minutes, 1440)
        hours, mins = divmod(rest, 60)
        if days:
            text = f'{days}d {hours}h'
        elif hours:
            text = f'{hours}h {mins}m'
        else:
            text = f'{mins}m'
        return f'{text} overdue' if seconds < 0 else f'{text} left'


def compute_deadlines(detected_at):
    """Map each phase to its absolute deadline."""
    return {
        'early_warning': detected_at + timedelta(hours=EARLY_WARNING_HOURS),
        'notification': detected_at + timedelta(hours=NOTIFICATION_HOURS),
        'final_report': detected_at + timedelta(days=FINAL_REPORT_DAYS),
    }


def phase_clocks(detected_at, submitted=None, now=None):
    """Return the three phase clocks, in statutory order.

    ``submitted`` maps phase -> datetime for the reports already filed.
    """
    now = now or datetime.now(detected_at.tzinfo)
    submitted = submitted or {}
    deadlines = compute_deadlines(detected_at)
    clocks = []
    for phase in PHASE_ORDER:
        due_at = deadlines[phase]
        submitted_at = submitted.get(phase)
        remaining = due_at - now
        if submitted_at is not None:
            state = 'submitted'
        elif remaining <= timedelta(0):
            state = 'breached'
        elif remaining <= timedelta(hours=PRE_DEADLINE_ALERT_HOURS):
            state = 'due_soon'
        else:
            state = 'pending'
        clocks.append(PhaseClock(
            phase=phase,
            label=PHASE_LABELS[phase],
            due_at=due_at,
            submitted_at=submitted_at,
            state=state,
            remaining=remaining,
        ))
    return clocks


def derive_phase(submitted=None):
    """The next report the organisation owes, or ``complete``."""
    submitted = submitted or {}
    for phase in PHASE_ORDER:
        if submitted.get(phase) is None:
            return phase
    return 'complete'
