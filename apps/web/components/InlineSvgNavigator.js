'use client';

import {useEffect,useRef,useState} from 'react';
import {ECMS_HOTSPOT_PAGES} from '../lib/ecmsHotspots.mjs';

export default function InlineSvgNavigator({src,pageId='',highlight='',eventLabel='',onView,onEquipment,title}){
  const ref=useRef(null);
  const [svg,setSvg]=useState('');
  const [error,setError]=useState('');

  useEffect(()=>{
    let active=true;
    setError('');
    fetch(src,{cache:'no-store'}).then(r=>{
      if(!r.ok)throw new Error('SVG HTTP '+r.status);
      return r.text();
    }).then(text=>{if(active)setSvg(text)}).catch(err=>{if(active)setError(String(err.message||err))});
    return()=>{active=false};
  },[src]);

  useEffect(()=>{
    const root=ref.current;
    if(!root||!svg)return;
    const svgEl=root.querySelector('svg');
    if(!svgEl)return;
    svgEl.style.width='100%';
    svgEl.style.height='auto';
    svgEl.style.display='block';

    root.querySelectorAll('.triplens-hotspot-layer,.triplens-highlight-layer').forEach(x=>x.remove());

    const page=ECMS_HOTSPOT_PAGES[pageId];
    const ns='http://www.w3.org/2000/svg';

    if(page){
      const layer=document.createElementNS(ns,'g');
      layer.setAttribute('class','triplens-hotspot-layer');
      for(const [key,hit] of Object.entries(page.hotspots)){
        const [x,y,w,h]=hit.box;
        const rect=document.createElementNS(ns,'rect');
        rect.setAttribute('x',String(x));
        rect.setAttribute('y',String(y));
        rect.setAttribute('width',String(w));
        rect.setAttribute('height',String(h));
        rect.setAttribute('rx','8');
        rect.setAttribute('fill','transparent');
        rect.setAttribute('stroke','transparent');
        rect.setAttribute('pointer-events','all');
        rect.style.cursor='pointer';
        rect.dataset.equipment=key;
        if(hit.view)rect.dataset.view=hit.view;
        rect.setAttribute('aria-label',hit.label||key);
        layer.appendChild(rect);
      }
      svgEl.appendChild(layer);

      const active=page.hotspots[highlight];
      if(active){
        const [x,y,w,h]=active.box;
        const hLayer=document.createElementNS(ns,'g');
        hLayer.setAttribute('class','triplens-highlight-layer');

        const halo=document.createElementNS(ns,'rect');
        halo.setAttribute('x',String(x-12));
        halo.setAttribute('y',String(y-12));
        halo.setAttribute('width',String(w+24));
        halo.setAttribute('height',String(h+24));
        halo.setAttribute('rx','14');
        halo.setAttribute('fill','rgba(216,75,58,0.10)');
        halo.setAttribute('stroke','#d84b3a');
        halo.setAttribute('stroke-width','5');
        halo.setAttribute('stroke-dasharray','12 8');
        halo.setAttribute('vector-effect','non-scaling-stroke');
        halo.setAttribute('pointer-events','none');
        hLayer.appendChild(halo);

        const labelText=eventLabel||active.label||highlight;
        if(labelText){
          const pad=8;
          const labelWidth=Math.min(360,Math.max(150,labelText.length*7.2+pad*2));
          let lx=x+w+18;
          if(lx+labelWidth>page.viewBox[2]-8)lx=Math.max(8,x-labelWidth-18);
          let ly=Math.max(8,y-42);

          const bg=document.createElementNS(ns,'rect');
          bg.setAttribute('x',String(lx));
          bg.setAttribute('y',String(ly));
          bg.setAttribute('width',String(labelWidth));
          bg.setAttribute('height','30');
          bg.setAttribute('rx','7');
          bg.setAttribute('fill','#fff7f2');
          bg.setAttribute('stroke','#d84b3a');
          bg.setAttribute('stroke-width','2');
          bg.setAttribute('pointer-events','none');
          hLayer.appendChild(bg);

          const text=document.createElementNS(ns,'text');
          text.setAttribute('x',String(lx+10));
          text.setAttribute('y',String(ly+20));
          text.setAttribute('font-family','Arial, sans-serif');
          text.setAttribute('font-size','13');
          text.setAttribute('font-weight','700');
          text.setAttribute('fill','#a73528');
          text.setAttribute('pointer-events','none');
          text.textContent=labelText;
          hLayer.appendChild(text);
        }
        svgEl.appendChild(hLayer);
      }
    }

    const click=e=>{
      const target=e.target.closest?.('[data-view],[data-equipment]');
      if(!target||!root.contains(target))return;
      const view=target.getAttribute('data-view');
      const equipment=target.getAttribute('data-equipment');
      if(view&&onView)onView(view);
      else if(equipment&&onEquipment)onEquipment(equipment);
    };
    root.addEventListener('click',click);
    return()=>root.removeEventListener('click',click);
  },[svg,pageId,highlight,eventLabel,onView,onEquipment]);

  if(error)return <div style={{padding:24,color:'#8b2f2f'}}>도면을 읽지 못했습니다: {error}</div>;
  if(!svg)return <div style={{padding:24,color:'#617685'}}>도면 불러오는 중…</div>;
  return <div ref={ref} className="dm-inline-svg" aria-label={title} dangerouslySetInnerHTML={{__html:svg}}/>;
}
