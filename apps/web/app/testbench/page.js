import IntegrationTestbench from '../../components/IntegrationTestbench';
import {notFound} from 'next/navigation';

export const metadata={title:'TripLens 연동 단위기기 테스트'};

export default function TestbenchPage(){
  if(process.env.NODE_ENV!=='development')notFound();
  return <IntegrationTestbench/>;
}
