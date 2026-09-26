import {EQUIPMENT_DRAWING_MASTER,resolveEquipmentDrawing} from './equipmentDrawingMaster.mjs';
import {resolveEventDrawing} from './eventDrawingMap.mjs';
import {resolvePlantFocus} from './plantDrawingFocus.mjs';

const unique=values=>[...new Set((values||[]).map(value=>String(value||'').trim()).filter(Boolean))];
const list=value=>Array.isArray(value)?value:value==null?[]:[value];
const ST_POWER_TAGS=new Set(['vppSTGridPowerMW','vppSTGeneratorPowerMW']);
const ST_BREAKER_TAGS=new Set([
  'vppSTGridPowerMW',
  'vppSTGeneratorPowerMW',
  'vpp52STClosed',
  'vppSTTripLatchPublished',
  'vppSTTripRequest',
  'vppExternalSTTripCommandNative',
  'vppCauseDirectSTTrip',
  'vppCauseSTBreakerOpenWhileRunning',
  'vppECMS52STClosedCommandNative',
]);

export function buildClaimReferenceTargets(item={},catalog=[]){
  const ids=new Set(unique(list(item?.evidence_ids)));
  const evidence=(catalog||[]).filter(row=>ids.has(String(row?.evidence_id||row?.event_id||'')));
  const evidenceTags=evidence.flatMap(row=>[
    row?.source_node,row?.canonical_tag,row?.original_tag,row?.tag,
  ]);
  const tags=unique([...list(item?.related_tags),...evidenceTags]);
  const logicTag=tags[0]||'';
  const stBreakerTag=tags.find(tag=>ST_BREAKER_TAGS.has(tag));
  if(stBreakerTag){
    const query=new URLSearchParams({equipment:'52ST',view:'ecms'});
    query.set(ST_POWER_TAGS.has(stBreakerTag)?'tag':'event',stBreakerTag);
    return {logicTag,drawingHref:`/drawing?${query.toString()}`};
  }

  for(const row of evidence){
    const eventDrawing=resolveEventDrawing({
      rule_id:row?.rule_id,
      equipment:row?.equipment||row?.event_equipment,
      tag:row?.event_tag||row?.tag||row?.original_tag,
    });
    const mappedRow=eventDrawing?.location_id
      ?EQUIPMENT_DRAWING_MASTER.find(item=>item.plant_location_id===eventDrawing.location_id)
      :null;
    const directRow=resolveEquipmentDrawing(row?.equipment||row?.event_equipment);
    const plantRow=[mappedRow,directRow].find(candidate=>resolvePlantFocus(candidate));
    if(!plantRow)continue;

    const sourceTag=unique([
      row?.source_node,row?.canonical_tag,row?.original_tag,row?.tag,
    ]).find(tag=>tags.includes(tag));
    const eventTag=sourceTag||logicTag||row?.event_tag||row?.tag||'';
    const query=new URLSearchParams({equipment:plantRow.event_equipment,view:'plant'});
    if(eventTag)query.set('event',eventTag);
    return {logicTag,drawingHref:`/drawing?${query.toString()}`};
  }

  return {logicTag,drawingHref:''};
}
