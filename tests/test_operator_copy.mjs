import test from 'node:test';
import assert from 'node:assert/strict';
import {operatorPhrase,operatorReviewItems} from '../apps/web/lib/workspacePresentation.mjs';

test('operator phrase converts polite AI prose into concise report style',()=>{
  assert.equal(
    operatorPhrase('48.44초에 가스터빈 트립 래치 및 증기터빈 트립 래치가 활성화되었습니다.'),
    'GT·ST Trip Latch 동시 동작'
  );
  assert.equal(
    operatorPhrase('RAW 변화 시간구간이 Direct Trigger 시각과 겹칩니다. 선후관계는 표본만으로 확정할 수 없습니다.'),
    'RAW 변화구간 · Direct Trigger 시각 중첩 · 선후관계 미확정'
  );
  assert.equal(
    operatorPhrase('관련 로직 조회가 확인되지 않았습니다. 승인 로직 원장을 확인해야 합니다.'),
    '관련 로직 조회가 미확인 · 승인 로직 원장을 확인 필요'
  );
});

test('screen 03 review items derive structured titles without inventing plant actions',()=>{
  const items=operatorReviewItems({
    additional_evidence_required:[
      '외부 트립 명령(vppExternalTripCommandNative)의 발신 출처(DCS 조작반 수동 트립 버튼 조작 여부, 인터락 연동 등)에 대한 상위 감사 로그 확인 필요',
      '외부 신호 전송 라인의 하드웨어 접점 및 통신 링크 상태 기록 확인 필요',
      'RAW 변화 시간구간이 Direct Trigger 시각과 겹칩니다. 선후관계는 표본만으로 확정할 수 없습니다.',
    ],
    review_recommendations:[
      'DCS 운전원 조작 이벤트 로그 및 비상 정지(ESD/E-Stop) 입력 채널 점검',
      'vppExternalTripCommandNative 신호 라인의 노이즈 또는 접점 단선/단락 여부 점검',
    ],
  });
  assert.deepEqual(items.map(item=>item.title),[
    '외부 Trip Command 발신 경로',
    '신호 경로 건전성',
    '시각 선후관계',
    '운전 조작이력',
    '입력 신호 건전성',
  ]);
  assert.equal(items[0].status,'확인 필요');
  assert.equal(items[3].status,'담당자 검토');
  assert.deepEqual(items[0].tags,['vppExternalTripCommandNative']);
  assert.ok(items.every(item=>!/(차단기 투입|밸브 개방|재기동 실시)/.test(item.detail)));
});
