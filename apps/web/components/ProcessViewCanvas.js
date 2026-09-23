'use client';

import {useEffect,useRef} from 'react';
import {PLANT_PROCESS,modelBoxStyle} from '../lib/plantHotspots.mjs';

export default function ProcessViewCanvas({locationId='',eventLabel='',onSelect}){
  const frameRef=useRef(null);
  const selectedRef=useRef(null);
  const selected=PLANT_PROCESS.hotspots[locationId];

  useEffect(()=>{
    if(!selected||!frameRef.current||!selectedRef.current)return;
    const frame=frameRef.current;
    const spot=selectedRef.current;
    frame.scrollTo({left:Math.max(0,spot.offsetLeft-frame.clientWidth/2),
      top:Math.max(0,spot.offsetTop-frame.clientHeight/2),behavior:'instant'});
    if(window.innerWidth<=860)frame.scrollIntoView({block:'start',behavior:'instant'});
  },[locationId,selected]);

  return <div className="process-view">
    <div className="drawing-scroll" ref={frameRef} aria-label="Plant Process View 도면">
      <div className="drawing-canvas" style={{aspectRatio:`${PLANT_PROCESS.imageSize[0]} / ${PLANT_PROCESS.imageSize[1]}`}}>
        <img src={PLANT_PROCESS.image} alt="TripLens CCPP Dynamic Process View v36 원본 화면" draggable="false"/>
        {Object.entries(PLANT_PROCESS.hotspots).map(([id,hit])=>{
          const active=id===locationId;
          return <button type="button" key={id} ref={active?selectedRef:null}
            className={`drawing-hotspot${active?' is-active':''}`} style={modelBoxStyle(hit.box)}
            title={hit.label} aria-label={`${hit.label} 도면 위치`} aria-pressed={active}
            onClick={()=>onSelect?.(id)}>
            {active&&<span className="drawing-callout">{eventLabel?`${eventLabel} · `:''}{hit.label}</span>}
          </button>;
        })}
      </div>
    </div>
    <p className="drawing-caption">{locationId&&!selected?'이 설비는 v36 전체 도면에 개별 심볼이 없습니다. 상세도면을 확인하세요.':'Process View v36 기준 화면 · 표시값은 캡처 시점의 정적 값입니다.'}</p>
  </div>;
}
