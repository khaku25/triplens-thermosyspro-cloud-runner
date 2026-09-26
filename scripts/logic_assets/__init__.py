"""One-source TripLens logic diagram assets."""
from copy import deepcopy

from .model import RULE_FIELDS, TAG_FIELDS, digest, parts, screen_for, text, validate_model
from .drawio import build_document, create_index
from .drawing_master import create_drawing_master


def _rebuild_groups(model):
    """Rebuild input groups after an approved metadata-only rule override."""
    groups = {}
    ids = {}
    signatures = {}
    for rule in model['rules']:
        signature = ' | '.join(sorted(rule['inputs']))
        group_id = rule.get('input_group_id') or signatures.get(signature) or ('IG-' + digest(signature)[:10])
        if group_id in ids and ids[group_id] != signature:
            raise ValueError(f'Input group ID has different source sets after overlay: {group_id}')
        if signature in signatures and signatures[signature] != group_id:
            raise ValueError(f'Same source set has conflicting input group IDs after overlay: {signature}')
        ids[group_id] = signature
        signatures[signature] = group_id
        rule['input_group_id'] = group_id
        rule['input_signature'] = signature
        groups.setdefault(group_id, []).append(rule)
    model['groups'] = {
        gid: sorted(rows, key=lambda row: row['rule_id'])
        for gid, rows in sorted(groups.items())
    }
    return model


def _apply_rule_updates(model, updates):
    """Apply explicit rule replacements without inventing nodes or changing plant code."""
    if not updates:
        return model
    by_id = {rule['rule_id']: rule for rule in model['rules']}
    for update in updates:
        rid = text(update.get('rule_id'))
        if rid not in by_id:
            raise ValueError(f'overlay rule does not exist: {rid}')
        rule = by_id[rid]
        for key, value in update.items():
            if key == 'rule_id':
                continue
            rule[key] = text(value) if not isinstance(value, (list, dict, bool)) else value
        rule['inputs'] = parts(rule.get('input_nodes'))
        rule['outputs'] = parts(rule.get('output_nodes_or_tags'))
        if not rule['inputs'] or not rule['outputs']:
            raise ValueError(f'overlay rule has empty input/output: {rid}')
        if any(tag not in model['tags'] and tag not in model['derived'] for tag in rule['inputs'] + rule['outputs']):
            missing = [tag for tag in rule['inputs'] + rule['outputs']
                       if tag not in model['tags'] and tag not in model['derived']]
            raise ValueError(f'overlay rule references unknown tags: {rid}: {missing}')
        rule['screen'] = screen_for(rule['group'])
    _rebuild_groups(model)
    model['semantic_sha256'] = digest({
        'tags': model['tags'], 'rules': model['rules'],
        'census_names': sorted(tag for tag, row in model['tags'].items()
                               if not row.get('model_source_only'))
    })
    return model


def _search_model(live_model, source_tags, source_rules, overlay=None):
    """Add reviewed supplemental observations to search/diagram views only."""
    search = deepcopy(live_model)
    overlay = overlay or {}
    observed = {}
    combined_tags = list(source_tags) + list(overlay.get('source_tags', []))
    allowed_source_kinds = {'MODEL_SOURCE_RAW_OBSERVED', 'MODEL_SOURCE_RUNTIME_OBSERVED'}
    allowed_open_status = {'', 'NOT_TESTED', 'RUNTIME_VERIFIED'}
    for source in combined_tags:
        tag = text(source.get('raw_tag_id'))
        if not tag or tag in search['tags'] or tag in observed:
            raise ValueError(f'duplicate or missing supplemental tag: {tag}')
        source_kind = text(source.get('source_kind'))
        if source_kind not in allowed_source_kinds:
            raise ValueError(f'supplemental tag has wrong source_kind: {tag}: {source_kind}')
        if text(source.get('runtime_inclusion')) != 'SEARCH_ONLY':
            raise ValueError(f'supplemental tag must remain SEARCH_ONLY: {tag}')
        if text(source.get('open_behavior_test_status')) not in allowed_open_status:
            raise ValueError(f'supplemental tag has unsupported OPEN test status: {tag}')
        row = {k:text(source.get(k)) for k in TAG_FIELDS}
        row.update({k:text(v) for k,v in source.items() if k not in TAG_FIELDS})
        row.update(is_native=True, live_existence=source_kind,
                   live_variant_type='', live_node_id='', model_source_only=True)
        observed[tag] = row
    search['tags'].update(observed)

    for tag, update in overlay.get('tag_updates', {}).items():
        if tag not in search['tags']:
            raise ValueError(f'overlay tag update references unknown tag: {tag}')
        search['tags'][tag].update({k:(text(v) if not isinstance(v, (list, dict, bool)) else v)
                                    for k,v in update.items()})

    source_normalized = []
    combined_rules = list(source_rules) + list(overlay.get('source_rules', []))
    for source in combined_rules:
        rid = text(source.get('rule_id'))
        if not rid or any(r['rule_id'] == rid for r in search['rules']+source_normalized):
            raise ValueError(f'duplicate or missing supplemental rule: {rid}')
        source_kind = text(source.get('source_kind'))
        if source_kind not in allowed_source_kinds:
            raise ValueError(f'supplemental rule has wrong source_kind: {rid}: {source_kind}')
        if text(source.get('runtime_inclusion')) != 'SEARCH_ONLY':
            raise ValueError(f'supplemental rule must remain SEARCH_ONLY: {rid}')
        if text(source.get('open_behavior_test_status')) not in allowed_open_status:
            raise ValueError(f'supplemental rule has unsupported OPEN status: {rid}')
        rule = {k:text(source.get(k)) for k in RULE_FIELDS}
        rule.update({k:text(v) for k,v in source.items() if k not in RULE_FIELDS})
        rule['inputs'] = parts(rule.get('input_nodes'))
        rule['outputs'] = parts(rule.get('output_nodes_or_tags'))
        if not rule['inputs'] or not rule['outputs']:
            raise ValueError(f'supplemental rule has an empty input or output: {rid}')
        if any(tag not in search['tags'] and tag not in search['derived']
               for tag in rule['inputs']+rule['outputs']):
            missing = [tag for tag in rule['inputs']+rule['outputs']
                       if tag not in search['tags'] and tag not in search['derived']]
            raise ValueError(f'supplemental rule references an unsearchable tag: {rid}: {missing}')
        rule['screen'] = screen_for(rule['group'])
        rule['source_mapped'] = True
        rule['source_existence_status'] = (
            text(source.get('source_existence_status')) or
            ('MODEL_SOURCE_RUNTIME_OBSERVED' if source_kind == 'MODEL_SOURCE_RUNTIME_OBSERVED'
             else 'MODEL_SOURCE_CONFIRMED_RAW_OBSERVED')
        )
        rule['behavior_validation'] = text(source.get('behavior_validation')) or rule['validation_status']
        signature = ' | '.join(sorted(rule['inputs']))
        rule['input_signature'] = signature
        rule['input_group_id'] = rule['input_group_id'] or ('IG-'+digest(signature)[:10])
        source_normalized.append(rule)
    search['rules'].extend(source_normalized)
    search['rules'].sort(key=lambda r:r['rule_id'])
    _rebuild_groups(search)

    _apply_rule_updates(search, overlay.get('search_rule_updates', []))
    search['rules'].sort(key=lambda r:r['rule_id'])
    _rebuild_groups(search)
    search['semantic_sha256'] = digest({
        'tags':search['tags'], 'rules':search['rules'],
        'census_names':sorted(live_model['tags'])
    })
    return search

def make_repository(tags, rules, census, *, source_tags=(), source_rules=(), layout_xml=None, overlay=None):
    model=validate_model(tags,rules,census)
    overlay = overlay or {}
    model=_apply_rule_updates(model,overlay.get('live_rule_updates', []))
    searchable=_search_model(model,source_tags,source_rules,overlay=overlay)
    xml=build_document(searchable,layout_xml)
    index=create_index(searchable,xml,live_model=model)
    drawing_master=create_drawing_master(
        xml,
        canonical_tags={tag: row['canonical_tag'] for tag,row in searchable['tags'].items() if row.get('canonical_tag')},
        file_path='logic_diagrams/TripLens_Logic_Master_Current_V8.drawio',
        aliases=[
            'generated/logic/TripLens_Logic_Master_Current_V8.drawio',
            'apps/web/public/logic-assets/TripLens_Logic_Master_Current_V8.drawio',
        ],
    )
    from .build import derive_views
    return {'xml':xml,'index':index,'drawing_master':drawing_master,
            'model':model,'search_model':searchable,
            'runtime_derived':derive_views(model,index),
            'derived':derive_views(searchable,index)}


def publish_repository(repository, target):
    from .build import publish_repository as publish
    return publish(repository,target)
