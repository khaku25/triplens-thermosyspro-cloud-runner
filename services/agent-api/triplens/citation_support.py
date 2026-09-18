"""Reference feedback over already retrieved samples. Never chooses a cause or adds citations."""
from __future__ import annotations
from .analysis_contract import LIST_FIELDS, as_list, normalize_claim, number, text

PREFIXES = ('미조회 또는 존재하지 않는 근거 ID:', '인용 근거에 없는 태그:',
            '주장한 시간구간과 인용 표본의 시각 불일치', 'AI 시각과 인용 근거 시각 불일치',
            '태그별 관측 구간의 경계 표본 인용 누락:')


def citation_feedback(raw, store):
    if not isinstance(raw, dict):
        return []
    catalog = store.evidence_catalog()
    issues = []
    for name in ('primary_cause', 'direct_trigger', *LIST_FIELDS):
        for i, claim in enumerate(as_list(raw.get(name))):
            if not isinstance(claim, dict) or not text(claim):
                continue
            normalized = normalize_claim(claim, name, store)
            notes = [n for n in normalized['verification_notes'] if n.startswith(PREFIXES)]
            if not notes:
                continue
            tags = set(normalized['related_tags'])
            refs = [r for r in catalog if tags.intersection({r.get('tag'), r.get('source_node'), r.get('original_tag'), r.get('canonical_tag')})]
            bounds = claim.get('time_interval_s')
            requested = [number(t) for t in bounds] if isinstance(bounds, list) else [number(claim.get('model_time_s'))]
            requested = [t for t in requested if t is not None]
            if requested:
                refs.sort(key=lambda r: min(abs((number(r.get('model_time_s')) or 0)-t) for t in requested))
            evidence = [{k:r.get(k) for k in ('evidence_id','source_kind','source_node','tag','model_time_s','value','state')} for r in refs[:64]]
            issues.append({'claim_path':f'{name}[{i}]' if name in LIST_FIELDS else name,
                'reference_errors':notes,'already_retrieved_candidate_records':evidence})
    return issues

REPAIR_INSTRUCTION = '''주장별 근거 연결 검사에서 누락 또는 시간구간 불일치가 발견되었습니다.
이것은 추가 사고원인 정답이나 새로운 관측이 아닙니다. 아래 후보 기록은 이미 도구로 조회한 원본 표본만입니다.
전체 분석 JSON을 한 번만 보완해서 반환하세요. 각 문장에 실제로 필요한 근거만 직접 선택해 인용하고,
서술한 태그와 관측 구간의 시작·끝 표본을 확인하세요. 후보 ID를 무조건 붙이지 마세요.
새 도구 호출, 새 태그, 새 관측값, 정답 시나리오 추측은 금지합니다.
근거가 실제 주장을 뒷받침하지 않으면 주장의 범위를 좁히거나 UNKNOWN으로 남기세요.
기존 표본 오차, 시간구간 겹침, 인간의 최종 승인 필요성은 제거하지 마세요.
'''
