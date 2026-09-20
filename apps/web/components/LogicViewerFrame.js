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

function scrubViewer(document) {
  const headerCopy = document.querySelector('.top p');
  setText(headerCopy, '태그 검색 · 설비별 분류 · 로직 연결 · 상세 정보');

  const revision = document.querySelector('#revision');
  setText(revision, '태그 및 로직 데이터 · Current V8');

  const notice = document.querySelector('#notice');
  setText(notice, '등록된 태그, 설비 분류, 로직 연결 정보를 조회할 수 있습니다.');

  document.querySelectorAll('.small-actions, .badge.status').forEach(element => {
    element.hidden = true;
  });

  document.querySelectorAll('.inspector h2').forEach(element => {
    setText(element, element.textContent.replace('DETAIL / ', '').replace('TAG / ', '').replace('LOGIC / ', ''));
  });

  document.querySelectorAll('.inspector p, .inspector span, #context-note, .legend span').forEach(element => {
    const text = element.textContent.trim();
    if (text.startsWith('등록되지 않은 태그입니다.')) {
      setText(element, '검색 결과가 없습니다.');
      return;
    }
    if (HIDDEN_PHRASES.some(phrase => text.includes(phrase))) element.hidden = true;
  });

  document.querySelectorAll('#diagram tspan').forEach(element => {
    const text = element.textContent;
    if (HIDDEN_PHRASES.some(phrase => text.includes(phrase))) {
      setText(element, '');
      return;
    }
    setText(element, text
      .replace('ADDITIONAL INFO', '상세 정보')
      .replace('SOURCE INPUT', '입력 태그')
      .replace('SOURCE OUTPUT', '출력 태그'));
  });
}

export default function LogicViewerFrame({ src = '/logic-assets/viewer.html', title, tag = '', rule = '', style }) {
  const frameRef = useRef(null);
  const observerRef = useRef(null);

  useEffect(() => () => observerRef.current?.disconnect(), []);

  function prepareViewer() {
    const frame = frameRef.current;
    const document = frame?.contentDocument;
    const viewer = frame?.contentWindow;
    if (!document || !viewer) return;

    observerRef.current?.disconnect();
    scrubViewer(document);
    const observer = new MutationObserver(() => scrubViewer(document));
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
