import {NextResponse} from 'next/server';

const UPSTREAM=(process.env.TRIPLENS_API_UPSTREAM||'https://triplens-agent-api-preview.vercel.app').replace(/\/$/,'');

async function proxy(request,{params}){
  const {path=[]}=await params;
  const target=`${UPSTREAM}/${path.join('/')}`;
  const body=request.method==='GET'||request.method==='HEAD'?undefined:await request.formData();
  const response=await fetch(target,{method:request.method,body,cache:'no-store'});
  const headers=new Headers(response.headers);
  headers.delete('content-encoding');
  headers.delete('content-length');
  return new NextResponse(await response.arrayBuffer(),{status:response.status,headers});
}

export const GET=proxy;
export const POST=proxy;
