'use client';

import {useMemo,useState} from 'react';
import {EVENT_DRAWING_MAP} from '../lib/eventDrawingMap.mjs';

const RAW='https://raw.githubusercontent.com/khaku25/triplens-thermosyspro-cloud-runner/main/topology/';
const VIEWS=[
  {id:'event',label:'EVENT 위치',title:'ECMS Event Overview',note:'EVENT registry의 각 사건을 전체 계통에서 한 위치로 찾는 1차 화면'},
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

const POINTS={GT:[80,90],GT_EXHAUST:[170,90],HP_DRUM:[300,50],IP_DRUM:[300,110],LP_DRUM:[300,170],HP_FEEDWATER:[300,235],IP_FEEDWATER:[300,285],LP_FEEDWATER:[300,335],HP_BFP:[165,235],IP_BFP:[165,285],LP_BFP:[165,335],HP_BFP_NRV:[235,235],IP_BFP_NRV:[235,285],LP_BFP_NRV:[235,335],HP_TURBINE:[475,70],IP_TURBINE:[565,110],LP_TURBINE:[655,150],ST:[750,110],BUS_A:[115,430],BUS_B:[300,430],'CB-IN-A':[115,475],'CB-IN-B':[300,475],'CB-TIE-AB':[210,430],'VCB-A01':[75,520],'VCB-A02':[165,520],'VCB-B01':[300,520],HP_FWCV:[355,50],HP_STEAM_VLV:[405,50],IP_FWCV:[355,110],IP_STEAM_VLV:[405,110],LP_FW_VLV:[355,170],LP_STEAM_VLV:[405,170],HP_TURB_ADM_VLV:[430,70],IP_TURB_ADM_VLV:[520,110],HP_FW_ISO_VLV:[265,235],IP_FW_ISO_VLV:[265,285],LP_TO_HPIP_FW_VLV:[355,235],COND_EXTRACTION_VLV:[750,235]};

function keyFor(e){return e&&POINTS[e.location_id]?e.location_id:(e&&e.equipment==='52GT'?'GT':e&&e.equipment==='52ST'?'ST':'');}
function Box({id,label,x,y,w=78,selected}){return <g><rect x={x-w/2} y={y-17} width={w} height={34} rx="7" fill={selected?'#fff1ad':'#f8fafc'} stroke={selected?'#bc7900':'#91a5b3'} strokeWidth={selected?4:1.5}/><text x={x} y={y+4} textAnchor="middle" fontSize="11" fontWeight={selected?800:650} fill="#18354d">{label}</text></g>}
function EventOverview({event}){
  const key=keyFor(event); const at=id=>id===key; const p=POINTS[key];
  return <div style={{padding:10,overflow:'auto',background:'#f7fafc'}}><svg viewBox="0 0 830 560" aria-label="ECMS 전체 EVENT 위치 개요" style={{width:'100%',minWidth:700,background:'white',border:'1px solid #d5e0e7',borderRadius:10}}>
    <text x="25" y="28" fontSize="18" fontWeight="800" fill="#17364d">ECMS EVENT Location Overview</text><text x="25" y="47" fontSize="11" fill="#657986">EVENT exact identity → 전체 계통 위치 → 상세 도면 → Tag/Logic</text>
    <path d="M115 90 H130 M210 90 H255 M340 70 H430 M515 100 H520 M605 130 H615 M695 150 H740" stroke="#c75a50" strokeWidth="4" fill="none"/>
    <path d="M165 235 H285 M165 285 H285 M165 335 H285" stroke="#3d82ad" strokeWidth="4" fill="none"/>
    <path d="M115 430 H300 M210 430 V410 H750 V130" stroke="#6d57a3" strokeWidth="3" fill="none"/>
    <Box id="GT" label="GT" x={80} y={90} selected={at('GT')}/><Box id="GT_EXHAUST" label="GT EXHAUST" x={170} y={90} w={94} selected={at('GT_EXHAUST')}/>
    <Box id="HP_DRUM" label="HP DRUM" x={300} y={50} selected={at('HP_DRUM')}/><Box id="IP_DRUM" label="IP DRUM" x={300} y={110} selected={at('IP_DRUM')}/><Box id="LP_DRUM" label="LP DRUM" x={300} y={170} selected={at('LP_DRUM')}/>
    <Box id="HP_BFP" label="HP BFP" x={165} y={235} selected={at('HP_BFP')}/><Box id="HP_BFP_NRV" label="NRV" x={235} y={235} w={52} selected={at('HP_BFP_NRV')}/><Box id="HP_FEEDWATER" label="HP FW" x={300} y={235} selected={at('HP_FEEDWATER')}/>
    <Box id="IP_BFP" label="IP BFP" x={165} y={285} selected={at('IP_BFP')}/><Box id="IP_BFP_NRV" label="NRV" x={235} y={285} w={52} selected={at('IP_BFP_NRV')}/><Box id="IP_FEEDWATER" label="IP FW" x={300} y={285} selected={at('IP_FEEDWATER')}/>
    <Box id="LP_BFP" label="LP BFP" x={165} y={335} selected={at('LP_BFP')}/><Box id="LP_BFP_NRV" label="NRV" x={235} y={335} w={52} selected={at('LP_BFP_NRV')}/><Box id="LP_FEEDWATER" label="LP FW" x={300} y={335} selected={at('LP_FEEDWATER')}/>
    <Box id="HP_TURBINE" label="HP TURB" x={475} y={70} selected={at('HP_TURBINE')}/><Box id="IP_TURBINE" label="IP TURB" x={565} y={110} selected={at('IP_TURBINE')}/><Box id="LP_TURBINE" label="LP TURB" x={655} y={150} selected={at('LP_TURBINE')}/><Box id="ST" label="ST/52ST" x={750} y={110} selected={at('ST')}/>
    <Box id="BUS_A" label="BUS-A" x={115} y={430} selected={at('BUS_A')}/><Box id="BUS_B" label="BUS-B" x={300} y={430} selected={at('BUS_B')}/><Box id="CB-TIE-AB" label="TIE" x={210} y={430} w={52} selected={at('CB-TIE-AB')}/>
    <Box id="CB-IN-A" label="IN-A" x={115} y={475} w={58} selected={at('CB-IN-A')}/><Box id="CB-IN-B" label="IN-B" x={300} y={475} w={58} selected={at('CB-IN-B')}/><Box id="VCB-A01" label="A01" x={75} y={520} w={52} selected={at('VCB-A01')}/><Box id="VCB-A02" label="A02" x={165} y={520} w={52} selected={at('VCB-A02')}/><Box id="VCB-B01" label="B01" x={300} y={520} w={52} selected={at('VCB-B01')}/>
    {['HP_FWCV','HP_STEAM_VLV','IP_FWCV','IP_STEAM_VLV','LP_FW_VLV','LP_STEAM_VLV','HP_TURB_ADM_VLV','IP_TURB_ADM_VLV','HP_FW_ISO_VLV','IP_FW_ISO_VLV','LP_TO_HPIP_FW_VLV','COND_EXTRACTION_VLV'].map(id=>{const q=POINTS[id];return <Box key={id} id={id} label={id.replaceAll('_',' ')} x={q[0]} y={q[1]} w={68} selected={at(id)}/>})}
    {p?<g><circle cx={p[0]} cy={p[1]} r="26" fill="none" stroke="#d24b3e" strokeWidth="4" strokeDasharray="6 4"/><text x={p[0]} y={p[1]-30} textAnchor="middle" fontSize="10" fontWeight="800" fill="#b23a30">SELECTED EVENT</text></g>:null}
  </svg></div>
}

export default function PlantDrawingMaster(){
  const [view,setView]=useState('event'); const [selectedValve,setSelectedValve]=useState(null); const [eventQuery,setEventQuery]=useState(''); const [valveQuery,setValveQuery]=useState(''); const [selectedEvent,setSelectedEvent]=useState(EVENT_DRAWING_MAP[0]||null);
  const active=VIEWS.find(v=>v.id===view)||VIEWS[0];
  const events=useMemo(()=>{const q=eventQuery.trim().toLowerCase();return (q?EVENT_DRAWING_MAP.filter(e=>[e.rule_id,e.equipment,e.tag,e.active_message,e.source_node].join(' ').toLowerCase().includes(q)):EVENT_DRAWING_MAP).slice(0,80)},[eventQuery]);
  const valves=useMemo(()=>{const q=valveQuery.trim().toLowerCase();return q?VALVES.filter(v=>[v.id,v.equipment,v.system,v.service].join(' ').toLowerCase().includes(q)):VALVES},[valveQuery]);
  const currentSrc=selectedValve?selectedValve.src:active.src; const currentTitle=selectedValve?selectedValve.equipment:active.title; const currentNote=selectedValve?selectedValve.service:active.note;
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
const panel={background:'white',border:'1px solid #c9d6df',borderRadius:12,padding:12,minWidth:0}; const h2={fontSize:16,margin:'0 0 8px'}; const muted={fontSize:12,color:'#617685'}; const small={fontSize:12,color:'#5f7382'}; const tiny={fontSize:11,color:'#7a8c98'}; const hr={border:0,borderTop:'1px solid #dde5eb',margin:'14px 0'};
const topLink={color:'white',border:'1px solid rgba(255,255,255,.45)',borderRadius:7,padding:'7px 10px',textDecoration:'none',fontSize:13}; const smallButton={border:'1px solid #b8c8d2',background:'white',color:'#1b5f77',borderRadius:7,padding:'7px 10px',cursor:'pointer',fontSize:13}; const searchStyle={boxSizing:'border-box',width:'100%',margin:'9px 0',padding:'10px 11px',border:'1px solid #b9cad5',borderRadius:8,fontSize:14};
const buttonStyle=active=>({textAlign:'left',border:'1px solid '+(active?'#1c718a':'#c8d6df'),background:active?'#e9f5f8':'#f8fafb',color:'#17364d',borderRadius:8,padding:'9px 10px',cursor:'pointer',fontWeight:700}); const equipmentStyle=active=>({textAlign:'left',display:'grid',gap:3,border:'1px solid '+(active?'#9a6f13':'#d3dde4'),background:active?'#fff7d9':'white',color:'#203b50',borderRadius:8,padding:'9px 10px',cursor:'pointer'});