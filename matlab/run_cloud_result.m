function result = run_cloud_result(resultFolder)
%RUN_CLOUD_RESULT Load and inspect a TripLens ECMS 3.1 6.9 kV result.
%   RESULT = RUN_CLOUD_RESULT() loads the package's bundled outputs folder.
%   RESULT = RUN_CLOUD_RESULT(FOLDER) loads FOLDER/outputs or FOLDER.
%   This viewer never falls back to the legacy 6.6 kV/SST model.

arguments
    resultFolder (1,1) string = ""
end

baseDir = fileparts(mfilename("fullpath"));
packageRoot = fileparts(baseDir);
if strlength(resultFolder) == 0
    resultFolder = packageRoot;
end

outputsFolder = resultFolder;
if isfolder(fullfile(resultFolder,"outputs"))
    outputsFolder = fullfile(resultFolder,"outputs");
end

required = ["processbus.csv","ecms-trend.csv","ecms-events.csv", ...
    "ecms-feeders.csv","manifest.json"];
missingFiles = strings(0,1);
for index = 1:numel(required)
    candidate = fullfile(outputsFolder,required(index));
    if ~isfile(candidate)
        missingFiles(end+1,1) = candidate; %#ok<AGROW>
    end
end
if ~isempty(missingFiles)
    error("TripLens:MissingCloudResult", ...
        "ECMS 3.1 result is incomplete. Missing:\n%s\nRun ECMS_RUN or the full cloud pipeline first.", ...
        join(missingFiles,newline));
end

result = struct();
result.ProcessBus = readtable(fullfile(outputsFolder,"processbus.csv"), ...
    "Delimiter",",","ReadVariableNames",true,"VariableNamingRule","preserve");
result.ECMSTrend = readtable(fullfile(outputsFolder,"ecms-trend.csv"), ...
    "Delimiter",",","ReadVariableNames",true,"VariableNamingRule","preserve");
result.ECMSEvents = readtable(fullfile(outputsFolder,"ecms-events.csv"), ...
    "Delimiter",",","ReadVariableNames",true,"VariableNamingRule","preserve","TextType","string");
result.ECMSFeeders = readtable(fullfile(outputsFolder,"ecms-feeders.csv"), ...
    "Delimiter",",","ReadVariableNames",true,"VariableNamingRule","preserve","TextType","string");
result.Manifest = jsondecode(fileread(fullfile(outputsFolder,"manifest.json")));
result.OutputsFolder = outputsFolder;

requireColumns(result.ProcessBus, ...
    ["time_s","stg_power_w","gt_exhaust_mass_flow_kg_s","gt_exhaust_temperature_k"],"processbus.csv");
requireColumns(result.ECMSTrend, ...
    ["source_time_ms","bus_a_voltage_pu","bus_b_voltage_pu"],"ecms-trend.csv");
requireColumns(result.ECMSEvents, ...
    ["source_time_ms","tag","new_value","event_class"],"ecms-events.csv");
requireColumns(result.ECMSFeeders, ...
    ["source_time_ms","equipment_id","bus","feeder_id","breaker_closed", ...
    "energized","bus_voltage_kv"],"ecms-feeders.csv");

[sourceLabel,isSynthetic,isVerifiedPhysics] = identifySource(result.Manifest,result.ProcessBus);
result.SourceLabel = sourceLabel;
result.IsSynthetic = isSynthetic;
result.IsVerifiedPhysics = isVerifiedPhysics;

viewer = figure("Name","TripLens ECMS 3.1 Result — 6.9 kV / no SST","Color","w");
try
    viewer.WindowState = "maximized";
catch
    viewer.Position = [40 60 1180 760];
end
layout = tiledlayout(viewer,4,1,"TileSpacing","compact","Padding","compact");
if isSynthetic
    header = "SYNTHETIC MATLAB FALLBACK — ThermoSysPro 결과가 아님";
elseif isVerifiedPhysics
    header = "Verified ThermoSysPro Cloud + TripLens ECMS";
else
    header = "UNVERIFIED RESULT SOURCE — provenance 확인 필요";
end
title(layout,header+" · 6.9 kV / no SST","FontWeight","bold");

nexttile(layout);
plot(asDouble(result.ProcessBus.time_s,"processbus.time_s"), ...
    asDouble(result.ProcessBus.stg_power_w,"processbus.stg_power_w")./1e6,"LineWidth",1.2);
grid on;
ylabel("STG MW");
title(sourceLabel+" · steam-turbine generator output");

nexttile(layout);
processTime = asDouble(result.ProcessBus.time_s,"processbus.time_s");
plot(processTime,asDouble(result.ProcessBus.gt_exhaust_mass_flow_kg_s, ...
    "processbus.gt_exhaust_mass_flow_kg_s"),"LineWidth",1.2);
hold on;
yyaxis right;
plot(processTime,asDouble(result.ProcessBus.gt_exhaust_temperature_k, ...
    "processbus.gt_exhaust_temperature_k"),"LineWidth",1.2);
grid on;
ylabel("Temperature K");
yyaxis left;
ylabel("Flow kg/s");
title("GT exhaust boundary conditions");

nexttile(layout);
timeSeconds = asDouble(result.ECMSTrend.source_time_ms,"trend.source_time_ms")./1000;
stairs(timeSeconds,asDouble(result.ECMSTrend.bus_a_voltage_pu, ...
    "trend.bus_a_voltage_pu"),"LineWidth",1.2);
hold on;
stairs(timeSeconds,asDouble(result.ECMSTrend.bus_b_voltage_pu, ...
    "trend.bus_b_voltage_pu"),"LineWidth",1.2);
grid on;
xlabel("Simulation time s");
ylabel("Voltage pu");
legend("BUS-A","BUS-B","Location","best");
title("Derived ECMS 6.9 kV auxiliary-bus voltage");

nexttile(layout);
feederTime = asDouble(result.ECMSFeeders.source_time_ms,"feeders.source_time_ms")./1000;
feederEnergized = asDouble(result.ECMSFeeders.energized,"feeders.energized");
[sampleTimes,~,sampleGroup] = unique(feederTime,"sorted");
energizedCount = accumarray(sampleGroup,feederEnergized,[],@sum);
stairs(sampleTimes,energizedCount,"LineWidth",1.2);
grid on;
xlabel("Simulation time s");
ylabel("Energized feeders");
title("A-equipment feeder state reflected in ECMS output");

fprintf("TripLens ECMS 3.1 result loaded from: %s\n",char(outputsFolder));
fprintf("Result source: %s\n",char(sourceLabel));
if isSynthetic
    warning("TripLens:SyntheticFallback", ...
        "This result is a synthetic MATLAB fallback, not a ThermoSysPro result or field measurement.");
elseif ~isVerifiedPhysics
    warning("TripLens:UnverifiedResultSource", ...
        "The manifest does not explicitly prove a ThermoSysPro run. Treat this result as unverified.");
end
disp(result.ECMSEvents);
end

function requireColumns(inputTable,requiredNames,fileLabel)
actualNames = string(inputTable.Properties.VariableNames);
missingNames = setdiff(requiredNames,actualNames,"stable");
if ~isempty(missingNames)
    error("TripLens:InvalidCloudResult", ...
        "%s is missing required columns: %s",fileLabel,join(missingNames,", "));
end
end

function values = asDouble(input,label)
if isnumeric(input) || islogical(input)
    values = double(input);
else
    values = str2double(string(input));
end
values = values(:);
if any(~isfinite(values))
    error("TripLens:InvalidCloudResult","%s contains a non-finite numeric value.",label);
end
end

function [label,isSynthetic,isVerifiedPhysics] = identifySource(manifest,processBus)
isSynthetic = false;
isVerifiedPhysics = false;
if isstruct(manifest) && isfield(manifest,"runtime") && isstruct(manifest.runtime)
    runtime = manifest.runtime;
    if isfield(runtime,"thermosyspro_used") && isequal(runtime.thermosyspro_used,false)
        isSynthetic = true;
    end
    if isfield(runtime,"engine") && contains(upper(string(runtime.engine)),"SYNTHETIC")
        isSynthetic = true;
    end
    if isfield(runtime,"thermosyspro_used") && isequal(runtime.thermosyspro_used,true)
        if isfield(runtime,"engine") && contains(upper(string(runtime.engine)),"THERMOSYSPRO")
            isVerifiedPhysics = true;
        elseif isfield(runtime,"thermosyspro_commit") && strlength(string(runtime.thermosyspro_commit))>0
            isVerifiedPhysics = true;
        end
    end
end
if any(string(processBus.Properties.VariableNames)=="data_origin")
    if any(contains(upper(string(processBus.data_origin)),"SYNTHETIC"))
        isSynthetic = true;
    end
end
if isSynthetic
    label = "MATLAB synthetic fallback";
    isVerifiedPhysics = false;
elseif isVerifiedPhysics
    label = "Verified ThermoSysPro cloud result";
else
    label = "Unverified result source";
end
end
