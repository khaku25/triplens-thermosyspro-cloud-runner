import {EQUIPMENT_DRAWING_MASTER,resolveEquipmentDrawing} from './equipmentDrawingMaster.mjs';
import {EVENT_DRAWING_MAP,resolveEventDrawing} from './eventDrawingMap.mjs';
import {resolvePlantFocus} from './plantDrawingFocus.mjs';
import {ST_POWER_DISPLAY} from './stPowerDisplay.mjs';

const unique=values=>[...new Set((values||[]).map(value=>String(value||'').trim()).filter(Boolean))];
const list=value=>Array.isArray(value)?value:value==null?[]:[value];
const ST_POWER_TAGS=new Set([ST_POWER_DISPLAY.tag,'vppSTGeneratorPowerMW']);
const ST_BREAKER_TAGS=new Set([
  ...ST_POWER_TAGS,
  'vpp52STClosed',
  'vppSTTripLatchPublished',
  'vppSTTripRequest',
  'vppExternalSTTripCommandNative',
  'vppCauseDirectSTTrip',
  'vppCauseSTBreakerOpenWhileRunning',
  'vppECMS52STClosedCommandNative',
]);

function recordTags(row){
  return unique([row?.source_node,row?.canonical_tag,row?.original_tag,row?.event_tag,row?.tag]);
}

function resolveStBreakerTarget(tag){
  const breaker=resolveEquipmentDrawing('52ST');
  if(!breaker?.ecms_location_id)return null;
  const query=new URLSearchParams({equipment:breaker.event_equipment,view:'ecms'});
  query.set(ST_POWER_TAGS.has(tag)?'tag':'event',tag);
  return {
    equipment:breaker.event_equipment,
    view:'ecms',
    kind:ST_POWER_TAGS.has(tag)?'tag':'event',
    href:`/drawing?${query.toString()}`,
  };
}

function resolveDrawingTarget(row,fallbackTag=''){
  const tags=recordTags(row);
  const stTag=tags.find(tag=>ST_BREAKER_TAGS.has(tag)&&!ST_POWER_TAGS.has(tag))
    ||tags.find(tag=>ST_POWER_TAGS.has(tag))
    ||(ST_BREAKER_TAGS.has(fallbackTag)?fallbackTag:'');
  if(stTag)return resolveStBreakerTarget(stTag);

  const eventDrawing=resolveEventDrawing({
    rule_id:row?.rule_id||row?.event_rule_id,
    equipment:row?.equipment||row?.event_equipment,
    tag:row?.event_tag||row?.tag||row?.original_tag,
  })||EVENT_DRAWING_MAP.find(item=>item.source_node&&tags.includes(item.source_node));

  const directRow=resolveEquipmentDrawing(row?.equipment||row?.event_equipment||eventDrawing?.equipment);
  const mappedPlantRow=eventDrawing?.location_id
    ?EQUIPMENT_DRAWING_MASTER.find(item=>item.plant_location_id===eventDrawing.location_id&&resolvePlantFocus(item))
    :null;
  const plantRow=[mappedPlantRow,directRow].find(item=>resolvePlantFocus(item));
  const directElectricalRow=directRow
    &&['BREAKER','BUS'].includes(directRow.equipment_type)
    &&directRow.ecms_page&&directRow.ecms_location_id
    ?directRow
    :null;
  const targetRow=directElectricalRow||plantRow||directRow||mappedPlantRow;
  if(!targetRow)return null;

  const focus=resolvePlantFocus(targetRow);
  const view=focus
    ?'plant'
    :targetRow.ecms_page==='ECMS_6P9KV'
      ?'sld'
      :targetRow.ecms_page==='ECMS_VPP'
        ?'vpp'
        :eventDrawing?.view==='sld'||eventDrawing?.view==='vpp'
          ?eventDrawing.view
          :'';
  if(!view)return null;

  const sourceTag=tags[0]||fallbackTag||eventDrawing?.source_node||'';
  const isEvent=Boolean(eventDrawing||row?.event_id||row?.event_tag||row?.rule_id||row?.event_rule_id);
  const query=new URLSearchParams({equipment:targetRow.event_equipment,view});
  if(sourceTag)query.set(isEvent?'event':'tag',sourceTag);
  return {
    equipment:targetRow.event_equipment,
    view,
    kind:isEvent?'event':'tag',
    href:`/drawing?${query.toString()}`,
  };
}

function relatedTagRecord(tag){
  if(ST_BREAKER_TAGS.has(tag))return {equipment:'52ST',source_node:tag,tag};
  const event=EVENT_DRAWING_MAP.find(row=>row.source_node===tag);
  return event?{...event,source_node:tag}:null;
}

export function buildClaimReferenceTargets(item={},catalog=[]){
  const ids=new Set(unique(list(item?.evidence_ids)));
  const evidence=(catalog||[]).filter(row=>ids.has(String(row?.evidence_id||row?.event_id||'')));
  const evidenceTags=evidence.flatMap(recordTags);
  const tags=unique([...list(item?.related_tags),...evidenceTags]);
  const logicTag=tags[0]||'';
  const records=[...evidence];
  const representedTags=new Set(evidenceTags);
  for(const tag of tags){
    if(representedTags.has(tag))continue;
    const related=relatedTagRecord(tag);
    if(related)records.push(related);
  }

  const targets=new Map();
  for(const row of records){
    const relatedTags=recordTags(row);
    const fallbackTag=relatedTags.find(tag=>tags.includes(tag))||'';
    const target=resolveDrawingTarget(row,fallbackTag);
    if(!target)continue;
    const key=`${target.view}:${target.equipment}`;
    const previous=targets.get(key);
    if(!previous||previous.kind==='tag'&&target.kind==='event')targets.set(key,target);
  }

  const drawingLinks=[...targets.values()].map(({equipment,href})=>({equipment,href}));
  return {logicTag,drawingLinks};
}
