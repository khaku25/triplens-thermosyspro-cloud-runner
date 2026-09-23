import {resolveEquipmentDrawing} from './equipmentDrawingMaster.mjs';

// Names are the nine equipment-page titles in the current Logic Master index.
// Each value resolves through the existing Equipment Master, not through a
// guessed physical location in the logic diagram.
const equipmentPages=Object.freeze({
  'GT Exhaust':'GT EXHAUST',
  'ST Protection':'ST',
  'FWP HP':'HP BFP',
  'GT Protection':'GT',
  'IP Drum':'IP DRUM',
  'FWP IP':'IP BFP',
  'LP Drum':'LP DRUM',
  'HP Drum':'HP DRUM',
  'FWP LP':'LP BFP',
});

export function resolveLogicEquipmentPage(pageName){
  return resolveEquipmentDrawing(equipmentPages[pageName]||'');
}

export function logicDrawingHref(pageName){
  const row=resolveLogicEquipmentPage(pageName);
  if(!row)return '/drawing?view=plant';
  return '/drawing?'+new URLSearchParams({equipment:row.event_equipment,view:row.plant_location_id?'plant':'ecms'});
}
