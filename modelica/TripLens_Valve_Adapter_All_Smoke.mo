within ;
model TripLens_Valve_Adapter_All_Smoke
  extends TripLens_CombinedCycle_TripTAC(
    fmuVlvHPFWCVModeAuto(start=true)=time < 0.2,
    fmuVlvHPFWCVManualCmd(start=0.76)=0.76,
    fmuVlvHPSteamModeAuto(start=true)=time < 0.2,
    fmuVlvHPSteamManualCmd(start=0.475)=0.475,
    fmuVlvIPFWCVModeAuto(start=true)=time < 0.2,
    fmuVlvIPFWCVManualCmd(start=0.76)=0.76,
    fmuVlvIPSteamModeAuto(start=true)=time < 0.2,
    fmuVlvIPSteamManualCmd(start=0.475)=0.475,
    fmuVlvLPSteamModeAuto(start=true)=time < 0.2,
    fmuVlvLPSteamManualCmd(start=0.76)=0.76,
    fmuVlvLPFWModeAuto(start=true)=time < 0.2,
    fmuVlvLPFWManualCmd(start=0.475)=0.475,
    fmuVlvLPToHPIPFWModeAuto(start=true)=time < 0.2,
    fmuVlvLPToHPIPFWManualCmd(start=0.95)=0.95,
    fmuVlvCondExtractionModeAuto(start=true)=time < 0.2,
    fmuVlvCondExtractionManualCmd(start=0.76)=0.76,
    fmuVlvHPTurbAdmModeAuto(start=true)=time < 0.2,
    fmuVlvHPTurbAdmManualCmd(start=0.76)=0.76,
    fmuVlvHPFWIsoModeAuto(start=true)=time < 0.2,
    fmuVlvHPFWIsoManualCmd(start=0.76)=0.76,
    fmuVlvIPFWIsoModeAuto(start=true)=time < 0.2,
    fmuVlvIPFWIsoManualCmd(start=0.76)=0.76,
    fmuVlvIPTurbAdmModeAuto(start=true)=time < 0.2,
    fmuVlvIPTurbAdmManualCmd(start=0.76)=0.76);
end TripLens_Valve_Adapter_All_Smoke;
