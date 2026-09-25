"""One-source TripLens logic diagram assets."""
from copy import deepcopy

from .model import RULE_FIELDS, TAG_FIELDS, digest, parts, screen_for, text, validate_model
from .drawio import build_document, create_index
from .drawing_master import create_drawing_master


def _search_model(live_model, source_tags, source_rules):
    """Add source observations to the searchable view, never to runtime data."""
    search = deepcopy(live_model)
    observed = {}
    for source in source_tags:
        tag = text(source.get('raw_tag_id'))
        if not tag or tag in search['tags'] or tag in observed:
            raise ValueError(f'duplicate or missing model-source tag: {tag}')
        if text(source.get('source_kind')) != 'MODEL_SOURCE_RAW_OBSERVED':
            raise ValueError(f'model-source tag has wrong source_kind: {tag}')
        if text(source.get('runtime_inclusion')) != 'SEARCH_ONLY':
            raise ValueError(f'model-source tag must remain SEARCH_ONLY: {tag}')
        if text(source.get('open_behavior_test_status')) != 'NOT_TESTED':
            raise ValueError(f'model-source tag has unsupported OPEN test status: {tag}')
        row = {k:text(source.get(k)) for k in TAG_FIELDS}
        row.update({k:text(v) for k,v in source.items() if k not in TAG_FIELDS})
        row.update(is_native=True, live_existence='MODEL_SOURCE_RAW_OBSERVED',
                   live_variant_type='', live_node_id='', model_source_only=True)
        observed[tag] = row
    if observed and set(observed) != {'vppSTGeneratorPowerMW', 'vppSTGridPowerMW'}:
        raise ValueError('ST source search requires exactly the two observed MW tags')
    search['tags'].update(observed)

    source_normalized = []
    for source in source_rules:
        rid = text(source.get('rule_id'))
        if not rid or any(r['rule_id'] == rid for r in search['rules']+source_normalized):
            raise ValueError(f'duplicate or missing model-source rule: {rid}')
        if text(source.get('source_kind')) != 'MODEL_SOURCE_RAW_OBSERVED':
            raise ValueError(f'model-source rule has wrong source_kind: {rid}')
        if text(source.get('runtime_inclusion')) != 'SEARCH_ONLY':
            raise ValueError(f'model-source rule must remain SEARCH_ONLY: {rid}')
        if text(source.get('model_source_status')) != 'MODEL_SOURCE_CONFIRMED':
            raise ValueError(f'model-source rule lacks source confirmation: {rid}')
        if text(source.get('raw_session_status')) != 'RAW_SESSION_OBSERVED_CLOSED_ONLY':
            raise ValueError(f'model-source rule lacks closed-only RAW status: {rid}')
        if text(source.get('open_behavior_test_status')) != 'NOT_TESTED':
            raise ValueError(f'model-source rule must retain OPEN NOT_TESTED: {rid}')
        rule = {k:text(source.get(k)) for k in RULE_FIELDS}
        rule.update({k:text(v) for k,v in source.items() if k not in RULE_FIELDS})
        rule['inputs'] = parts(rule.get('input_nodes'))
        rule['outputs'] = parts(rule.get('output_nodes_or_tags'))
        if not rule['inputs'] or not rule['outputs']:
            raise ValueError(f'model-source rule has an empty input or output: {rid}')
        if 'vppSTGeneratorPowerMW' not in rule['inputs']:
            raise ValueError(f'model-source response is missing vppSTGeneratorPowerMW: {rid}')
        if 'vppSTGridPowerMW' not in rule['outputs']:
            raise ValueError(f'model-source response is missing vppSTGridPowerMW: {rid}')
        if any(tag not in search['tags'] and tag not in search['derived']
               for tag in rule['inputs']+rule['outputs']):
            raise ValueError(f'model-source rule references an unsearchable tag: {rid}')
        rule['screen'] = screen_for(rule['group'])
        rule['source_mapped'] = True
        rule['source_existence_status'] = 'MODEL_SOURCE_CONFIRMED_RAW_OBSERVED'
        rule['behavior_validation'] = 'PARTIAL'
        signature = ' | '.join(sorted(rule['inputs']))
        rule['input_signature'] = signature
        rule['input_group_id'] = rule['input_group_id'] or ('IG-'+digest(signature)[:10])
        existing = search['groups'].get(rule['input_group_id'])
        if existing and existing[0]['input_signature'] != signature:
            raise ValueError(f'input group conflicts with source rule: {rid}')
        source_normalized.append(rule)
    for rule in source_normalized:
        search['groups'].setdefault(rule['input_group_id'], []).append(rule)
    search['rules'].extend(source_normalized)
    search['rules'].sort(key=lambda r:r['rule_id'])
    search['groups'] = {gid:sorted(rs,key=lambda r:r['rule_id'])
                        for gid,rs in sorted(search['groups'].items())}
    search['semantic_sha256'] = digest({
        'tags':search['tags'], 'rules':search['rules'],
        'census_names':sorted(live_model['tags'])
    })
    return search


def make_repository(tags, rules, census, *, source_tags=(), source_rules=(), layout_xml=None):
    model=validate_model(tags,rules,census)
    searchable=_search_model(model,source_tags,source_rules)
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
