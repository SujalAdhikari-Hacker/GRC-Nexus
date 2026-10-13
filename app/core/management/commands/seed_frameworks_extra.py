from django.core.management.base import BaseCommand
from django.db import transaction

from frameworks.models import Framework, FrameworkControl
from controls.models import Control, ControlFrameworkMapping


class Command(BaseCommand):
    help = 'Seed SOC 2, PCI DSS, GDPR frameworks with sample controls and mappings'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('Seeding extra frameworks...'))

        # ---------- SOC 2 ----------
        soc2, _ = Framework.objects.get_or_create(
            name='SOC 2', version='2017 TSC',
            defaults={'description': 'AICPA Trust Services Criteria for service organizations'}
        )
        soc2_controls = [
            ('CC6.1', 'Logical and physical access controls'),
            ('CC6.2', 'User registration and authorization'),
            ('CC6.3', 'Role-based access and least privilege'),
            ('CC6.6', 'Protection against external threats'),
            ('CC7.2', 'Monitoring infrastructure for anomalies'),
            ('CC8.1', 'Change management process'),
        ]
        for code, title in soc2_controls:
            FrameworkControl.objects.get_or_create(
                framework=soc2, code=code, defaults={'title': title}
            )

        # ---------- PCI DSS ----------
        pci, _ = Framework.objects.get_or_create(
            name='PCI DSS', version='v4.0',
            defaults={'description': 'Payment Card Industry Data Security Standard'}
        )
        pci_controls = [
            ('Req 1', 'Install and maintain network security controls'),
            ('Req 2', 'Apply secure configurations to all system components'),
            ('Req 3', 'Protect stored account data'),
            ('Req 4', 'Protect cardholder data with strong cryptography during transmission'),
            ('Req 8', 'Identify users and authenticate access to system components'),
            ('Req 10', 'Log and monitor all access to system components and cardholder data'),
        ]
        for code, title in pci_controls:
            FrameworkControl.objects.get_or_create(
                framework=pci, code=code, defaults={'title': title}
            )

        # ---------- GDPR ----------
        gdpr, _ = Framework.objects.get_or_create(
            name='GDPR', version='2018',
            defaults={'description': 'EU General Data Protection Regulation'}
        )
        gdpr_controls = [
            ('Art 5',  'Principles relating to processing of personal data'),
            ('Art 25', 'Data protection by design and by default'),
            ('Art 30', 'Records of processing activities'),
            ('Art 32', 'Security of processing'),
            ('Art 33', 'Notification of a personal data breach'),
            ('Art 35', 'Data protection impact assessment'),
        ]
        for code, title in gdpr_controls:
            FrameworkControl.objects.get_or_create(
                framework=gdpr, code=code, defaults={'title': title}
            )

        # ---------- Sample mappings (adds ✓ marks to the matrix) ----------
        def fc(fw_name, code):
            return FrameworkControl.objects.filter(
                framework__name=fw_name, code=code
            ).first()

        mappings = [
            # (control_code, framework_name, framework_code, relationship)
            ('CTL-ACC-001', 'ISO/IEC 27001', 'A.5.15', 'equal'),
            ('CTL-ACC-001', 'ISO/IEC 27001', 'A.8.2',  'equal'),
            ('CTL-ACC-001', 'NIST CSF',      'PR.AA-01', 'equal'),
            ('CTL-ACC-001', 'SOC 2',         'CC6.1',   'equal'),
            ('CTL-ACC-001', 'SOC 2',         'CC6.3',   'superset'),
            ('CTL-ACC-001', 'PCI DSS',       'Req 8',   'equal'),
            ('CTL-ACC-001', 'GDPR',          'Art 32',  'subset'),
            ('CTL-ACC-001', 'CIS Controls',  '5.1',     'equal'),
            ('CTL-ACC-001', 'CIS Controls',  '6.3',     'equal'),

            ('CTL-MON-001', 'ISO/IEC 27001', 'A.8.16',  'equal'),
            ('CTL-MON-001', 'NIST CSF',      'DE.CM-01','equal'),
            ('CTL-MON-001', 'SOC 2',         'CC7.2',   'equal'),
            ('CTL-MON-001', 'PCI DSS',       'Req 10',  'equal'),
            ('CTL-MON-001', 'CIS Controls',  '8.2',     'equal'),

            ('CTL-NET-001', 'ISO/IEC 27001', 'A.5.15',  'subset'),
            ('CTL-NET-001', 'NIST CSF',      'PR.AA-01','subset'),
            ('CTL-NET-001', 'SOC 2',         'CC6.6',   'equal'),
            ('CTL-NET-001', 'PCI DSS',       'Req 1',   'equal'),
            ('CTL-NET-001', 'GDPR',          'Art 32',  'subset'),
            ('CTL-NET-001', 'CIS Controls',  '1.1',     'equal'),

            ('CTL-BAK-001', 'ISO/IEC 27001', 'A.8.13',  'equal'),
            ('CTL-BAK-001', 'SOC 2',         'CC7.2',   'functional_partial'),
            ('CTL-BAK-001', 'PCI DSS',       'Req 3',   'subset'),
            ('CTL-BAK-001', 'GDPR',          'Art 32',  'subset'),
            ('CTL-BAK-001', 'CIS Controls',  '1.1',     'functional_partial'),

            ('CTL-PAT-001', 'ISO/IEC 27001', 'A.8.8',   'equal'),
            ('CTL-PAT-001', 'NIST CSF',      'ID.AM-01','equal'),
            ('CTL-PAT-001', 'SOC 2',         'CC7.2',   'subset'),
            ('CTL-PAT-001', 'PCI DSS',       'Req 2',   'equal'),
            ('CTL-PAT-001', 'CIS Controls',  '7.1',     'equal'),

            ('CTL-END-001', 'ISO/IEC 27001', 'A.8.7',   'equal'),
            ('CTL-END-001', 'SOC 2',         'CC6.6',   'subset'),
            ('CTL-END-001', 'CIS Controls',  '10.1',    'functional_partial'),

            ('CTL-AUD-001', 'ISO/IEC 27001', 'A.8.16',  'subset'),
            ('CTL-AUD-001', 'NIST CSF',      'DE.CM-01','subset'),
            ('CTL-AUD-001', 'SOC 2',         'CC7.2',   'subset'),
            ('CTL-AUD-001', 'PCI DSS',       'Req 10',  'equal'),
            ('CTL-AUD-001', 'GDPR',          'Art 30',  'subset'),
            ('CTL-AUD-001', 'CIS Controls',  '8.2',     'equal'),

            ('CTL-AWR-001', 'ISO/IEC 27001', 'A.5.1',   'subset'),
            ('CTL-AWR-001', 'SOC 2',         'CC6.2',   'subset'),
            ('CTL-AWR-001', 'GDPR',          'Art 25',  'subset'),

            ('CTL-IRP-001', 'ISO/IEC 27001', 'A.5.23',  'functional_partial'),
            ('CTL-IRP-001', 'NIST CSF',      'RS.MA-01','equal'),
            ('CTL-IRP-001', 'SOC 2',         'CC7.2',   'subset'),
            ('CTL-IRP-001', 'GDPR',          'Art 33',  'equal'),

            ('CTL-ACC-002', 'ISO/IEC 27001', 'A.5.15',  'equal'),
            ('CTL-ACC-002', 'NIST CSF',      'PR.AA-01','equal'),
            ('CTL-ACC-002', 'SOC 2',         'CC6.2',   'equal'),
            ('CTL-ACC-002', 'PCI DSS',       'Req 8',   'functional_partial'),
            ('CTL-ACC-002', 'CIS Controls',  '5.1',     'equal'),

            ('CTL-PHY-001', 'ISO/IEC 27001', 'A.5.15',  'superset'),
            ('CTL-PHY-001', 'PCI DSS',       'Req 1',   'subset'),
        ]

        created = 0
        for control_code, fw_name, fc_code, relationship in mappings:
            control = Control.objects.filter(code=control_code).first()
            framework_control = fc(fw_name, fc_code)
            if not (control and framework_control):
                continue
            obj, was_created = ControlFrameworkMapping.objects.get_or_create(
                control=control,
                framework_control=framework_control,
                defaults={'relationship': relationship}
            )
            if was_created:
                created += 1

        self.stdout.write(self.style.SUCCESS(f'\n✔ Extra frameworks seed complete.'))
        self.stdout.write(f"  Frameworks:        {Framework.objects.count()}")
        self.stdout.write(f"  Framework ctrls:   {FrameworkControl.objects.count()}")
        self.stdout.write(f"  Mappings created:  {created}")
        self.stdout.write(f"  Total mappings:    {ControlFrameworkMapping.objects.count()}")
