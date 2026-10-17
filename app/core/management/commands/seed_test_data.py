"""
Seed clearly-labeled TEST data across every app for end-to-end verification.

Every record is prefixed with [TEST] or TEST- so it's instantly recognizable.
Re-runnable. Pass --clean to wipe all prior TEST data first.

Usage:
    docker compose exec web python manage.py seed_test_data
    docker compose exec web python manage.py seed_test_data --clean
    docker compose exec web python manage.py seed_test_data --clean --fresh   # wipe + re-seed
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import Department, User
from assets.models import Asset, AssetCategory
from vendors.models import Vendor, VendorAssessment
from policies.models import Policy, PolicyCategory
from controls.models import Control, ControlFrameworkMapping
from frameworks.models import Framework, FrameworkControl, ComplianceAssessment, ComplianceAssessmentItem
from risks.models import Risk, RiskCategory, RiskAppetite, RiskTreatment, RiskException
from kris.models import KRI, KRIReading
from vulnerabilities.models import Vulnerability, Finding as VulnFinding
from audits.models import Audit, AuditFinding, ActionItem, EvidenceItem, EvidenceScore, ControlTest
from threatintel.models import Tactic, Technique, ThreatActor, IOC


TEST = '[TEST]'
CODE = 'TEST-'


class Command(BaseCommand):
    help = 'Seed clearly-labeled TEST data across every app.'

    def add_arguments(self, parser):
        parser.add_argument('--clean', action='store_true',
                            help='Delete all prior TEST data before seeding.')

    @transaction.atomic
    def handle(self, *args, **options):
        if options['clean']:
            self._clean()
            self.stdout.write(self.style.WARNING('Cleaned prior TEST data.\n'))
        self._seed()
        self.stdout.write(self.style.SUCCESS('\n✔ Test data seed complete.\n'))
        self._summary()

    # ------------------------------------------------------------------
    # CLEAN
    # ------------------------------------------------------------------
    def _clean(self):
        # Delete children first to avoid protected-FK clashes
        ActionItem.objects.filter(finding__title__startswith=TEST).delete()
        AuditFinding.objects.filter(title__startswith=TEST).delete()
        EvidenceScore.objects.filter(evidence__title__startswith=TEST).delete()
        EvidenceItem.objects.filter(title__startswith=TEST).delete()
        ControlTest.objects.filter(control__code__startswith=CODE).delete()
        Audit.objects.filter(name__startswith=TEST).delete()

        VulnFinding.objects.filter(vulnerability__title__startswith=TEST).delete()
        Vulnerability.objects.filter(title__startswith=TEST).delete()

        ComplianceAssessmentItem.objects.filter(assessment__name__startswith=TEST).delete()
        ComplianceAssessment.objects.filter(name__startswith=TEST).delete()

        ControlFrameworkMapping.objects.filter(control__code__startswith=CODE).delete()

        RiskException.objects.filter(title__startswith=TEST).delete()
        RiskTreatment.objects.filter(risk__title__startswith=TEST).delete()
        Risk.objects.filter(title__startswith=TEST).delete()
        RiskAppetite.objects.filter(description__startswith=TEST).delete()

        KRIReading.objects.filter(kri__name__startswith=TEST).delete()
        KRI.objects.filter(name__startswith=TEST).delete()

        Control.objects.filter(code__startswith=CODE).delete()
        Policy.objects.filter(code__startswith=CODE).delete()

        VendorAssessment.objects.filter(vendor__name__startswith=TEST).delete()
        Vendor.objects.filter(name__startswith=TEST).delete()
        Asset.objects.filter(name__startswith=TEST).delete()

        IOC.objects.filter(value__startswith=CODE).delete()
        ThreatActor.objects.filter(name__startswith=TEST).delete()

    # ------------------------------------------------------------------
    # SEED
    # ------------------------------------------------------------------
    def _seed(self):
        today = timezone.now().date()
        now = timezone.now()

        # ---- Reference data (reuse existing) ----
        departments = {d.name: d for d in Department.objects.all()}
        it = departments.get('IT')
        fin = departments.get('Finance')
        hr = departments.get('HR')
        ops = departments.get('Operations')
        comp = departments.get('Compliance')

        # ---- Test user (locked accountability) ----
        test_user, created = User.objects.get_or_create(
            username='test_user',
            defaults={
                'email': 'test_user@grcnexus.local',
                'first_name': 'Test',
                'last_name': 'User',
                'department': it,
                'is_staff': False,
            }
        )
        if created:
            test_user.set_password('demo1234')
            test_user.save()
            self.stdout.write(f'  Test user: test_user / demo1234')

        # ---- Asset categories ----
        cats = {c.name: c for c in AssetCategory.objects.all()}

        # ---- Frameworks (reuse) ----
        iso = Framework.objects.filter(name='ISO/IEC 27001').first()
        nist = Framework.objects.filter(name='NIST CSF').first()
        cis = Framework.objects.filter(name='CIS Controls').first()
        soc2 = Framework.objects.filter(name='SOC 2').first()
        pci = Framework.objects.filter(name='PCI DSS').first()
        gdpr = Framework.objects.filter(name='GDPR').first()

        # ---- Risk & Policy categories ----
        risk_cats, _ = zip(*[RiskCategory.objects.get_or_create(name=n) for n in [
            'Information Security', 'Operational', 'Compliance', 'Physical', 'Supply Chain'
        ]])
        risk_cats = {c.name: c for c in risk_cats}

        pol_cats, _ = zip(*[PolicyCategory.objects.get_or_create(name=n) for n in [
            'Information Security', 'Access Control', 'Data Protection', 'Incident Response'
        ]])
        pol_cats = {c.name: c for c in pol_cats}

        # ==========================================================
        # VENDORS (6 — all tiers, all services, all statuses)
        # ==========================================================
        vendors_data = [
            ('[TEST] Vendor — Tier 1 · Cloud Hosting',    'cloud',    1, 4, 'active',      'it',   45),
            ('[TEST] Vendor — Tier 1 · Payment Processor','payments', 1, 4, 'active',      'fin',  72),
            ('[TEST] Vendor — Tier 2 · SaaS CRM',         'saas',     2, 3, 'active',      'ops',  38),
            ('[TEST] Vendor — Tier 2 · Audit Firm',       'audit',    2, 2, 'under_review','comp', 22),
            ('[TEST] Vendor — Tier 3 · Office Cleaning',  'logistics',3, 1, 'active',      'ops',   8),
            ('[TEST] Vendor — Tier 3 · Legal Counsel',    'legal',    3, 2, 'suspended',   'comp', 15),
        ]
        vendors = {}
        for name, svc, tier, sens, status, dept_key, score in vendors_data:
            v, _ = Vendor.objects.get_or_create(
                name=name,
                defaults={
                    'service': svc,
                    'tier': tier,
                    'data_sensitivity': sens,
                    'status': status,
                    'owner_dept': departments[dept_key.upper() if dept_key != 'it' else 'IT'] if dept_key != 'it' else it,
                    'contact_name': 'Test Contact',
                    'contact_email': f'test-{svc}@vendor.local',
                    'contract_start': today - timedelta(days=180),
                    'contract_renewal_date': today + timedelta(days=185),
                    'description': f'{TEST} Vendor for platform testing — covers tier {tier}, {svc}.',
                }
            )
            vendors[name] = v
            # One assessment per vendor
            per = score // 5
            VendorAssessment.objects.get_or_create(
                vendor=v,
                assessment_date=today - timedelta(days=30),
                defaults={
                    'vendor_tier': tier,
                    'security_score': per,
                    'compliance_score': per,
                    'financial_score': per,
                    'reputation_score': per,
                    'operational_score': per,
                    'status': 'completed',
                    'key_findings': f'{TEST} baseline assessment for {name}.',
                    'recommended_mitigation': f'{TEST} schedule next review in 12 months.',
                }
            )

        # ==========================================================
        # ASSETS (14 — full matrix: type × hosting × classification)
        # ==========================================================
        assets_data = [
            # (name, type, hosting, cloud, region, os, classification, env, crit, C,I,A, dept)
            ('[TEST] Asset — Hardware · On-Prem · Restricted',   'hardware', 'on_prem',    'on_prem','','linux',  'restricted',   'production',  4, 3,3,3, 'it'),
            ('[TEST] Asset — Hardware · On-Prem · Confidential', 'hardware', 'on_prem',    'on_prem','','windows','confidential', 'production',  3, 3,2,3, 'it'),
            ('[TEST] Asset — Software · Cloud · Confidential',   'software', 'cloud',      'aws',   'us-east-1','linux','confidential','production',4, 3,3,3, 'ops'),
            ('[TEST] Asset — Software · SaaS · Internal',        'software', 'cloud',      'azure', 'eu-west-1','linux','internal',    'production',3, 2,3,2, 'fin'),
            ('[TEST] Asset — Software · Cloud · Public',         'software', 'cloud',      'gcp',   'us-central1','linux','public',   'development',1,1,1,1, 'it'),
            ('[TEST] Asset — Data · Cloud · Restricted',         'data',     'cloud',      'aws',   'us-east-1','other','restricted',  'production', 4, 3,3,3, 'fin'),
            ('[TEST] Asset — Data · On-Prem · Confidential',     'data',     'on_prem',    'on_prem','','other',   'confidential','staging',   3, 3,2,2, 'hr'),
            ('[TEST] Asset — Network · On-Prem · Internal',      'network',  'on_prem',    'on_prem','','network', 'internal',   'production',  4, 2,3,3, 'it'),
            ('[TEST] Asset — Network · Hybrid · Confidential',   'network',  'hybrid',     'aws',   'us-west-2','network','confidential','production',3,3,3,3, 'it'),
            ('[TEST] Asset — Service · Cloud · Internal',        'service',  'cloud',      'digitalocean','nyc3','linux','internal',   'production', 2, 2,2,3, 'ops'),
            ('[TEST] Asset — Service · Third-Party · Public',    'service',  'third_party','other','','other',    'public',    'production',  2, 1,2,2, 'comp'),
            ('[TEST] Asset — People · On-Prem · Internal',       'people',   'on_prem',    'on_prem','','other',   'internal',  'production',  2, 1,2,3, 'hr'),
            ('[TEST] Asset — Facility · On-Prem · Internal',     'facility', 'on_prem',    'on_prem','','other',   'internal',  'production',  3, 2,2,3, 'ops'),
            ('[TEST] Asset — Hardware · Cloud · Test Env',       'hardware', 'cloud',      'linode','us-east','linux', 'internal',  'test',        1, 1,1,1, 'it'),
        ]
        assets = {}
        for name, atyp, host, cloud, region, osf, classif, env, crit, c,i,a, dept_key in assets_data:
            a, _ = Asset.objects.get_or_create(
                name=name,
                defaults={
                    'asset_type': atyp,
                    'hosting': host,
                    'cloud_provider': cloud,
                    'cloud_region': region,
                    'os_family': osf,
                    'classification': classif,
                    'environment': env,
                    'criticality': crit,
                    'confidentiality': c,
                    'integrity': i,
                    'availability': a,
                    'owner_dept': departments[dept_key.upper() if dept_key != 'it' else 'IT'],
                    'description': f'{TEST} test asset — {atyp} / {host} / {classif}.',
                }
            )
            assets[name] = a

        # Link two assets to vendors
        vendors['[TEST] Vendor — Tier 1 · Cloud Hosting'].provides_assets.set([
            assets['[TEST] Asset — Software · Cloud · Confidential'],
            assets['[TEST] Asset — Data · Cloud · Restricted'],
        ])
        vendors['[TEST] Vendor — Tier 1 · Payment Processor'].provides_assets.set([
            assets['[TEST] Asset — Software · SaaS · Internal'],
        ])

        # ==========================================================
        # POLICIES (8 — every status)
        # ==========================================================
        policies_data = [
            (f'{CODE}POL-001', 'Draft policy',    'Information Security', 'it',   'draft'),
            (f'{CODE}POL-002', 'Review policy',   'Access Control',       'it',   'review'),
            (f'{CODE}POL-003', 'Approved policy', 'Data Protection',      'comp', 'approved'),
            (f'{CODE}POL-004', 'Approved policy 2','Incident Response',   'it',   'approved'),
            (f'{CODE}POL-005', 'Retired policy',  'Information Security', 'it',   'retired'),
            (f'{CODE}POL-006', 'HR policy',       'Data Protection',      'hr',   'approved'),
            (f'{CODE}POL-007', 'Finance policy',  'Access Control',       'fin',  'review'),
            (f'{CODE}POL-008', 'Ops policy',      'Incident Response',    'ops',  'draft'),
        ]
        for code, title, cat_name, dept_key, status in policies_data:
            Policy.objects.get_or_create(
                code=code,
                defaults={
                    'title': f'{TEST} Policy — {title} ({status})',
                    'category': pol_cats[cat_name],
                    'owner_dept': departments[dept_key.upper() if dept_key != 'it' else 'IT'],
                    'status': status,
                    'version': '1.0',
                    'description': f'{TEST} description for {title}.',
                    'content': f'{TEST} body text for {title}. This is dummy content for platform testing.',
                }
            )

        # ==========================================================
        # CONTROLS (16 — every lifecycle stage + every effectiveness)
        # ==========================================================
        controls_data = [
            # (code, name, type, category, lifecycle, effectiveness, status, freq)
            (f'{CODE}CTL-001', 'Proposed control',    'preventive','access_control',   'proposed',    'not_tested',          'planned',        'continuous'),
            (f'{CODE}CTL-002', 'Designed control',    'preventive','access_control',   'designed',    'not_tested',          'planned',        'daily'),
            (f'{CODE}CTL-003', 'Implemented ctl',     'detective', 'logging',          'implemented', 'not_tested',          'implemented',    'weekly'),
            (f'{CODE}CTL-004', 'Operational ctl',     'preventive','network_security', 'operational', 'partially_effective', 'implemented',    'monthly'),
            (f'{CODE}CTL-005', 'Monitored ctl',       'detective', 'logging',          'monitored',   'effective',           'implemented',    'continuous'),
            (f'{CODE}CTL-006', 'Reviewed ctl',        'corrective','incident_mgmt',    'reviewed',    'effective',           'implemented',    'quarterly'),
            (f'{CODE}CTL-007', 'Retired ctl',         'preventive','technical',        'retired',     'ineffective',         'not_implemented','annual'),
            (f'{CODE}CTL-008', 'Infective ctl',       'preventive','data_protection',  'operational', 'ineffective',         'implemented',    'weekly'),
            (f'{CODE}CTL-009', 'Partial ctl',         'detective', 'asset_management', 'operational', 'partially_effective', 'implemented',    'daily'),
            (f'{CODE}CTL-010', 'Untested ctl',        'corrective','risk_management',  'implemented', 'not_tested',          'implemented',    'monthly'),
            (f'{CODE}CTL-011', 'Effective ctl',       'preventive','network_security', 'monitored',   'effective',           'implemented',    'continuous'),
            (f'{CODE}CTL-012', 'Compliance ctl',      'detective', 'compliance',       'operational', 'effective',           'implemented',    'quarterly'),
            (f'{CODE}CTL-013', 'Physical ctl',        'preventive','physical',         'operational', 'effective',           'implemented',    'daily'),
            (f'{CODE}CTL-014', 'Admin ctl',           'administrative','administrative','operational', 'partially_effective', 'implemented',   'monthly'),
            (f'{CODE}CTL-015', 'Incident ctl',        'corrective','incident_mgmt',    'monitored',   'effective',           'implemented',    'continuous'),
            (f'{CODE}CTL-016', 'Backup ctl',          'corrective','technical',        'monitored',   'effective',           'implemented',    'daily'),
        ]
        controls = {}
        for code, name, ctype, cat, lifecycle, eff_rating, status, freq in controls_data:
            c, _ = Control.objects.get_or_create(
                code=code,
                defaults={
                    'name': f'{TEST} {name}',
                    'description': f'{TEST} control — lifecycle={lifecycle}, effectiveness={eff_rating}.',
                    'control_type': ctype,
                    'category': cat,
                    'status': status,
                    'lifecycle_status': lifecycle,
                    'effectiveness_rating': eff_rating,
                    'frequency': freq,
                    'owner_dept': it,
                    'reference': f'{TEST} internal ref for {code}',
                }
            )
            controls[code] = c

        # Map some controls to framework controls
        if iso:
            for code, fc_code in [
                (f'{CODE}CTL-005', 'A.8.16'),
                (f'{CODE}CTL-006', 'A.5.23'),
                (f'{CODE}CTL-011', 'A.5.15'),
                (f'{CODE}CTL-013', 'A.8.7'),
                (f'{CODE}CTL-016', 'A.8.13'),
            ]:
                fc = FrameworkControl.objects.filter(framework=iso, code=fc_code).first()
                if fc:
                    ControlFrameworkMapping.objects.get_or_create(
                        control=controls[code],
                        framework_control=fc,
                        defaults={'relationship': 'equal'},
                    )

        # ==========================================================
        # RISK CATEGORIES handled above; RISK APPETITE
        # ==========================================================
        RiskAppetite.objects.get_or_create(
            department=it,
            category=None,
            defaults={
                'appetite_level': 'moderate',
                'appetite_statement': f'{TEST} moderate appetite for IT dept.',
                'max_inherent_score': 15,
                'max_residual_score': 8,
                'risk_capacity': 20,
                'description': f'{TEST} IT department appetite baseline.',
            }
        )

        # ==========================================================
        # RISKS (16 — every status, every strategy, breach/no-breach)
        # ==========================================================
        risks_data = [
            # (title, category, dept, L, I, strategy, status, ctrl_codes)
            ('Breach risk (mitigate, treating)',       'Information Security', 'IT',         4, 5, 'mitigate', 'treating',   [f'{CODE}CTL-005', f'{CODE}CTL-011']),
            ('Breach risk (accept, monitored)',        'Information Security', 'IT',         5, 5, 'accept',   'monitored',  []),
            ('No-breach risk (mitigate, treating)',    'Operational',          'Operations', 2, 3, 'mitigate', 'treating',   [f'{CODE}CTL-005']),
            ('No-breach risk (transfer, treating)',    'Supply Chain',         'Compliance', 3, 4, 'transfer', 'treating',   [f'{CODE}CTL-011']),
            ('No-breach risk (avoid, assessed)',       'Compliance',           'Compliance', 2, 3, 'avoid',    'assessed',   []),
            ('Identified risk — needs assessment',     'Information Security', 'IT',         3, 4, 'mitigate', 'identified', []),
            ('Identified risk — needs assessment 2',   'Physical',             'Operations', 2, 2, 'mitigate', 'identified', []),
            ('Closed risk — historical',               'Operational',          'IT',         2, 2, 'mitigate', 'closed',     []),
            ('Critical L×I = 25',                      'Information Security', 'IT',         5, 5, 'mitigate', 'treating',   [f'{CODE}CTL-005', f'{CODE}CTL-011', f'{CODE}CTL-016']),
            ('Low L×I = 1',                            'Operational',          'HR',         1, 1, 'accept',   'monitored',  []),
            ('Mid L×I = 12',                           'Information Security', 'Finance',    3, 4, 'mitigate', 'treating',   [f'{CODE}CTL-005']),
            ('High L×I = 20',                          'Information Security', 'IT',         4, 5, 'mitigate', 'treating',   [f'{CODE}CTL-005', f'{CODE}CTL-016']),
            ('HR risk',                                'Compliance',           'HR',         2, 4, 'mitigate', 'assessed',   []),
            ('Compliance risk',                        'Compliance',           'Compliance', 3, 3, 'mitigate', 'treating',   []),
            ('Operations risk',                        'Operational',          'Operations', 3, 5, 'transfer', 'treating',   [f'{CODE}CTL-011']),
            ('Another IT risk',                        'Information Security', 'IT',         2, 4, 'mitigate', 'monitored',  [f'{CODE}CTL-005']),
        ]
        risks = {}
        for title, cat_name, dept_key, lik, imp, strat, status, ctrl_codes in risks_data:
            dept = departments[dept_key.upper() if dept_key not in ('IT','HR') else dept_key]
            r, _ = Risk.objects.get_or_create(
                title=f'{TEST} {title}',
                owner_dept=dept,
                defaults={
                    'category': risk_cats[cat_name],
                    'likelihood': lik,
                    'impact': imp,
                    'treatment_strategy': strat,
                    'status': status,
                    'identified_date': today - timedelta(days=45),
                    'description': f'{TEST} description — {title}.',
                }
            )
            risks[title] = r
            if ctrl_codes:
                r.controls.set([controls[c] for c in ctrl_codes if c in controls])

        # Link risks to assets (some)
        assets_by_key = list(assets.values())
        for i, r in enumerate(risks.values()):
            if i % 2 == 0 and i < len(assets_by_key):
                r.assets.add(assets_by_key[i])

        # ==========================================================
        # RISK TREATMENTS (6)
        # ==========================================================
        for title in ['Breach risk (mitigate, treating)', 'Critical L×I = 25', 'Mid L×I = 12']:
            r = risks.get(title)
            if r:
                RiskTreatment.objects.get_or_create(
                    risk=r,
                    action_plan=f'{TEST} treatment plan for {title}',
                    defaults={
                        'strategy': 'mitigate',
                        'status': 'in_progress',
                        'due_date': today + timedelta(days=60),
                        'notes': f'{TEST} notes.',
                    }
                )

        # ==========================================================
        # RISK EXCEPTIONS (3 — pending, active, expired)
        # ==========================================================
        RiskException.objects.get_or_create(
            title=f'{TEST} Exception — Pending approval',
            defaults={
                'risk': risks['Breach risk (accept, monitored)'],
                'justification': f'{TEST} waiting for board approval to accept this risk.',
                'status': 'pending',
                'expiry_date': today + timedelta(days=180),
            }
        )
        RiskException.objects.get_or_create(
            title=f'{TEST} Exception — Active',
            defaults={
                'risk': risks['No-breach risk (avoid, assessed)'],
                'justification': f'{TEST} approved exception for testing.',
                'status': 'active',
                'approver': test_user,
                'approval_date': today - timedelta(days=30),
                'expiry_date': today + timedelta(days=150),
            }
        )
        RiskException.objects.get_or_create(
            title=f'{TEST} Exception — Expired',
            defaults={
                'risk': risks['HR risk'],
                'justification': f'{TEST} expired exception for testing.',
                'status': 'active',
                'approver': test_user,
                'approval_date': today - timedelta(days=400),
                'expiry_date': today - timedelta(days=30),
            }
        )

        # ==========================================================
        # KRIs (9 — all RAG states × 2 directions + one perfect green)
        # ==========================================================
        kris_data = [
            ('Green — higher is worse',  'cybersecurity', 'higher_worse',  5,  10, 3),
            ('Amber — higher is worse',  'cybersecurity', 'higher_worse',  5,  10, 7),
            ('Red — higher is worse',    'cybersecurity', 'higher_worse',  5,  10, 15),
            ('Green — higher is better', 'technology',    'higher_better', 95, 85, 98),
            ('Amber — higher is better', 'technology',    'higher_better', 95, 85, 90),
            ('Red — higher is better',   'technology',    'higher_better', 95, 85, 80),
            ('Compliance KRI',           'compliance',    'higher_better', 90, 80, 92),
            ('People KRI',               'people',        'higher_better', 95, 85, 87),
            ('Financial KRI',            'financial',     'higher_worse',  5,  15, 3),
        ]
        for name, cat, direction, amber, red, current in kris_data:
            k, _ = KRI.objects.get_or_create(
                name=f'{TEST} KRI — {name}',
                defaults={
                    'category': cat,
                    'direction': direction,
                    'amber_threshold': amber,
                    'red_threshold': red,
                    'current_value': current,
                    'unit': '%' if 'better' in direction else 'count',
                    'frequency': 'monthly',
                    'owner_dept': it,
                }
            )
            # Seed 6 months of readings
            for i in range(6, 0, -1):
                KRIReading.objects.get_or_create(
                    kri=k,
                    reading_date=today - timedelta(days=i*30),
                    defaults={'value': current, 'notes': f'{TEST} historical reading.'}
                )

        # ==========================================================
        # VULNERABILITIES (5) + VULN FINDINGS (8)
        # ==========================================================
        vulns_data = [
            ('TEST-CVE-001', 'Critical vuln — KEV active',    10.0, 'critical', 0.95, True),
            ('TEST-CVE-002', 'High vuln — KEV active',        8.5,  'high',     0.80, True),
            ('TEST-CVE-003', 'Medium vuln',                   6.0,  'medium',   0.30, False),
            ('TEST-CVE-004', 'Low vuln',                      3.0,  'low',      0.10, False),
            ('TEST-CVE-005', 'Critical vuln — no KEV',        9.5,  'critical', 0.60, False),
        ]
        vulns = {}
        for cve, title, score, sev, epss, kev in vulns_data:
            v, _ = Vulnerability.objects.get_or_create(
                cve_id=cve,
                defaults={
                    'title': f'{TEST} {title}',
                    'description': f'{TEST} description for {cve}.',
                    'cvss_score': score,
                    'cvss_severity': sev,
                    'epss_score': epss,
                    'epss_percentile': min(epss + 0.03, 0.99),
                    'kev_status': kev,
                    'source': 'manual',
                    'published_date': today - timedelta(days=90),
                }
            )
            vulns[cve] = v

        findings_data = [
            ('TEST-CVE-001', '[TEST] Asset — Hardware · On-Prem · Restricted', 'open',  '443',  15),
            ('TEST-CVE-001', '[TEST] Asset — Software · Cloud · Confidential', 'in_progress', '443', 25),
            ('TEST-CVE-002', '[TEST] Asset — Data · Cloud · Restricted',       'remediated', '8443', 60),
            ('TEST-CVE-003', '[TEST] Asset — Service · Cloud · Internal',      'accepted',  '80',   30),
            ('TEST-CVE-004', '[TEST] Asset — Network · On-Prem · Internal',    'false_positive', '22', 20),
            ('TEST-CVE-005', '[TEST] Asset — Data · On-Prem · Confidential',   'open', '', 45),
            ('TEST-CVE-005', '[TEST] Asset — Software · SaaS · Internal',      'triaged', '443', 12),
            ('TEST-CVE-001', '[TEST] Asset — Network · Hybrid · Confidential', 'pending_verification', '443', 40),
        ]
        for cve, asset_name, status, port, days_ago in findings_data:
            a = assets.get(asset_name)
            if not a:
                continue
            VulnFinding.objects.get_or_create(
                vulnerability=vulns[cve],
                asset=a,
                port=port,
                defaults={
                    'owner_dept': a.owner_dept,
                    'status': status,
                    'discovered_date': today - timedelta(days=days_ago),
                    'evidence': f'{TEST} evidence for {cve} on {asset_name}.',
                    'solution': f'{TEST} recommended fix.',
                    'remediated_date': today - timedelta(days=5) if status == 'remediated' else None,
                }
            )

        # ==========================================================
        # AUDITS (3) + FINDINGS + ACTIONS + EVIDENCE + TESTS
        # ==========================================================
        audits_data = [
            ('[TEST] Audit — Internal (Complete)',       'internal',        'complete',    iso),
            ('[TEST] Audit — External (In Progress)',    'external',        'in_progress', soc2),
            ('[TEST] Audit — Self-Assessment (Planned)', 'self_assessment', 'planned',     gdpr),
        ]
        for name, atype, status, fw in audits_data:
            a, _ = Audit.objects.get_or_create(
                name=name,
                defaults={
                    'audit_type': atype,
                    'status': status,
                    'owner_dept': it,
                    'auditor_lead': test_user,
                    'start_date': today - timedelta(days=60),
                    'end_date': today - timedelta(days=5) if status == 'complete' else None,
                    'scope': f'{TEST} test scope for {atype} audit.',
                    'notes': f'{TEST} test notes.',
                }
            )
            if fw:
                a.frameworks.add(fw)

        # Findings (across audits, all severities)
        findings_setup = [
            ('[TEST] Audit — Internal (Complete)',    'Finding — Critical', 'critical', 'open',        'internal_audit',  f'{CODE}CTL-005'),
            ('[TEST] Audit — Internal (Complete)',    'Finding — High',     'high',     'in_progress', 'internal_audit',  f'{CODE}CTL-011'),
            ('[TEST] Audit — Internal (Complete)',    'Finding — Medium',   'medium',   'resolved',    'internal_audit',  None),
            ('[TEST] Audit — External (In Progress)', 'Finding — Low',      'low',      'accepted',    'external_audit',  None),
            ('[TEST] Audit — External (In Progress)', 'Finding — Critical 2','critical','open',        'external_audit',  f'{CODE}CTL-016'),
            ('[TEST] Audit — Self-Assessment (Planned)','Finding — Closed', 'medium',   'closed',      'self_assessment', None),
        ]
        audit_findings = []
        for audit_name, title, sev, status, source, ctrl_code in findings_setup:
            audit = Audit.objects.get(name=audit_name)
            f, _ = AuditFinding.objects.get_or_create(
                title=f'{TEST} {title}',
                defaults={
                    'audit': audit,
                    'severity': sev,
                    'status': status,
                    'source': source,
                    'owner_dept': it,
                    'owner_user': test_user,
                    'related_control': controls.get(ctrl_code) if ctrl_code else None,
                    'due_date': today + timedelta(days=60),
                    'description': f'{TEST} test finding description.',
                    'recommendation': f'{TEST} test recommendation.',
                }
            )
            audit_findings.append(f)

        # Actions (all priorities, all statuses)
        actions_data = [
            ('Action — Critical priority', 4, 'not_started', 0),
            ('Action — High priority',     3, 'in_progress', 50),
            ('Action — Medium priority',   2, 'blocked',     30),
            ('Action — Low priority',      1, 'completed',   100),
            ('Action — Cancelled',         2, 'cancelled',   0),
            ('Action — Overdue',           4, 'in_progress', 25),
        ]
        for title, priority, status, progress in actions_data:
            finding = audit_findings[priority % len(audit_findings)]
            due = today + timedelta(days=-5) if 'Overdue' in title else today + timedelta(days=30)
            ActionItem.objects.get_or_create(
                title=f'{TEST} {title}',
                finding=finding,
                defaults={
                    'priority': priority,
                    'status': status,
                    'owner_dept': it,
                    'owner_user': test_user,
                    'progress_percent': progress,
                    'due_date': due,
                    'description': f'{TEST} action item description.',
                }
            )

        # Evidence items
        evidence_setup = [
            ('Evidence — Screenshot', 'screenshot', f'{CODE}CTL-005'),
            ('Evidence — Document',   'document',   f'{CODE}CTL-011'),
            ('Evidence — Log',        'log',        f'{CODE}CTL-016'),
            ('Evidence — Report',     'report',     None),
        ]
        for title, etype, ctrl_code in evidence_setup:
            ev, _ = EvidenceItem.objects.get_or_create(
                title=f'{TEST} {title}',
                defaults={
                    'evidence_type': etype,
                    'owner_dept': it,
                    'owner_user': test_user,
                    'related_control': controls.get(ctrl_code) if ctrl_code else None,
                    'notes': f'{TEST} evidence notes.',
                }
            )
            # Add a score to half of them
            if 'Screenshot' in title or 'Log' in title:
                EvidenceScore.objects.get_or_create(
                    evidence=ev,
                    defaults={
                        'relevance': 18,
                        'completeness': 15,
                        'timeliness': 16,
                        'reliability': 17,
                        'sufficiency': 15,
                        'assessor': test_user,
                        'assessor_notes': f'{TEST} scorer notes.',
                    }
                )

        # Control tests
        tests_setup = [
            ('pass', 'Control test — Passed'),
            ('fail', 'Control test — Failed'),
            ('partial', 'Control test — Partial'),
            ('continuous_monitoring', 'Control test — Continuous'),
            ('self_audit', 'Control test — Self audit'),
        ]
        for result, label in tests_setup:
            ControlTest.objects.get_or_create(
                control=controls[f'{CODE}CTL-005'],
                test_date=today - timedelta(days=15),
                result=result,
                defaults={
                    'tester': test_user,
                    'owner_dept': it,
                    'procedure_notes': f'{TEST} {label} procedure notes.',
                }
            )

        # ==========================================================
        # COMPLIANCE ASSESSMENTS (2 — one per framework)
        # ==========================================================
        for fw, name, status in [
            (iso, '[TEST] ISO 27001 Readiness', 'in_progress'),
            (nist, '[TEST] NIST CSF Readiness', 'draft'),
        ]:
            if not fw:
                continue
            assess, created = ComplianceAssessment.objects.get_or_create(
                name=name,
                defaults={
                    'framework': fw,
                    'status': status,
                    'owner_dept': it,
                    'assessor': test_user,
                    'assessment_date': today - timedelta(days=20),
                    'description': f'{TEST} readiness assessment.',
                }
            )
            if created:
                # Auto-create items for each framework control, cycling through statuses
                statuses = ['compliant', 'partial', 'non_compliant', 'na', 'not_assessed']
                for idx, fc in enumerate(fw.controls.all()):
                    ComplianceAssessmentItem.objects.create(
                        assessment=assess,
                        framework_control=fc,
                        status=statuses[idx % len(statuses)],
                        owner_user=test_user,
                        created_by=test_user,
                        updated_by=test_user,
                    )

        # ==========================================================
        # THREAT INTEL (2 actors, 6 IOCs)
        # ==========================================================
        tactics = list(Tactic.objects.all()[:3])
        techniques = list(Technique.objects.all()[:5])

        for name, attack_id, aliases in [
            ('[TEST] Actor — APT Test Alpha', 'TEST-G0001', ['TestAlpha', 'TA-Test']),
            ('[TEST] Actor — APT Test Beta',  'TEST-G0002', ['TestBeta', 'TB-Test']),
        ]:
            actor, _ = ThreatActor.objects.get_or_create(
                attack_id=attack_id,
                defaults={
                    'name': name,
                    'aliases': aliases,
                    'description': f'{TEST} dummy threat actor for platform testing.',
                }
            )
            actor.techniques.set(techniques)

        iocs_data = [
            (f'{CODE}IOC-IP-001', 'ipv4', '198.51.100.42', 'ransomware'),
            (f'{CODE}IOC-DOM-001', 'domain', 'test-malware.example.com', 'c2'),
            (f'{CODE}IOC-HASH-001', 'sha256', 'deadbeef' * 8, 'malware'),
            (f'{CODE}IOC-URL-001', 'url', 'https://evil.example.com/payload', 'phishing'),
            (f'{CODE}IOC-IP-002', 'ipv4', '203.0.113.99', 'botnet'),
            (f'{CODE}IOC-DOM-002', 'domain', 'malicious-c2.example.org', 'apt'),
        ]
        for value, ioc_type, ioc_val, threat in iocs_data:
            IOC.objects.get_or_create(
                value=value,
                ioc_type=ioc_type,
                source='manual',
                defaults={
                    'threat_type': threat,
                    'confidence': 3,
                    'is_active': True,
                    'notes': f'{TEST} dummy IOC for platform testing.',
                }
            )

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------
    def _summary(self):
        rows = [
            ('Assets',                  Asset.objects.filter(name__startswith=TEST).count()),
            ('Vendors',                 Vendor.objects.filter(name__startswith=TEST).count()),
            ('Vendor assessments',      VendorAssessment.objects.filter(vendor__name__startswith=TEST).count()),
            ('Policies',                Policy.objects.filter(code__startswith=CODE).count()),
            ('Controls',                Control.objects.filter(code__startswith=CODE).count()),
            ('Risks',                   Risk.objects.filter(title__startswith=TEST).count()),
            ('Risk treatments',         RiskTreatment.objects.filter(risk__title__startswith=TEST).count()),
            ('Risk exceptions',         RiskException.objects.filter(title__startswith=TEST).count()),
            ('KRIs',                    KRI.objects.filter(name__startswith=TEST).count()),
            ('Vulnerabilities',         Vulnerability.objects.filter(title__startswith=TEST).count()),
            ('Vuln findings',           VulnFinding.objects.filter(vulnerability__title__startswith=TEST).count()),
            ('Audits',                  Audit.objects.filter(name__startswith=TEST).count()),
            ('Audit findings',          AuditFinding.objects.filter(title__startswith=TEST).count()),
            ('Actions',                 ActionItem.objects.filter(title__startswith=TEST).count()),
            ('Evidence items',          EvidenceItem.objects.filter(title__startswith=TEST).count()),
            ('Control tests',           ControlTest.objects.filter(control__code__startswith=CODE).count()),
            ('Compliance assessments',  ComplianceAssessment.objects.filter(name__startswith=TEST).count()),
            ('Threat actors',           ThreatActor.objects.filter(name__startswith=TEST).count()),
            ('IOCs',                    IOC.objects.filter(value__startswith=CODE).count()),
        ]
        self.stdout.write(self.style.MIGRATE_HEADING('TEST data summary:'))
        for label, count in rows:
            self.stdout.write(f'  {label:<26} {count}')