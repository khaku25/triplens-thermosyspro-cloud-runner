'use client';

import {useEffect,useRef,useState} from 'react';

export default function InlineSvgNavigator({src,highlight='',onView,onEquipment,title}){
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

    const click=e=>{
      const target=e.target.closest?.('[data-view],[data-equipment]');
      if(!target||!root.contains(target))return;
      const view=target.getAttribute('data-view');
      const equipment=target.getAttribute('data-equipment');
      if(view&&onView)onView(view);
      else if(equipment&&onEquipment)onEquipment(equipment);
    };
    root.addEventListener('click',click);

    root.querySelectorAll('.triplens-highlight-ring').forEach(x=>x.remove());
    if(highlight){
      const target=[...root.querySelectorAll('[data-equipment]')].find(x=>x.getAttribute('data-equipment')===highlight);
      if(target){
        target.style.cursor='pointer';
        try{
          const box=target.getBBox();
          const ring=document.createElementNS('http://www.w3.org/2000/svg','rect');
          const pad=Math.max(14,Math.min(34,Math.max(box.width,box.height)*0.08));
          ring.setAttribute('x',String(box.x-pad));
          ring.setAttribute('y',String(box.y-pad));
          ring.setAttribute('width',String(box.width+pad*2));
          ring.setAttribute('height',String(box.height+pad*2));
          ring.setAttribute('rx','12');
          ring.setAttribute('fill','none');
          ring.setAttribute('stroke','#d84b3a');
          ring.setAttribute('stroke-width','5');
          ring.setAttribute('stroke-dasharray','12 8');
          ring.setAttribute('vector-effect','non-scaling-stroke');
          ring.setAttribute('pointer-events','none');
          ring.setAttribute('class','triplens-highlight-ring');
          target.parentNode.appendChild(ring);
        }catch{}
      }
    }
    return()=>root.removeEventListener('click',click);
  },[svg,highlight,onView,onEquipment]);

  if(error)return <div style={{padding:24,color:'#8b2f2f'}}>도면을 읽지 못했습니다: {error}</div>;
  if(!svg)return <div style={{padding:24,color:'#617685'}}>도면 불러오는 중…</div>;
  return <div ref={ref} className="dm-inline-svg" aria-label={title} dangerouslySetInnerHTML={{__html:svg}}/>;
}
