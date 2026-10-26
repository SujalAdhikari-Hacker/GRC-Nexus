#!/usr/bin/env python3
"""Fail if a high-confidence secret is present in a git-tracked file.

Usage:
    python scripts/scan_secrets.py            # scan git-tracked files
    python scripts/scan_secrets.py --all      # scan the working tree too

The scanner is intentionally conservative: it looks for credential formats
(AWS, GitHub, Slack, Google, Stripe, private keys) and for ``key = "value"``
assignments whose value looks random rather than like a placeholder. Findings
print a masked value so the scanner itself never writes a secret to a log.

Exit status is 1 when anything is found, so it can run in CI.
"""
from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# High-confidence token formats. These do not need an entropy check.
TOKEN_PATTERNS = [
    ('private key', re.compile(
        r'-----BEGIN (?:RSA |OPENSSH |EC |DSA |PGP )?PRIVATE KEY-----'
    )),
    ('AWS access key', re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
    ('GitHub token', re.compile(r'\bgh[pousr]_[A-Za-z0-9]{36,}\b')),
    ('Slack token', re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{10,}\b')),
    ('Google API key', re.compile(r'\bAIza[0-9A-Za-z_-]{35}\b')),
    ('Stripe live key', re.compile(r'\bsk_live_[0-9A-Za-z]{24,}\b')),
    ('SendGrid key', re.compile(r'\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b')),
]

# key = "value" / key: 'value'. Only values with enough entropy are reported.
ASSIGNMENT_RE = re.compile(
    r'''(?ix)
    \b(
        api[_-]?key | apikey | auth[_-]?key | access[_-]?token |
        client[_-]?secret | secret[_-]?key | password | passwd | token
    )\b
    \s*[:=]\s*
    (['"])(?P<value>[^'"\s]{8,200})\2
    '''
)

PLACEHOLDER_MARKERS = (
    'change-me', 'change_me', 'changeme', 'your-', 'your_', 'example',
    'placeholder', 'dummy', 'sample', 'redacted', 'replace', 'todo',
    'not-set', 'not_set', 'secret-key', 'test-only', 'test_only',
    'localhost', 'postgres', 'password123', 'hunter2', 'xxxx',
)

SKIP_SUFFIXES = {
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.pdf',
    '.zip', '.gz', '.tgz', '.7z', '.woff', '.woff2', '.ttf', '.otf',
    '.pyc', '.pyo', '.so', '.dll', '.exe', '.drawio', '.docx', '.xlsx',
}


def entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    return -sum(
        (count / len(value)) * math.log2(count / len(value))
        for count in counts.values()
    )


def looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
        return True
    # A single repeated character or a very short value is not a secret.
    return len(set(value)) <= 3


def mask(value: str) -> str:
    if len(value) <= 8:
        return '*' * len(value)
    return f'{value[:3]}...{value[-2:]}'


def tracked_files(scan_all: bool):
    if scan_all:
        for path in ROOT.rglob('*'):
            if path.is_file():
                yield path
        return

    result = subprocess.run(
        ['git', 'ls-files', '-z'],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    for raw in result.stdout.split(b'\x00'):
        if raw:
            yield ROOT / raw.decode('utf-8', 'surrogateescape')


def is_test_path(path: Path) -> bool:
    name = path.name.lower()
    return (
        name.startswith('test_')
        or name.endswith('_test.py')
        or name == 'tests.py'
        or 'tests' in path.parts
    )


def scan_file(path: Path):
    if path.suffix.lower() in SKIP_SUFFIXES:
        return
    try:
        data = path.read_bytes()
    except OSError:
        return
    if b'\x00' in data[:8192]:
        return
    text = data.decode('utf-8', 'replace')

    for label, pattern in TOKEN_PATTERNS:
        for match in pattern.finditer(text):
            yield label, match.group(0)

    # Test fixtures intentionally contain realistic-looking passwords. Still
    # scan them for token formats above, but not for generic assignments.
    if is_test_path(path):
        return

    for match in ASSIGNMENT_RE.finditer(text):
        value = match.group('value')
        if looks_like_placeholder(value) or entropy(value) < 3.5:
            continue
        yield match.group(1), value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--all', action='store_true',
        help='scan the working tree instead of git-tracked files',
    )
    args = parser.parse_args()

    findings = []
    for path in tracked_files(args.all):
        for label, value in scan_file(path):
            findings.append((path, label, value))

    if findings:
        print(f'{len(findings)} potential secret(s) found:', file=sys.stderr)
        for path, label, value in findings:
            try:
                relative = path.relative_to(ROOT)
            except ValueError:
                relative = path
            print(f'  {relative}: {label}: {mask(value)}', file=sys.stderr)
        return 1

    scope = 'working tree' if args.all else 'git-tracked files'
    print(f'No high-confidence secrets found in {scope}.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
