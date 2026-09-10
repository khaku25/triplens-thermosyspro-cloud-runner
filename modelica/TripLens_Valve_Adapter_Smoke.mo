within ;
model TripLens_Valve_Adapter_Smoke
  extends TripLens_CombinedCycle_TripTAC(
    fmuVlvHPSteamModeAuto=false,
    fmuVlvHPSteamManualCmd=0.2,
    fmuVlvHPSteamFaultEnable=false,
    fmuVlvIPTurbAdmModeAuto=true,
    fmuVlvIPTurbAdmFaultEnable=true,
    fmuVlvIPTurbAdmFaultValue=0);
end TripLens_Valve_Adapter_Smoke;
