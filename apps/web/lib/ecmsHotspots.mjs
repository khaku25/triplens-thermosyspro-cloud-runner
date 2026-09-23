export const ECMS_HOTSPOT_PAGES = Object.freeze({
  ECMS_VPP: {
    viewBox:[0,0,1400,800],
    src:'/drawing/ecms-overview-matlab.svg',
    hotspots:{
      GT:{box:[42,307,56,56],label:'GT Generator'},
      '52GT':{box:[165,311,50,48],label:'52GT'},
      'TR-GT':{box:[300,215,60,40],label:'GT Main TR'},
      'UAT-A':{box:[300,425,60,40],label:'UAT-A'},
      'CB-IN-A':{box:[305,526,50,48],label:'A Incoming'},
      'BUS-A':{box:[255,665,150,40],label:'6.9 kV BUS-A',view:'BUS-A'},
      'CB-TIE-AB':{box:[675,661,50,48],label:'6.9 kV Bus Tie'},
      'BUS-B':{box:[995,665,150,40],label:'6.9 kV BUS-B',view:'BUS-B'},
      'CB-IN-B':{box:[1045,526,50,48],label:'B Incoming'},
      'UAT-B':{box:[1040,425,60,40],label:'UAT-B'},
      'TR-ST':{box:[1040,215,60,40],label:'ST Main TR'},
      '52ST':{box:[1185,311,50,48],label:'52ST'},
      ST:{box:[1302,307,56,56],label:'ST Generator'}
    }
  },
  ECMS_6P9KV: {
    viewBox:[0,0,1500,900],
    src:'/drawing/ecms-6p9kv-matlab.svg',
    hotspots:{
      'UAT-A':{box:[350,120,95,130],label:'UAT-A'},
      'CB-IN-A':{box:[355,175,105,52],label:'IN-A'},
      'BUS-A':{box:[70,225,620,55],label:'6.9 kV BUS-A'},
      'VCB-A01':{box:[125,295,50,62],label:'VCB-A01'},
      'FWP-HP':{box:[68,380,165,96],label:'HP 급수펌프'},
      'VCB-A02':{box:[585,295,50,62],label:'VCB-A02'},
      'FWP-LP':{box:[528,380,165,96],label:'LP 급수펌프'},
      'CB-TIE-AB':{box:[700,220,100,82],label:'TIE-AB'},
      'UAT-B':{box:[1090,120,105,130],label:'UAT-B'},
      'CB-IN-B':{box:[1095,175,110,52],label:'IN-B'},
      'BUS-B':{box:[810,225,620,55],label:'6.9 kV BUS-B'},
      'VCB-B01':{box:[1325,295,50,62],label:'VCB-B01'},
      'FWP-IP':{box:[1268,380,165,96],label:'IP 급수펌프'}
    }
  }
});

const ALIASES=Object.freeze({
  'LP BFP':'FWP-LP',
  'HP BFP':'FWP-HP',
  'IP BFP':'FWP-IP'
});

export function resolveEcmsHotspot(pageId,equipmentOrObject){
  const page=ECMS_HOTSPOT_PAGES[pageId];
  if(!page)return null;
  const key=ALIASES[equipmentOrObject]||equipmentOrObject;
  const hit=page.hotspots[key];
  return hit?{...hit,key,pageId,src:page.src,viewBox:page.viewBox}:null;
}
