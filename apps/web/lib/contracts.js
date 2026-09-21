import CURRENT_LOGIC_SUMMARY from './current-logic-summary.json';

export const WORKSPACE_TABS = [
  { id: 'timeline', no: '01', label: '사고 진행 과정', sub: '시간순 주요 사건' },
  { id: 'cause', no: '02', label: '원인 분석', sub: '원인 · 보호동작 · 파급' },
  { id: 'checks', no: '03', label: '즉시 확인·대응', sub: '주요 확인사항' },
  { id: 'recovery', no: '04', label: '복구 · 준비상태', sub: 'GT·HRSG·ST 준비상태 · 복구 기록' },
  { id: 'evidence', no: '05', label: '상세 분석 근거', sub: 'EVENT · RAW 기록' },
];

export const STATUS_LABELS = {
  CONFIRMED: '■ 확인 (CONFIRMED)',
  CANDIDATE: '△ 후보 (CANDIDATE)',
  OBSERVED: '○ 관측 (OBSERVED)',
  UNKNOWN: '— 미확인 (UNKNOWN)',
};

export const DEFAULT_LOGIC_SUMMARY = CURRENT_LOGIC_SUMMARY;

export const EMPTY_ANALYSIS = {
  critical_events: [],
  primary_cause: { status: 'UNKNOWN', claim: '', evidence_ids: [], related_tags: [] },
  direct_trigger: { status: 'UNKNOWN', claim: '', evidence_ids: [], related_tags: [] },
  propagation: [],
  causal_chain: [],
  counter_evidence: [],
  additional_evidence_required: [],
  verification_gate: 'HOLD',
};

export const DEMO_ANALYSIS = {
  critical_events: [
    { status: 'OBSERVED', claim: 'LP BFP SPEED_PROVEN_LOST 관측', evidence_ids: ['EV-DEMO-01'], related_tags: ['SPEED_PROVEN_LOST'], recorded_time: '30.680' },
    { status: 'OBSERVED', claim: 'LP BFP Trip Latch 동작', evidence_ids: ['EV-DEMO-02'], related_tags: ['LP_BFP_TRIP_LATCH'], recorded_time: '30.920' },
    { status: 'OBSERVED', claim: 'VCB-A02 Open 관측', evidence_ids: ['EV-DEMO-03'], related_tags: ['VCB_A02_CLOSED'], recorded_time: '31.120' },
  ],
  primary_cause: {
    status: 'CANDIDATE',
    claim: 'LP BFP speed-proven 상실 선행 원인 후보',
    evidence_ids: ['EV-DEMO-01'],
    related_tags: ['SPEED_PROVEN_LOST'],
    recorded_time: '30.680',
    logic_master_status: 'NOT_VERIFIED',
    ai_confidence: 0.84,
  },
  direct_trigger: {
    status: 'CANDIDATE',
    claim: 'LP BFP Trip Latch 동작',
    evidence_ids: ['EV-DEMO-02'],
    related_tags: ['LP_BFP_TRIP_LATCH'],
    recorded_time: '30.920',
    logic_master_status: 'VERIFIED',
    ai_confidence: 0.93,
  },
  propagation: [
    { status: 'OBSERVED', claim: 'VCB-A02 Open', evidence_ids: ['EV-DEMO-03'], related_tags: ['VCB_A02_CLOSED'], recorded_time: '31.120' },
  ],
  causal_chain: [
    'SPEED_PROVEN_LOST → Trip Latch',
    'Trip Latch → VCB-A02 Open',
    'VCB-A02 Open → Speed / Flow 감소',
  ],
  counter_evidence: [],
  additional_evidence_required: ['Primary Cause 확정을 위한 Logic Master 및 반대근거 검증'],
  verification_gate: 'HOLD',
};
