const uniq = values => [...new Set((values || []).filter(Boolean).map(String))];

export const DEVICE_TEST_CASES = [
  { id:'GT-LATCH', equipment:'GT', tag:'vppGTTripLatch', rule:'PROT-GT-LATCH' },
  { id:'ST-LATCH', equipment:'ST', tag:'vppSTTripLatchPublished', rule:'PROT-ST-LATCH' },
  { id:'52GT-TRIP', equipment:'52GT', tag:'vpp52GTTripCmd', rule:'SEQ-52GT-TRIPCMD' },
  { id:'52ST-TRIP', equipment:'52ST', tag:'vpp52STTripCmd', rule:'SEQ-52ST-TRIPCMD' },
  { id:'HP-FWP-TRIP', equipment:'HP FWP', tag:'vppHPFWPTripLatchNative', rule:'CMD-FWP-HP-TRIP' },
  { id:'IP-FWP-TRIP', equipment:'IP FWP', tag:'vppIPFWPTripLatchNative', rule:'CMD-FWP-IP-TRIP' },
  { id:'LP-FWP-TRIP', equipment:'LP FWP', tag:'vppLPFWPTripLatchNative', rule:'CMD-FWP-LP-TRIP' },
  { id:'HP-DRUM-LL', equipment:'HP DRUM', tag:'vppHPDrumLLRaw', rule:'PROT-HP-DRUM-LL' },
  { id:'IP-DRUM-LL', equipment:'IP DRUM', tag:'vppIPDrumLLRaw', rule:'PROT-IP-DRUM-LL' },
  { id:'LP-DRUM-LL', equipment:'LP DRUM', tag:'vppLPDrumLLRaw', rule:'PROT-LP-DRUM-LL' },
];

export function evaluateDeviceCases(index, cases = DEVICE_TEST_CASES) {
  const tags=index?.tags || {};
  const rules=index?.rules || {};
  const pages=index?.pages || {};
  return cases.map(item => {
    const tag=tags[item.tag];
    const rule=rules[item.rule];
    const checks={
      tag_master:Boolean(tag),
      logic_link:Boolean(tag?.rule_ids?.includes(item.rule)),
      logic_master:Boolean(rule),
      diagram_page:Boolean(rule?.rule_page && pages[rule.rule_page]),
    };
    return {...item,checks,status:Object.values(checks).every(Boolean)?'PASS':'FAIL',description:tag?.description_ko || tag?.description_en || ''};
  });
}

export function buildEvidenceLogicTargets(evidence = {}) {
  const rows=Array.isArray(evidence)?evidence:[evidence];
  const tags=uniq(rows.map(item=>item?.source_node || item?.canonical_tag || item?.tag));
  const rules=uniq(rows.flatMap(item=>item?.logic_ids||[]));
  const roles=rules.map(id=>({
    id,
    label:/TRIPCMD|COMMAND/i.test(id)?'Trip Command 연계':/OPEN/i.test(id)?'차단기 개방 순서':/LATCH|PROT/i.test(id)?'보호 래치':'연결 로직',
  }));
  return {tags,rules,roles,entry:tags.length?{tag:tags[0],ruleCount:rules.length}:null};
}

function evidenceFor(ids, catalog) {
  const wanted=new Set(uniq(ids));
  return catalog.filter(item => wanted.has(String(item.evidence_id || item.event_id))).map(item => ({
    source_system:item.source || item.source_kind || '',
    event_id:item.evidence_id || item.event_id || '',
    original_time:item.model_time_s ?? '',
    aligned_time:item.model_time_s ?? '',
    equipment:item.equipment || '',
    event_tag:item.original_tag || item.tag || '',
    canonical_tag:item.canonical_tag || item.source_node || '',
    value:item.value ?? '',
    unit:item.unit || '',
    state:item.state || '',
    evidence_role:item.evidence_role || '',
    logic_id:uniq(item.logic_ids).join('; '),
    mapping_status:item.mapping_status || '',
  }));
}

function enrichClaim(value, catalog) {
  if (!value || typeof value !== 'object') return value;
  return {
    ...value,
    recorded_time:value.recorded_time ?? value.model_time_s ?? '',
    evidence:evidenceFor(value.evidence_ids, catalog),
  };
}

export function buildExportReport({result={},analysis={},events=[],catalog=[],reportRows=[],eventFileName='EVENT.csv',rawFileName='RAW.csv'}) {
  result=result || {};
  analysis=analysis || {};
  events=events || [];
  catalog=catalog || [];
  reportRows=reportRows || [];
  const critical=(analysis.critical_events || []).map(value => enrichClaim(value,catalog));
  const primary=enrichClaim(analysis.primary_cause || {},catalog);
  const direct=enrichClaim(analysis.direct_trigger || {},catalog);
  const propagation=(analysis.propagation || []).map(value => enrichClaim(value,catalog));
  const chain=(analysis.causal_chain || []).map(value => enrichClaim(value,catalog));
  const counter=(analysis.counter_evidence || []).map(value => enrichClaim(value,catalog));
  return {
    run_id:result.run_id || '',
    data_digest:result.data_digest || '',
    verification_gate:analysis.verification_gate || 'HOLD',
    metadata:{run_id:result.run_id || '',event_file:eventFileName,raw_file:rawFileName,data_digest:result.data_digest || '',analysis_engine:'Gemini Tool Analysis'},
    incident_summary:critical[0]?.claim || direct?.claim || 'EVENT + RAW 사고분석 결과',
    critical_events:critical,
    primary_cause:primary,
    direct_trigger:direct,
    propagation,
    causal_chain:chain,
    counter_evidence:counter,
    additional_evidence_required:analysis.additional_evidence_required || [],
    review_recommendations:analysis.review_recommendations || [],
    recovery_check:'UNKNOWN · 실제 복구 기록 및 담당자 승인 필요',
    report_rows:reportRows.map(row => ({...row})),
    chronological_events:[...events].sort((a,b)=>{
      const left=a.model_time_s===null||a.model_time_s===undefined||String(a.model_time_s).trim()===''?Infinity:Number(a.model_time_s);
      const right=b.model_time_s===null||b.model_time_s===undefined||String(b.model_time_s).trim()===''?Infinity:Number(b.model_time_s);
      return (Number.isFinite(left)?left:Infinity)-(Number.isFinite(right)?right:Infinity);
    }).map(event => ({
      wall_time_utc:event.wall_time_utc || '',
      model_time_s:event.model_time_s ?? null,
      equipment:event.equipment || '',
      recorded_time:event.model_time_s ?? '',
      category:event.event_class || event.source || 'EVENT',
      claim:event.message || `${event.equipment || ''} ${event.tag || ''}`.trim(),
      status:'OBSERVED',
      evidence_ids:(event.evidence_ids?.length?event.evidence_ids:[event.evidence_id || event.event_id]).filter(Boolean),
      related_tags:(event.related_tags?.length?event.related_tags:[event.source_node || event.tag]).filter(Boolean),
    })),
    sections:[
      {id:'critical_events',title:'Critical Events',value:critical},
      {id:'primary_cause',title:'Primary Cause',value:primary},
      {id:'direct_trigger',title:'Direct Trigger',value:direct},
      {id:'propagation',title:'Propagation',value:propagation},
      {id:'causal_chain',title:'Causal Chain',value:chain},
      {id:'counter_evidence',title:'Counter Evidence',value:counter},
    ],
  };
}
