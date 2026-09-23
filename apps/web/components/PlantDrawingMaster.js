'use client';

import {useEffect,useMemo,useState} from 'react';
import InlineSvgNavigator from './InlineSvgNavigator';
import {EQUIPMENT_DRAWING_MASTER,resolveEquipmentDrawing} from '../lib/equipmentDrawingMaster.mjs';

const PLANT_POS={
  GT:[95,150],GT_EXHAUST:[210,150],HP_DRUM:[390,125],IP_DRUM:[390,205],LP_DRUM:[390,285],
  HP_BFP:[330,410],IP_BFP:[455,410],LP_BFP:[580,410],HP_BFP_NRV:[365,365],IP_BFP_NRV:[490,365],LP_BFP_NRV:[615,365],
  HP_FEEDWATER:[390,155],IP_FEEDWATER:[390,235],LP_FEEDWATER:[390,315],HP_TURBINE:[760,125],IP_TURBINE:[875,205],LP_TURBINE:[990,285],ST:[1090,205],
  HP_FWCV:[455,125],HP_STEAM_VLV:[515,125],IP_FWCV:[455,205],IP_STEAM_VLV:[515,205],LP_FW_VLV:[455,285],LP_STEAM_VLV:[515,285],
  HP_TURB_ADM_VLV:[700,125],IP_TURB_ADM_VLV:[815,205],HP_FW_ISO_VLV:[350,365],IP_FW_ISO_VLV:[475,365],LP_TO_HPIP_FW_VLV:[600,365],COND_EXTRACTION_VLV:[1060,410]
};

function Device({id,label,x,y,w=96,selected=false}){
  return <g><rect x={x-w/2} y={y-22} width={w} height={44} rx="10" fill={selected?'#fff0b8':'#fff'} stroke={selected?'#c47a00':'#9db0bd'} strokeWidth={selected?4:1.6}/><text x={x} y={y+5} textAnchor="middle" fontSize="14" fontWeight={selected?800:700} fill="#18354d">{label}</text></g>;
}
function Dot({x,y,selected}){return <circle cx={x} cy={y} r={selected?11:7} fill={selected?'#d95c3f':'#7893a5'} stroke="#fff" strokeWidth="3"/>}

function PlantOverview({equipment}){
  const key=equipment?.plant_location_id||'';
  const pos=PLANT_POS[key];
  const at=id=>id===key;
  return <div style={{padding:12,overflow:'auto',background:'#f5f8fa'}}><svg viewBox="0 0 1180 500" role="img" aria-label="Plant Overview" style={{display:'block',width:'100%',minWidth:900,background:'#fff',border:'1px solid #d6e0e6',borderRadius:12}}>
    <text x="34" y="40" fontSize="24" fontWeight="800" fill="#17364d">Plant Overview</text><text x="34" y="63" fontSize="13" fill="#647987">공정 설비의 전체 위치 확인 · ECMS와 독립된 Plant 페이지</text>
    <rect x="35" y="88" width="235" height="135" rx="18" fill="#f4f7f9" stroke="#d5e0e7"/><text x="55" y="115" fontSize="13" fontWeight="800" fill="#647987">GT / EXHAUST</text><Device id="GT" label="GT" x={95} y={160} w={80} selected={at('GT')}/><Device id="GT_EXHAUST" label="EXHAUST" x={210} y={160} w={105} selected={at('GT_EXHAUST')}/>
    <rect x="295" y="88" width="335" height="235" rx="18" fill="#f7fbfd" stroke="#cddde7"/><text x="315" y="115" fontSize="13" fontWeight="800" fill="#647987">HRSG</text><Device id="HP_DRUM" label="HP DRUM" x={390} y={145} w={105} selected={at('HP_DRUM')}/><Device id="IP_DRUM" label="IP DRUM" x={390} y={215} w={105} selected={at('IP_DRUM')}/><Device id="LP_DRUM" label="LP DRUM" x={390} y={285} w={105} selected={at('LP_DRUM')}/>
    {['HP_FWCV','HP_STEAM_VLV','IP_FWCV','IP_STEAM_VLV','LP_FW_VLV','LP_STEAM_VLV'].map(id=>{const p=PLANT_POS[id];return <Dot key={id} x={p[0]} y={p[1]} selected={at(id)}/>})}
    <rect x="665" y="88" width="480" height="235" rx="18" fill="#fbf8f5" stroke="#e0d8cf"/><text x="685" y="115" fontSize="13" fontWeight="800" fill="#647987">STEAM TURBINE TRAIN</text><Device id="HP_TURBINE" label="HP TURB" x={760} y={145} selected={at('HP_TURBINE')}/><Device id="IP_TURBINE" label="IP TURB" x={875} y={215} selected={at('IP_TURBINE')}/><Device id="LP_TURBINE" label="LP TURB" x={990} y={285} selected={at('LP_TURBINE')}/><Device id="ST" label="ST" x={1090} y={215} w={80} selected={at('ST')}/><Dot x={700} y={145} selected={at('HP_TURB_ADM_VLV')}/><Dot x={815} y={215} selected={at('IP_TURB_ADM_VLV')}/>
    <rect x="295" y="345" width="620" height="115" rx="18" fill="#f4f9fc" stroke="#d1e0e9"/><text x="315" y="372" fontSize="13" fontWeight="800" fill="#647987">FEEDWATER / BFP</text><Device id="HP_BFP" label="HP BFP" x={330} y={415} selected={at('HP_BFP')}/><Device id="IP_BFP" label="IP BFP" x={455} y={415} selected={at('IP_BFP')}/><Device id="LP_BFP" label="LP BFP" x={580} y={415} selected={at('LP_BFP')}/>{['HP_BFP_NRV','IP_BFP_NRV','LP_BFP_NRV','HP_FW_ISO_VLV','IP_FW_ISO_VLV','LP_TO_HPIP_FW_VLV'].map(id=>{const p=PLANT_POS[id];return <Dot key={id} x={p[0]} y={p[1]} selected={at(id)}/>})}
    <rect x="945" y="345" width="200" height="115" rx="18" fill="#f5faf7" stroke="#d6e5dc"/><text x="965" y="372" fontSize="13" fontWeight="800" fill="#647987">CONDENSATE</text><Device id="COND_EXTRACTION_VLV" label="CONDENSER" x={1060} y={415} w={120} selected={at('COND_EXTRACTION_VLV')}/>
    {pos?<circle cx={pos[0]} cy={pos[1]} r="30" fill="none" stroke="#d84b3a" strokeWidth="4" strokeDasharray="7 5"/>:null}
  </svg></div>;
}

function DetailAsset({row}){
  if(!row?.detail_asset)return <Empty text="등록된 상세도면이 없습니다."/>;
  return <div style={{padding:12,background:'#f5f8fa',overflow:'auto'}}><object data={'/'+row.detail_asset} type="image/svg+xml" aria-label={row.event_equipment+' 상세도면'} style={{display:'block',width:'100%',minHeight:620,border:0,background:'#fff',borderRadius:10}}><img src={'/'+row.detail_asset} alt={row.event_equipment}/></object></div>;
}

export default function PlantDrawingMaster(){
  const [query,setQuery]=useState('');
  const [selected,setSelected]=useState(null);
  const [screen,setScreen]=useState('ecms-overview');
  const [manualFocus,setManualFocus]=useState('');

  const filtered=useMemo(()=>{
    const q=query.trim().toLowerCase();
    return q?EQUIPMENT_DRAWING_MASTER.filter(x=>[x.equipment_id,x.event_equipment,x.aliases,x.equipment_type].join(' ').toLowerCase().includes(q)):EQUIPMENT_DRAWING_MASTER;
  },[query]);

  useEffect(()=>{
    const params=new URLSearchParams(window.location.search);
    const equipment=params.get('equipment')||params.get('eq');
    if(!equipment)return;
    const row=resolveEquipmentDrawing(equipment);
    if(!row)return;
    setSelected(row);
    const requested=params.get('view');
    if(requested==='plant'&&row.plant_location_id){setScreen('plant');return;}
    if(row.ecms_page==='ECMS_6P9KV'){setScreen('ecms-detail');setManualFocus('');return;}
    if(row.ecms_page==='ECMS_VPP'){setScreen('ecms-overview');setManualFocus('');return;}
    if(row.plant_location_id){setScreen('plant');return;}
    if(row.detail_asset)setScreen('detail');
  },[]);

  function goEquipment(row){
    setSelected(row);
    setManualFocus('');
    if(row.ecms_page==='ECMS_6P9KV')setScreen('ecms-detail');
    else if(row.ecms_page==='ECMS_VPP')setScreen('ecms-overview');
    else if(row.plant_location_id)setScreen('plant');
    else if(row.detail_asset)setScreen('detail');
  }

  function overviewNavigate(view){
    if(view==='BUS-A'||view==='BUS-B'){
      setSelected(resolveEquipmentDrawing(view));
      setManualFocus(view);
      setScreen('ecms-detail');
    }
  }

  function equipmentClicked(id){
    const row=resolveEquipmentDrawing(id);
    if(row)setSelected(row);
  }

  const overviewHighlight=screen==='ecms-overview'&&selected?.ecms_page==='ECMS_VPP'?selected.ecms_location_id:'';
  const detailHighlight=screen==='ecms-detail'?(manualFocus||(selected?.ecms_page==='ECMS_6P9KV'?selected.ecms_location_id:'')):'';

  return <main style={{minHeight:'100dvh',background:'#eef3f7',color:'#17324a'}}>
    <header style={{display:'flex',flexWrap:'wrap',justifyContent:'space-between',alignItems:'center',gap:12,padding:'12px 18px',background:'#17364d',color:'#fff'}}>
      <div><div style={{fontSize:12,opacity:.75,fontWeight:700}}>TRIPLENS DRAWING MASTER</div><h1 style={{fontSize:20,margin:'3px 0 0'}}>Overview 탐색 + EVENT Direct Jump</h1></div>
      <div style={{display:'flex',gap:8,flexWrap:'wrap'}}><a href="/" style={topLink}>← 분석 화면</a><a href="/logic" style={topLink}>Logic</a></div>
    </header>

    <section className="dm-layout" style={{display:'grid',gridTemplateColumns:'minmax(260px,330px) minmax(0,1fr)',gap:14,padding:14,maxWidth:1680,margin:'0 auto'}}>
      <aside style={panel}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}><h2 style={h2}>Equipment</h2><span style={muted}>{EQUIPMENT_DRAWING_MASTER.length}</span></div>
        <input value={query} onChange={e=>setQuery(e.target.value)} placeholder="LP BFP · BUS TIE · VCB-A02..." style={searchStyle}/>
        <div style={{display:'grid',gap:6,maxHeight:360,overflow:'auto'}}>{filtered.map(row=><button key={row.equipment_id} type="button" onClick={()=>goEquipment(row)} style={equipmentStyle(selected?.equipment_id===row.equipment_id)}><b>{row.event_equipment}</b><span style={tiny}>{row.equipment_id}</span></button>)}</div>
        <hr style={hr}/>
        <h2 style={h2}>수동 탐색</h2>
        <button type="button" onClick={()=>{setScreen('ecms-overview');setManualFocus('')}} style={navButton(screen==='ecms-overview')}>ECMS Overview</button>
        <button type="button" onClick={()=>setScreen('plant')} style={navButton(screen==='plant')}>Plant Overview</button>
        {selected?.detail_asset?<button type="button" onClick={()=>setScreen('detail')} style={navButton(screen==='detail')}>선택 설비 상세도면</button>:null}
        <p style={{...muted,lineHeight:1.5,marginTop:12}}>Overview에서는 도면을 직접 클릭해 들어가고, EVENT에서는 <code>?equipment=...</code>로 같은 상세 페이지에 바로 진입합니다.</p>
      </aside>

      <section style={{...panel,padding:0,overflow:'hidden'}}>
        <div style={{padding:'12px 14px',borderBottom:'1px solid #d7e1e7',display:'flex',flexWrap:'wrap',justifyContent:'space-between',alignItems:'center',gap:10}}>
          <div>
            <h2 style={{fontSize:19,margin:0}}>{screen==='ecms-overview'?'ECMS Overview':screen==='ecms-detail'?'6.9 kV SWGR Detail':screen==='plant'?'Plant Overview':'Equipment Detail'}</h2>
            <p style={{...muted,margin:'4px 0 0'}}>{selected?selected.event_equipment+' · '+selected.notes:'도면에서 영역을 클릭하거나 Equipment를 선택하세요.'}</p>
          </div>
          <div style={{display:'flex',gap:7,flexWrap:'wrap'}}>
            {screen==='ecms-detail'?<button type="button" onClick={()=>{setScreen('ecms-overview');setManualFocus('')}} style={smallButton}>← ECMS Overview</button>:null}
            {selected?.plant_location_id&&screen!=='plant'?<button type="button" onClick={()=>setScreen('plant')} style={smallButton}>Plant 위치</button>:null}
            {selected?.ecms_location_id&&screen==='plant'?<button type="button" onClick={()=>selected.ecms_page==='ECMS_6P9KV'?setScreen('ecms-detail'):setScreen('ecms-overview')} style={smallButton}>ECMS 위치</button>:null}
          </div>
        </div>

        {screen==='ecms-overview'?<div style={canvas}><InlineSvgNavigator src="/drawing/ecms-overview.svg" title="ECMS Overview" highlight={overviewHighlight} onView={overviewNavigate} onEquipment={equipmentClicked}/></div>:null}
        {screen==='ecms-detail'?<><div style={selectionBar}><b>Direct detail</b><span>{detailHighlight||'BUS를 선택하세요'}</span></div><div style={canvas}><InlineSvgNavigator src="/drawing/ecms-6p9kv.svg" title="6.9 kV SWGR Detail" highlight={detailHighlight} onEquipment={equipmentClicked}/></div></>:null}
        {screen==='plant'?<PlantOverview equipment={selected}/>:null}
        {screen==='detail'?<DetailAsset row={selected}/>:null}

        {selected?<div style={{padding:14,display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(170px,1fr))',gap:8,borderTop:'1px solid #e1e8ed'}}>
          <Info label="Equipment ID" value={selected.equipment_id}/><Info label="Plant" value={selected.plant_location_id}/><Info label="ECMS page" value={selected.ecms_page}/><Info label="ECMS location" value={selected.ecms_location_id}/><Info label="Detail" value={selected.detail_asset}/>
        </div>:null}
      </section>
    </section>
    <footer style={{maxWidth:1680,margin:'0 auto',padding:'0 16px 18px',fontSize:12,color:'#617685'}}>수동: Overview → 내부 상세 · EVENT: equipment → 동일 상세로 Direct Jump · Equipment Master exact mapping · READ-ONLY</footer>
    <style jsx global>{'@media(max-width:860px){.dm-layout{grid-template-columns:1fr!important;padding:8px!important}.dm-inline-svg{overflow:auto}.dm-inline-svg svg{min-width:760px}}'}</style>
  </main>;
}

function Empty({text}){return <div style={{padding:30,color:'#617685'}}>{text}</div>}
function Info({label,value}){return <div style={{border:'1px solid #d7e1e7',borderRadius:8,padding:'9px 10px'}}><span style={{display:'block',fontSize:11,color:'#718490'}}>{label}</span><b style={{fontSize:12,overflowWrap:'anywhere'}}>{value||'—'}</b></div>}
const panel={background:'#fff',border:'1px solid #c9d6df',borderRadius:12,minWidth:0,padding:12};
const canvas={padding:12,background:'#f5f8fa',overflow:'auto'};
const h2={fontSize:16,margin:'0 0 8px'}; const muted={fontSize:12,color:'#617685'}; const tiny={fontSize:11,color:'#7a8c98'}; const hr={border:0,borderTop:'1px solid #dde5eb',margin:'14px 0'};
const searchStyle={boxSizing:'border-box',width:'100%',margin:'9px 0',padding:'10px 11px',border:'1px solid #b9cad5',borderRadius:8,fontSize:14};
const topLink={color:'#fff',border:'1px solid rgba(255,255,255,.45)',borderRadius:7,padding:'7px 10px',textDecoration:'none',fontSize:13};
const smallButton={border:'1px solid #b8c8d2',background:'#fff',color:'#1b5f77',borderRadius:7,padding:'7px 10px',cursor:'pointer',fontSize:13};
const selectionBar={display:'flex',gap:10,alignItems:'center',flexWrap:'wrap',padding:'9px 14px',background:'#f6f9fb',borderBottom:'1px solid #dbe4ea',fontSize:12,color:'#5e7280'};
const equipmentStyle=active=>({textAlign:'left',display:'grid',gap:3,border:'1px solid '+(active?'#1c718a':'#d3dde4'),background:active?'#e9f5f8':'#fff',color:'#203b50',borderRadius:8,padding:'9px 10px',cursor:'pointer'});
const navButton=active=>({width:'100%',textAlign:'left',marginBottom:6,border:'1px solid '+(active?'#1c718a':'#c8d6df'),background:active?'#e9f5f8':'#fff',color:'#17364d',borderRadius:8,padding:'9px 10px',cursor:'pointer',fontWeight:700});
