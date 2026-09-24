// Coordinates come from the Diagram graphics of the uploaded ProcessView v36.
// Box order is Modelica x-min, y-min, x-max, y-max (y increases upwards).
const plant = {
  GT: ['GT',[-220,18,-204,35]], GTG: ['GTG',[-195,18,-179,35]],
  HP_DRUM: ['HP Drum',[-126,-101,-94,-67]], IP_DRUM: ['IP Drum',[27,-101,59,-67]],
  LP_DRUM: ['LP Drum',[196,-110,228,-67]],
  HP_TURBINE: ['HP Turbine',[-76,58,-44,90]], IP_TURBINE: ['IP Turbine',[116,58,148,90]],
  LP_TURBINE: ['LP Turbine',[186,58,218,90]],
  HP_TURB_ADM_VLV: ['HP Turbine Admission Valve',[-114,62,-84,86]],
  IP_TURB_ADM_VLV: ['IP Turbine Admission Valve',[78,62,108,86]],
  HP_BYPASS_VLV: ['HP Bypass',[-112,22,-86,42]], LP_BYPASS_VLV: ['LP Bypass',[76,22,102,42]],
  HP_SPRAY: ['HP Spray',[-74,22,-48,42]], LP_SPRAY: ['LP Spray',[114,22,140,42]],
  HP_BFP: ['HP BFP',[-194,-88,-170,-64]], IP_BFP: ['IP BFP',[-41,-88,-17,-64]],
  LP_BFP: ['LP BFP',[140,-88,164,-64]],
  HP_BFP_NRV: ['HP BFP NRV',[-158,-85,-146,-67]],
  IP_BFP_NRV: ['IP BFP NRV',[-5,-85,7,-67]],
  LP_BFP_NRV: ['LP BFP NRV',[174,-85,186,-67]],
  CONDENSER: ['Condenser',[180,-48,228,-10]],
};

export const PLANT_PROCESS = Object.freeze({
  image: '/drawing/plant-process-v36.png',
  imageSize: [2044,1285],
  viewBox: [-240,-165,240,140],
  source: 'TripLens_CombinedCycle_TripTAC_ProcessView_v36(2).mo · Diagram annotation',
  hotspots: Object.freeze(Object.fromEntries(Object.entries(plant).map(([id,[label,box]]) => [id,{label,box}]))),
});

export const PLANT_REGISTERED_SIGNALS = Object.freeze([
  Object.freeze({
    label: 'ST GRID POWER',
    tag: 'vppSTGridPowerMW',
    unit: 'MW',
    access: 'READ-ONLY',
    href: '/logic?tag=vppSTGridPowerMW',
  }),
]);

export function modelBoxStyle(box, viewBox = PLANT_PROCESS.viewBox) {
  const [left,bottom,right,top] = box;
  const [minX,minY,maxX,maxY] = viewBox;
  const pct = n => `${Number((n * 100).toFixed(5))}%`;
  return {left:pct((left-minX)/(maxX-minX)),top:pct((maxY-top)/(maxY-minY)),
    width:pct((right-left)/(maxX-minX)),height:pct((top-bottom)/(maxY-minY))};
}
