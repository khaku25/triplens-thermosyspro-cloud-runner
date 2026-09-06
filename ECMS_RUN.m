function result = ECMS_RUN(varargin)
%ECMS_RUN Run and view the MATLAB-native TripLens ECMS VPP.
%   ECMS_RUN creates a new atomic run with the canonical package CSV files.
%   ECMS_RUN('FaultPreset','grid_loss') selects a fault preset.
%   ECMS_RUN('CommandFile','examples/commands.csv') applies a command queue.
%   Live editor tables can be passed as SettingsTable, EquipmentTable and
%   CommandTable. No legacy start_here function is ever called.

packageRoot = fileparts(mfilename("fullpath"));
matlabDir = fullfile(packageRoot,"matlab");
engineFile = fullfile(matlabDir,"triplens_ecms_vpp_simulate.m");
viewerFile = fullfile(matlabDir,"run_cloud_result.m");
assert(isfile(engineFile),"TripLens:MissingNativeEngine", ...
    "MATLAB-native ECMS engine not found: %s",engineFile);
assert(isfile(viewerFile),"TripLens:MissingViewer", ...
    "ECMS result viewer not found: %s",viewerFile);

addpath(matlabDir,"-begin");
rehash;
clear triplens_ecms_vpp_simulate run_cloud_result;
resolvedEngine = string(which("triplens_ecms_vpp_simulate"));
resolvedViewer = string(which("run_cloud_result"));
assert(resolvedEngine==string(engineFile),"TripLens:WrongNativeEngine", ...
    "A different ECMS engine is shadowing this package: %s",resolvedEngine);
assert(resolvedViewer==string(viewerFile),"TripLens:WrongViewer", ...
    "A different ECMS viewer is shadowing this package: %s",resolvedViewer);

simulation = triplens_ecms_vpp_simulate("PackageRoot",packageRoot,varargin{:});
view = run_cloud_result(simulation.RunFolder);
view.Simulation = simulation;
result = view;
fprintf("PASS: ECMS_RUN generated and opened %s\n",simulation.RunFolder);
end
