'use client';

import {useMemo,useState} from 'react';
import {EVENT_DRAWING_MAP} from '../lib/eventDrawingMap.mjs';

const RAW='https://raw.githubusercontent.com/khaku25/triplens-thermosyspro-cloud-runner/main/topology/';
const VIEWS=[
  {id:'event',label:'EVENT 위치',title:'ECMS Event Overview',note:'EVENT registry의 사건을 전체 계통에서 한 위치로 찾는 1차 화면'},
  {id:'vpp',label:'VPP 계통',title:'ECMS VPP Overview',src:'triplens_ecms_vpp.svg',note:'GT/ST 주 변압기 · 6.9 kV BUS · FWP 전원계통'},
  {id:'sld',label:'6.9 kV',title:'6.9 kV SLD',src:'triplens_ecms_6p9kv.svg',note:'보조전원 BUS-A/B · 인커밍 · 타이 · FWP 피더'},
  {id:'bypass',label:'터빈 Bypass',title:'HPBP · LPBP',src:'turbine_bypass_vpp.svg',note:'HP Main Steam → Cold Reheat / Hot Reheat → Condenser 경로'},
  {id:'valves',label:'ThermoSys 밸브',title:'FMU Valve Overview',src:'fmu_valves_overview.svg',note:'ThermoSysPro 3.1 전체 모델에 FMU로 연결된 밸브 설비도'},
];

const VALVES=[
  ['HP_FWCV','HP-FWCV','HRSG','HP 드럼 급수조절밸브','valves/hp-fwcv.svg'],
  ['HP_STEAM_VLV','HP-STM-VLV','HRSG','HP 드럼 증기밸브','valves/hp-steam-vlv.svg'],
  ['IP_FWCV','IP-FWCV','HRSG','IP 드럼 급수조절밸브','valves/ip-fwcv.svg'],
  ['IP_STEAM_VLV','IP-STM-VLV','HRSG','IP 드럼 증기밸브','valves/ip-steam-vlv.svg'],
  ['LP_STEAM_VLV','LP-STM-VLV','HRSG','LP 드럼 증기조절밸브','valves/lp-steam-vlv.svg'],
  ['LP_FW_VLV','LP-FW-VLV','HRSG','LP 드럼 급수밸브','valves/lp-fw-vlv.svg'],
  ['LP_TO_HPIP_FW_VLV','LP-HPIP-FW-VLV','HRSG','LP → HP/IP 급수밸브','valves/lp-to-hpip-fw-vlv.svg'],
  ['COND_EXTRACTION_VLV','COND-EXT-VLV','BOP','복수기 수위조절 추출밸브','valves/cond-extraction-vlv.svg'],
  ['HP_TURB_ADM_VLV','HP-TURB-ADM-VLV','ST','HP 터빈 입구 조절밸브','valves/hp-turb-adm-vlv.svg'],
  ['HP_FW_ISO_VLV','HP-FW-ISO-VLV','HRSG','HP 급수펌프 토출측 밸브','valves/hp-fw-iso-vlv.svg'],
  ['IP_FW_ISO_VLV','IP-FW-ISO-VLV','HRSG','IP 급수펌프 토출측 밸브','valves/ip-fw-iso-vlv.svg'],
  ['IP_TURB_ADM_VLV','IP-TURB-ADM-VLV','ST','IP 터빈 입구 조절밸브','valves/ip-turb-adm-vlv.svg'],
].map(([id,equipment,system,service,src])=>({id,equipment,system,service,src}));

const LOC={
  GT:[90,150],GT_EXHAUST:[200,150],
  HP_DRUM:[390,125],IP_DRUM:[390,205],LP_DRUM:[390,285],
  HP_BFP:[330,405],IP_BFP:[430,405],LP_BFP:[530,405],
  HP_BFP_NRV:[365,365],IP_BFP_NRV:[465,365],LP_BFP_NRV:[565,365],
  HP_FEEDWATER:[390,155],IP_FEEDWATER:[390,235],LP_FEEDWATER:[390,315],
  HP_TURBINE:[760,125],IP_TURBINE:[865,205],LP_TURBINE:[970,285],ST:[1080,205],
  BUS_A:[390,565],BUS_B:[650,565],'CB-TIE-AB':[520,565],'CB-IN-A':[390,520],'CB-IN-B':[650,520],
  'VCB-A01':[320,620],'VCB-A02':[460,620],'VCB-B01':[650,620],
  HP_FWCV:[455,125],HP_STEAM_VLV:[510,125],IP_FWCV:[455,205],IP_STEAM_VLV:[510,205],
  LP_FW_VLV:[455,285],LP_STEAM_VLV:[510,285],LP_TO_HPIP_FW_VLV:[575,345],
  HP_TURB_ADM_VLV:[700,125],IP_TURB_ADM_VLV:[805,205],
  HP_FW_ISO_VLV:[350,345],IP_FW_ISO_VLV:[450,345],COND_EXTRACTION_VLV:[1060,365]
};

function drawingKey(e){
  if(!e)return '';
  if(LOC[e.location_id])return e.location_id;
  if(e.equipment==='52GT')return 'GT';
  if(e.equipment==='52ST')return 'ST';
  return '';
}

function Device({id,label,x,y,w=90,selected=false}){
  return <g>
    <rect x={x-w/2} y={y-22} width={w} height={44} rx="10" fill={selected?'#fff0b8':'#ffffff'} stroke={selected?'#c47a00':'#9db0bd'} strokeWidth={selected?4:1.6}/>
    <text x={x} y={y+5} textAnchor="middle" fontSize="14" fontWeight={selected?800:700} fill="#18354d">{label}</text>
  </g>;
}

function Dot({id,x,y,selected=false}){
  return <g><circle cx={x} cy={y} r={selected?11:7} fill={selected?'#d95c3f':'#7893a5'} stroke="white" strokeWidth="3"/></g>;
}

function EventOverview({event}){
  const key=drawingKey(event);
  const p=LOC[key];
  const sel=id=>id===key;
  const label=event?event.equipment+' · '+event.tag:'EVENT를 선택하세요';
  return <div style={{padding:12,overflow:'auto',background:'#f5f8fa'}}>
    <svg viewBox="0 0 1180 680" role="img" aria-label="ECMS 전체 계통 EVENT 위치" style={{display:'block',width:'100%',minWidth:900,background:'white',border:'1px solid #d6e0e6',borderRadius:12}}>
      <defs>
        <marker id="steamArrow" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto"><path d="M0 0 L9 4.5 L0 9z" fill="#cc5a50"/></marker>
        <marker id="waterArrow" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto"><path d="M0 0 L9 4.5 L0 9z" fill="#4587ad"/></marker>
      </defs>
      <text x="34" y="42" fontSize="24" fontWeight="800" fill="#17364d">ECMS Plant Overview</text>
      <text x="34" y="66" fontSize="13" fill="#647987">사건 위치를 먼저 보여주고, 상세 도면과 Tag/Logic은 다음 단계에서 확인</text>

      <rect x="35" y="92" width="235" height="125" rx="18" fill="#f4f7f9" stroke="#d5e0e7"/>
      <text x="55" y="118" fontSize="13" fontWeight="800" fill="#647987">GAS TURBINE / EXHAUST</text>
      <Device id="GT" label="GT" x={90} y={150} w={78} selected={sel('GT')}/>
      <Device id="GT_EXHAUST" label="EXHAUST" x={200} y={150} w={105} selected={sel('GT_EXHAUST')}/>
      <path d="M129 150 H147" stroke="#cc5a50" strokeWidth="5" markerEnd="url(#steamArrow)"/>

      <rect x="295" y="92" width="335" height="235" rx="18" fill="#f7fbfd" stroke="#cddde7"/>
      <text x="315" y="118" fontSize="13" fontWeight="800" fill="#647987">HRSG</text>
      <Device id="HP_DRUM" label="HP DRUM" x={390} y={145} w={105} selected={sel('HP_DRUM')}/>
      <Device id="IP_DRUM" label="IP DRUM" x={390} y={215} w={105} selected={sel('IP_DRUM')}/>
      <Device id="LP_DRUM" label="LP DRUM" x={390} y={285} w={105} selected={sel('LP_DRUM')}/>
      <text x="545" y="145" fontSize="12" fill="#6f8290">FWCV / Steam valve</text>
      <text x="545" y="215" fontSize="12" fill="#6f8290">FWCV / Steam valve</text>
      <text x="545" y="285" fontSize="12" fill="#6f8290">FW valve / Steam valve</text>
      {['HP_FWCV','HP_STEAM_VLV','IP_FWCV','IP_STEAM_VLV','LP_FW_VLV','LP_STEAM_VLV'].map(id=><Dot key={id} id={id} x={LOC[id][0]} y={LOC[id][1]} selected={sel(id)}/>)}

      <rect x="665" y="92" width="480" height="235" rx="18" fill="#fbf8f5" stroke="#e0d8cf"/>
      <text x="685" y="118" fontSize="13" fontWeight="800" fill="#647987">STEAM TURBINE TRAIN</text>
      <Device id="HP_TURBINE" label="HP TURB" x={760} y={145} w={100} selected={sel('HP_TURBINE')}/>
      <Device id="IP_TURBINE" label="IP TURB" x={865} y={215} w={100} selected={sel('IP_TURBINE')}/>
      <Device id="LP_TURBINE" label="LP TURB" x={970} y={285} w={100} selected={sel('LP_TURBINE')}/>
      <Device id="ST" label="ST / 52ST" x={1080} y={215} w={112} selected={sel('ST')}/>
      <Dot id="HP_TURB_ADM_VLV" x={700} y={145} selected={sel('HP_TURB_ADM_VLV')}/><Dot id="IP_TURB_ADM_VLV" x={805} y={215} selected={sel('IP_TURB_ADM_VLV')}/>
      <path d="M630 145 H700 H710" stroke="#cc5a50" strokeWidth="5" fill="none" markerEnd="url(#steamArrow)"/>
      <path d="M810 145 C825 145 825 215 815 215" stroke="#cc5a50" strokeWidth="5" fill="none"/>
      <path d="M915 215 C935 215 935 285 920 285" stroke="#cc5a50" strokeWidth="5" fill="none"/>

      <rect x="295" y="345" width="620" height="110" rx="18" fill="#f4f9fc" stroke="#d1e0e9"/>
      <text x="315" y="372" fontSize="13" fontWeight="800" fill="#647987">FEEDWATER / BFP</text>
      <Device id="HP_BFP" label="HP BFP" x={330} y={410} w={92} selected={sel('HP_BFP')}/>
      <Device id="IP_BFP" label="IP BFP" x={455} y={410} w={92} selected={sel('IP_BFP')}/>
      <Device id="LP_BFP" label="LP BFP" x={580} y={410} w={92} selected={sel('LP_BFP')}/>
      {['HP_BFP_NRV','IP_BFP_NRV','LP_BFP_NRV','HP_FW_ISO_VLV','IP_FW_ISO_VLV','LP_TO_HPIP_FW_VLV'].map(id=><Dot key={id} id={id} x={LOC[id][0]} y={LOC[id][1]} selected={sel(id)}/>)}
      <path d="M625 410 H700 V315" stroke="#4587ad" strokeWidth="5" fill="none" markerEnd="url(#waterArrow)"/>
      <text x="735" y="382" fontSize="12" fill="#6f8290">→ HRSG feedwater</text>

      <rect x="945" y="345" width="200" height="110" rx="18" fill="#f5faf7" stroke="#d6e5dc"/>
      <text x="965" y="372" fontSize="13" fontWeight="800" fill="#647987">CONDENSATE</text>
      <Device id="COND_EXTRACTION_VLV" label="CONDENSER" x={1045} y={410} w={118} selected={sel('COND_EXTRACTION_VLV')}/>

      <rect x="35" y="485" width="1110" height="155" rx="18" fill="#f7f5fb" stroke="#dad5e8"/>
      <text x="55" y="512" fontSize="13" fontWeight="800" fill="#647987">6.9 kV AUXILIARY POWER</text>
      <Device id="BUS_A" label="BUS-A" x={390} y={565} w={100} selected={sel('BUS_A')}/>
      <Device id="CB-TIE-AB" label="TIE" x={520} y={565} w={72} selected={sel('CB-TIE-AB')}/>
      <Device id="BUS_B" label="BUS-B" x={650} y={565} w={100} selected={sel('BUS_B')}/>
      <Device id="CB-IN-A" label="IN-A" x={390} y={520} w={80} selected={sel('CB-IN-A')}/>
      <Device id="CB-IN-B" label="IN-B" x={650} y={520} w={80} selected={sel('CB-IN-B')}/>
      <Device id="VCB-A01" label="A01" x={320} y={620} w={72} selected={sel('VCB-A01')}/>
      <Device id="VCB-A02" label="A02" x={460} y={620} w={72} selected={sel('VCB-A02')}/>
      <Device id="VCB-B01" label="B01" x={650} y={620} w={72} selected={sel('VCB-B01')}/>
      <path d="M440 565 H484 M556 565 H600" stroke="#765aa6" strokeWidth="4"/>

      {p?<g>
        <circle cx={p[0]} cy={p[1]} r="30" fill="none" stroke="#d84b3a" strokeWidth="4" strokeDasharray="7 5"/>
        <path d={'M'+p[0]+' '+(p[1]-30)+' C '+p[0]+' '+(p[1]-70)+' 865 470 880 470'} fill="none" stroke="#d84b3a" strokeWidth="2.5"/>
        <rect x="875" y="445" width="245" height="54" rx="10" fill="#fff8ee" stroke="#d84b3a" strokeWidth="2"/>
        <text x="892" y="467" fontSize="12" fontWeight="800" fill="#b13b2c">SELECTED EVENT</text>
        <text x="892" y="486" fontSize="12" fill="#5a6670">{label}</text>
      </g>:null}
    </svg>
  </div>;
}

export default function PlantDrawingMaster(){
  const [view,setView]=useState('event');
  const [selectedValve,setSelectedValve]=useState(null);
  const [eventQuery,setEventQuery]=useState('');
  const [valveQuery,setValveQuery]=useState('');
  const [selectedEvent,setSelectedEvent]=useState(EVENT_DRAWING_MAP[0]||null);
  const active=VIEWS.find(v=>v.id===view)||VIEWS[0];
  const events=useMemo(()=>{const q=eventQuery.trim().toLowerCase();return (q?EVENT_DRAWING_MAP.filter(e=>[e.rule_id,e.equipment,e.tag,e.active_message,e.source_node].join(' ').toLowerCase().includes(q)):EVENT_DRAWING_MAP).slice(0,80)},[eventQuery]);
  const valves=useMemo(()=>{const q=valveQuery.trim().toLowerCase();return q?VALVES.filter(v=>[v.id,v.equipment,v.system,v.service].join(' ').toLowerCase().includes(q)):VALVES},[valveQuery]);
  const currentSrc=selectedValve?selectedValve.src:active.src;
  const currentTitle=selectedValve?selectedValve.equipment:active.title;
  const currentNote=selectedValve?selectedValve.service:active.note;
  function chooseEvent(e){setSelectedEvent(e);setSelectedValve(null);setView('event')}
  function openDetail(){if(!selectedEvent)return;if(selectedEvent.view==='valves'){const v=VALVES.find(x=>x.id===selectedEvent.location_id);if(v){setSelectedValve(v);setView('valves');return}}setSelectedValve(null);if(selectedEvent.view!=='event')setView(selectedEvent.view)}
  return <main style={{minHeight:'100dvh',background:'#eef3f7',color:'#17324a'}}>
    <header style={{display:'flex',flexWrap:'wrap',alignItems:'center',justifyContent:'space-between',gap:12,padding:'12px 18px',background:'#17364d',color:'white'}}><div><div style={{fontSize:12,opacity:.75,fontWeight:700}}>TRIPLENS DRAWING MASTER</div><h1 style={{fontSize:20,margin:'3px 0 0'}}>ECMS EVENT → 설비 위치 → 상세 도면</h1></div><nav style={{display:'flex',gap:8,flexWrap:'wrap'}}><a href="/" style={topLink}>분석 화면</a><a href="/logic" style={topLink}>Logic View</a></nav></header>
    <section style={{display:'grid',gridTemplateColumns:'minmax(270px,350px) minmax(0,1fr)',gap:14,padding:14,maxWidth:1680,margin:'0 auto'}}>
      <aside style={panel}><div style={{display:'flex',justifyContent:'space-between'}}><h2 style={h2}>EVENT 1:1 위치</h2><span style={muted}>{EVENT_DRAWING_MAP.length} rules</span></div><p style={{...muted,lineHeight:1.5}}>rule_id 또는 정확한 equipment::tag로 한 사건을 한 위치에 연결합니다. Logic은 1:1로 강제하지 않습니다.</p><input value={eventQuery} onChange={e=>setEventQuery(e.target.value)} placeholder="LP BFP · TRIP_LATCH · LEVEL_LOW..." style={searchStyle}/><div style={{display:'grid',gap:6,maxHeight:300,overflow:'auto'}}>{events.map(e=><button key={e.rule_id} onClick={()=>chooseEvent(e)} style={equipmentStyle(selectedEvent&&selectedEvent.rule_id===e.rule_id&&view==='event')}><span><b>{e.equipment}</b> <small>{e.priority}</small></span><span style={small}>{e.tag}</span><span style={tiny}>{e.rule_id}</span></button>)}</div>
        <hr style={hr}/><h2 style={h2}>도면 계층</h2><div style={{display:'grid',gap:7}}>{VIEWS.map(v=><button key={v.id} onClick={()=>{setView(v.id);setSelectedValve(null)}} style={buttonStyle(view===v.id&&!selectedValve)}>{v.label}<small style={{display:'block',fontWeight:400,opacity:.7}}>{v.title}</small></button>)}</div>
        {view==='valves'?<><hr style={hr}/><h2 style={h2}>ThermoSys 밸브</h2><input value={valveQuery} onChange={e=>setValveQuery(e.target.value)} placeholder="HP FWCV · turbine..." style={searchStyle}/><div style={{display:'grid',gap:6,maxHeight:240,overflow:'auto'}}>{valves.map(v=><button key={v.id} onClick={()=>setSelectedValve(v)} style={equipmentStyle(selectedValve&&selectedValve.id===v.id)}><b>{v.equipment}</b><span style={small}>{v.service}</span></button>)}</div></>:null}
      </aside>
      <section style={{...panel,padding:0,overflow:'hidden'}}><div style={{display:'flex',flexWrap:'wrap',alignItems:'center',justifyContent:'space-between',gap:10,padding:'12px 14px',borderBottom:'1px solid #d8e2e9'}}><div><h2 style={{fontSize:18,margin:0}}>{view==='event'?'전체 계통 EVENT 위치':currentTitle}</h2><p style={{...muted,margin:'4px 0 0'}}>{view==='event'&&selectedEvent?selectedEvent.rule_id+' · '+selectedEvent.equipment+' · '+selectedEvent.tag:currentNote}</p></div><div style={{display:'flex',gap:8,flexWrap:'wrap'}}>{view==='event'&&selectedEvent?<button onClick={openDetail} style={smallButton}>관련 상세 도면</button>:null}{selectedEvent&&selectedEvent.source_node?<a href={'/logic?tag='+encodeURIComponent(selectedEvent.source_node)} style={{...smallButton,textDecoration:'none'}}>관련 Tag/Logic</a>:null}{view!=='event'?<button onClick={()=>{setView('event');setSelectedValve(null)}} style={smallButton}>← 전체 계통 위치</button>:null}</div></div>
        {view==='event'?<EventOverview event={selectedEvent}/>:<div style={{background:'#f7fafc',overflow:'auto',padding:10}}><object data={RAW+currentSrc} type="image/svg+xml" style={{width:'100%',minHeight:600,border:0,background:'white'}}><img src={RAW+currentSrc} alt={currentTitle}/></object></div>}
        {view==='event'&&selectedEvent?<div style={{padding:14,display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(170px,1fr))',gap:8}}><Info label="EVENT rule" value={selectedEvent.rule_id}/><Info label="Exact key" value={selectedEvent.lookup_key}/><Info label="Source" value={selectedEvent.source_node}/><Info label="Drawing location" value={selectedEvent.location_id}/></div>:null}
      </section>
    </section>
    <footer style={{maxWidth:1680,margin:'0 auto',padding:'0 16px 18px',fontSize:12,color:'#617685'}}>EVENT 67/67 exact mapping · Logic은 Tag를 통해 0..N 관계로 별도 탐색 · READ-ONLY · 운전/정비/LOTO용 아님</footer>
  </main>
}

function Info({label,value}){return <div style={{border:'1px solid #d7e1e7',borderRadius:8,padding:'9px 10px'}}><span style={{display:'block',fontSize:11,color:'#718490'}}>{label}</span><b style={{fontSize:12,overflowWrap:'anywhere'}}>{value||'—'}</b></div>}
const panel={background:'white',border:'1px solid #c9d6df',borderRadius:12,padding:12,minWidth:0};
const h2={fontSize:16,margin:'0 0 8px'}; const muted={fontSize:12,color:'#617685'}; const small={fontSize:12,color:'#5f7382'}; const tiny={fontSize:11,color:'#7a8c98'}; const hr={border:0,borderTop:'1px solid #dde5eb',margin:'14px 0'};
const topLink={color:'white',border:'1px solid rgba(255,255,255,.45)',borderRadius:7,padding:'7px 10px',textDecoration:'none',fontSize:13};
const smallButton={border:'1px solid #b8c8d2',background:'white',color:'#1b5f77',borderRadius:7,padding:'7px 10px',cursor:'pointer',fontSize:13};
const searchStyle={boxSizing:'border-box',width:'100%',margin:'9px 0',padding:'10px 11px',border:'1px solid #b9cad5',borderRadius:8,fontSize:14};
const buttonStyle=active=>({textAlign:'left',border:'1px solid '+(active?'#1c718a':'#c8d6df'),background:active?'#e9f5f8':'#f8fafb',color:'#17364d',borderRadius:8,padding:'9px 10px',cursor:'pointer',fontWeight:700});
const equipmentStyle=active=>({textAlign:'left',display:'grid',gap:3,border:'1px solid '+(active?'#9a6f13':'#d3dde4'),background:active?'#fff7d9':'white',color:'#203b50',borderRadius:8,padding:'9px 10px',cursor:'pointer'});