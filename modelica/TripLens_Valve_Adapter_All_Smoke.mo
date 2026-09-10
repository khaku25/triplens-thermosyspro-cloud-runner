within ;
model TripLens_Valve_Adapter_All_Smoke
  extends TripLens_CombinedCycle_TripTAC(
    fmuVlvHPFWCVModeAuto(start=false)=false,
    fmuVlvHPFWCVManualCmd(start=0.76)=0.76,
    fmuVlvHPSteamModeAuto(start=false)=false,
    fmuVlvHPSteamManualCmd(start=0.475)=0.475,
    fmuVlvIPFWCVModeAuto(start=false)=false,
    fmuVlvIPFWCVManualCmd(start=0.76)=0.76,
    fmuVlvIPSteamModeAuto(start=false)=false,
    fmuVlvIPSteamManualCmd(start=0.475)=0.475,
    fmuVlvLPSteamModeAuto(start=false)=false,
    fmuVlvLPSteamManualCmd(start=0.76)=0.76,
    fmuVlvLPFWModeAuto(start=false)=false,
    fmuVlvLPFWManualCmd(start=0.475)=0.475,
    fmuVlvLPToHPIPFWModeAuto(start=false)=false,
    fmuVlvLPToHPIPFWManualCmd(start=0.95)=0.95,
    fmuVlvCondExtractionModeAuto(start=false)=false,
    fmuVlvCondExtractionManualCmd(start=0.76)=0.76,
    fmuVlvHPTurbAdmModeAuto(start=false)=false,
    fmuVlvHPTurbAdmManualCmd(start=0.76)=0.76,
    fmuVlvHPFWIsoModeAuto(start=false)=false,
    fmuVlvHPFWIsoManualCmd(start=0.76)=0.76,
    fmuVlvIPFWIsoModeAuto(start=false)=false,
    fmuVlvIPFWIsoManualCmd(start=0.76)=0.76,
    fmuVlvIPTurbAdmModeAuto(start=false)=false,
    fmuVlvIPTurbAdmManualCmd(start=0.76)=0.76);
end TripLens_Valve_Adapter_All_Smoke;
