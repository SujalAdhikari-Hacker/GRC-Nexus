from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Department, User
from assets.models import Asset, AssetCategory
from frameworks.models import Framework, FrameworkControl
from django.utils import timezone
from datetime import timedelta
from vendors.models import Vendor, VendorAssessment
from policies.models import Policy, PolicyCategory
from controls.models import Control
from risks.models import Risk, RiskCategory, RiskAppetite, RiskTreatment
from risks.services import recalculate_risk


class Command(BaseCommand):
    help = 'Seed demo GRC data (departments, users, assets, frameworks)'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('Seeding demo data...'))

        # ---------- Departments ----------
        departments = {}
        for name in ['IT', 'Finance', 'HR', 'Operations', 'Compliance']:
            dept, created = Department.objects.get_or_create(name=name)
            departments[name] = dept
            self.stdout.write(f"  Department: {name} {'(created)' if created else '(exists)'}")

        # ---------- Users ----------
        users_data = [
            ('it_hod',       'IT',         True),
            ('it_user',      'IT',         False),
            ('fin_hod',      'Finance',    True),
            ('fin_user',     'Finance',    False),
            ('hr_hod',       'HR',         True),
            ('ops_hod',      'Operations', True),
            ('comp_hod',     'Compliance', True),
        ]
        for username, dept_name, is_hod in users_data:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': f'{username}@grc.local',
                    'department': departments[dept_name],
                    'is_hod': is_hod,
                }
            )
            if created:
                user.set_password('demo1234')
                user.save()
            self.stdout.write(f"  User: {username} {'(created)' if created else '(exists)'}")

        # ---------- Asset Categories ----------
        categories = {}
        for name in ['Hardware', 'Software', 'Data', 'People', 'Facility']:
            cat, created = AssetCategory.objects.get_or_create(name=name)
            categories[name] = cat

        # Map AssetCategory.name -> Asset.asset_type
        CATEGORY_TO_TYPE = {
            'Hardware': 'hardware',
            'Software': 'software',
            'Data':     'data',
            'People':   'people',
            'Facility': 'facility',
        }

        # ---------- Assets ----------
        assets_data = [
            # (name, category, dept, criticality, C, I, A, value)
            ('Web Application Server',    'Hardware', 'IT',         4, 3, 3, 3, 15000),
            ('Database Server',            'Hardware', 'IT',         4, 3, 3, 3, 25000),
            ('Employee Laptops (batch)',   'Hardware', 'IT',         2, 2, 2, 2, 40000),
            ('Firewall - Perimeter',       'Hardware', 'IT',         4, 3, 3, 3, 8000),
            ('Payroll System',             'Software', 'Finance',    4, 3, 3, 3, 30000),
            ('Accounting Software',        'Software', 'Finance',    3, 3, 3, 2, 12000),
            ('HR Management System',       'Software', 'HR',         3, 3, 3, 2, 18000),
            ('Email Service',              'Software', 'IT',         3, 3, 2, 3, 5000),
            ('Customer Database',          'Data',     'Operations', 4, 3, 3, 3, 100000),
            ('Employee Records',           'Data',     'HR',         4, 3, 3, 2, 60000),
            ('Financial Ledger',           'Data',     'Finance',    4, 3, 3, 3, 200000),
            ('Compliance Audit Reports',   'Data',     'Compliance', 3, 3, 3, 2, 10000),
            ('IT Support Staff',           'People',   'IT',         2, 1, 2, 3, 0),
            ('Finance Team',               'People',   'Finance',    3, 2, 3, 2, 0),
            ('Main Office Building',       'Facility', 'Operations', 3, 2, 2, 3, 500000),
        ]
        for name, cat_name, dept_name, crit, c, i, a, val in assets_data:
            asset, created = Asset.objects.get_or_create(
                name=name,
                defaults={
                    'category': categories[cat_name],
                    'asset_type': CATEGORY_TO_TYPE.get(cat_name, 'hardware'),
                    'owner_dept': departments[dept_name],
                    'criticality': crit,
                    'confidentiality': c,
                    'integrity': i,
                    'availability': a,
                    'value': val,
                }
            )
            if created:
                self.stdout.write(f"  Asset: {name}")

        # ---------- Frameworks ----------
        iso, _ = Framework.objects.get_or_create(
            name='ISO/IEC 27001', version='2022',
            defaults={'description': 'Information security management system standard'}
        )
        nist, _ = Framework.objects.get_or_create(
            name='NIST CSF', version='2.0',
            defaults={'description': 'NIST Cybersecurity Framework'}
        )
        cis, _ = Framework.objects.get_or_create(
            name='CIS Controls', version='v8',
            defaults={'description': 'Center for Internet Security Critical Security Controls'}
        )

        # ---------- Framework Controls ----------
        iso_controls = [
            ('A.5.1',  'Policies for information security'),
            ('A.5.15', 'Access control'),
            ('A.5.23', 'Information security for use of cloud services'),
            ('A.8.2',  'Privileged access rights'),
            ('A.8.7',  'Protection against malware'),
            ('A.8.8',  'Management of technical vulnerabilities'),
            ('A.8.13', 'Information backup'),
            ('A.8.16', 'Monitoring activities'),
        ]
        for code, title in iso_controls:
            FrameworkControl.objects.get_or_create(
                framework=iso, code=code,
                defaults={'title': title}
            )

        nist_controls = [
            ('ID.AM-01', 'Inventories of hardware managed by the organization are maintained'),
            ('ID.AM-02', 'Inventories of software, services, and systems managed by the organization are maintained'),
            ('PR.AA-01', 'Identities and credentials for authorized users, services, and hardware are managed'),
            ('PR.DS-01', 'The confidentiality, integrity, and availability of data-at-rest are protected'),
            ('DE.CM-01', 'Networks and network services are monitored to find potentially adverse events'),
            ('RS.MA-01', 'The incident response plan is executed in coordination with relevant third parties'),
        ]
        for code, title in nist_controls:
            FrameworkControl.objects.get_or_create(
                framework=nist, code=code,
                defaults={'title': title}
            )

        cis_controls = [
            ('1.1', 'Establish and Maintain Detailed Enterprise Asset Inventory'),
            ('2.1', 'Establish and Maintain a Software Inventory'),
            ('5.1', 'Establish and Maintain an Inventory of Accounts'),
            ('6.3', 'Require MFA for Externally-Exposed Applications'),
            ('7.1', 'Establish and Maintain a Vulnerability Management Process'),
            ('8.2', 'Collect Audit Logs'),
        ]
        for code, title in cis_controls:
            FrameworkControl.objects.get_or_create(
                framework=cis, code=code,
                defaults={'title': title}
            )
        # ---------- Vendors ----------
        vendors_data = [
            # (name, tier, sensitivity, dept, assets_it_provides, score)
            ('AWS',                   1, 4, 'IT',          ['Web Application Server', 'Database Server'], 25),
            ('Microsoft 365',         1, 4, 'IT',          ['Email Service'], 20),
            ('Payroll Processing Co', 2, 3, 'Finance',     ['Payroll System'], 45),
            ('Office Cleaning Ltd',   3, 1, 'Operations',  [], 15),
            ('External Audit Firm',   2, 3, 'Compliance',  ['Compliance Audit Reports'], 30),
        ]
        for vname, tier, sens, dept_name, asset_names, score in vendors_data:
            vendor, created = Vendor.objects.get_or_create(
                name=vname,
                defaults={
                    'tier': tier,
                    'data_sensitivity': sens,
                    'owner_dept': departments[dept_name],
                    'contact_email': f'contact@{vname.lower().replace(" ", "")}.example',
                    'contract_start': timezone.localdate() - timedelta(days=365),
                    'contract_renewal_date': timezone.localdate() + timedelta(days=365),
                }
            )
            if created:
                # Link assets
                assets_qs = Asset.objects.filter(name__in=asset_names)
                vendor.provides_assets.set(assets_qs)

                # Map old 0-100 aggregate score to 5 dimensions of 0-25 each
                per_dim = max(0, min(25, score // 5))

                # Create an assessment
                VendorAssessment.objects.create(
                    vendor=vendor,
                    assessment_date=timezone.localdate() - timedelta(days=30),
                    security_score=per_dim,
                    compliance_score=per_dim,
                    financial_score=per_dim,
                    reputation_score=per_dim,
                    operational_score=per_dim,
                    status='completed',
                    key_findings=(
                        f'Initial assessment for {vname}. '
                        f'Baseline risk profile established across all five dimensions.'
                    ),
                    recommended_mitigation=(
                        f'Maintain annual assessment cadence for {vname} '
                        f'and monitor for material changes in scope or security posture.'
                    ),
                )
                self.stdout.write(f"  Vendor: {vname}")

        # ---------- Policy Categories ----------
        policy_categories = {}
        for name in ['Information Security', 'Access Control', 'Data Protection',
                     'Incident Response', 'Business Continuity', 'HR Security']:
            cat, _ = PolicyCategory.objects.get_or_create(name=name)
            policy_categories[name] = cat

        # ---------- Policies ----------
        policies_data = [
            ('POL-ISMS-001', 'Information Security Policy',          'Information Security', 'IT',         'approved'),
            ('POL-ACC-001',  'Access Control Policy',                'Access Control',       'IT',         'approved'),
            ('POL-DATA-001', 'Data Classification Policy',           'Data Protection',      'Compliance', 'approved'),
            ('POL-DATA-002', 'Data Retention and Disposal Policy',   'Data Protection',      'Compliance', 'review'),
            ('POL-IR-001',   'Incident Response Policy',             'Incident Response',    'IT',         'approved'),
            ('POL-BCP-001',  'Business Continuity Policy',           'Business Continuity',  'Operations', 'draft'),
            ('POL-HR-001',   'Acceptable Use Policy',                'HR Security',          'HR',         'approved'),
            ('POL-HR-002',   'Remote Work Security Policy',          'HR Security',          'HR',         'review'),
        ]
        for code, title, cat_name, dept_name, status in policies_data:
            policy, created = Policy.objects.get_or_create(
                code=code,
                defaults={
                    'title': title,
                    'category': policy_categories[cat_name],
                    'owner_dept': departments[dept_name],
                    'status': status,
                    'version': '1.0',
                    'description': f'{title} for the organization.',
                    'approval_date': timezone.localdate() - timedelta(days=90) if status == 'approved' else None,
                    'next_review_date': timezone.localdate() + timedelta(days=275) if status == 'approved' else None,
                }
            )
            if created:
                self.stdout.write(f"  Policy: {code}")

        # ---------- Controls ----------
        controls_data = [
            # (code, name, type, category, status, effectiveness, dept, framework_controls)
            ('CTL-END-001', 'Endpoint Antivirus / EDR',       'preventive', 'technical',      'implemented', 4, 'IT',         ['A.8.7']),
            ('CTL-NET-001', 'Perimeter Firewall + Segmentation', 'preventive', 'technical',   'implemented', 5, 'IT',         ['A.5.15']),
            ('CTL-ACC-001', 'Multi-Factor Authentication',    'preventive', 'technical',      'implemented', 5, 'IT',         ['A.8.2', '6.3']),
            ('CTL-ACC-002', 'Quarterly Access Reviews',       'detective',  'administrative', 'implemented', 3, 'IT',         ['A.5.15', '5.1']),
            ('CTL-PAT-001', 'Vulnerability & Patch Management', 'preventive', 'administrative', 'implemented', 4, 'IT',       ['A.8.8', '7.1']),
            ('CTL-BAK-001', 'Backup & Disaster Recovery',     'corrective', 'technical',      'implemented', 4, 'IT',         ['A.8.13']),
            ('CTL-MON-001', 'IDS / SIEM Monitoring',          'detective',  'technical',      'implemented', 3, 'IT',         ['A.8.16', 'DE.CM-01']),
            ('CTL-AWR-001', 'Security Awareness Training',    'preventive', 'administrative', 'implemented', 3, 'HR',         []),
            ('CTL-PHY-001', 'Physical Access Control',        'preventive', 'physical',       'implemented', 4, 'Operations', []),
            ('CTL-IRP-001', 'Incident Response Plan',         'corrective', 'administrative', 'implemented', 4, 'IT',         ['RS.MA-01']),
            ('CTL-AUD-001', 'Audit Logging',                  'detective',  'technical',      'implemented', 4, 'IT',         ['8.2']),
        ]
        # Map numeric effectiveness (0-5) to the rating string Control.save() expects
        EFF_RATING_MAP = {
            0: 'not_tested',
            1: 'ineffective',
            2: 'ineffective',
            3: 'partially_effective',
            4: 'effective',
            5: 'effective',
        }

        controls_by_code = {}
        for code, name, ctype, cat, status, eff, dept_name, fw_codes in controls_data:
            ctl, created = Control.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'control_type': ctype,
                    'category': cat,
                    'status': status,
                    'effectiveness_rating': EFF_RATING_MAP.get(eff, 'not_tested'),
                    'owner_dept': departments[dept_name],
                }
            )
            if created:
                # Link to framework controls
                fw_qs = FrameworkControl.objects.filter(code__in=fw_codes)
                ctl.framework_controls.set(fw_qs)
                self.stdout.write(f"  Control: {code}")
            controls_by_code[code] = ctl

        # ---------- Risk Categories ----------
        risk_cats = {}
        for name in ['Information Security', 'Operational', 'Compliance',
                     'Physical', 'Supply Chain', 'Financial']:
            cat, _ = RiskCategory.objects.get_or_create(name=name)
            risk_cats[name] = cat

        # ---------- Risk Appetite (org-wide baseline) ----------
        # NOT using get_or_create: (department=NULL, category=NULL) isn't unique,
        # so if there's already more than one row, .get() inside get_or_create raises.
        appetite = RiskAppetite.objects.filter(
            department__isnull=True, category__isnull=True,
        ).order_by('pk').first()
        if not appetite:
            RiskAppetite.objects.create(
                department=None,
                category=None,
                max_inherent_score=15,
                max_residual_score=8,
                description='Org-wide baseline appetite',
            )
            self.stdout.write('  Risk appetite: org-wide baseline created')
        else:
            self.stdout.write('  Risk appetite: org-wide baseline exists')

        # ---------- Risks ----------
        risks_data = [
            # (title, category, dept, lik, impact, strategy, status, controls)
            ('Ransomware attack on file server',   'Information Security', 'IT',         4, 5, 'mitigate', 'treating',
                ['CTL-END-001', 'CTL-BAK-001', 'CTL-PAT-001', 'CTL-MON-001']),
            ('Data breach of customer database',   'Information Security', 'Operations', 3, 5, 'mitigate', 'treating',
                ['CTL-NET-001', 'CTL-ACC-001', 'CTL-AUD-001']),
            ('Phishing compromise of employee email', 'Information Security', 'IT',      4, 4, 'mitigate', 'monitored',
                ['CTL-ACC-001', 'CTL-AWR-001', 'CTL-END-001']),
            ('Unpatched vulnerability in web app', 'Information Security', 'IT',         3, 4, 'mitigate', 'treating',
                ['CTL-PAT-001', 'CTL-NET-001']),
            ('Insider data exfiltration',          'Information Security', 'HR',         2, 5, 'mitigate', 'assessed',
                ['CTL-ACC-002', 'CTL-AUD-001']),
            ('Loss of laptop with sensitive data', 'Physical',             'Operations', 3, 3, 'mitigate', 'assessed',
                ['CTL-PHY-001']),
            ('Power outage at data center',        'Operational',          'Operations', 2, 4, 'mitigate', 'assessed',
                []),
            ('Third-party vendor breach',          'Supply Chain',         'Compliance', 3, 4, 'transfer', 'treating',
                ['CTL-ACC-002']),
            ('Non-compliance with data protection laws', 'Compliance',     'Compliance', 2, 5, 'mitigate', 'assessed',
                ['CTL-AUD-001']),
            ('HR data mishandling',                'Compliance',           'HR',         2, 3, 'mitigate', 'identified',
                []),
        ]
        for title, cat_name, dept_name, lik, imp, strat, status, ctl_codes in risks_data:
            risk, created = Risk.objects.get_or_create(
                title=title,
                owner_dept=departments[dept_name],
                defaults={
                    'category': risk_cats[cat_name],
                    'likelihood': lik,
                    'impact': imp,
                    'treatment_strategy': strat,
                    'status': status,
                    'identified_date': timezone.localdate() - timedelta(days=60),
                }
            )
            if created:
                # Link controls
                ctl_qs = Control.objects.filter(code__in=ctl_codes)
                risk.controls.set(ctl_qs)
                # Now compute residual score (cascade will re-trigger too, but this ensures consistency)
                recalculate_risk(risk)
                self.stdout.write(f"  Risk: {title}")

        # ---------- Summary ----------
        self.stdout.write(self.style.SUCCESS('\n✔ Seed complete.\n'))
        self.stdout.write(f"  Vendors:            {Vendor.objects.count()}")
        self.stdout.write(f"  Vendor assessments: {VendorAssessment.objects.count()}")
        self.stdout.write(f"  Policy categories:  {PolicyCategory.objects.count()}")
        self.stdout.write(f"  Policies:           {Policy.objects.count()}")
        self.stdout.write(f"  Departments:        {Department.objects.count()}")
        self.stdout.write(f"  Controls:           {Control.objects.count()}")
        self.stdout.write(f"  Risk categories:    {RiskCategory.objects.count()}")
        self.stdout.write(f"  Risks:              {Risk.objects.count()}")
        self.stdout.write(f"  Risk treatments:    {RiskTreatment.objects.count()}")
        self.stdout.write(f"  Users:              {User.objects.count()}")
        self.stdout.write(f"  Asset categories:   {AssetCategory.objects.count()}")
        self.stdout.write(f"  Assets:             {Asset.objects.count()}")
        self.stdout.write(f"  Frameworks:         {Framework.objects.count()}")
        self.stdout.write(f"  Framework controls: {FrameworkControl.objects.count()}")
        self.stdout.write(self.style.WARNING(
            "\n  All seeded users have password: demo1234"
        ))