'use client';
import { useEffect, useRef, useState } from 'react';
import LogicViewerFrame from './LogicViewerFrame';

export function openLogicLibrary(detail = {}) {
  window.dispatchEvent(new CustomEvent('triplens:open-logic', { detail }));
}
export function LogicLinks({ tags }) {
  const values = Array.isArray(tags) ? tags : String(tags || '').split(',').map(x => x.trim()).filter(Boolean);
  if (!values.length) return '—';
  return values.map((tag, i) => (
    <span key={`${tag}-${i}`}>
      {i ? ', ' : ''}
      <button type="button" onClick={() => openLogicLibrary({ tag })}
        title={`${tag} · 태그와 관련 로직 상세보기`}
        style={{ background: 'transparent', border: 0, padding: 0, color: '#126176', textDecoration: 'underline', cursor: 'pointer', font: 'inherit', overflowWrap: 'anywhere' }}>{tag}</button>
    </span>
  ));
}
export function LogicLibraryDialog({analysisMode = false}) {
  const ref = useRef(null);
  const [selection, setSelection] = useState(null);
  useEffect(() => {
    const open = event => {
      const d = event.detail || {};
      setSelection({ tag: typeof d.tag === 'string' ? d.tag : '', rule: typeof d.rule === 'string' ? d.rule : '', revision: Date.now() });
      if (ref.current && !ref.current.open) ref.current.showModal();
    };
    window.addEventListener('triplens:open-logic', open);
    return () => window.removeEventListener('triplens:open-logic', open);
  }, []);
  function close() { ref.current?.close(); setSelection(null); }
  const query = new URLSearchParams();
  if (selection?.rule) query.set('rule', selection.rule);
  else if (selection?.tag) query.set('tag', selection.tag);
  const src = `/logic-assets/viewer.html${query.toString() ? '#' + query : ''}`;
  const title = analysisMode ? (selection?.rule ? '운전조건·룰 기준 도면' : selection?.tag ? '태그 기준 도면' : '태그·운전조건·룰 기준 도면') : '태그·로직 상세보기';
  return (
    <dialog ref={ref} aria-label={title} onCancel={close}
      onClick={event => { if (event.target === ref.current) close(); }}
      style={{ width: 'min(1600px, 98vw)', height: '94dvh', maxWidth: '98vw', maxHeight: '96dvh', padding: 0, border: '1px solid #b5c8d5', borderRadius: 12 }}>
      <div style={{ display: 'grid', gridTemplateRows: 'auto minmax(0, 1fr)', height: '100%', minWidth: 0 }}>
        <header style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', background: '#17364d', color: 'white', minHeight: 48 }}>
          <strong>{analysisMode ? `TripLens · ${title}` : 'TripLens · 로직 상세보기'}</strong>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12 }}>
            <a href={`/logic${query.toString() ? '?' + query : ''}`} target="_blank" rel="noreferrer" style={{ color: 'white' }}>별도 화면</a>
            <button type="button" onClick={close} style={{ background: 'white', color: '#17364d', border: 0, borderRadius: 6, padding: '7px 12px', cursor: 'pointer' }}>분석 화면으로 돌아가기 ×</button>
            <button type="button" onClick={close} style={{ background: 'transparent', color: 'white', border: '1px solid #b5c8d5', borderRadius: 6, padding: '7px 12px', cursor: 'pointer' }}>닫기</button>
          </div>
        </header>
        {selection ? <LogicViewerFrame key={selection.revision} title={analysisMode ? title : '태그와 로직 도면'} src={src} tag={selection.tag} rule={selection.rule} style={{ width: '100%', height: '100%', minHeight: 0, border: 0, display: 'block' }} /> : null}
      </div>
    </dialog>
  );
}
