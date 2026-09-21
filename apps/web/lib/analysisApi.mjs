const SAME_ORIGIN_API_BASE='/api/triplens';

export function analysisApiUrl(path=''){
  const suffix=String(path).startsWith('/')?String(path):`/${path}`;
  return `${SAME_ORIGIN_API_BASE}${suffix}`;
}
