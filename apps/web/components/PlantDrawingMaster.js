'use client';

import {useMemo,useState} from 'react';

const RAW='https://raw.githubusercontent.com/khaku25/triplens-thermosyspro-cloud-runner/main/topology/';
const VIEWS=[
  {id:'valves',label:'ThermoSys 밸브',title:'FMU Valve Overview',src:'fmu_valves_overview.svg',note:'ThermoSysPro 3.1 전체 모델에 FMU로 연결된 밸브 설비도'},
  {id:'bypass',label:'터빈 Bypass',title:'HPBP · LPBP',src:'turbine_bypass_vpp.svg',note:'HP Main Steam → Cold Reheat / Hot Reheat → Condenser 경로'},
  {id:'vpp',label:'VPP 계통',title:'ECMS VPP Overview',src:'triplens_ecms_vpp.svg',note:'GT/ST 주 변압기 · 6.9 kV BUS · FWP 전원계통'},
  {id:'sld',label:'6.9 kV',title:'6.9 kV SLD',src:'triplens_ecms_6p9kv.svg',note:'보조전원 BUS-A/B · 인커밍 · 타이 · FWP 피더'},
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

export default function PlantDrawingMaster(){
  const [view,setView]=useState('valves');
  const [selected,setSelected]=useState(null);
  const [query,setQuery]=useState('');
  const active=VIEWS.find(item=>item.id===view)||VIEWS[0];
  const filtered=useMemo(()=>{
    const q=query.trim().toLowerCase();
    return q?VALVES.filter(v=>[v.id,v.equipment,v.system,v.service].join(' ').toLowerCase().includes(q)):VALVES;
  },[query]);
  const currentSrc=selected?selected.src:active.src;
  const currentTitle=selected?selected.equipment:active.title;
  const currentNote=selected?selected.service:active.note;

  function switchView(id){setView(id);setSelected(null);}

  return <main style={{minHeight:'100dvh',background:'#eef3f7',color:'#17324a'}}>
    <header style={{display:'flex',flexWrap:'wrap',alignItems:'center',justifyContent:'space-between',gap:12,padding:'12px 18px',background:'#17364d',color:'white'}}>
      <div>
        <div style={{fontSize:12,opacity:.75,fontWeight:700,letterSpacing:'.08em'}}>TRIPLENS DRAWING MASTER</div>
        <h1 style={{fontSize:20,margin:'3px 0 0'}}>ThermoSysPro 설비 · 공정 도면</h1>
      </div>
      <nav style={{display:'flex',gap:8,flexWrap:'wrap'}}>
        <a href="/" style={topLink}>분석 화면</a>
        <a href="/logic" style={topLink}>Logic View</a>
      </nav>
    </header>

    <section style={{display:'grid',gridTemplateColumns:'minmax(240px,320px) minmax(0,1fr)',gap:14,padding:14,maxWidth:1680,margin:'0 auto'}} className="plant-drawing-layout">
      <aside style={{background:'white',border:'1px solid #c9d6df',borderRadius:12,padding:12,minWidth:0}}>
        <h2 style={{fontSize:16,margin:'0 0 10px'}}>도면 선택</h2>
        <div style={{display:'grid',gap:7}}>
          {VIEWS.map(item=><button key={item.id} type="button" onClick={()=>switchView(item.id)} style={buttonStyle(view===item.id&&!selected)}>{item.label}<small style={{display:'block',fontWeight:400,opacity:.72,marginTop:2}}>{item.title}</small></button>)}
        </div>

        <hr style={{border:0,borderTop:'1px solid #dde5eb',margin:'14px 0'}}/>
        <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:8}}><h2 style={{fontSize:16,margin:0}}>ThermoSys 밸브</h2><span style={{fontSize:12,color:'#617685'}}>{filtered.length}/12</span></div>
        <input value={query} onChange={e=>setQuery(e.target.value)} placeholder="HP FWCV · turbine · 급수..." aria-label="설비 검색" style={{boxSizing:'border-box',width:'100%',margin:'9px 0',padding:'10px 11px',border:'1px solid #b9cad5',borderRadius:8,fontSize:14}}/>
        <div style={{display:'grid',gap:6,maxHeight:'52dvh',overflow:'auto',paddingRight:2}}>
          {filtered.map(v=><button key={v.id} type="button" onClick={()=>{setView('valves');setSelected(v)}} style={equipmentStyle(selected?.id===v.id)}>
            <span style={{display:'flex',justifyContent:'space-between',gap:8}}><b>{v.equipment}</b><small>{v.system}</small></span>
            <span style={{fontSize:12,color:'#5f7382'}}>{v.service}</span>
          </button>)}
        </div>
      </aside>

      <section style={{background:'white',border:'1px solid #c9d6df',borderRadius:12,minWidth:0,overflow:'hidden',display:'grid',gridTemplateRows:'auto minmax(520px,1fr)'}}>
        <div style={{display:'flex',flexWrap:'wrap',alignItems:'center',justifyContent:'space-between',gap:10,padding:'12px 14px',borderBottom:'1px solid #d8e2e9'}}>
          <div>
            <h2 style={{fontSize:18,margin:0}}>{currentTitle}</h2>
            <p style={{fontSize:13,color:'#607585',margin:'4px 0 0'}}>{currentNote}</p>
          </div>
          <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
            {selected?<button type="button" onClick={()=>setSelected(null)} style={smallButton}>← 밸브 개요</button>:null}
            <a href={RAW+currentSrc} target="_blank" rel="noreferrer" style={{...smallButton,textDecoration:'none'}}>원본 SVG</a>
          </div>
        </div>
        <div style={{background:'#f7fafc',minHeight:0,overflow:'auto',padding:10}}>
          <object data={RAW+currentSrc} type="image/svg+xml" aria-label={currentTitle} style={{width:'100%',height:'100%',minHeight:560,border:0,background:'white',borderRadius:8}}>
            <img src={RAW+currentSrc} alt={currentTitle} style={{maxWidth:'100%'}}/>
          </object>
        </div>
      </section>
    </section>

    <footer style={{maxWidth:1680,margin:'0 auto',padding:'0 16px 18px',fontSize:12,color:'#617685'}}>
      READ-ONLY 도면 탐색 · ThermoSysPro/TripLens 모델 자산 기준 · 운전/정비/LOTO용 아님 · Logic Master는 별도 Logic View에서 확인
    </footer>
    <style jsx global>{`
      @media(max-width:860px){
        .plant-drawing-layout{grid-template-columns:1fr!important;padding:8px!important}
        .plant-drawing-layout aside{order:2}
        .plant-drawing-layout section{order:1}
      }
    `}</style>
  </main>;
}

const topLink={color:'white',border:'1px solid rgba(255,255,255,.45)',borderRadius:7,padding:'7px 10px',textDecoration:'none',fontSize:13};
const smallButton={border:'1px solid #b8c8d2',background:'white',color:'#1b5f77',borderRadius:7,padding:'7px 10px',cursor:'pointer',fontSize:13};
const buttonStyle=active=>({textAlign:'left',border:'1px solid '+(active?'#1c718a':'#c8d6df'),background:active?'#e9f5f8':'#f8fafb',color:'#17364d',borderRadius:8,padding:'9px 10px',cursor:'pointer',fontWeight:700});
const equipmentStyle=active=>({textAlign:'left',display:'grid',gap:3,border:'1px solid '+(active?'#74519d':'#d3dde4'),background:active?'#f3effa':'white',color:'#203b50',borderRadius:8,padding:'9px 10px',cursor:'pointer'});
