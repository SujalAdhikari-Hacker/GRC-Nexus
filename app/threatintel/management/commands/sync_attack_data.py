"""
Sync MITRE ATT&CK Enterprise framework from the official STIX bundle.

Source: https://github.com/mitre-attack/attack-stix-data
Bundle: ~30MB JSON, contains tactics, techniques, threat actors, and relationships.

Usage:
    python manage.py sync_attack_data
    python manage.py sync_attack_data --domain enterprise
    python manage.py sync_attack_data --domain mobile
    python manage.py sync_attack_data --domain ics
"""
from core.management.base import LoggedCommand
from core.safe_http import safe_get

from threatintel.models import Tactic, Technique, ThreatActor


STIX_URLS = {
    'enterprise': 'https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json',
    'mobile':     'https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/mobile-attack/mobile-attack.json',
    'ics':        'https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/ics-attack/ics-attack.json',
}

HTTP_TIMEOUT = 120
STIX_MAX_BYTES = 60 * 1024 * 1024

BASELINE_TACTICS = [
    ('TA0043', 'Reconnaissance', 'reconnaissance', 'Gathering information to plan future adversary operations.'),
    ('TA0042', 'Resource Development', 'resource-development', 'Establishing resources to support operations.'),
    ('TA0001', 'Initial Access', 'initial-access', 'Techniques used to gain an initial foothold within a network.'),
    ('TA0002', 'Execution', 'execution', 'Techniques resulting in adversary-controlled code running on a system.'),
    ('TA0003', 'Persistence', 'persistence', 'Techniques used to keep access across restarts and credential changes.'),
    ('TA0004', 'Privilege Escalation', 'privilege-escalation', 'Techniques used to gain higher-level permissions.'),
    ('TA0005', 'Defense Evasion', 'defense-evasion', 'Techniques used to avoid detection throughout compromise.'),
    ('TA0006', 'Credential Access', 'credential-access', 'Techniques for stealing account names and passwords.'),
    ('TA0007', 'Discovery', 'discovery', 'Techniques used to gain knowledge about the system and internal network.'),
    ('TA0008', 'Lateral Movement', 'lateral-movement', 'Techniques used to enter and control remote systems on a network.'),
    ('TA0009', 'Collection', 'collection', 'Techniques used to gather data of interest to the adversary goal.'),
    ('TA0011', 'Command and Control', 'command-and-control', 'Techniques used to communicate with compromised systems.'),
    ('TA0010', 'Exfiltration', 'exfiltration', 'Techniques used to steal data from your network.'),
    ('TA0040', 'Impact', 'impact', 'Techniques used to disrupt availability or compromise integrity.'),
]

BASELINE_TECHNIQUES = [
    ('T1595', 'Active Scanning', ['reconnaissance'], ['PRE']),
    ('T1598', 'Phishing for Information', ['reconnaissance'], ['PRE']),
    ('T1583', 'Acquire Infrastructure', ['resource-development'], ['PRE']),
    ('T1588', 'Obtain Capabilities', ['resource-development'], ['PRE']),
    ('T1566', 'Phishing', ['initial-access'], ['Windows', 'macOS', 'Linux', 'Office Suite']),
    ('T1190', 'Exploit Public-Facing Application', ['initial-access'], ['Windows', 'Linux', 'Containers']),
    ('T1078', 'Valid Accounts', ['initial-access', 'persistence', 'privilege-escalation', 'defense-evasion'], ['Windows', 'Linux', 'Cloud']),
    ('T1059', 'Command and Scripting Interpreter', ['execution'], ['Windows', 'macOS', 'Linux']),
    ('T1204', 'User Execution', ['execution'], ['Windows', 'macOS', 'Linux']),
    ('T1053', 'Scheduled Task/Job', ['execution', 'persistence', 'privilege-escalation'], ['Windows', 'Linux', 'macOS']),
    ('T1547', 'Boot or Logon Autostart Execution', ['persistence', 'privilege-escalation'], ['Windows', 'macOS', 'Linux']),
    ('T1136', 'Create Account', ['persistence'], ['Windows', 'Linux', 'Cloud']),
    ('T1068', 'Exploitation for Privilege Escalation', ['privilege-escalation'], ['Windows', 'Linux']),
    ('T1027', 'Obfuscated Files or Information', ['defense-evasion'], ['Windows', 'macOS', 'Linux']),
    ('T1070', 'Indicator Removal', ['defense-evasion'], ['Windows', 'macOS', 'Linux']),
    ('T1562', 'Impair Defenses', ['defense-evasion'], ['Windows', 'Linux', 'Cloud']),
    ('T1110', 'Brute Force', ['credential-access'], ['Windows', 'Linux', 'Cloud']),
    ('T1003', 'OS Credential Dumping', ['credential-access'], ['Windows', 'Linux']),
    ('T1087', 'Account Discovery', ['discovery'], ['Windows', 'Linux', 'Cloud']),
    ('T1046', 'Network Service Discovery', ['discovery'], ['Windows', 'Linux']),
    ('T1021', 'Remote Services', ['lateral-movement'], ['Windows', 'Linux']),
    ('T1570', 'Lateral Tool Transfer', ['lateral-movement'], ['Windows', 'Linux']),
    ('T1560', 'Archive Collected Data', ['collection'], ['Windows', 'macOS', 'Linux']),
    ('T1114', 'Email Collection', ['collection'], ['Windows', 'Office Suite']),
    ('T1071', 'Application Layer Protocol', ['command-and-control'], ['Windows', 'macOS', 'Linux']),
    ('T1105', 'Ingress Tool Transfer', ['command-and-control'], ['Windows', 'macOS', 'Linux']),
    ('T1041', 'Exfiltration Over C2 Channel', ['exfiltration'], ['Windows', 'macOS', 'Linux']),
    ('T1486', 'Data Encrypted for Impact', ['impact'], ['Windows', 'Linux']),
    ('T1490', 'Inhibit System Recovery', ['impact'], ['Windows', 'Linux']),
    ('T1498', 'Network Denial of Service', ['impact'], ['Linux', 'Network']),
]

BASELINE_ACTORS = [
    ('G0032', 'Lazarus Group', ['HIDDEN COBRA', 'Guardians of Peace', 'APT38'],
     'State-sponsored cyber threat group active since at least 2009 targeting financial, defense, and technology sectors.',
     ['T1566', 'T1059', 'T1027', 'T1071', 'T1486']),
    ('G0007', 'APT28', ['Fancy Bear', 'Sofacy', 'STRONTIUM'],
     'Threat group attributed to Russian military intelligence conducting espionage campaigns worldwide.',
     ['T1566', 'T1190', 'T1078', 'T1110', 'T1003', 'T1071']),
    ('G0016', 'APT29', ['Cozy Bear', 'Midnight Blizzard', 'The Dukes'],
     'Espionage threat group targeting government, cloud identity, and critical enterprise environments.',
     ['T1566', 'T1078', 'T1059', 'T1114', 'T1041']),
    ('G0046', 'FIN7', ['Carbanak Group', 'Carbon Spider'],
     'Financially motivated threat group known for point-of-sale malware, phishing, and ransomware deployment.',
     ['T1566', 'T1059', 'T1053', 'T1003', 'T1021']),
    ('G0102', 'Wizard Spider', ['TrickBot Group', 'UNC1878'],
     'Financially motivated cybercrime group operating TrickBot, BazarLoader, and Conti ransomware operations.',
     ['T1566', 'T1059', 'T1003', 'T1021', 'T1486', 'T1490']),
    ('G1017', 'Volt Typhoon', ['BRONZE SILHOUETTE', 'Vanguard Panda'],
     'Threat actor focused on espionage and stealthy living-off-the-land persistence in critical infrastructure.',
     ['T1190', 'T1078', 'T1059', 'T1070', 'T1021']),
    ('G0094', 'Kimsuky', ['Velvet Chollima', 'Emerald Sleet'],
     'Cyber espionage group known for spearphishing and credential harvesting against think tanks and agencies.',
     ['T1598', 'T1566', 'T1059', 'T1547', 'T1041']),
    ('G0069', 'MuddyWater', ['Mercury', 'Mango Sandstorm'],
     'Espionage group conducting targeted operations primarily across telecommunications and government organizations.',
     ['T1566', 'T1190', 'T1059', 'T1027', 'T1105']),
    ('G0034', 'Sandworm Team', ['VOODOO BEAR', 'Seashell Blizzard'],
     'Destructive cyber threat group associated with disruptive attacks on energy, telecommunications, and enterprise networks.',
     ['T1190', 'T1078', 'T1021', 'T1486', 'T1490', 'T1498']),
    ('G1015', 'Scattered Spider', ['Octo Tempest', 'UNC3944'],
     'Financially motivated group specializing in social engineering, MFA fatigue, SIM swapping, and cloud identity abuse.',
     ['T1598', 'T1078', 'T1136', 'T1562', 'T1486']),
]


class Command(LoggedCommand):
    help = 'Sync MITRE ATT&CK tactics, techniques, and threat actors from the STIX bundle'

    def add_arguments(self, parser):
        parser.add_argument('--domain', default='enterprise',
                            choices=list(STIX_URLS.keys()))
        parser.add_argument('--seed-baseline', action='store_true',
                            help='Populate a curated offline baseline of ATT&CK tactics, techniques, and actors.')
        parser.add_argument('--fallback-baseline', action='store_true',
                            help='If the remote MITRE STIX download fails, populate the curated baseline instead.')

    def _seed_baseline(self):
        tactic_map = {}
        for idx, (attack_id, name, shortname, desc) in enumerate(BASELINE_TACTICS):
            t, _ = Tactic.objects.update_or_create(
                attack_id=attack_id,
                defaults={
                    'name': name,
                    'shortname': shortname,
                    'description': desc,
                    'order': idx,
                    'url': f'https://attack.mitre.org/tactics/{attack_id}/',
                },
            )
            tactic_map[shortname] = t

        tech_map = {}
        for attack_id, name, t_shortnames, platforms in BASELINE_TECHNIQUES:
            tech, _ = Technique.objects.update_or_create(
                attack_id=attack_id,
                defaults={
                    'name': name,
                    'description': f'MITRE ATT&CK technique {attack_id} ({name}).',
                    'platforms': platforms,
                    'is_subtechnique': False,
                    'deprecated': False,
                    'url': f'https://attack.mitre.org/techniques/{attack_id}/',
                },
            )
            tech.tactics.set([tactic_map[sn] for sn in t_shortnames if sn in tactic_map])
            tech_map[attack_id] = tech

        for attack_id, name, aliases, desc, tech_ids in BASELINE_ACTORS:
            actor, _ = ThreatActor.objects.update_or_create(
                attack_id=attack_id,
                defaults={
                    'name': name,
                    'aliases': aliases,
                    'description': desc,
                    'url': f'https://attack.mitre.org/groups/{attack_id}/',
                },
            )
            actor.techniques.set([tech_map[tid] for tid in tech_ids if tid in tech_map])

        tactics_total = Tactic.objects.count()
        techniques_total = Technique.objects.count()
        actors_total = ThreatActor.objects.count()
        self.record_counts(
            tactics=tactics_total,
            techniques=techniques_total,
            actors=actors_total,
            baseline=1,
        )
        self.stdout.write(self.style.SUCCESS(
            f'MITRE ATT&CK curated baseline seeded: '
            f'{tactics_total} tactics, {techniques_total} techniques, {actors_total} threat actors.'
        ))

    def handle(self, *args, **options):
        if options.get('seed_baseline'):
            self._seed_baseline()
            return

        domain = options['domain']
        url = STIX_URLS[domain]

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'Downloading MITRE ATT&CK {domain} STIX bundle...'
        ))

        try:
            r = safe_get(url, timeout=HTTP_TIMEOUT, max_bytes=STIX_MAX_BYTES)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            if options.get('fallback_baseline'):
                self.stdout.write(self.style.WARNING(
                    f'Remote MITRE STIX download unavailable ({e}); seeding curated baseline.'
                ))
                self._seed_baseline()
                return
            self.stdout.write(self.style.ERROR(f'Download failed: {e}'))
            self.record_counts(tactics=0, techniques=0, actors=0, failed=1)
            return

        objects = data.get('objects', [])
        self.stdout.write(f'  {len(objects)} STIX objects in bundle.')

        # ============ TACTICS ============
        tactics_created = 0
        tactic_map = {}  # shortname -> Tactic
        for obj in objects:
            if obj.get('type') != 'x-mitre-tactic':
                continue
            shortname = obj.get('x_mitre_shortname', '')
            t, created = Tactic.objects.update_or_create(
                attack_id=obj.get('external_references', [{}])[0].get('external_id', ''),
                defaults={
                    'name': obj.get('name', ''),
                    'shortname': shortname,
                    'description': (obj.get('description') or '')[:2000],
                    'url': obj.get('external_references', [{}])[0].get('url', ''),
                }
            )
            tactic_map[shortname] = t
            if created:
                tactics_created += 1

        # Set tactic order (kill chain phase order)
        kill_chain_order = [
            'reconnaissance', 'resource-development', 'initial-access', 'execution',
            'persistence', 'privilege-escalation', 'defense-evasion', 'credential-access',
            'discovery', 'lateral-movement', 'collection', 'command-and-control',
            'exfiltration', 'impact',
        ]
        for idx, sn in enumerate(kill_chain_order):
            if sn in tactic_map:
                Tactic.objects.filter(pk=tactic_map[sn].pk).update(order=idx)

        self.stdout.write(f'  Tactics: {tactics_created} created, {len(tactic_map)} total')

        # ============ TECHNIQUES ============
        techniques_created = 0
        technique_map = {}  # attack_id -> Technique
        pending_tactics = []  # (technique_obj, [shortnames])
        pending_subtech = []  # (subtechnique_id, parent_id)

        for obj in objects:
            if obj.get('type') != 'attack-pattern':
                continue
            if obj.get('revoked') or obj.get('x_mitre_deprecated'):
                continue

            ext_refs = obj.get('external_references', [])
            attack_id = ''
            url = ''
            for ref in ext_refs:
                if ref.get('source_name') == 'mitre-attack':
                    attack_id = ref.get('external_id', '')
                    url = ref.get('url', '')
                    break
            if not attack_id:
                continue

            # Determine parent (sub-technique of)
            parent_id = ''
            for ref in ext_refs:
                if ref.get('source_name') == 'mitre-attack' and ref.get('external_id', '').count('.') > 0:
                    parent_id = ref.get('external_id').split('.')[0]
                    break

            t, created = Technique.objects.update_or_create(
                attack_id=attack_id,
                defaults={
                    'stix_id': obj.get('id', ''),
                    'name': obj.get('name', '')[:300],
                    'description': (obj.get('description') or '')[:5000],
                    'platforms': obj.get('x_mitre_platforms', []) or [],
                    'is_subtechnique': obj.get('x_mitre_is_subtechnique', False),
                    'detection': (obj.get('x_mitre_detection') or '')[:3000],
                    'url': url,
                }
            )
            technique_map[attack_id] = t
            if created:
                techniques_created += 1

            # Queue tactic links
            shortnames = []
            for phase in obj.get('kill_chain_phases', []):
                if phase.get('kill_chain_name') == 'mitre-attack':
                    shortnames.append(phase.get('phase_name'))
            if shortnames:
                pending_tactics.append((t, shortnames))

            if parent_id:
                pending_subtech.append((attack_id, parent_id))

        # Apply tactic links
        for t, shortnames in pending_tactics:
            tacs = [tactic_map[sn] for sn in shortnames if sn in tactic_map]
            if tacs:
                t.tactics.set(tacs)

        # Apply parent links
        for sub_id, parent_id in pending_subtech:
            if parent_id in technique_map and sub_id in technique_map:
                Technique.objects.filter(pk=technique_map[sub_id].pk).update(
                    parent=technique_map[parent_id]
                )

        self.stdout.write(f'  Techniques: {techniques_created} created, {len(technique_map)} total')

        # ============ THREAT ACTORS ============
        actors_created = 0
        actor_map = {}  # stix id -> ThreatActor

        for obj in objects:
            if obj.get('type') != 'intrusion-set':
                continue
            if obj.get('revoked'):
                continue

            ext_refs = obj.get('external_references', [])
            attack_id = ''
            url = ''
            for ref in ext_refs:
                if ref.get('source_name') == 'mitre-attack':
                    attack_id = ref.get('external_id', '')
                    url = ref.get('url', '')
                    break
            if not attack_id:
                continue

            a, created = ThreatActor.objects.update_or_create(
                attack_id=attack_id,
                defaults={
                    'name': obj.get('name', '')[:200],
                    'aliases': obj.get('aliases', []) or [],
                    'description': (obj.get('description') or '')[:5000],
                    'url': url,
                }
            )
            actor_map[obj.get('id')] = a
            if created:
                actors_created += 1

        self.stdout.write(f'  Threat actors: {actors_created} created, {len(actor_map)} total')

        # ============ ACTOR → TECHNIQUE RELATIONSHIPS ============
        # Find "uses" relationships where source = intrusion-set, target = attack-pattern
        tech_by_stix_id = {t.stix_id: t for t in Technique.objects.exclude(stix_id='')}
        links_created = 0

        for obj in objects:
            if obj.get('type') != 'relationship':
                continue
            if obj.get('relationship_type') != 'uses':
                continue
            source_ref = obj.get('source_ref', '')
            target_ref = obj.get('target_ref', '')
            if not (source_ref.startswith('intrusion-set--') and target_ref.startswith('attack-pattern--')):
                continue

            actor = actor_map.get(source_ref)
            tech = tech_by_stix_id.get(target_ref)
            if actor and tech:
                actor.techniques.add(tech)
                links_created += 1

        self.stdout.write(f'  Actor→Technique links: {links_created}')

        # ============ SUMMARY ============
        tactics_total = Tactic.objects.count()
        techniques_total = Technique.objects.count()
        actors_total = ThreatActor.objects.count()
        self.record_counts(
            tactics=tactics_total,
            techniques=techniques_total,
            actors=actors_total,
        )
        self.stdout.write(self.style.SUCCESS('\n✔ MITRE ATT&CK sync complete.\n'))
        self.stdout.write(f'  Tactics:        {tactics_total}')
        self.stdout.write(f'  Techniques:     {techniques_total}')
        self.stdout.write(f'  Threat actors:  {actors_total}')
