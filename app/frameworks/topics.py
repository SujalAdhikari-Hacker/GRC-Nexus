"""A small topic taxonomy shared by cross-framework matching.

Every framework describes the same underlying controls in different words
("Access control", "Identities and credentials are managed", "Establish and
maintain an inventory of accounts"). Each requirement is assigned one primary
topic so equivalents can be found without a hand-maintained crosswalk.

Order matters: the first topic that matches wins, so specific subjects come
before general ones (a "backup encryption" requirement is about backups, not
cryptography in general).
"""
import re

TOPIC_RULES = (
    ('malware', re.compile(r'malware|anti-?virus|anti-?malware')),
    ('backup', re.compile(r'backup|restore')),
    ('crypto', re.compile(r'encrypt|cryptograph|key management|digital signature')),
    ('incident', re.compile(r'incident|breach|cyber attack|response plan|emergency')),
    ('vulnerability', re.compile(r'vulnerabilit|penetration test|security scan')),
    ('patch', re.compile(r'patch|software update|security update')),
    ('physical', re.compile(r'physical|premises|data cent|facility|site security|building')),
    ('network', re.compile(r'network|firewall|segmentation|perimeter|remote access|wireless')),
    ('supplier', re.compile(r'supplier|vendor|third.party|outsourc|service provider|supply chain')),
    ('access', re.compile(
        r'access control|access right|identity|authentication|privileged|password'
        r'|credential|least privilege|account'
    )),
    ('logging', re.compile(
        r'\blog\b|logging|audit trail|monitor|detect|siem|anomal|security event'
    )),
    ('awareness', re.compile(r'training|awareness|competenc|skill')),
    ('hr', re.compile(r'personnel|employee|screening|disciplinary|termination|human resource')),
    ('privacy', re.compile(r'privacy|personal data|personal information|data protection|confidential')),
    ('continuity', re.compile(r'business continuity|disaster|recovery plan|business impact|resilien')),
    ('asset', re.compile(r'asset|inventory|classification|labell|removable media|\bmedia\b')),
    ('audit', re.compile(r'audit|assurance|independent review|compliance review')),
    ('governance', re.compile(
        r'policy|governance|roles and responsibilities|board|strategy'
        r'|risk management|objective|responsibilit'
    )),
)


def primary_topic(text):
    """Return the first topic whose pattern matches ``text``, else ``None``."""
    text = (text or '').lower()
    for topic, pattern in TOPIC_RULES:
        if pattern.search(text):
            return topic
    return None
