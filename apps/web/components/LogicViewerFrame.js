'use client';

import { useEffect, useRef } from 'react';

const TAG_ALIASES = Object.freeze({
  TRIP_LATCH: 'vppGTTripLatch',
  'GT.TRIP.LATCH': 'vppGTTripLatch',
  GT_TRIP_LATCH: 'vppGTTripLatch',
  'ST.TRIP.LATCH': 'vppSTTripLatchPublished',
  ST_TRIP_LATCH: 'vppSTTripLatchPublished',
});

const HIDDEN_PHRASES = [
  '원장 기반 로직도',
  '태그 존재 확인',
  'UNKNOWN/PARTIAL',
  '동작 검증(원장)',
  '출력 분류:',
  'Source ID 연결 확인',
  '등록 확인은 사고 원인 확정과 다릅니다.',
  '등록 Logic: 미확인',
  '미등록 관측 태그',
  'CANDIDATE',
  'HOLD',
];

function canonicalTag(tag) {
  return TAG_ALIASES[tag] || tag;
}

function setText(element, value) {
  if (element && element.textContent !== value) element.textContent = value;
}

function operatorDiagramText(value) {
  return String(value || '')
    .replace('원장 기반 로직도 · 조건 실행기가 아님', '태그·로직 연결도')
    .replace(/(\d+) source tags/g, '$1개 태그')
    .replace(/(\d+) rules/g, '$1개 로직')
    .replace(/(\d+) input groups/g, '$1개 입력 그룹')
    .replace('파란 태그 = OPC UA 원천  /  황색 태그 = 등록된 파생 출력', '태그 검색 · 설비별 분류 · 로직 연결 · 상세 정보')
    .replace('ADDITIONAL INFO', '상세 정보')
    .replace('SOURCE INPUT', '입력 태그')
    .replace('SOURCE OUTPUT', '출력 태그')
    .replace('DERIVED INPUT', '파생 입력')
    .replace('DERIVED OUTPUT', '파생 출력')
    .replace('등록된 파생 알람 · OPC UA Node 아님', '연결된 파생 알람 출력');
}

function setLegendText(element, value) {
  if (!element || element.textContent.trim() === value) return;
  const icon = element.querySelector('i');
  if (icon) element.replaceChildren(icon, element.ownerDocument.createTextNode(value));
  else setText(element, value);
}

function scrubViewer(document) {
  setText(document.querySelector('#equipment-view'), '설비별 로직');
  setText(document.querySelector('#tab-screens'), '설비 로직');
  setText(document.querySelector('#tab-drawings'), '도면');
  const equipmentGroup = [...document.querySelectorAll('#page-select optgroup')].find(group => group.label === '설비 화면');
  if (equipmentGroup) equipmentGroup.label = '설비별 로직';
  const headerCopy = document.querySelector('.top p');
  setText(headerCopy, '태그 · 로직 · 도면 검색 · 상세 정보');

  const revision = document.querySelector('#revision');
  setText(revision, '태그 및 로직 데이터 · Current V8');

  const notice = document.querySelector('#notice');
  setText(notice, '등록된 태그, 로직 연결, 도면 위치를 조회할 수 있습니다.');

  const legendItems = document.querySelectorAll('.legend > span');
  setLegendText(legendItems[0], '입력 태그');
  setLegendText(legendItems[1], '파생 출력');
  setLegendText(legendItems[2], '입·출력 연결');
  setLegendText(document.querySelector('.legend .condition'), '조건');
  setLegendText(document.querySelector('.legend .operation'), '동작');
  setLegendText(document.querySelector('.legend .additional'), '상세 정보');

  document.querySelectorAll('.small-actions, .badge.status').forEach(element => {
    element.hidden = true;
  });

  document.querySelectorAll('.inspector h2').forEach(element => {
    setText(element, element.textContent.replace('DETAIL / ', '').replace('TAG / ', '').replace('LOGIC / ', '').replace('Drawing Master','연결 도면'));
  });

  document.querySelectorAll('.inspector p, .inspector span, #context-note, .legend span').forEach(element => {
    const text = element.textContent.trim();
    if (text.startsWith('등록되지 않은 태그입니다.')) {
      setText(element, '검색 결과가 없습니다.');
      return;
    }
    if (text === 'OPC UA 원천 · 검증자료에 존재') {
      setText(element, '입력 태그');
      return;
    }
    if (text === '파생 출력 · OPC UA Node 아님') {
      setText(element, '파생 출력');
      return;
    }
    if (element.id === 'context-note' && text.includes('원장 정의 그대로 표시')) {
      setText(element, text.replace(' · 원장 정의 그대로 표시', ''));
      return;
    }
    if (HIDDEN_PHRASES.some(phrase => text.includes(phrase))) element.hidden = true;
  });

  document.querySelectorAll('#diagram tspan').forEach(element => {
    const text = operatorDiagramText(element.textContent);
    if (HIDDEN_PHRASES.some(phrase => text.includes(phrase))) {
      setText(element, '');
      return;
    }
    setText(element, text);
  });

  document.querySelectorAll('#diagram [aria-label]').forEach(element => {
    const visibleLabel = [...element.querySelectorAll('tspan')]
      .map(item => item.textContent.trim())
      .filter(Boolean)
      .join(' · ');
    const label = visibleLabel || operatorDiagramText(element.getAttribute('aria-label'));
    if (element.getAttribute('aria-label') !== label) element.setAttribute('aria-label', label);
  });
}

export default function LogicViewerFrame({ src = '/logic-assets/viewer.html', title, tag = '', rule = '', style, onEquipmentPage }) {
  const frameRef = useRef(null);
  const observerRef = useRef(null);

  useEffect(() => () => observerRef.current?.disconnect(), []);

  function prepareViewer() {
    const frame = frameRef.current;
    const document = frame?.contentDocument;
    const viewer = frame?.contentWindow;
    if (!document || !viewer) return;

    observerRef.current?.disconnect();
    let currentPage;
    const update = () => {
      scrubViewer(document);
      const selectedOption = document.querySelector('#page-select option:checked');
      const nextPage = selectedOption?.parentElement?.label === '설비별 로직'
        ? document.querySelector('#page-title')?.textContent?.trim() || '' : '';
      if (nextPage !== currentPage) {
        currentPage = nextPage;
        onEquipmentPage?.(nextPage);
      }
    };
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    observerRef.current = observer;

    if (rule) viewer.TripLensLogic?.openRule(rule);
    else if (tag) viewer.TripLensLogic?.openTag(canonicalTag(tag));
  }

  return (
    <iframe
      ref={frameRef}
      src={src}
      title={title}
      onLoad={prepareViewer}
      style={style}
    />
  );
}
