'use client';

import {useEffect,useMemo,useState} from 'react';
import InlineSvgNavigator from './InlineSvgNavigator';
import ProcessViewCanvas from './ProcessViewCanvas';
import {EQUIPMENT_DRAWING_MASTER,resolveEquipmentDrawing} from '../lib/equipmentDrawingMaster.mjs';
import {PLANT_PROCESS} from '../lib/plantHotspots.mjs';
import {resolvePlantFocus} from '../lib/plantDrawingFocus.mjs';

const detailOnlyValves=EQUIPMENT_DRAWING_MASTER.filter(row=>
  row.equipment_type==='VALVE'&&row.detail_asset&&!PLANT_PROCESS.hotspots[row.plant_location_id]);

function DetailAsset({row,eventLabel}){
  if(!row?.detail_asset)return <Empty text="등록된 상세도면이 없습니다."/>;
  const valveAsset=row.detail_asset.startsWith('topology/valves/');
  const src='/'+row.detail_asset;
  return <div style={{padding:12,background:'#f5f8fa'}}>
    {eventLabel?<div className="valve-event-focus" role="status" style={{padding:'10px 12px',marginBottom:10,border:'2px solid #e65b31',borderRadius:8,background:'#fff0e8',color:'#9b2c19',fontWeight:800}}>{eventLabel} · {row.event_equipment}</div>:null}
    {valveAsset&&!PLANT_PROCESS.hotspots[row.plant_location_id]?<p style={{margin:'0 0 10px',fontSize:13,color:'#496476'}}>v36 전체 공정도에 개별 심볼이 없어 등록된 밸브 상세도면을 표시합니다.</p>:null}
    <div style={{overflowX:'auto',maxWidth:'100%'}}><div style={{position:'relative',width:valveAsset?1000:512,height:valveAsset?700:512,background:'#fff'}}>
      <object data={src} type="image/svg+xml" aria-label={row.event_equipment+' 상세도면'} style={{display:'block',width:'100%',height:'100%',border:0}}><img src={src} alt={row.event_equipment}/></object>
      {valveAsset?<div aria-hidden="true" style={{position:'absolute',left:375,top:135,width:250,height:100,pointerEvents:'none',border:`3px solid ${eventLabel?'#e65b31':'#147c92'}`,borderRadius:12,background:eventLabel?'#ff794520':'#50b9bd16',boxShadow:eventLabel?'0 0 0 9px #ff92362e':'0 0 0 6px #52b4c323'}}/>:null}
    </div></div>
  </div>;
}

export default function PlantDrawingMaster(){
  const [query,setQuery]=useState('');
  const [selected,setSelected]=useState(null);
  const [screen,setScreen]=useState('ecms-overview');
  const [manualFocus,setManualFocus]=useState('');
  const [eventLabel,setEventLabel]=useState('');

  const filtered=useMemo(()=>{
    const q=query.trim().toLowerCase();
    return q?EQUIPMENT_DRAWING_MASTER.filter(x=>[x.equipment_id,x.event_equipment,x.aliases,x.equipment_type].join(' ').toLowerCase().includes(q)):EQUIPMENT_DRAWING_MASTER;
  },[query]);

  useEffect(()=>{
    const params=new URLSearchParams(window.location.search);
    const equipment=params.get('equipment')||params.get('eq');
    const event=params.get('event')||params.get('tag')||'';
    const requested=params.get('view');
    setEventLabel(event?('EVENT · '+event):'');
    if(requested==='plant') {setScreen('plant');}
    if(!equipment)return;
    const row=resolveEquipmentDrawing(equipment);
    if(!row)return;
    setSelected(row);
    if(requested==='detail'&&row.detail_asset){setScreen('detail');return;}
    if(requested!=='ecms'&&requested!=='sld'&&requested!=='vpp'&&resolvePlantFocus(row)){setScreen('plant');return;}
    if(row.ecms_page==='ECMS_6P9KV'){setScreen('ecms-detail');setManualFocus('');return;}
    if(row.ecms_page==='ECMS_VPP'){setScreen('ecms-overview');setManualFocus('');return;}
    if(row.detail_asset){setScreen('detail');return;}
    if(resolvePlantFocus(row))setScreen('plant');
  },[]);

  function goEquipment(row){
    setSelected(row);
    setManualFocus('');
    setEventLabel('');
    if(resolvePlantFocus(row))setScreen('plant');
    else if(row.ecms_page==='ECMS_6P9KV')setScreen('ecms-detail');
    else if(row.ecms_page==='ECMS_VPP')setScreen('ecms-overview');
    else if(row.detail_asset)setScreen('detail');
  }

  function overviewNavigate(view){
    if(view==='BUS-A'||view==='BUS-B'){
      setSelected(resolveEquipmentDrawing(view));
      setManualFocus(view);
      setEventLabel('');
      setScreen('ecms-detail');
    }
  }

  function equipmentClicked(id){
    const row=resolveEquipmentDrawing(id);
    if(row){setSelected(row);setEventLabel('');}
  }

  function processClicked(locationId){
    const row=EQUIPMENT_DRAWING_MASTER.find(item=>item.plant_location_id===locationId);
    if(!row)return;
    setSelected(row);
    setEventLabel('');
    window.history.replaceState(null,'',`/drawing?equipment=${encodeURIComponent(row.event_equipment)}&view=plant`);
  }

  const overviewHighlight=screen==='ecms-overview'&&selected?.ecms_page==='ECMS_VPP'?selected.ecms_location_id:'';
  const detailHighlight=screen==='ecms-detail'?(manualFocus||(selected?.ecms_page==='ECMS_6P9KV'?selected.ecms_location_id:'')):'';
  const selectedFocus=resolvePlantFocus(selected);
  const relatedEquipment=selectedFocus?.kind==='related'?selected.event_equipment:'';

  return <main style={{minHeight:'100dvh',background:'#eef3f7',color:'#17324a'}}>
    <header style={{display:'flex',flexWrap:'wrap',justifyContent:'space-between',alignItems:'center',gap:12,padding:'12px 18px',background:'#17364d',color:'#fff'}}>
      <div><div style={{fontSize:12,opacity:.75,fontWeight:700}}>TRIPLENS DRAWING MASTER</div><h1 style={{fontSize:20,margin:'3px 0 0'}}>설비 위치 도면</h1></div>
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
        <button type="button" onClick={()=>setScreen('plant')} style={navButton(screen==='plant')}>Plant Process View</button>
        {selected?.detail_asset?<button type="button" onClick={()=>setScreen('detail')} style={navButton(screen==='detail')}>선택 설비 상세도면</button>:null}
        <p style={{...muted,lineHeight:1.5,marginTop:12}}>도면에서 설비를 누르거나 목록에서 선택하세요.</p>
      </aside>

      <section style={{...panel,padding:0,overflow:'hidden'}}>
        <div style={{padding:'12px 14px',borderBottom:'1px solid #d7e1e7',display:'flex',flexWrap:'wrap',justifyContent:'space-between',alignItems:'center',gap:10}}>
          <div>
            <h2 style={{fontSize:19,margin:0}}>{screen==='ecms-overview'?'ECMS Overview':screen==='ecms-detail'?'6.9 kV SWGR Detail':screen==='plant'?'Plant Process View':'Equipment Detail'}</h2>
            <p style={{...muted,margin:'4px 0 0'}}>{selected?selected.event_equipment+' · '+selected.notes:'도면에서 영역을 클릭하거나 Equipment를 선택하세요.'}</p>
          </div>
          <div style={{display:'flex',gap:7,flexWrap:'wrap'}}>
            {screen==='ecms-detail'?<button type="button" onClick={()=>{setScreen('ecms-overview');setManualFocus('')}} style={smallButton}>← ECMS Overview</button>:null}
            {selectedFocus&&screen!=='plant'?<button type="button" onClick={()=>setScreen('plant')} style={smallButton}>{relatedEquipment?'← Plant 관련 영역':'← Plant 위치'}</button>:null}
            {selected?.detail_asset&&screen==='plant'?<button type="button" onClick={()=>setScreen('detail')} style={smallButton}>선택 설비 상세도면</button>:null}
            {selected?.ecms_location_id&&screen==='plant'?<button type="button" onClick={()=>selected.ecms_page==='ECMS_6P9KV'?setScreen('ecms-detail'):setScreen('ecms-overview')} style={smallButton}>ECMS 위치</button>:null}
          </div>
        </div>

        {screen==='ecms-overview'?<div style={canvas}><InlineSvgNavigator src="/drawing/ecms-overview-matlab.svg" pageId="ECMS_VPP" title="ECMS Overview" highlight={overviewHighlight} eventLabel={eventLabel} onView={overviewNavigate} onEquipment={equipmentClicked}/></div>:null}
        {screen==='ecms-detail'?<><div style={selectionBar}><b>Direct detail</b><span>{detailHighlight||'BUS를 선택하세요'}</span></div><div style={canvas}><InlineSvgNavigator src="/drawing/ecms-6p9kv-matlab.svg" pageId="ECMS_6P9KV" title="6.9 kV SWGR Detail" highlight={detailHighlight} eventLabel={eventLabel} onEquipment={equipmentClicked}/></div></>:null}
        {screen==='plant'?<><ProcessViewCanvas locationId={selectedFocus?.locationId} relatedEquipment={relatedEquipment} eventLabel={eventLabel} onSelect={processClicked}/>
          <section aria-label="추가 밸브 상세도면" style={{padding:'12px 14px',borderTop:'1px solid #d7e1e7'}}>
            <h3 style={{fontSize:15,margin:'0 0 4px'}}>추가 밸브 상세도면</h3>
            <p style={{...muted,margin:'0 0 10px'}}>v36 전체 도면에 개별 심볼이 없는 등록 밸브입니다.</p>
            <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(155px,1fr))',gap:7}}>{detailOnlyValves.map(row=><button key={row.equipment_id} type="button" onClick={()=>goEquipment(row)} style={{...smallButton,minHeight:44,textAlign:'left'}}>{row.event_equipment}</button>)}</div>
          </section></>:null}
        {screen==='detail'?<DetailAsset row={selected} eventLabel={eventLabel}/>:null}

        {selected?<section aria-label="설비 상세 정보" style={{padding:14,borderTop:'1px solid #e1e8ed'}}>
          <h3 style={{fontSize:15,margin:'0 0 6px'}}>설비 상세 · {selected.event_equipment}</h3>
          <p style={{...muted,margin:'0 0 10px',lineHeight:1.5}}>{selectedFocus?.kind==='related'?`v36에 개별 심볼 없음 · 관련 설비 ${PLANT_PROCESS.hotspots[selectedFocus.locationId].label} 강조`:selectedFocus?'v36 원본 도면의 개별 심볼 강조':'ECMS 원본 도면의 설비 위치 강조'} · {selected.detail_asset?'등록된 개별 상세도면 보기 가능':'개별 상세도면 미등록'}</p>
          <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(170px,1fr))',gap:8}}>
            <Info label="Equipment ID" value={selected.equipment_id}/><Info label="Plant" value={selected.plant_location_id}/><Info label="ECMS page" value={selected.ecms_page}/><Info label="ECMS location" value={selected.ecms_location_id}/><Info label="Detail" value={selected.detail_asset}/>
          </div>
        </section>:null}
      </section>
    </section>
    <footer style={{maxWidth:1680,margin:'0 auto',padding:'0 16px 18px',fontSize:12,color:'#617685'}}>읽기 전용 도면 · 사고 설비를 선택해 위치를 확인합니다.</footer>
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
