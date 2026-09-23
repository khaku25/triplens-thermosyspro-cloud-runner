'use client';

import { useEffect, useRef, useState } from 'react';
import { PLANT_PROCESS, ECMS_VIEWS, modelBoxStyle, pixelBoxStyle } from '../lib/plantHotspots.mjs';
import { EQUIPMENT_MASTER, resolveDrawingRequest } from '../lib/equipmentMaster.mjs';

function browserQuery() {
  const query = new URLSearchParams(window.location.search);
  return {equipment:query.get('equipment') || '',view:query.get('view') || '',page:query.get('page') || ''};
}

export default function DrawingMaster({ initialQuery = {} }) {
  const [query,setQuery] = useState(initialQuery);
  const selectedRef = useRef(null);
  const canvasRef = useRef(null);
  const target = resolveDrawingRequest(query);
  const isPlant = target.view === 'plant';
  const drawing = isPlant ? PLANT_PROCESS : ECMS_VIEWS[target.page];
  const hotspots = drawing.hotspots;
  const current = target.locationId && hotspots[target.locationId];

  useEffect(() => {
    const restore = () => setQuery(browserQuery());
    window.addEventListener('popstate',restore);
    return () => window.removeEventListener('popstate',restore);
  }, []);
  useEffect(() => {
    if (!current || !selectedRef.current || !canvasRef.current) return;
    const frame = canvasRef.current;
    const selected = selectedRef.current;
    frame.scrollTo({left:Math.max(0, selected.offsetLeft - frame.clientWidth / 2),
      top:Math.max(0, selected.offsetTop - frame.clientHeight / 2),behavior:'instant'});
  }, [target.view,target.page,target.locationId,current]);

  function navigate(next) {
    const params = new URLSearchParams();
    if (next.view) params.set('view',next.view);
    if (next.page && next.view === 'ecms') params.set('page',next.page);
    if (next.equipment) params.set('equipment',next.equipment);
    window.history.pushState(null,'',`/drawing${params.size ? `?${params}` : ''}`);
    setQuery(next);
  }

  function select(id, hotspot) {
    navigate({view:target.view,page:hotspot.drill || target.page,equipment:id});
  }

  return <main className="drawing-master">
    <header className="drawing-header">
      <div><a href="/" className="drawing-back">← 사고 분석</a><h1>Drawing Master</h1><p>사고 설비의 위치를 전체 계통에서 확인합니다.</p></div>
      <a href="/logic" className="drawing-logic">태그 · 로직 도면</a>
    </header>
    <nav className="drawing-tabs" aria-label="도면 페이지">
      <button type="button" aria-current={!isPlant ? 'page' : undefined} onClick={() => navigate({view:'ecms',page:'overview'})}>01 ECMS</button>
      <button type="button" aria-current={isPlant ? 'page' : undefined} onClick={() => navigate({view:'plant'})}>02 Plant Process View</button>
    </nav>
    {!isPlant && <nav className="drawing-subtabs" aria-label="ECMS 화면">
      <button type="button" aria-current={target.page === 'overview' ? 'page' : undefined} onClick={() => navigate({view:'ecms',page:'overview'})}>ECMS Overview</button>
      <button type="button" aria-current={target.page === 'detail' ? 'page' : undefined} onClick={() => navigate({view:'ecms',page:'detail'})}>6.9 kV SWGR Detail</button>
    </nav>}
    <section className="drawing-toolbar" aria-label="설비 선택">
      <label htmlFor="drawing-equipment">설비 위치</label>
      <select id="drawing-equipment" value={target.record?.equipment_id || ''}
        onChange={event => {const equipment = event.target.value;
          navigate(equipment ? {equipment} : {view:target.view,page:target.page});}}>
        <option value="">전체 보기</option>
        <optgroup label="Plant Process View">
          {EQUIPMENT_MASTER.filter(row => row.plant_location_id).map(row =>
            <option key={row.equipment_id} value={row.equipment_id}>{PLANT_PROCESS.hotspots[row.plant_location_id].label}</option>)}
        </optgroup>
        <optgroup label="ECMS">
          {EQUIPMENT_MASTER.filter(row => row.ecms_location_id && !row.plant_location_id).map(row =>
            <option key={row.equipment_id} value={row.equipment_id}>{row.equipment_id}</option>)}
        </optgroup>
      </select>
      <span role="status">{current ? `${current.label} 위치 표시 중` : query.equipment ? '등록된 도면 위치가 없습니다' : '설비를 선택하거나 도면을 누르세요'}</span>
    </section>
    <section className="drawing-scroll" ref={canvasRef} aria-label={isPlant ? 'Plant Process View 도면' : 'ECMS 도면'}>
      <div className="drawing-canvas" style={{aspectRatio:`${drawing.imageSize[0]} / ${drawing.imageSize[1]}`}}>
        <img src={drawing.image} alt={isPlant ? 'TripLens CCPP Dynamic Process View v36 기준 도면' : target.page === 'overview' ? 'ECMS 발전기 및 모선 개요' : '6.9 kV 스위치기어 상세'} draggable="false"/>
        {Object.entries(hotspots).map(([id,spot]) => {
          const active = id === target.locationId;
          const style = isPlant ? modelBoxStyle(spot.box) : pixelBoxStyle(spot.box,drawing.imageSize);
          return <button type="button" key={id} ref={active ? selectedRef : null}
            className={`drawing-hotspot${active ? ' is-active' : ''}`} style={style}
            aria-label={`${spot.label} 도면 위치`} aria-pressed={active} title={spot.label}
            onClick={() => select(id,spot)}>
            {active && <span className="drawing-callout">{spot.label}</span>}
          </button>;
        })}
      </div>
    </section>
    <p className="drawing-caption">{isPlant ? 'Process View v36 기준 화면 · 표시값은 캡처 시점의 정적 값' : 'ECMS 계통 기준 도면 · 모선을 누르면 피더 상세로 이동'}</p>
  </main>;
}
