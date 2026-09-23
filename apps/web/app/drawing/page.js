import DrawingMaster from '../../components/DrawingMaster';
import './drawing.css';

export const metadata = { title: 'TripLens | Drawing Master' };

export default async function DrawingPage({ searchParams }) {
  const params = await searchParams;
  return <DrawingMaster initialQuery={{
    equipment: typeof params?.equipment === 'string' ? params.equipment : '',
    view: typeof params?.view === 'string' ? params.view : '',
    page: typeof params?.page === 'string' ? params.page : '',
  }}/>
}
