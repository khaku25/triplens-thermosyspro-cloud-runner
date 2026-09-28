"""Safe correlation metadata for analysis-provider failures."""
from __future__ import annotations

import json
import logging
import re
import uuid
from urllib.error import HTTPError

_SAFE_VALUE=re.compile(r'^[A-Za-z0-9_.:-]{1,160}$')


def _safe_value(value):
    if not isinstance(value,str):
        return None
    cleaned=value.strip()
    return cleaned if _SAFE_VALUE.fullmatch(cleaned) else None


def _upstream_status(exc):
    for name in ('code','status_code','status'):
        value=getattr(exc,name,None)
        if isinstance(value,int) and 100<=value<=599:
            return value
    return None


def _upstream_headers(exc):
    headers=getattr(exc,'headers',None) or getattr(exc,'hdrs',None)
    if headers is not None:
        return headers
    response=getattr(exc,'response',None)
    return getattr(response,'headers',None)


def _upstream_request_id(exc):
    headers=_upstream_headers(exc)
    if headers is None:
        return None
    for name in ('x-request-id','request-id','x-goog-request-id'):
        value=_safe_value(headers.get(name))
        if value:
            return value
    return None


def _upstream_error_code(exc):
    if not isinstance(exc,HTTPError):
        return None
    try:
        payload=json.loads(exc.read(16_384).decode('utf-8'))
    except (AttributeError,UnicodeError,ValueError):
        return None
    error=payload.get('error') if isinstance(payload,dict) else None
    if not isinstance(error,dict):
        return None
    return _safe_value(error.get('code')) or _safe_value(error.get('type'))


def build_provider_failure_detail(provider,label,exc,*,trace_id=None):
    """Build a user-safe error and correlate it with sanitized server logs."""
    trace_id=trace_id or f"TL-{uuid.uuid4().hex[:12].upper()}"
    detail={
        'stage':f'{provider}_agent',
        'provider':provider,
        'error_type':type(exc).__name__,
        'trace_id':trace_id,
    }
    status=_upstream_status(exc)
    error_code=_upstream_error_code(exc)
    request_id=_upstream_request_id(exc)
    if status is not None:
        detail['upstream_status']=status
    if error_code:
        detail['upstream_error_code']=error_code
    if request_id:
        detail['upstream_request_id']=request_id

    message=f'{label} 분석 실패: {detail["error_type"]}. 입력은 유지됩니다.'
    if status is not None:
        message+=f' 외부 API HTTP {status}.'
    if error_code:
        message+=f' 오류 코드 {error_code}.'
    detail['message']=message+f' 서버 로그 추적 ID: {trace_id}.'
    return detail


def log_provider_failure(logger:logging.Logger,detail):
    """Log only correlation and sanitized provider metadata, never body/key text."""
    allowed=('trace_id','stage','provider','error_type','upstream_status',
             'upstream_error_code','upstream_request_id')
    fields={key:detail[key] for key in allowed if key in detail}
    logger.error('analysis_provider_failed %s',json.dumps(fields,sort_keys=True))
