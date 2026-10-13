"""
Chart generation for PDF reports using matplotlib.
Returns base64-encoded PNG data URIs for embedding in HTML.
"""
import base64
from io import BytesIO

import matplotlib
matplotlib.use('Agg')  # headless
import matplotlib.pyplot as plt
import numpy as np


# Brand colors
NAVY      = '#0B1220'
AMBER     = '#F59E0B'
RED       = '#DC2626'
ORANGE    = '#EA580C'
YELLOW    = '#D97706'
GREEN     = '#059669'
BLUE      = '#0284C7'
GREY      = '#6B7280'
LIGHTGREY = '#E5E7EB'


def _fig_to_base64(fig):
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=110, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return 'data:image/png;base64,' + base64.b64encode(buf.read()).decode('ascii')


def _severity_color(score):
    if score >= 20: return RED
    if score >= 12: return ORANGE
    if score >= 6:  return YELLOW
    return GREEN


# ============================================================
# RISK HEATMAP
# ============================================================

def risk_heatmap_png(risks_by_cell):
    """
    risks_by_cell: dict {(likelihood, impact): count}
    Renders 5x5 grid, top-left = (L1, I5), bottom-right = (L5, I1).
    """
    fig, ax = plt.subplots(figsize=(6.5, 5))

    for impact in range(5, 0, -1):
        for likelihood in range(1, 6):
            score = likelihood * impact
            color = _severity_color(score)
            count = risks_by_cell.get((likelihood, impact), 0)
            row = 5 - impact  # 0 = top
            col = likelihood - 1

            # Fade color based on count
            alpha = 0.15 + (min(count, 5) / 5) * 0.6

            rect = plt.Rectangle((col, row), 1, 1,
                                  facecolor=color, edgecolor='white',
                                  linewidth=2, alpha=alpha)
            ax.add_patch(rect)

            if count:
                ax.text(col + 0.5, row + 0.55, str(count),
                        ha='center', va='center',
                        fontsize=18, fontweight='bold', color=NAVY)
                ax.text(col + 0.5, row + 0.25, f'score {score}',
                        ha='center', va='center',
                        fontsize=7, color=NAVY, alpha=0.7)
            else:
                ax.text(col + 0.5, row + 0.5, str(score),
                        ha='center', va='center',
                        fontsize=8, color=NAVY, alpha=0.35)

    # Axis labels
    for i in range(1, 6):
        ax.text(i - 0.5, 5.15, f'L{i}', ha='center', va='bottom',
                fontsize=10, fontweight='bold', color=NAVY)
        ax.text(-0.15, 5 - i + 0.5, f'I{i}', ha='right', va='center',
                fontsize=10, fontweight='bold', color=NAVY)

    ax.text(2.5, 5.55, 'Likelihood →', ha='center', fontsize=9,
            style='italic', color=GREY)
    ax.text(-0.65, 2.5, 'Impact →', ha='center', va='center',
            rotation=90, fontsize=9, style='italic', color=GREY)

    ax.set_xlim(-0.8, 5.2)
    ax.set_ylim(-0.2, 5.9)
    ax.axis('off')
    fig.tight_layout()
    return _fig_to_base64(fig)


# ============================================================
# RISK CATEGORY DOUGHNUT
# ============================================================

def risk_category_png(labels, values):
    if not labels:
        return None
    fig, ax = plt.subplots(figsize=(5, 4))
    palette = [BLUE, RED, YELLOW, GREEN, '#6F42C1', ORANGE, '#20C997', GREY]
    colors = [palette[i % len(palette)] for i in range(len(labels))]
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct='%1.0f%%',
        colors=colors, startangle=90,
        wedgeprops=dict(width=0.42, edgecolor='white', linewidth=2),
        textprops=dict(fontsize=8, color=NAVY),
    )
    for t in autotexts:
        t.set_color('white')
        t.set_fontsize(8)
        t.set_fontweight('bold')
    ax.axis('equal')
    fig.tight_layout()
    return _fig_to_base64(fig)


# ============================================================
# RISK TREND LINE
# ============================================================

def risk_trend_png(labels, inherent, residual):
    fig, ax = plt.subplots(figsize=(7, 3))
    x = range(len(labels))

    ax.plot(x, inherent, marker='o', color=RED, linewidth=2,
            label='Avg inherent', markersize=6)
    ax.plot(x, residual, marker='o', color=GREEN, linewidth=2,
            label='Avg residual', markersize=6)

    ax.fill_between(x, inherent, residual, color=AMBER, alpha=0.12)

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel('Score (1–25)', fontsize=9, color=GREY)
    ax.set_ylim(bottom=0, top=25)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.legend(fontsize=9, frameon=False, loc='best')

    for spine in ['top', 'right']:
        ax.spines[spine].set_visible(False)
    for spine in ['left', 'bottom']:
        ax.spines[spine].set_color(LIGHTGREY)

    fig.tight_layout()
    return _fig_to_base64(fig)


# ============================================================
# CONTROL EFFECTIVENESS BAR
# ============================================================

def control_effectiveness_png(counts):
    """
    counts: dict like {'effective': N, 'partially_effective': N, 'ineffective': N, 'not_tested': N}
    """
    labels = ['Effective', 'Partially\nEffective', 'Ineffective', 'Not Tested']
    values = [
        counts.get('effective', 0),
        counts.get('partially_effective', 0),
        counts.get('ineffective', 0),
        counts.get('not_tested', 0),
    ]
    colors = [GREEN, YELLOW, RED, GREY]

    fig, ax = plt.subplots(figsize=(6, 3))
    bars = ax.bar(labels, values, color=colors, width=0.6)

    for bar, v in zip(bars, values):
        if v:
            ax.text(bar.get_x() + bar.get_width() / 2, v + 0.1, str(v),
                    ha='center', va='bottom', fontsize=10,
                    fontweight='bold', color=NAVY)

    ax.set_ylabel('Controls', fontsize=9, color=GREY)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    for spine in ['top', 'right']:
        ax.spines[spine].set_visible(False)
    for spine in ['left', 'bottom']:
        ax.spines[spine].set_color(LIGHTGREY)

    fig.tight_layout()
    return _fig_to_base64(fig)


# ============================================================
# VULNERABILITY SEVERITY DOUGHNUT
# ============================================================

def vuln_severity_png(counts):
    """counts: dict {'critical': N, 'high': N, 'medium': N, 'low': N}"""
    labels = []
    values = []
    colors = []
    color_map = {'critical': RED, 'high': ORANGE, 'medium': YELLOW, 'low': GREEN}
    for sev in ['critical', 'high', 'medium', 'low']:
        c = counts.get(sev, 0)
        if c:
            labels.append(sev.title())
            values.append(c)
            colors.append(color_map[sev])

    if not values:
        return None

    fig, ax = plt.subplots(figsize=(4.5, 3.5))
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct='%1.0f%%',
        colors=colors, startangle=90,
        wedgeprops=dict(width=0.42, edgecolor='white', linewidth=2),
        textprops=dict(fontsize=9, color=NAVY),
    )
    for t in autotexts:
        t.set_color('white')
        t.set_fontweight('bold')
    ax.axis('equal')
    fig.tight_layout()
    return _fig_to_base64(fig)


# ============================================================
# SLA COMPLIANCE DONUT
# ============================================================

def sla_donut_png(within, overdue, closed):
    total = within + overdue + closed
    if not total:
        return None

    fig, ax = plt.subplots(figsize=(4.5, 3.5))
    labels = []
    values = []
    colors = []
    if within:
        labels.append('Within SLA'); values.append(within); colors.append(GREEN)
    if overdue:
        labels.append('Overdue'); values.append(overdue); colors.append(RED)
    if closed:
        labels.append('Closed'); values.append(closed); colors.append(GREY)

    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct='%1.0f%%',
        colors=colors, startangle=90,
        wedgeprops=dict(width=0.42, edgecolor='white', linewidth=2),
        textprops=dict(fontsize=9, color=NAVY),
    )
    for t in autotexts:
        t.set_color('white')
        t.set_fontweight('bold')
    ax.axis('equal')
    fig.tight_layout()
    return _fig_to_base64(fig)


# ============================================================
# FRAMEWORK COVERAGE HORIZONTAL BAR
# ============================================================

def framework_coverage_png(names, percents):
    if not names:
        return None
    fig, ax = plt.subplots(figsize=(7, max(2, len(names) * 0.35)))
    y = np.arange(len(names))
    colors = [GREEN if p >= 75 else YELLOW if p >= 40 else RED for p in percents]

    ax.barh(y, percents, color=colors, height=0.55)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel('Coverage %', fontsize=9, color=GREY)
    ax.grid(axis='x', alpha=0.3, linestyle='--')

    for yi, p in zip(y, percents):
        ax.text(p + 1.5, yi, f'{p}%', va='center', fontsize=8,
                fontweight='bold', color=NAVY)

    for spine in ['top', 'right']:
        ax.spines[spine].set_visible(False)
    for spine in ['left', 'bottom']:
        ax.spines[spine].set_color(LIGHTGREY)

    fig.tight_layout()
    return _fig_to_base64(fig)
