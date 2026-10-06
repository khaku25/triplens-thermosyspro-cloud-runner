model If97DomainGuardRegression
  ThermoSysPro.Properties.WaterSteam.Common.ThermoProperties_ph at_10_2641_MPa;
  ThermoSysPro.Properties.WaterSteam.Common.ThermoProperties_ph at_15_7443_MPa;
equation
  at_10_2641_MPa = ThermoSysPro.Properties.Fluid.Ph(
    P=10.2641e6, h=4.2e6, mode=0, fluid=1);
  at_15_7443_MPa = ThermoSysPro.Properties.Fluid.Ph(
    P=15.7443e6, h=4.2e6, mode=0, fluid=1);
  assert(at_10_2641_MPa.d > 0,
    "IF97 guard returned nonpositive density at 10.2641 MPa");
  assert(at_15_7443_MPa.d > 0,
    "IF97 guard returned nonpositive density at 15.7443 MPa");
end If97DomainGuardRegression;
