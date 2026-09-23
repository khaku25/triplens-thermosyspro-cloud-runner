import { PLANT_PROCESS, ECMS_VIEWS } from './plantHotspots.mjs';

// Canonical identifiers retain ECMS's FWP-HP/IP/LP equipment IDs.
const entries = [
  ['GT','GT',null,['Gas Turbine']], ['GTG','GTG','GTG',['GT GENERATOR']],
  ['HP-DRUM','HP_DRUM',null,['HP DRUM']], ['IP-DRUM','IP_DRUM',null,['IP DRUM']],
  ['LP-DRUM','LP_DRUM',null,['LP DRUM']],
  ['HP-TURBINE','HP_TURBINE',null,['HP TURB']],
  ['IP-TURBINE','IP_TURBINE',null,['IP TURB']],
  ['LP-TURBINE','LP_TURBINE',null,['LP TURB']],
  ['HP-BYPASS-VLV','HP_BYPASS_VLV',null,['HP BYPASS','HP BYPASS VALVE']],
  ['LP-BYPASS-VLV','LP_BYPASS_VLV',null,['LP BYPASS','LP BYPASS VALVE']],
  ['HP-SPRAY','HP_SPRAY',null,['HP SPRAY VALVE']],
  ['LP-SPRAY','LP_SPRAY',null,['LP SPRAY VALVE']],
  ['FWP-HP','HP_BFP','VCB-A01',['HP BFP','HP FWP','BFP-HP','HP BFP TRIP']],
  ['FWP-IP','IP_BFP','VCB-B01',['IP BFP','IP FWP','BFP-IP','IP BFP TRIP']],
  ['FWP-LP','LP_BFP','VCB-A02',['LP BFP','LP FWP','BFP-LP','LP BFP TRIP']],
  ['HP-BFP-NRV','HP_BFP_NRV',null,['HP FWP NRV','HP NRV']],
  ['IP-BFP-NRV','IP_BFP_NRV',null,['IP FWP NRV','IP NRV']],
  ['LP-BFP-NRV','LP_BFP_NRV',null,['LP FWP NRV','LP NRV']],
  ['CONDENSER','CONDENSER',null,[]],
  ['STG',null,'STG',['ST GENERATOR']],
  ['52GT',null,'52GT',['CB-52GT']], ['52ST',null,'52ST',['CB-52ST']],
  ['BUS-A',null,'BUS-A',['6.9 KV BUS-A']], ['BUS-B',null,'BUS-B',['6.9 KV BUS-B']],
  ['CB-TIE-AB',null,'CB-TIE-AB',['TIE-AB']],
  ['VCB-A01',null,'VCB-A01',[]], ['VCB-A02',null,'VCB-A02',[]],
  ['VCB-B01',null,'VCB-B01',[]],
];

const key = value => String(value || '').trim().toUpperCase().replace(/[\s_]+/g,'-');
export const EQUIPMENT_MASTER = Object.freeze(entries.map(([equipment_id,plant_location_id,ecms_location_id,aliases]) =>
  Object.freeze({equipment_id,plant_location_id,ecms_location_id,aliases:Object.freeze(aliases)})));
const byName = new Map();
for (const row of EQUIPMENT_MASTER) {
  if (row.plant_location_id && !PLANT_PROCESS.hotspots[row.plant_location_id]) throw Error(`Plant location missing: ${row.equipment_id}`);
  if (row.ecms_location_id && !Object.values(ECMS_VIEWS).some(v => v.hotspots[row.ecms_location_id])) throw Error(`ECMS location missing: ${row.equipment_id}`);
  for (const name of [row.equipment_id,...row.aliases]) {
    const normalized = key(name);
    if (byName.has(normalized) && byName.get(normalized) !== row) throw Error(`Duplicate equipment alias: ${name}`);
    byName.set(normalized,row);
  }
}

export function resolveEquipment(name) { return byName.get(key(name)) || null; }

export function resolveDrawingRequest({equipment = '',view = '',page = ''} = {}) {
  const record = resolveEquipment(equipment);
  const selectedView = view === 'plant' || view === 'ecms' ? view : record?.plant_location_id ? 'plant' : 'ecms';
  const locationId = selectedView === 'plant' ? record?.plant_location_id || null : record?.ecms_location_id || null;
  const selectedPage = selectedView === 'ecms'
    ? (page === 'detail' || (page !== 'overview' && locationId && !ECMS_VIEWS.overview.hotspots[locationId])) ? 'detail' : 'overview'
    : 'overview';
  return {view:selectedView,page:selectedPage,locationId,record};
}

export function drawingHref(equipment, view = '') {
  const query = new URLSearchParams({equipment:String(equipment || '')});
  if (view === 'plant' || view === 'ecms') query.set('view',view);
  return `/drawing?${query}`;
}
