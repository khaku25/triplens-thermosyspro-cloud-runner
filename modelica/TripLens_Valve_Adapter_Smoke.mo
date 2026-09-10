within ;
model TripLens_Valve_Adapter_Smoke
  extends TripLens_CombinedCycle_TripTAC(
    fmuVlvHPSteamModeAuto(start=false)=false,
    fmuVlvHPSteamManualCmd(start=0.45)=0.45,
    fmuVlvHPSteamFaultEnable(start=false)=false,
    fmuVlvIPTurbAdmModeAuto(start=true)=true,
    fmuVlvIPTurbAdmFaultEnable(start=true)=true,
    fmuVlvIPTurbAdmFaultValue(start=0.6)=0.6);
end TripLens_Valve_Adapter_Smoke;
