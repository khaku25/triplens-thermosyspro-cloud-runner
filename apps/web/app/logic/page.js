import LogicViewerFrame from '../../components/LogicViewerFrame';

export const metadata = { title: 'TripLens | 태그·로직 상세보기' };
export default function LogicPage() {
  return <main style={{ height: '100dvh', display: 'flex', flexDirection: 'column', background: '#f4f7fb' }}>
    <header style={{ minHeight: 46, padding: '10px 16px', display: 'flex', gap: 20, alignItems: 'center', color: '#18354d' }}>
      <a href="/" style={{ color: '#145970', fontWeight: 700 }}>← TripLens 분석 화면</a>
      <span>태그 · 로직 · Drawing Master 도면 검색 · 설비별 분류</span>
    </header>
    <LogicViewerFrame src="/logic-assets/viewer.html" title="TripLens 태그·로직 상세보기" style={{ flex: 1, width: '100%', border: 0, minHeight: 0 }} />
  </main>;
}
