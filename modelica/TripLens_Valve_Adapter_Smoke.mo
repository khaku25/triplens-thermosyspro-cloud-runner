within ;
model TripLens_Valve_Adapter_Smoke
  extends TripLens_CombinedCycle_TripTAC(
    fmuVlvHPSteamModeAuto(start=false)=false,
    fmuVlvHPSteamManualCmd(start=0.2)=0.2,
    fmuVlvHPSteamFaultEnable(start=false)=false,
    fmuVlvIPTurbAdmModeAuto(start=true)=true,
    fmuVlvIPTurbAdmFaultEnable(start=true)=true,
    fmuVlvIPTurbAdmFaultValue(start=0)=0);
end TripLens_Valve_Adapter_Smoke;
