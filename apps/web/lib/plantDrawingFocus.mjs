import {PLANT_PROCESS} from './plantHotspots.mjs';

// These source-drawing anchors show the related process area only. The v36
// Diagram has no separate symbol for the equipment identities on the left.
const relatedAreas=Object.freeze({
  HP_FWCV:'HP_DRUM',
  HP_STEAM_VLV:'HP_DRUM',
  IP_FWCV:'IP_DRUM',
  IP_STEAM_VLV:'IP_DRUM',
  LP_STEAM_VLV:'LP_DRUM',
  LP_FW_VLV:'LP_DRUM',
  LP_TO_HPIP_FW_VLV:'LP_BFP',
  COND_EXTRACTION_VLV:'CONDENSER',
  HP_FW_ISO_VLV:'HP_BFP_NRV',
  IP_FW_ISO_VLV:'IP_BFP_NRV',
  HP_FEEDWATER:'HP_BFP',
  IP_FEEDWATER:'IP_BFP',
  LP_FEEDWATER:'LP_BFP',
  GT_EXHAUST:'GT',
});

export function resolvePlantFocus(row){
  const id=row?.plant_location_id;
  if(!id)return null;
  if(PLANT_PROCESS.hotspots[id])return {locationId:id,kind:'exact'};
  const locationId=relatedAreas[id];
  return locationId&&PLANT_PROCESS.hotspots[locationId]?{locationId,kind:'related'}:null;
}
