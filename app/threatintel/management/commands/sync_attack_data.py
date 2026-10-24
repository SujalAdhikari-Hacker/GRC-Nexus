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
from django.core.management.base import BaseCommand
from core.safe_http import safe_get

from threatintel.models import Tactic, Technique, ThreatActor


STIX_URLS = {
    'enterprise': 'https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json',
    'mobile':     'https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/mobile-attack/mobile-attack.json',
    'ics':        'https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/ics-attack/ics-attack.json',
}

HTTP_TIMEOUT = 120


class Command(BaseCommand):
    help = 'Sync MITRE ATT&CK tactics, techniques, and threat actors from the STIX bundle'

    def add_arguments(self, parser):
        parser.add_argument('--domain', default='enterprise',
                            choices=list(STIX_URLS.keys()))

    def handle(self, *args, **options):
        domain = options['domain']
        url = STIX_URLS[domain]

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'Downloading MITRE ATT&CK {domain} STIX bundle...'
        ))

        try:
            r = safe_get(url, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Download failed: {e}'))
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
        self.stdout.write(self.style.SUCCESS('\n✔ MITRE ATT&CK sync complete.\n'))
        self.stdout.write(f'  Tactics:        {Tactic.objects.count()}')
        self.stdout.write(f'  Techniques:     {Technique.objects.count()}')
        self.stdout.write(f'  Threat actors:  {ThreatActor.objects.count()}')
