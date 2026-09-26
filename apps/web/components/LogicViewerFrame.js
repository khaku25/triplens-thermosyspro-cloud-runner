'use client';

import { useEffect, useRef } from 'react';
import { EQUIPMENT_DRAWING_MASTER } from '../lib/equipmentDrawingMaster.mjs';
import { plantDrawingHref, searchPlantViewEquipment } from '../lib/plantViewSearch.mjs';

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
  setText(document.querySelector('#tab-drawings'), '로직 다이어그램');
  const equipmentGroup = [...document.querySelectorAll('#page-select optgroup')].find(group => group.label === '설비 화면');
  if (equipmentGroup) equipmentGroup.label = '설비별 로직';
  const headerCopy = document.querySelector('.top p');
  setText(headerCopy, '태그 · 로직 · 설비별 로직 · 로직 다이어그램 · Plant View 설비');

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
    let plantMode = false;
    const searchInput = document.querySelector('#search');
    const results = document.querySelector('#results');
    const resultCount = document.querySelector('#result-count');
    const workspace = document.querySelector('#workspace');
    const main = document.querySelector('#workspace .main');
    const side = document.querySelector('#workspace .side');
    const inspector = document.querySelector('#inspector');

    function ensurePlantViewTab() {
      const tabs = document.querySelector('.tabs');
      if (!tabs) return null;
      let button = document.querySelector('#tab-plant-view');
      if (!button) {
        button = document.createElement('button');
        button.type = 'button';
        button.id = 'tab-plant-view';
        button.setAttribute('aria-label', 'Plant View 설비');
        button.title = 'Equipment Master에 등록된 설비 위치 검색';
        button.textContent = 'Plant View 설비';
        tabs.append(button);
      }
      return button;
    }

    function renderPlantViewResults() {
      if (!searchInput || !results) return;
      const rows = searchPlantViewEquipment(EQUIPMENT_DRAWING_MASTER, searchInput.value);
      resultCount && (resultCount.textContent = `Plant View 설비 검색 결과 ${rows.length}개`);
      const items = rows.map(row => {
        const button = document.createElement('button');
        button.type = 'button';
        button.dataset.plantEquipmentId = row.equipment_id;
        button.setAttribute('aria-label', `${row.event_equipment} · ${row.equipment_type} · ${row.plant_location_id ? 'Plant View' : 'ECMS 도면'}`);

        const name = document.createElement('strong');
        name.textContent = row.event_equipment || row.equipment_id;
        const details = document.createElement('small');
        details.textContent = [row.aliases, row.equipment_type, row.plant_location_id ? 'Plant View' : 'ECMS 도면']
          .filter(Boolean).join(' · ');
        button.append(name, details);
        return button;
      });
      results.replaceChildren(...items);
      const moreResults = document.querySelector('#more-results');
      if (moreResults) moreResults.hidden = true;
    }

    function showPlantViewSearch() {
      plantMode = true;
      document.querySelectorAll('.tabs button').forEach(button => {
        button.classList.toggle('active', button.id === 'tab-plant-view');
      });
      if (searchInput) {
        searchInput.placeholder = '설비명 · Equipment ID · 별칭 검색';
        searchInput.setAttribute('aria-label', 'Plant View 설비 검색');
      }
      if (workspace) workspace.style.gridTemplateColumns = 'minmax(0, 1fr)';
      if (side) side.style.gridTemplateColumns = 'minmax(0, 1fr)';
      if (main) main.hidden = true;
      if (inspector) inspector.hidden = true;
      renderPlantViewResults();
    }

    function leavePlantViewSearch(nextTabId) {
      if (!plantMode) return;
      plantMode = false;
      if (workspace) workspace.style.gridTemplateColumns = '';
      if (side) side.style.gridTemplateColumns = '';
      if (main) main.hidden = false;
      if (inspector) inspector.hidden = false;
      if (searchInput) {
        const isDrawing = nextTabId === 'tab-drawings';
        searchInput.placeholder = isDrawing ? '태그 · 로직 · 페이지 · 셀 검색' : '태그 ID · 설명 · 로직 검색';
        searchInput.setAttribute('aria-label', isDrawing ? '로직 다이어그램 검색' : '태그 또는 로직 검색');
      }
    }

    document.addEventListener('click', event => {
      const plantTab = event.target?.closest?.('#tab-plant-view');
      if (plantTab) {
        event.preventDefault();
        event.stopImmediatePropagation();
        showPlantViewSearch();
        return;
      }

      const equipmentButton = event.target?.closest?.('[data-plant-equipment-id]');
      if (plantMode && equipmentButton) {
        event.preventDefault();
        event.stopImmediatePropagation();
        const row = EQUIPMENT_DRAWING_MASTER.find(item => item.equipment_id === equipmentButton.dataset.plantEquipmentId);
        if (row) window.location.assign(plantDrawingHref(row));
        return;
      }

      const nativeTab = event.target?.closest?.('#tab-tags, #tab-rules, #tab-screens, #tab-drawings');
      if (plantMode && nativeTab) leavePlantViewSearch(nativeTab.id);
    }, true);

    document.addEventListener('input', event => {
      if (!plantMode || event.target !== searchInput) return;
      event.stopImmediatePropagation();
      renderPlantViewResults();
    }, true);

    const update = () => {
      scrubViewer(document);
      ensurePlantViewTab();
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
