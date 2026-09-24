'use client';

import {useEffect,useRef} from 'react';
import {PLANT_PROCESS,PLANT_REGISTERED_SIGNALS,modelBoxStyle} from '../lib/plantHotspots.mjs';

function sourceFocus(box){
  const [left,bottom,right,top]=box;
  const [minX,minY,maxX,maxY]=PLANT_PROCESS.viewBox;
  const [imageWidth,imageHeight]=PLANT_PROCESS.imageSize;
  const x=(left-minX)/(maxX-minX)*imageWidth;
  const y=(maxY-top)/(maxY-minY)*imageHeight;
  const width=(right-left)/(maxX-minX)*imageWidth;
  const height=(top-bottom)/(maxY-minY)*imageHeight;
  const cropWidth=520,cropHeight=320;
  const cropX=Math.max(0,Math.min(imageWidth-cropWidth,x+width/2-cropWidth/2));
  const cropY=Math.max(0,Math.min(imageHeight-cropHeight,y+height/2-cropHeight/2));
  return {x,y,width,height,cropX,cropY,cropWidth,cropHeight};
}

export default function ProcessViewCanvas({locationId='',eventLabel='',relatedEquipment='',onSelect}){
  const frameRef=useRef(null);
  const selectedRef=useRef(null);
  const selected=PLANT_PROCESS.hotspots[locationId];
  const detail=selected?sourceFocus(selected.box):null;

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
            {active&&<span className="drawing-callout">{relatedEquipment?`${eventLabel?'EVENT · ':''}관련 설비 · ${hit.label}`:`${eventLabel?`${eventLabel} · `:''}${hit.label}`}</span>}
          </button>;
        })}
      </div>
    </div>
    <p className="drawing-caption">{relatedEquipment&&selected?`${relatedEquipment} 개별 심볼은 v36에 없습니다. 빨간 테두리는 관련 설비 ${selected.label}의 위치입니다.`:'Process View v36 기준 화면 · 표시값은 캡처 시점의 정적 값입니다.'}</p>
    <p className="drawing-signal-row">
      <span>등록 신호</span>
      {PLANT_REGISTERED_SIGNALS.map(signal=><a key={signal.tag} href={signal.href}>{signal.label} · {signal.tag} · {signal.unit} · {signal.access}</a>)}
    </p>
    {detail?<figure className="drawing-detail-figure">
      <figcaption>선택 위치 확대 · {relatedEquipment?`${relatedEquipment} 관련 영역 (${selected.label})`:selected.label}</figcaption>
      <svg className="drawing-detail-zoom" role="img" aria-label={`${selected.label} 원본 도면 확대`}
        viewBox={`${detail.cropX} ${detail.cropY} ${detail.cropWidth} ${detail.cropHeight}`}>
        <image href={PLANT_PROCESS.image} width={PLANT_PROCESS.imageSize[0]} height={PLANT_PROCESS.imageSize[1]}/>
        <rect x={detail.x} y={detail.y} width={detail.width} height={detail.height} rx="8"
          fill="rgba(255,91,40,.12)" stroke="#e34227" strokeWidth="4" strokeDasharray={relatedEquipment?'10 7':undefined}/>
      </svg>
    </figure>:null}
  </div>;
}
