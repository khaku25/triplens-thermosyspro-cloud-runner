function result = triplens_ecms_vpp_simulate(varargin)
%TRIPLENS_ECMS_VPP_SIMULATE Run the MATLAB-native TripLens ECMS VPP.
%   RESULT = TRIPLENS_ECMS_VPP_SIMULATE() creates a complete, atomic run
%   folder under <package>/runs.  It does not require Python, GitHub,
%   OpenModelica, or the current MATLAB folder.
%
%   Name-value inputs:
%     PackageRoot    Package folder. Normally inferred from this file.
%     SettingsTable  Live A-setting table from the editor (optional).
%     EquipmentTable Live A-equipment table from the editor (optional).
%     CommandTable   Live command table from the editor (optional).
%     SettingsFile   CSV used when SettingsTable is empty.
%     EquipmentFile  CSV used when EquipmentTable is empty.
%     CommandFile    Optional command CSV used when CommandTable is empty.
%     OutputRoot     Parent folder for atomic run folders.
%     FaultPreset    none, grid_loss, relay_fail, etc.
%     TripTime       Synthetic GT Trip time in seconds.
%     StopTime       Synthetic run stop time in seconds.
%     SamplingProfile standard (default) or incident_1ms.
%     IncidentPeriodMs Incident-window trend period in milliseconds.
%     IncidentPreMs  Incident-window duration before TripTime in ms.
%     IncidentPostMs Incident-window duration after TripTime in ms.
%
%   This is an explicitly SYNTHETIC MATLAB fallback.  It preserves the
%   TripLens 6.9 kV topology (UAT-A/UAT-B taps, no SST) and consumes the
%   same A configuration as the cloud/Python pipeline, but its ProcessBus
%   is not a ThermoSysPro physics result.

parser = inputParser;
parser.FunctionName = mfilename;
defaultPackageRoot = fileparts(fileparts(mfilename("fullpath")));
addParameter(parser,"PackageRoot",defaultPackageRoot,@isTextScalar);
addParameter(parser,"SettingsTable",table(),@(x) isempty(x) || istable(x));
addParameter(parser,"EquipmentTable",table(),@(x) isempty(x) || istable(x));
addParameter(parser,"CommandTable",table(),@(x) isempty(x) || istable(x));
addParameter(parser,"SettingsFile","",@isTextScalar);
addParameter(parser,"EquipmentFile","",@isTextScalar);
addParameter(parser,"CommandFile","",@isTextScalar);
addParameter(parser,"OutputRoot","",@isTextScalar);
addParameter(parser,"FaultPreset","none",@isTextScalar);
addParameter(parser,"TripTime",2,@isFiniteScalar);
addParameter(parser,"StopTime",8,@isFiniteScalar);
addParameter(parser,"SamplingProfile","standard",@isTextScalar);
addParameter(parser,"IncidentPeriodMs",1,@isFiniteScalar);
addParameter(parser,"IncidentPreMs",2000,@isFiniteScalar);
addParameter(parser,"IncidentPostMs",5000,@isFiniteScalar);
parse(parser,varargin{:});
options = parser.Results;

packageRoot = char(string(options.PackageRoot));
assert(isfolder(packageRoot),"TripLens:MissingPackageRoot", ...
    "ECMS package root does not exist: %s",packageRoot);

settingsFile = resolveOptionalPath(packageRoot,options.SettingsFile, ...
    fullfile("config","ecms_a_settings.csv"));
equipmentFile = resolveOptionalPath(packageRoot,options.EquipmentFile, ...
    fullfile("config","ecms_a_equipment.csv"));
commandFile = resolveOptionalPath(packageRoot,options.CommandFile,"");

if isempty(options.SettingsTable)
    assert(isfile(settingsFile),"TripLens:MissingASettings", ...
        "A-setting CSV does not exist: %s",settingsFile);
    settingsTable = readCsv(settingsFile);
else
    settingsTable = options.SettingsTable;
end
if isempty(options.EquipmentTable)
    assert(isfile(equipmentFile),"TripLens:MissingAEquipment", ...
        "A-equipment CSV does not exist: %s",equipmentFile);
    equipmentTable = readCsv(equipmentFile);
else
    equipmentTable = options.EquipmentTable;
end
if isempty(options.CommandTable)
    if isempty(commandFile)
        commandTable = emptyCommandTable();
    else
        assert(isfile(commandFile),"TripLens:MissingCommandFile", ...
            "Command CSV does not exist: %s",commandFile);
        commandTable = readCsv(commandFile);
    end
else
    commandTable = options.CommandTable;
end

[settings,settingsStatus] = validateSettings(settingsTable);
[equipment,equipmentStatus] = validateEquipment(equipmentTable);
assert(abs(settings.AUX_BUS_VOLTAGE_KV-6.9)<=1e-9, ...
    "TripLens:WrongTopologyVoltage", ...
    "This authoritative ECMS topology requires AUX_BUS_VOLTAGE_KV=6.9.");
assert(all(abs(equipment.voltage_kv-settings.AUX_BUS_VOLTAGE_KV)<=1e-9), ...
    "TripLens:EquipmentVoltageMismatch", ...
    "Every ECMS feeder voltage_kv must match AUX_BUS_VOLTAGE_KV (6.9 kV).");
configStatus = combineConfigStatus(settingsStatus,equipmentStatus);
commands = validateCommands(commandTable,packageRoot);
resolvedCommandTable = commandsToTable(commands);
faultPreset = lower(strtrim(char(string(options.FaultPreset))));
fault = loadFaultPreset(fullfile(packageRoot,"config","fault_presets.json"),faultPreset);
commonTripFile = fullfile(packageRoot,"config","common_trip_matrix.csv");
assert(isfile(commonTripFile),"TripLens:MissingCommonTripMatrix", ...
    "Common Trip matrix does not exist: %s",commonTripFile);
commonTripMatrix = validateCommonTripMatrix(readCsv(commonTripFile));

tripTime = double(options.TripTime);
stopTime = double(options.StopTime);
assert(tripTime >= 0,"TripLens:InvalidTripTime","TripTime must be non-negative.");
commandTripTimes = commands.time_s(commands.equipment_id == "GTG" & commands.command == "TRIP");
if ~isempty(commandTripTimes)
    if any(strcmp(parser.UsingDefaults,"TripTime"))
        tripTime = min(commandTripTimes);
    else
        tripTime = min([tripTime;commandTripTimes]);
    end
end
if ~isempty(commands.time_s) && max(commands.time_s)>stopTime
    if any(strcmp(parser.UsingDefaults,"StopTime"))
        stopTime = max(commands.time_s)+5;
    else
        error("TripLens:CommandOutsideRun", ...
            "Every command time_s must be within StopTime (%.3f s).",stopTime);
    end
end
if stopTime<=tripTime
    if any(strcmp(parser.UsingDefaults,"StopTime"))
        stopTime = tripTime+5;
    else
        error("TripLens:InvalidStopTime", ...
            "StopTime must be greater than the effective TripTime (%.3f s).",tripTime);
    end
end
tripTime = round(tripTime*1000)/1000;
stopTime = round(stopTime*1000)/1000;
assert(stopTime>tripTime,"TripLens:InvalidTimeResolution", ...
    "TripTime and StopTime must remain distinct at 1 ms resolution.");
feederProtection = resolveFeederProtection(fault,equipment,settings, ...
    round(tripTime*1000));

periodMs = round(settings.TREND_PERIOD_MS);
assert(periodMs > 0,"TripLens:InvalidTrendPeriod","TREND_PERIOD_MS must be positive.");
stopMs = round(stopTime*1000);
samplingProfile = lower(strtrim(string(options.SamplingProfile)));
assert(any(samplingProfile==["standard","incident_1ms"]), ...
    "TripLens:UnknownSamplingProfile", ...
    "SamplingProfile must be standard or incident_1ms, got %s.",samplingProfile);
incidentPeriodMs = validateWholeMilliseconds(options.IncidentPeriodMs, ...
    "IncidentPeriodMs",true);
incidentPreMs = validateWholeMilliseconds(options.IncidentPreMs, ...
    "IncidentPreMs",false);
incidentPostMs = validateWholeMilliseconds(options.IncidentPostMs, ...
    "IncidentPostMs",false);
assert(incidentPeriodMs<=periodMs,"TripLens:InvalidIncidentPeriod", ...
    "IncidentPeriodMs must not exceed TREND_PERIOD_MS (%d ms).",periodMs);
if samplingProfile=="incident_1ms"
    assert(incidentPeriodMs==1,"TripLens:InvalidIncidentPeriod", ...
        "incident_1ms requires IncidentPeriodMs=1.");
end
[timeMs,incidentStartMs,incidentStopMs,estimatedTrendRows] = buildSampleTimes( ...
    stopMs,periodMs,round(tripTime*1000),samplingProfile,incidentPeriodMs, ...
    incidentPreMs,incidentPostMs);
assert(estimatedTrendRows<=50000,"TripLens:FallbackRunTooLarge", ...
    "The MATLAB fallback would create about %d trend rows and too many feeder rows. " + ...
    "Shorten StopTime, shorten the incident window, or increase a sampling period.", ...
    estimatedTrendRows);
timeSeconds = timeMs./1000;

processBus = makeSyntheticProcessBus(timeSeconds,tripTime);
[trend,events] = simulateElectrical(processBus,timeMs,tripTime,settings, ...
    configStatus,fault,faultPreset,commands,samplingProfile,incidentPeriodMs, ...
    incidentStartMs,incidentStopMs,commonTripMatrix,feederProtection);
feeders = makeFeederTrend(trend,equipment,commands,settings,packageRoot, ...
    feederProtection);
events = addFeederTransitionRows(events,feeders);

outputRoot = char(string(options.OutputRoot));
usingDefaultOutputRoot = isempty(outputRoot);
if isempty(outputRoot)
    outputRoot = fullfile(packageRoot,"runs");
elseif ~isAbsolutePath(outputRoot)
    outputRoot = fullfile(packageRoot,outputRoot);
end
if ~isfolder(outputRoot)
    mkdir(outputRoot);
end
runId = createRunId();
runFolder = fullfile(outputRoot,runId);
stagingFolder = fullfile(outputRoot,char(".staging_"+string(runId)));
assert(~isfolder(runFolder) && ~isfolder(stagingFolder), ...
    "TripLens:RunCollision","Run folder already exists: %s",runFolder);
mkdir(stagingFolder);
cleanup = onCleanup(@() cleanupStaging(stagingFolder)); %#ok<NASGU>

writetable(processBus,fullfile(stagingFolder,"processbus.csv"), ...
    "Delimiter",",","WriteVariableNames",true);
writetable(trend,fullfile(stagingFolder,"ecms-trend.csv"), ...
    "Delimiter",",","WriteVariableNames",true);
writetable(events,fullfile(stagingFolder,"ecms-events.csv"), ...
    "Delimiter",",","WriteVariableNames",true);
writetable(feeders,fullfile(stagingFolder,"ecms-feeders.csv"), ...
    "Delimiter",",","WriteVariableNames",true);

configFolder = fullfile(stagingFolder,"config");
mkdir(configFolder);
writetable(settingsTable,fullfile(configFolder,"ecms_a_settings.csv"), ...
    "Delimiter",",","WriteVariableNames",true);
writetable(equipmentTable,fullfile(configFolder,"ecms_a_equipment.csv"), ...
    "Delimiter",",","WriteVariableNames",true);
if height(resolvedCommandTable) > 0
    commandFolder = fullfile(stagingFolder,"commands");
    mkdir(commandFolder);
    writetable(resolvedCommandTable,fullfile(commandFolder,"commands.csv"), ...
        "Delimiter",",","WriteVariableNames",true);
    writetable(commandTable,fullfile(commandFolder,"submitted_commands.csv"), ...
        "Delimiter",",","WriteVariableNames",true);
end
copyReferenceFiles(packageRoot,stagingFolder);

manifest = makeManifest(runId,tripTime,stopTime,faultPreset,configStatus, ...
    settings.AUX_BUS_VOLTAGE_KV,height(processBus),height(trend), ...
    height(events),height(feeders),height(resolvedCommandTable),samplingProfile, ...
    periodMs,incidentPeriodMs,incidentStartMs,incidentStopMs);
writeJson(fullfile(stagingFolder,"manifest.json"),manifest);
verifyStaging(stagingFolder,numel(equipment.id));

[moved,message] = movefile(stagingFolder,runFolder);
assert(moved,"TripLens:RunCommitFailed", ...
    "Could not commit ECMS run folder: %s",message);
if usingDefaultOutputRoot
    updateLatestRunPointer(packageRoot,runId);
end

result = struct();
result.RunId = string(runId);
result.RunFolder = string(runFolder);
result.Engine = "MATLAB_NATIVE_SYNTHETIC_FALLBACK";
result.Topology = "6.9 kV / UAT-A + UAT-B / NO SST";
result.SamplingProfile = samplingProfile;
result.IncidentWindowMs = [incidentStartMs,incidentStopMs];
result.ProcessBus = processBus;
result.ECMSTrend = trend;
result.ECMSEvents = events;
result.ECMSFeeders = feeders;
result.Settings = settingsTable;
result.Equipment = equipmentTable;
result.Commands = resolvedCommandTable;
result.SubmittedCommands = commandTable;
result.Manifest = manifest;
if usingDefaultOutputRoot
    result.LatestRunPointer = string(fullfile(packageRoot,"latest_run.txt"));
else
    result.LatestRunPointer = "";
end
fprintf("PASS: MATLAB-native ECMS VPP run committed to %s\n",runFolder);
fprintf("NOTICE: ProcessBus origin is SYNTHETIC MATLAB FALLBACK, not ThermoSysPro.\n");
end

function value = isTextScalar(input)
value = (ischar(input) && (isrow(input) || isempty(input))) || ...
    (isstring(input) && isscalar(input));
end

function value = isFiniteScalar(input)
value = isnumeric(input) && isscalar(input) && isfinite(input);
end

function value = validateWholeMilliseconds(input,label,strictlyPositive)
value = double(input);
rounded = round(value);
assert(abs(value-rounded)<=1e-9,"TripLens:InvalidSamplingMilliseconds", ...
    "%s must be a whole number of milliseconds.",label);
if strictlyPositive
    assert(rounded>0,"TripLens:InvalidSamplingMilliseconds", ...
        "%s must be greater than zero.",label);
else
    assert(rounded>=0,"TripLens:InvalidSamplingMilliseconds", ...
        "%s must be non-negative.",label);
end
value = rounded;
end

function [timeMs,incidentStartMs,incidentStopMs,estimatedRows] = ...
        buildSampleTimes(stopMs,normalPeriodMs,tripMs,samplingProfile, ...
        incidentPeriodMs,incidentPreMs,incidentPostMs)
estimatedRows = floor(stopMs/normalPeriodMs)+2;
if samplingProfile=="incident_1ms"
    estimatedIncidentStart = max(0,tripMs-incidentPreMs);
    estimatedIncidentStop = min(stopMs,tripMs+incidentPostMs);
    estimatedRows = estimatedRows + ...
        floor((estimatedIncidentStop-estimatedIncidentStart)/incidentPeriodMs)+2;
end
assert(estimatedRows<=50000,"TripLens:FallbackRunTooLarge", ...
    "The MATLAB fallback would create about %d trend rows and too many feeder rows. " + ...
    "Shorten StopTime, shorten the incident window, or increase a sampling period.", ...
    estimatedRows);
normalTimes = (0:normalPeriodMs:stopMs).';
if normalTimes(end)~=stopMs
    normalTimes(end+1,1) = stopMs;
end
incidentStartMs = NaN;
incidentStopMs = NaN;
estimatedRows = numel(normalTimes);
if samplingProfile=="standard"
    % Preserve the legacy/default uniform grid byte-for-byte: 0, period, ...,
    % stop, with a final partial interval only when StopTime is not aligned.
    timeMs = normalTimes;
    return;
end

incidentStartMs = max(0,tripMs-incidentPreMs);
incidentStopMs = min(stopMs,tripMs+incidentPostMs);
incidentTimes = (incidentStartMs:incidentPeriodMs:incidentStopMs).';
if isempty(incidentTimes) || incidentTimes(end)~=incidentStopMs
    incidentTimes(end+1,1) = incidentStopMs;
end
% The trip instant is a semantic boundary and remains explicit even when an
% unusual incident-window boundary would otherwise omit it.
estimatedRows = numel(normalTimes)+numel(incidentTimes)+1;
timeMs = unique([normalTimes;incidentTimes;tripMs],"sorted");
estimatedRows = numel(timeMs);
end

function pathValue = resolveOptionalPath(packageRoot,inputValue,defaultRelative)
pathValue = char(string(inputValue));
if isempty(pathValue)
    pathValue = char(string(defaultRelative));
end
if isempty(pathValue)
    return;
end
if ~isAbsolutePath(pathValue)
    pathValue = fullfile(packageRoot,pathValue);
end
end

function value = isAbsolutePath(pathValue)
value = startsWith(pathValue,filesep) || ...
    ~isempty(regexp(pathValue,"^[A-Za-z]:[\\/]","once"));
end

function inputTable = readCsv(pathValue)
inputTable = readtable(pathValue,"Delimiter",",","ReadVariableNames",true, ...
    "VariableNamingRule","preserve","TextType","string");
end

function requireColumns(inputTable,required,fileLabel)
actual = string(inputTable.Properties.VariableNames);
missing = setdiff(string(required),actual,"stable");
if ~isempty(missing)
    error("TripLens:InvalidInputSchema", ...
        "%s is missing columns: %s",fileLabel,join(missing,", "));
end
end

function [settings,configStatus] = validateSettings(inputTable)
requireColumns(inputTable,{"setting_id","value","unit","status"},"A settings");
ids = upper(strtrim(string(inputTable.setting_id)));
assert(all(strlength(ids)>0),"TripLens:InvalidASettings", ...
    "A settings contain an empty setting_id.");
assert(numel(unique(ids))==numel(ids),"TripLens:DuplicateASetting", ...
    "A settings contain duplicate setting_id values.");
required = ["GRID_VOLTAGE_KV","GT_TERMINAL_VOLTAGE_KV", ...
    "ST_TERMINAL_VOLTAGE_KV","AUX_BUS_VOLTAGE_KV","POWER_FACTOR", ...
    "GTG_PRETRIP_POWER_MW","TRIP_RECEIVE_DELAY_MS", ...
    "LOCKOUT_OPERATE_DELAY_MS","GT_BREAKER_OPEN_DELAY_MS", ...
    "GT_POWER_DECAY_MS","ST_TRIP_POWER_PU","ST_BREAKER_OPEN_DELAY_MS", ...
    "MOTOR_BREAKER_OPEN_DELAY_MS", ...
    "FEEDER_FAULT_CURRENT_A","FEEDER_FAULT_RESIDUAL_VOLTAGE_PU", ...
    "FEEDER_50_PICKUP_A","FEEDER_50_DELAY_MS","FEEDER_51_PICKUP_A", ...
    "FEEDER_51_TIME_MULTIPLIER", ...
    "UNDERVOLTAGE_PICKUP_PU","UNDERVOLTAGE_DELAY_MS", ...
    "TREND_PERIOD_MS","CLOCK_OFFSET_MS","AUTO_BUS_TIE_TRANSFER", ...
    "ALLOW_SOURCE_PARALLEL"];
missing = setdiff(required,ids,"stable");
assert(isempty(missing),"TripLens:MissingASetting", ...
    "A settings are missing: %s",join(missing,", "));

settings = struct();
for index = 1:numel(required)
    id = required(index);
    row = find(ids==id,1);
    unit = upper(strtrim(toText(inputTable.unit(row))));
    raw = toText(inputTable.value(row));
    if unit == "BOOL"
        settings.(char(id)) = parseBool(raw,id);
    else
        number = str2double(raw);
        assert(isfinite(number),"TripLens:InvalidASetting", ...
            "%s must be numeric, got %s",id,raw);
        settings.(char(id)) = number;
    end
end
positive = ["GRID_VOLTAGE_KV","GT_TERMINAL_VOLTAGE_KV", ...
    "ST_TERMINAL_VOLTAGE_KV","AUX_BUS_VOLTAGE_KV","POWER_FACTOR", ...
    "TREND_PERIOD_MS","FEEDER_FAULT_CURRENT_A","FEEDER_50_PICKUP_A", ...
    "FEEDER_51_PICKUP_A","FEEDER_51_TIME_MULTIPLIER"];
for index = 1:numel(positive)
    assert(settings.(char(positive(index)))>0,"TripLens:InvalidASetting", ...
        "%s must be greater than zero.",positive(index));
end
assert(settings.UNDERVOLTAGE_PICKUP_PU>0 && settings.UNDERVOLTAGE_PICKUP_PU<=1, ...
    "TripLens:InvalidASetting","UNDERVOLTAGE_PICKUP_PU must be in (0,1].");
assert(settings.UNDERVOLTAGE_DELAY_MS>=0,"TripLens:InvalidASetting", ...
    "UNDERVOLTAGE_DELAY_MS must be non-negative.");
assert(settings.POWER_FACTOR<=1,"TripLens:InvalidASetting", ...
    "POWER_FACTOR must be in (0,1].");
assert(settings.ST_TRIP_POWER_PU>=0 && settings.ST_TRIP_POWER_PU<=1, ...
    "TripLens:InvalidASetting","ST_TRIP_POWER_PU must be in [0,1].");
assert(settings.FEEDER_FAULT_RESIDUAL_VOLTAGE_PU>=0 && ...
    settings.FEEDER_FAULT_RESIDUAL_VOLTAGE_PU<=1, ...
    "TripLens:InvalidASetting", ...
    "FEEDER_FAULT_RESIDUAL_VOLTAGE_PU must be in [0,1].");
delayNames = ["TRIP_RECEIVE_DELAY_MS","LOCKOUT_OPERATE_DELAY_MS", ...
    "GT_BREAKER_OPEN_DELAY_MS","GT_POWER_DECAY_MS", ...
    "ST_BREAKER_OPEN_DELAY_MS","MOTOR_BREAKER_OPEN_DELAY_MS", ...
    "FEEDER_50_DELAY_MS"];
for index = 1:numel(delayNames)
    assert(settings.(char(delayNames(index)))>=0,"TripLens:InvalidASetting", ...
        "%s must be non-negative.",delayNames(index));
end
assert(~settings.ALLOW_SOURCE_PARALLEL,"TripLens:UnsafeParallelSetting", ...
    "ALLOW_SOURCE_PARALLEL=true is not supported without a synchronism model.");

statuses = unique(upper(strtrim(string(inputTable.status))));
configStatus = deriveConfigStatus(statuses,"A settings");
end

function value = parseBool(raw,label)
normalized = lower(strtrim(string(raw)));
if any(normalized==["1","true","yes","on"])
    value = true;
elseif any(normalized==["0","false","no","off"])
    value = false;
else
    error("TripLens:InvalidBoolean","%s must be BOOL, got %s",label,raw);
end
end

function [equipment,configStatus] = validateEquipment(inputTable)
required = {"equipment_id","label_ko","bus","feeder_id","voltage_kv", ...
    "rated_kw","normal_breaker_state","normal_run_state","priority","status"};
requireColumns(inputTable,required,"A equipment");
assert(height(inputTable)>0,"TripLens:InvalidAEquipment", ...
    "A equipment is empty.");
equipment = struct();
equipment.id = upper(strtrim(string(inputTable.equipment_id)));
equipment.label = strtrim(string(inputTable.label_ko));
equipment.bus = upper(strtrim(string(inputTable.bus)));
equipment.feeder = strtrim(string(inputTable.feeder_id));
equipment.voltage_kv = toNumeric(inputTable.voltage_kv);
equipment.rated_kw = toNumeric(inputTable.rated_kw);
equipment.normal_closed = upper(strtrim(string(inputTable.normal_breaker_state)))=="CLOSED";
equipment.normal_running = upper(strtrim(string(inputTable.normal_run_state)))=="RUNNING";
equipment.priority = strtrim(string(inputTable.priority));
equipment.status = strtrim(string(inputTable.status));
textFields = {"id","label","bus","feeder","priority","status"};
for fieldIndex = 1:numel(textFields)
    name = char(textFields{fieldIndex});
    values = equipment.(name);
    values(ismissing(values)) = "";
    equipment.(name) = values;
end
assert(all(strlength(equipment.id)>0) && all(strlength(equipment.feeder)>0), ...
    "TripLens:InvalidAEquipment","Equipment and feeder IDs cannot be empty.");
assert(numel(unique(equipment.id))==height(inputTable), ...
    "TripLens:DuplicateEquipment","equipment_id values must be unique.");
assert(numel(unique(equipment.feeder))==height(inputTable), ...
    "TripLens:DuplicateFeeder","feeder_id values must be unique.");
assert(all(equipment.bus=="BUS-A" | equipment.bus=="BUS-B"), ...
    "TripLens:InvalidEquipmentBus","Equipment bus must be BUS-A or BUS-B.");
normalBreakerStates = upper(strtrim(string(inputTable.normal_breaker_state)));
normalRunStates = upper(strtrim(string(inputTable.normal_run_state)));
assert(all(ismember(normalBreakerStates,["OPEN","CLOSED"])), ...
    "TripLens:InvalidEquipmentState","normal_breaker_state must be OPEN or CLOSED.");
assert(all(ismember(normalRunStates,["RUNNING","STOPPED"])), ...
    "TripLens:InvalidEquipmentState","normal_run_state must be RUNNING or STOPPED.");
assert(all(isfinite(equipment.voltage_kv) & equipment.voltage_kv>0), ...
    "TripLens:InvalidEquipmentVoltage","Equipment voltage_kv must be positive.");
validRated = isnan(equipment.rated_kw) | ...
    (isfinite(equipment.rated_kw) & equipment.rated_kw>=0);
assert(all(validRated),"TripLens:InvalidEquipmentRating", ...
    "Equipment rated_kw must be blank or non-negative.");
states = upper(strtrim(string(inputTable.normal_breaker_state)));
assert(all(states=="OPEN" | states=="CLOSED"), ...
    "TripLens:InvalidEquipmentBreaker", ...
    "normal_breaker_state must be OPEN or CLOSED.");
assert(all(strlength(equipment.status)>0),"TripLens:InvalidEquipmentStatus", ...
    "Equipment status cannot be empty.");
configStatus = deriveConfigStatus(unique(upper(equipment.status)),"A equipment");
end

function status = deriveConfigStatus(statuses,label)
statuses = string(statuses);
statuses(ismissing(statuses)) = "";
statuses(statuses=="") = [];
assert(~isempty(statuses),"TripLens:MissingConfigStatus", ...
    "%s contains no configuration status.",label);
if any(statuses=="PROVISIONAL")
    status = "PROVISIONAL";
elseif numel(statuses)==1
    status = statuses(1);
else
    status = "MIXED";
end
end

function status = combineConfigStatus(settingsStatus,equipmentStatus)
if settingsStatus=="PROVISIONAL" || equipmentStatus=="PROVISIONAL"
    status = "PROVISIONAL";
elseif settingsStatus==equipmentStatus
    status = settingsStatus;
else
    status = "MIXED";
end
end

function commands = validateCommands(inputTable,packageRoot)
if isempty(inputTable) || height(inputTable)==0
    commands = emptyCommands();
    return;
end
requireColumns(inputTable,{"time_s","equipment_id","command"},"commands");
commands = struct();
commands.time_s = toNumeric(inputTable.time_s);
commands.equipment_id = upper(strtrim(string(inputTable.equipment_id)));
commands.command = upper(strtrim(string(inputTable.command)));
if any(string(inputTable.Properties.VariableNames)=="command_value")
    commands.command_value = strtrim(string(inputTable.command_value));
else
    commands.command_value = strings(height(inputTable),1);
end
if any(string(inputTable.Properties.VariableNames)=="execution_layer")
    commands.execution_layer = upper(strtrim(string(inputTable.execution_layer)));
else
    commands.execution_layer = strings(height(inputTable),1);
end
if any(string(inputTable.Properties.VariableNames)=="feedback_tag")
    commands.feedback_tag = strtrim(string(inputTable.feedback_tag));
else
    commands.feedback_tag = strings(height(inputTable),1);
end
assert(all(isfinite(commands.time_s) & commands.time_s>=0), ...
    "TripLens:InvalidCommandTime","Command time_s must be non-negative.");
assert(all(strlength(commands.equipment_id)>0 & strlength(commands.command)>0), ...
    "TripLens:InvalidCommand","Command equipment_id and command cannot be empty.");
allowed = ["START","STOP","TRIP","RESET","OPEN","CLOSE","LOSS", ...
    "RESTORE","OUT_OF_SERVICE","IN_SERVICE","SET_OPENING","AUTO","MANUAL"];
assert(all(ismember(commands.command,allowed)),"TripLens:UnsupportedCommand", ...
    "Command table contains an unsupported command. Allowed: %s",join(allowed,", "));
[commands.time_s,order] = sort(commands.time_s,"ascend");
commands.equipment_id = commands.equipment_id(order);
commands.command = commands.command(order);
commands.command_value = commands.command_value(order);
commands.execution_layer = commands.execution_layer(order);
commands.feedback_tag = commands.feedback_tag(order);
commandTextFields = {"equipment_id","command","command_value", ...
    "execution_layer","feedback_tag"};
for fieldIndex = 1:numel(commandTextFields)
    name = char(commandTextFields{fieldIndex});
    values = commands.(name);
    values(ismissing(values)) = "";
    commands.(name) = values;
end
catalogPath = fullfile(packageRoot,"config","ecms_command_catalog.csv");
assert(isfile(catalogPath),"TripLens:MissingCommandCatalog", ...
    "Commands require the authoritative catalog: %s",catalogPath);
if isfile(catalogPath)
    catalog = readCsv(catalogPath);
    requireColumns(catalog,{"equipment_id","command","value_type","default_value", ...
        "execution_layer","feedback_tag"},"command catalog");
    catalogEquipment = upper(strtrim(string(catalog.equipment_id)));
    catalogCommand = upper(strtrim(string(catalog.command)));
    for index = 1:numel(commands.time_s)
        match = find(catalogEquipment==commands.equipment_id(index) & ...
            catalogCommand==commands.command(index));
        assert(numel(match)==1,"TripLens:UnregisteredCommand", ...
            "Command is not registered in ecms_command_catalog.csv: %s %s", ...
            commands.equipment_id(index),commands.command(index));
        catalogRow = match(1);
        defaultValue = toText(catalog.default_value(catalogRow));
        if strlength(commands.command_value(index))==0 || ...
                ismissing(commands.command_value(index))
            commands.command_value(index) = defaultValue;
        end
        valueType = upper(toText(catalog.value_type(catalogRow)));
        if valueType=="REAL"
            numericValue = str2double(commands.command_value(index));
            minimum = -inf;
            maximum = inf;
            if any(string(catalog.Properties.VariableNames)=="min_value")
                candidate = str2double(toText(catalog.min_value(catalogRow)));
                if isfinite(candidate), minimum = candidate; end
            end
            if any(string(catalog.Properties.VariableNames)=="max_value")
                candidate = str2double(toText(catalog.max_value(catalogRow)));
                if isfinite(candidate), maximum = candidate; end
            end
            assert(isfinite(numericValue) && numericValue>=minimum && numericValue<=maximum, ...
                "TripLens:InvalidCommandValue", ...
                "%s %s command_value must be within [%g,%g].", ...
                commands.equipment_id(index),commands.command(index),minimum,maximum);
        else
            assert(commands.command_value(index)==defaultValue, ...
                "TripLens:InvalidCommandValue", ...
                "%s %s command_value must match catalog default %s.", ...
                commands.equipment_id(index),commands.command(index),defaultValue);
        end
        catalogLayer = upper(toText(catalog.execution_layer(catalogRow)));
        if strlength(commands.execution_layer(index))==0 || ...
                ismissing(commands.execution_layer(index))
            commands.execution_layer(index) = catalogLayer;
        else
            assert(commands.execution_layer(index)==catalogLayer, ...
                "TripLens:CommandMetadataMismatch", ...
                "%s %s execution_layer differs from the command catalog.", ...
                commands.equipment_id(index),commands.command(index));
        end
        catalogFeedback = toText(catalog.feedback_tag(catalogRow));
        if strlength(commands.feedback_tag(index))==0 || ismissing(commands.feedback_tag(index))
            commands.feedback_tag(index) = catalogFeedback;
        else
            assert(commands.feedback_tag(index)==catalogFeedback, ...
                "TripLens:CommandMetadataMismatch", ...
                "%s %s feedback_tag differs from the command catalog.", ...
                commands.equipment_id(index),commands.command(index));
        end
    end
end
end

function inputTable = emptyCommandTable()
inputTable = table(zeros(0,1),strings(0,1),strings(0,1), ...
    'VariableNames',{'time_s','equipment_id','command'});
end

function commands = emptyCommands()
commands = struct("time_s",zeros(0,1),"equipment_id",strings(0,1), ...
    "command",strings(0,1),"command_value",strings(0,1), ...
    "execution_layer",strings(0,1),"feedback_tag",strings(0,1));
end

function output = commandsToTable(commands)
count = numel(commands.time_s);
sequence = (1:count).';
output = table(sequence,commands.time_s,commands.equipment_id,commands.command, ...
    commands.command_value,commands.execution_layer,commands.feedback_tag, ...
    'VariableNames',{'sequence','time_s','equipment_id','command', ...
    'command_value','execution_layer','feedback_tag'});
end

function values = toNumeric(input)
if isnumeric(input)
    values = double(input);
else
    values = str2double(strtrim(string(input)));
end
values = values(:);
end

function output = toText(input)
if iscell(input)
    input = input{1};
end
output = strtrim(string(input));
if ismissing(output)
    output = "";
end
end

function fault = loadFaultPreset(pathValue,preset)
assert(isfile(pathValue),"TripLens:MissingFaultPresets", ...
    "Fault preset JSON does not exist: %s",pathValue);
definitions = jsondecode(fileread(pathValue));
assert(isfield(definitions,preset),"TripLens:UnknownFaultPreset", ...
    "Unknown fault preset: %s",preset);
fault = definitions.(preset);
end

function value = faultEnabled(fault,name)
fieldName = char(string(name));
value = isfield(fault,fieldName) && logical(fault.(fieldName));
end

function protection = resolveFeederProtection(fault,equipment,settings,faultStartMs)
% Deliberately simple RMS protection model.  It is not an EMT or short-circuit
% network solution; every setting remains PROVISIONAL until the approved SLD,
% system impedance and relay setting sheet are supplied.
protection = struct("enabled",false,"equipment_id","","feeder_id","", ...
    "fault_start_ms",inf,"fault_current_a",0,"residual_voltage_pu",1, ...
    "relay_50_operate_ms",inf,"relay_51_operate_ms",inf, ...
    "trip_command_ms",inf,"breaker_open_ms",inf);
if ~isfield(fault,"feeder_fault")
    return;
end
equipmentId = upper(strtrim(string(fault.feeder_fault)));
equipmentIndex = find(equipment.id==equipmentId);
assert(numel(equipmentIndex)==1,"TripLens:UnknownFeederFaultTarget", ...
    "Fault preset references unknown feeder equipment %s.",equipmentId);
faultCurrent = settings.FEEDER_FAULT_CURRENT_A;
if isfield(fault,"feeder_fault_current_a")
    faultCurrent = double(fault.feeder_fault_current_a);
end
assert(isfinite(faultCurrent) && faultCurrent>0, ...
    "TripLens:InvalidFeederFaultCurrent", ...
    "Feeder fault current must be a positive finite RMS value.");
relay50Ms = inf;
if faultCurrent>=settings.FEEDER_50_PICKUP_A
    relay50Ms = faultStartMs+round(settings.FEEDER_50_DELAY_MS);
end
relay51Ms = inf;
multiple = faultCurrent/settings.FEEDER_51_PICKUP_A;
if multiple>1
    delayMs = ceil(settings.FEEDER_51_TIME_MULTIPLIER*0.14/ ...
        (multiple^0.02-1)*1000);
    relay51Ms = faultStartMs+max(delayMs,1);
end
tripCommandMs = min(relay50Ms,relay51Ms);
breakerOpenMs = inf;
if isfinite(tripCommandMs)
    breakerOpenMs = tripCommandMs+round(settings.MOTOR_BREAKER_OPEN_DELAY_MS);
end
protection = struct("enabled",true,"equipment_id",equipmentId, ...
    "feeder_id",equipment.feeder(equipmentIndex), ...
    "fault_start_ms",faultStartMs,"fault_current_a",faultCurrent, ...
    "residual_voltage_pu",settings.FEEDER_FAULT_RESIDUAL_VOLTAGE_PU, ...
    "relay_50_operate_ms",relay50Ms,"relay_51_operate_ms",relay51Ms, ...
    "trip_command_ms",tripCommandMs,"breaker_open_ms",breakerOpenMs);
end

function matrix = validateCommonTripMatrix(inputTable)
requireColumns(inputTable,{"cause_id","source_signal","source_layer", ...
    "source_event_tag","gt_trip_request","st_trip_request"},"common Trip matrix");
assert(height(inputTable)>0,"TripLens:InvalidCommonTripMatrix", ...
    "Common Trip matrix is empty.");
matrix = struct();
matrix.cause_id = upper(strtrim(string(inputTable.cause_id)));
matrix.source_signal = strtrim(string(inputTable.source_signal));
matrix.source_layer = upper(strtrim(string(inputTable.source_layer)));
matrix.source_event_tag = upper(strtrim(string(inputTable.source_event_tag)));
matrix.gt_trip_request = toNumeric(inputTable.gt_trip_request)~=0;
matrix.st_trip_request = toNumeric(inputTable.st_trip_request)~=0;
assert(numel(unique(matrix.cause_id))==height(inputTable), ...
    "TripLens:DuplicateCommonTripCause","Common Trip cause_id values must be unique.");
assert(all(ismember(matrix.source_layer,["COMMAND","LAYER1_ALARM"])), ...
    "TripLens:InvalidCommonTripLayer","Unsupported common Trip source layer.");
end

function [gtRequestMs,stRequestMs,gtCauses,stCauses] = ...
        resolveCommonTripRequests(processBus,commands,scenarioTripMs,matrix)
gtRequestMs = inf;
stRequestMs = inf;
gtCauses = strings(0,1);
stCauses = strings(0,1);
processNames = string(processBus.Properties.VariableNames);
for index = 1:numel(matrix.cause_id)
    candidates = zeros(0,1);
    signal = matrix.source_signal(index);
    if signal=="gt_trip_cmd"
        candidates(end+1,1) = scenarioTripMs; %#ok<AGROW>
        commandTimes = commands.time_s(commands.equipment_id=="GTG" & ...
            commands.command=="TRIP");
        candidates = [candidates;round(commandTimes*1000)]; %#ok<AGROW>
    elseif signal=="st_trip_cmd"
        commandTimes = commands.time_s(commands.equipment_id=="STG" & ...
            commands.command=="TRIP");
        candidates = [candidates;round(commandTimes*1000)]; %#ok<AGROW>
    end
    signalIndex = find(processNames==signal,1);
    if ~isempty(signalIndex)
        values = toNumeric(processBus.(char(signal)));
        asserted = find(values>=0.5,1);
        if ~isempty(asserted)
            candidates(end+1,1) = round(processBus.time_s(asserted)*1000); %#ok<AGROW>
        end
    end
    if isempty(candidates)
        continue;
    end
    requestMs = min(candidates);
    if matrix.gt_trip_request(index)
        if requestMs<gtRequestMs
            gtRequestMs = requestMs;
            gtCauses = matrix.cause_id(index);
        elseif requestMs==gtRequestMs
            gtCauses(end+1,1) = matrix.cause_id(index); %#ok<AGROW>
        end
    end
    if matrix.st_trip_request(index)
        if requestMs<stRequestMs
            stRequestMs = requestMs;
            stCauses = matrix.cause_id(index);
        elseif requestMs==stRequestMs
            stCauses(end+1,1) = matrix.cause_id(index); %#ok<AGROW>
        end
    end
end
end

function processBus = makeSyntheticProcessBus(timeSeconds,tripTime)
progress = min(max((timeSeconds-tripTime)./3,0),1);
exhaustProgress = min(max((timeSeconds-tripTime)./1,0),1);
stgPowerW = 250e6 + (10e6-250e6).*progress;
flow = 606.94 + (50-606.94).*exhaustProgress;
temperature = 893.75 + (423-893.75).*exhaustProgress;
hpLevel = 1.05 + (0.95-1.05).*progress;
ipLevel = 1.05 + (0.90-1.05).*progress;
lpLevel = 1.75 + (1.55-1.75).*progress;
hpPressure = 12703151 + (10500000-12703151).*progress;
ipPressure = 2732895 + (2200000-2732895).*progress;
lpPressure = 450000 + (380000-450000).*progress;
hpSteam = 150 + (50-150).*progress;
ipSteam = 40 + (15-40).*progress;
lpSteam = 12 + (4-12).*progress;
hpValve = 0.80 + (0.50-0.80).*progress;
scenarioId = repmat("MATLAB_SYNTHETIC_GT_TRIP",numel(timeSeconds),1);
origin = repmat("SYNTHETIC_MATLAB_FALLBACK_NOT_THERMOSYSPRO",numel(timeSeconds),1);
gtTrip = double(timeSeconds>=tripTime);
processBus = table(scenarioId,timeSeconds,gtTrip,stgPowerW,flow,temperature, ...
    hpLevel,ipLevel,lpLevel,hpPressure,ipPressure,lpPressure, ...
    hpSteam,ipSteam,lpSteam,hpValve,origin, ...
    'VariableNames',{'scenario_id','time_s','gt_trip_cmd','stg_power_w', ...
    'gt_exhaust_mass_flow_kg_s','gt_exhaust_temperature_k', ...
    'hp_drum_level_m','ip_drum_level_m','lp_drum_level_m', ...
    'hp_drum_pressure_pa','ip_drum_pressure_pa','lp_drum_pressure_pa', ...
    'hp_steam_flow_kg_s','ip_steam_flow_kg_s','lp_steam_flow_kg_s', ...
    'hp_feedwater_valve_pu','data_origin'});
end

function [trend,eventTable] = simulateElectrical(processBus,timeMs,tripTime,settings, ...
        configStatus,fault,faultPreset,commands,samplingProfile, ...
        incidentPeriodMs,incidentStartMs,incidentStopMs,commonTripMatrix, ...
        feederProtection)
n = numel(timeMs);
tripMs = round(tripTime*1000);
[gtRequestMs,stRequestMs,gtCauses,stCauses] = resolveCommonTripRequests( ...
    processBus,commands,tripMs,commonTripMatrix);
relayTripMs = gtRequestMs + round(settings.TRIP_RECEIVE_DELAY_MS);
lockoutMs = relayTripMs + round(settings.LOCKOUT_OPERATE_DELAY_MS);
gtOpenMs = gtRequestMs + round(settings.GT_BREAKER_OPEN_DELAY_MS);
relayOperates = ~faultEnabled(fault,"relay_fail");
gtBreakerOpens = relayOperates && ~faultEnabled(fault,"gtg_breaker_fail");
stOpenMs = stRequestMs + round(settings.ST_BREAKER_OPEN_DELAY_MS);
stReference = max(abs(processBus.stg_power_w(1)),1);

ecmsTime = timeMs + round(settings.CLOCK_OFFSET_MS);
quality = repmat("GOOD",n,1);
config = repmat(string(configStatus),n,1);
samplingResolution = repmat("NORMAL_"+string(round(settings.TREND_PERIOD_MS))+"MS",n,1);
if samplingProfile=="incident_1ms"
    incidentRows = timeMs>=incidentStartMs & timeMs<=incidentStopMs;
    samplingResolution(incidentRows) = "INCIDENT_"+string(incidentPeriodMs)+"MS";
end
gtTrip = double(timeMs>=tripMs);
gtTripRequest = double(timeMs>=gtRequestMs);
stTripRequest = double(timeMs>=stRequestMs);
cb52gtTripCmd = double(timeMs>=lockoutMs & relayOperates);
cb52stTripCmd = double(timeMs>=stRequestMs);
stLowState = double(abs(processBus.stg_power_w) < ...
    stReference*settings.ST_TRIP_POWER_PU);
relay86 = zeros(n,1);
cb52gt = ones(n,1);
cb52st = ones(n,1);
cbInA = ones(n,1);
cbInB = ones(n,1);
cbTie = zeros(n,1);
gtDirection = strings(n,1);
stDirection = strings(n,1);
gtMw = zeros(n,1);
stMw = zeros(n,1);
gridPu = zeros(n,1);
frequency = zeros(n,1);
busAPu = zeros(n,1);
busBPu = zeros(n,1);
sourceParallelActive = zeros(n,1);
nativeALowStartMs = NaN;
nativeBLowStartMs = NaN;

for index = 1:n
    currentMs = timeMs(index);
    currentS = currentMs/1000;
    afterTrip = currentMs>=tripMs;
    afterGtRequest = currentMs>=gtRequestMs;
    gridLive = ~afterTrip || ~faultEnabled(fault,"grid_loss");
    gridLive = applyAvailabilityCommand(gridLive,commands,"GRID-154KV",currentS);
    gtTransformer = ~afterTrip || ~faultEnabled(fault,"gt_transformer_receive_fail");
    stTransformer = ~afterTrip || ~faultEnabled(fault,"st_transformer_receive_fail");
    gtTransformer = applyAvailabilityCommand(gtTransformer,commands,"TR-GT",currentS);
    stTransformer = applyAvailabilityCommand(stTransformer,commands,"TR-ST",currentS);
    uatA = ~afterTrip || ~faultEnabled(fault,"uat_a_fault");
    uatB = ~afterTrip || ~faultEnabled(fault,"uat_b_fault");
    uatA = applyAvailabilityCommand(uatA,commands,"UAT-A",currentS);
    uatB = applyAvailabilityCommand(uatB,commands,"UAT-B",currentS);
    busAFault = afterTrip && faultEnabled(fault,"bus_a_fault");
    busBFault = afterTrip && faultEnabled(fault,"bus_b_fault");

    if gtBreakerOpens
        gtAutomaticTripMs = gtOpenMs;
    else
        gtAutomaticTripMs = inf;
    end
    gtClosed = breakerWithAutomaticTrip(true,gtAutomaticTripMs,currentMs, ...
        commands,"CB-52GT");
    stClosed = breakerWithAutomaticTrip(true,stOpenMs,currentMs, ...
        commands,"CB-52ST");

    decay = 1;
    if afterGtRequest
        duration = settings.GT_POWER_DECAY_MS;
        if duration<=0 || currentMs>=gtRequestMs+duration
            decay = 0;
        else
            decay = max(0,1-(currentMs-gtRequestMs)/duration);
        end
    end
    gtPower = settings.GTG_PRETRIP_POWER_MW*decay*double(gtClosed);
    stPower = processBus.stg_power_w(index)/1e6*double(stClosed);
    gtGeneration = gtClosed && decay>=settings.UNDERVOLTAGE_PICKUP_PU;
    stGeneration = stClosed && abs(processBus.stg_power_w(index))>= ...
        stReference*settings.ST_TRIP_POWER_PU;
    gtReverse = gridLive && gtTransformer;
    stReverse = gridLive && stTransformer;
    gtSource = gtTransformer && (gtGeneration || gtReverse);
    stSource = stTransformer && (stGeneration || stReverse);

    inA = breakerWithAutomaticTrip(true,inf,currentMs,commands,"CB-IN-A") && ...
        uatA && ~busAFault;
    inB = breakerWithAutomaticTrip(true,inf,currentMs,commands,"CB-IN-B") && ...
        uatB && ~busBFault;
    nativeA = inA && gtSource;
    nativeB = inB && stSource;
    if nativeA || busAFault
        nativeALowStartMs = NaN;
    elseif isnan(nativeALowStartMs)
        nativeALowStartMs = currentMs;
    end
    if nativeB || busBFault
        nativeBLowStartMs = NaN;
    elseif isnan(nativeBLowStartMs)
        nativeBLowStartMs = currentMs;
    end
    transferA = ~nativeA && nativeB && ~isnan(nativeALowStartMs) && ...
        currentMs>nativeALowStartMs+settings.UNDERVOLTAGE_DELAY_MS;
    transferB = ~nativeB && nativeA && ~isnan(nativeBLowStartMs) && ...
        currentMs>nativeBLowStartMs+settings.UNDERVOLTAGE_DELAY_MS;
    tie = settings.AUTO_BUS_TIE_TRANSFER && (transferA || transferB) && ...
        ~(busAFault || busBFault);
    tie = breakerWithAutomaticTrip(tie,inf,currentMs,commands,"CB-TIE-AB");
    tie = tie && ~(busAFault || busBFault);
    if tie && ~nativeA
        inA = false;
    end
    if tie && ~nativeB
        inB = false;
    end
    parallel = tie && inA && inB && gtSource && stSource;
    if parallel && ~settings.ALLOW_SOURCE_PARALLEL
        tie = false;
        parallel = false;
    end
    busALive = nativeA || (tie && nativeB && ~busAFault);
    busBLive = nativeB || (tie && nativeA && ~busBFault);

    if afterTrip && faultEnabled(fault,"ecms_comms_loss")
        quality(index) = "BAD";
    end
    relay86(index) = double(lockoutState(relayOperates,lockoutMs,currentMs,commands));
    cb52gt(index) = double(gtClosed);
    cb52st(index) = double(stClosed);
    cbInA(index) = double(inA);
    cbInB(index) = double(inB);
    cbTie(index) = double(tie);
    gtDirection(index) = direction(gtGeneration,gtReverse);
    stDirection(index) = direction(stGeneration,stReverse);
    gtMw(index) = gtPower;
    stMw(index) = stPower;
    gridPu(index) = double(gridLive);
    frequency(index) = 60*double(gridLive || gtGeneration || stGeneration);
    busAPu(index) = double(busALive);
    busBPu(index) = double(busBLive);
    sourceParallelActive(index) = double(parallel);
end

gtCurrent = rmsCurrent(gtMw,settings.GT_TERMINAL_VOLTAGE_KV,settings.POWER_FACTOR);
stCurrent = rmsCurrent(stMw,settings.ST_TERMINAL_VOLTAGE_KV,settings.POWER_FACTOR);
busAKv = busAPu.*settings.AUX_BUS_VOLTAGE_KV;
busBKv = busBPu.*settings.AUX_BUS_VOLTAGE_KV;
gridKv = gridPu.*settings.GRID_VOLTAGE_KV;
parallelAllowed = repmat(double(settings.ALLOW_SOURCE_PARALLEL),n,1);
trend = table(ecmsTime,timeMs,quality,config,samplingResolution, ...
    gtTrip,gtTripRequest,stTripRequest,stLowState,relay86, ...
    cb52gtTripCmd,cb52stTripCmd,cb52gt,cb52st, ...
    cbInA,cbInB,cbTie,gtDirection,stDirection,gtMw,gtCurrent,stMw,stCurrent, ...
    gridPu,frequency,busAPu,busAKv,busBPu,busBKv,gridKv,parallelAllowed, ...
    sourceParallelActive, ...
    'VariableNames',{'ecms_time_ms','source_time_ms','quality','a_config_status', ...
    'sampling_resolution','gt_trip_cmd','gt_trip_request','st_trip_request', ...
    'stg_low_state','relay_86gt_operated','cb_52gt_trip_cmd','cb_52st_trip_cmd', ...
    'cb_52gt_closed','cb_52st_closed', ...
    'cb_in_a_closed','cb_in_b_closed','cb_tie_ab_closed', ...
    'gt_main_transformer_direction','st_main_transformer_direction', ...
    'gtg_power_mw','gtg_current_a','stg_power_mw','stg_current_a', ...
    'grid_voltage_pu','frequency_hz','bus_a_voltage_pu','bus_a_voltage_kv', ...
    'bus_b_voltage_pu','bus_b_voltage_kv','grid_voltage_kv', ...
    'source_parallel_allowed','source_parallel_active'});

events = baseEvents(tripMs,gtRequestMs,stRequestMs,gtCauses,stCauses, ...
    relayTripMs,lockoutMs,gtOpenMs,stOpenMs,relayOperates,gtBreakerOpens, ...
    fault,faultPreset,commands,settings.CLOCK_OFFSET_MS);
events = addFeederProtectionEvents(events,feederProtection);
events = addTrendTransitionEvents(events,trend);
events = addUndervoltageEvents(events,trend,settings.UNDERVOLTAGE_PICKUP_PU, ...
    round(settings.UNDERVOLTAGE_DELAY_MS));
if faultEnabled(fault,"ecms_comms_loss")
    for index = 1:numel(events)
        if events(index).time_ms>=tripMs
            events(index).quality = "BAD";
        end
    end
end
if ~isempty(events)
    eventTimes = [events.time_ms];
    events = events(eventTimes>=timeMs(1) & eventTimes<=timeMs(end));
end
eventTable = eventsToTable(events,round(settings.CLOCK_OFFSET_MS));
end

function output = direction(generation,reverse)
if generation
    output = "EXPORT";
elseif reverse
    output = "IMPORT";
else
    output = "DEAD";
end
end

function current = rmsCurrent(powerMw,voltageKv,powerFactor)
current = abs(powerMw).*1000./(sqrt(3)*voltageKv*powerFactor);
end

function state = applyAvailabilityCommand(state,commands,equipmentId,timeSeconds)
action = latestCommand(commands,equipmentId,timeSeconds);
if any(action==["IN_SERVICE","RESTORE","START","CLOSE"])
    state = true;
elseif any(action==["OUT_OF_SERVICE","LOSS","STOP","TRIP","OPEN"])
    state = false;
end
end

function state = breakerWithAutomaticTrip(initialState,automaticTripMs,currentMs, ...
        commands,equipmentId)
state = logical(initialState);
latched = false;
automaticApplied = ~isfinite(automaticTripMs);
indices = find(commands.equipment_id==equipmentId & ...
    round(commands.time_s*1000)<=currentMs);
for commandIndex = indices.'
    commandMs = round(commands.time_s(commandIndex)*1000);
    if ~automaticApplied && automaticTripMs<=commandMs
        state = false;
        latched = true;
        automaticApplied = true;
    end
    action = commands.command(commandIndex);
    if action=="RESET"
        latched = false;
    elseif any(action==["OPEN","TRIP","OUT_OF_SERVICE","LOSS"])
        state = false;
        if action=="TRIP"
            latched = true;
        end
    elseif any(action==["CLOSE","IN_SERVICE","RESTORE"]) && ~latched
        state = true;
    end
end
if ~automaticApplied && automaticTripMs<=currentMs
    state = false;
end
end

function state = motorFeederState(initialBreakerClosed,initialRunning,currentMs, ...
        commands,equipmentId,feederId,breakerOpenDelayMs,automaticTripCommandMs)
% Normal motor STOP/START controls the run command only.  TRIP latches and
% opens the VCB after its configured delay.  RESET clears the latch but never
% recloses the VCB; a subsequent feeder CLOSE is required.
breakerClosed = logical(initialBreakerClosed);
runEnable = logical(initialRunning);
runCommandFeedback = logical(initialRunning);
tripLatched = false;
tripCommanded = false;
pendingOpenMs = inf;

indices = find((commands.equipment_id==equipmentId | ...
    commands.equipment_id==feederId) & round(commands.time_s*1000)<=currentMs);
eventTimes = round(commands.time_s(indices)*1000);
eventTargets = commands.equipment_id(indices);
eventActions = commands.command(indices);
if isfinite(automaticTripCommandMs) && automaticTripCommandMs<=currentMs
    eventTimes(end+1,1) = automaticTripCommandMs;
    eventTargets(end+1,1) = feederId;
    eventActions(end+1,1) = "TRIP";
end
if ~isempty(eventTimes)
    ordinals = (1:numel(eventTimes)).';
    [~,order] = sortrows([eventTimes,ordinals],[1 2]);
    eventTimes = eventTimes(order);
    eventTargets = eventTargets(order);
    eventActions = eventActions(order);
end

for index = 1:numel(eventTimes)
    commandMs = eventTimes(index);
    if pendingOpenMs<=commandMs
        breakerClosed = false;
        pendingOpenMs = inf;
    end
    target = eventTargets(index);
    action = eventActions(index);
    isMotorCommand = target==equipmentId;
    if action=="RESET"
        tripLatched = false;
        tripCommanded = false;
    elseif action=="TRIP"
        tripLatched = true;
        tripCommanded = true;
        runEnable = false;
        runCommandFeedback = false;
        pendingOpenMs = min(pendingOpenMs,commandMs+breakerOpenDelayMs);
    elseif target==feederId && any(action==["OPEN","OUT_OF_SERVICE","LOSS"])
        breakerClosed = false;
        runEnable = false;
        runCommandFeedback = false;
    elseif target==feederId && any(action==["CLOSE","IN_SERVICE","RESTORE"])
        if ~tripLatched
            breakerClosed = true;
        end
    elseif isMotorCommand && action=="STOP"
        runEnable = false;
        runCommandFeedback = false;
    elseif isMotorCommand && action=="START" && ~tripLatched && breakerClosed
        runEnable = true;
        runCommandFeedback = true;
    end
end
if pendingOpenMs<=currentMs
    breakerClosed = false;
end
runFeedback = runCommandFeedback && breakerClosed;
speedProven = runFeedback;
if tripLatched
    stateCode = 5;
elseif runFeedback
    stateCode = 3;
elseif breakerClosed
    stateCode = 2;
else
    stateCode = 1;
end
state = struct("breaker_closed",breakerClosed,"run_enable",runEnable, ...
    "run_command_feedback",runCommandFeedback,"run_feedback",runFeedback, ...
    "speed_proven",speedProven,"trip_latched",tripLatched, ...
    "trip_commanded",tripCommanded,"state_code",stateCode);
end

function state = lockoutState(relayOperates,lockoutMs,currentMs,commands)
state = relayOperates && currentMs>=lockoutMs;
if ~state
    return;
end
resetTimes = commands.time_s(commands.equipment_id=="CB-52GT" & ...
    commands.command=="RESET").*1000;
if any(resetTimes>=lockoutMs & resetTimes<=currentMs)
    state = false;
end
end

function action = latestCommand(commands,equipmentId,timeSeconds)
indices = find(commands.equipment_id==equipmentId & commands.time_s<=timeSeconds);
if isempty(indices)
    action = "";
else
    action = commands.command(indices(end));
end
end

function events = baseEvents(tripMs,gtRequestMs,stRequestMs,gtCauses,stCauses, ...
        relayTripMs,lockoutMs,gtOpenMs,stOpenMs,relayOperates,gtBreakerOpens, ...
        fault,faultPreset,commands,clockOffset)
events = repmat(newEvent(0,"","","","","",""),0,1);
tripProvenance = "SYNTHETIC_SCENARIO";
if any(commands.equipment_id=="GTG" & commands.command=="TRIP" & ...
        round(commands.time_s*1000)==tripMs)
    tripProvenance = "USER_COMMAND";
end
if isfinite(gtRequestMs)
    events(end+1) = newEvent(gtRequestMs,"GT.TRIP.CMD","0","1","TRIP", ...
        "Synthetic MATLAB fallback GT Trip asserted",tripProvenance);
    events(end+1) = newEvent(gtRequestMs,"GT.TRIP.REQUEST","0","1", ...
        "TRIP_REQUEST","Resolved GT Trip request from "+join(gtCauses,", "), ...
        "COMMON_TRIP_MATRIX");
end
if isfinite(stRequestMs)
    events(end+1) = newEvent(stRequestMs,"ST.TRIP.REQUEST","0","1", ...
        "TRIP_REQUEST","Resolved ST Trip request from "+join(stCauses,", "), ...
        "COMMON_TRIP_MATRIX");
    events(end+1) = newEvent(stRequestMs,"52ST.TRIP.CMD","0","1", ...
        "TRIP_COMMAND","52ST Trip command latched from resolved ST Trip request", ...
        "COMMON_TRIP_MATRIX");
end
if relayOperates && isfinite(relayTripMs)
    events(end+1) = newEvent(relayTripMs,"86GT.TRIP.RECEIVED","0","1", ...
        "PICKUP","GT Trip received","E_DERIVED");
    events(end+1) = newEvent(lockoutMs,"86GT.OPERATE","0","1", ...
        "OPERATE","GT lockout relay operated","E_DERIVED");
    events(end+1) = newEvent(lockoutMs,"52GT.TRIP.CMD","0","1", ...
        "TRIP_COMMAND","52GT Trip command latched","E_DERIVED");
elseif isfinite(gtRequestMs)
    events(end+1) = newEvent(relayTripMs,"86GT.FAIL","0","1", ...
        "ALARM","GT protection failed","FAULTBUS");
end
if gtBreakerOpens
    gridAtGtOpen = ~faultEnabled(fault,"grid_loss");
    gridAtGtOpen = applyAvailabilityCommand(gridAtGtOpen,commands, ...
        "GRID-154KV",gtOpenMs/1000);
    gtReceiveAtOpen = ~faultEnabled(fault,"gt_transformer_receive_fail");
    gtReceiveAtOpen = applyAvailabilityCommand(gtReceiveAtOpen,commands, ...
        "TR-GT",gtOpenMs/1000);
    if gridAtGtOpen && gtReceiveAtOpen
        gtPostDirection = "IMPORT";
    else
        gtPostDirection = "DEAD";
    end
    events(end+1) = newEvent(gtOpenMs,"52GT.CLOSED","1","0", ...
        "POSITION","GT generator breaker opened","E_DERIVED");
    events(end+1) = newEvent(gtOpenMs,"TR-GT.DIRECTION","EXPORT",gtPostDirection, ...
        "STATE","GT main transformer post-trip direction: "+gtPostDirection,"E_DERIVED");
elseif relayOperates
    events(end+1) = newEvent(gtOpenMs,"52GT.FAIL_TO_OPEN","0","1", ...
        "ALARM","GT generator breaker failed to open","FAULTBUS");
end
if isfinite(stOpenMs)
    gridAtStOpen = ~faultEnabled(fault,"grid_loss");
    gridAtStOpen = applyAvailabilityCommand(gridAtStOpen,commands, ...
        "GRID-154KV",stOpenMs/1000);
    stReceiveAtOpen = ~faultEnabled(fault,"st_transformer_receive_fail");
    stReceiveAtOpen = applyAvailabilityCommand(stReceiveAtOpen,commands, ...
        "TR-ST",stOpenMs/1000);
    if gridAtStOpen && stReceiveAtOpen
        stPostDirection = "IMPORT";
    else
        stPostDirection = "DEAD";
    end
    events(end+1) = newEvent(stOpenMs,"52ST.CLOSED","1","0", ...
        "POSITION","ST generator breaker opened by resolved Trip command","E_DERIVED");
    events(end+1) = newEvent(stOpenMs,"TR-ST.DIRECTION","EXPORT",stPostDirection, ...
        "STATE","ST main transformer post-trip direction: "+stPostDirection,"E_DERIVED");
end

faultRows = {
    "grid_loss","GRID-154KV.AVAILABLE","External grid source lost";
    "uat_a_fault","UAT-A.FAULT","UAT-A unavailable";
    "uat_b_fault","UAT-B.FAULT","UAT-B unavailable";
    "gt_transformer_receive_fail","TR-GT.RECEIVE.FAIL","GT reverse feed unavailable";
    "st_transformer_receive_fail","TR-ST.RECEIVE.FAIL","ST reverse feed unavailable";
    "bus_a_fault","BUS-A.FAULT","6.9 kV BUS-A fault";
    "bus_b_fault","BUS-B.FAULT","6.9 kV BUS-B fault";
    "ecms_comms_loss","ECMS.COMMS.QUALITY","ECMS communications lost"};
for index = 1:size(faultRows,1)
    if faultEnabled(fault,faultRows{index,1})
        oldValue = "0";
        newValue = "1";
        if string(faultRows{index,1})=="grid_loss"
            oldValue = "1";
            newValue = "0";
        elseif string(faultRows{index,1})=="ecms_comms_loss"
            oldValue = "GOOD";
            newValue = "BAD";
        end
        events(end+1) = newEvent(tripMs,string(faultRows{index,2}),oldValue,newValue, ...
            "FAULT",string(faultRows{index,3}),"FAULTBUS"); %#ok<AGROW>
    end
end
for index = 1:numel(commands.time_s)
    description = "User command submitted to MATLAB fallback: " + ...
        commands.equipment_id(index) + " " + commands.command(index);
    if contains(commands.execution_layer(index),"THERMO_ADAPTER_REQUIRED")
        description = description + ...
            " (electrical indication only; no ThermoSysPro adapter)";
    end
    tag = "COMMAND." + commands.equipment_id(index) + "." + commands.command(index);
    events(end+1) = newEvent(round(commands.time_s(index)*1000),tag,"", ...
        commands.command_value(index), ...
        "COMMAND",description,"USER_COMMAND"); %#ok<AGROW>
end
if faultPreset ~= "none"
    events(end+1) = newEvent(tripMs,"FAULT.PRESET","none",string(faultPreset), ...
        "SCENARIO","MATLAB fallback fault preset applied","FAULTBUS");
end
if clockOffset ~= 0
    events(end+1) = newEvent(0,"ECMS.CLOCK.OFFSET","0",string(clockOffset), ...
        "CONFIG","ECMS display clock offset in milliseconds","A_CONFIG");
end
end

function event = newEvent(timeMs,tag,oldValue,newValue,eventClass,description,provenance)
event = struct("time_ms",double(timeMs),"tag",string(tag), ...
    "old_value",string(oldValue),"new_value",string(newValue), ...
    "event_class",string(eventClass),"quality","GOOD", ...
    "provenance",string(provenance),"description",string(description));
end

function events = addFeederProtectionEvents(events,protection)
if ~protection.enabled
    return;
end
source = "A_CONFIGURED_RMS_FAULT_MODEL";
events(end+1) = newEvent(protection.fault_start_ms, ...
    protection.equipment_id+".FEEDER.FAULT","0","1","FAULT", ...
    "Provisional RMS feeder fault asserted at "+ ...
    string(protection.fault_current_a)+" A",source);
if protection.fault_current_a>0 && isfinite(protection.relay_50_operate_ms)
    events(end+1) = newEvent(protection.fault_start_ms, ...
        "50"+protection.equipment_id+".PICKUP","0","1","PICKUP", ...
        "Instantaneous overcurrent element picked up",source);
    events(end+1) = newEvent(protection.relay_50_operate_ms, ...
        "50"+protection.equipment_id+".OPERATE","0","1","OPERATE", ...
        "Instantaneous overcurrent element operated",source);
end
if isfinite(protection.relay_51_operate_ms)
    events(end+1) = newEvent(protection.fault_start_ms, ...
        "51"+protection.equipment_id+".PICKUP","0","1","PICKUP", ...
        "IEC standard-inverse overcurrent element picked up",source);
    if ~isfinite(protection.breaker_open_ms) || ...
            protection.relay_51_operate_ms<=protection.breaker_open_ms
        events(end+1) = newEvent(protection.relay_51_operate_ms, ...
            "51"+protection.equipment_id+".OPERATE","0","1","OPERATE", ...
            "IEC standard-inverse overcurrent element operated",source);
    end
end
if isfinite(protection.trip_command_ms)
    events(end+1) = newEvent(protection.trip_command_ms, ...
        protection.feeder_id+".TRIP.CMD","0","1","TRIP_COMMAND", ...
        "Feeder protection issued VCB Trip command",source);
end
if isfinite(protection.breaker_open_ms)
    events(end+1) = newEvent(protection.breaker_open_ms, ...
        protection.feeder_id+".CLOSED","1","0","POSITION", ...
        "Feeder VCB opened and interrupted fault current",source);
end
end

function events = addTrendTransitionEvents(events,trend)
numericFields = { ...
    'relay_86gt_operated','86GT.OPERATE','OPERATE'; ...
    'cb_52gt_closed','52GT.CLOSED','POSITION'; ...
    'cb_52st_closed','52ST.CLOSED','POSITION'; ...
    'cb_in_a_closed','CB-IN-A.CLOSED','POSITION'; ...
    'cb_in_b_closed','CB-IN-B.CLOSED','POSITION'; ...
    'cb_tie_ab_closed','CB-TIE-AB.CLOSED','POSITION'; ...
    'grid_voltage_pu','GRID-154KV.AVAILABLE','POSITION'; ...
    'bus_a_voltage_pu','BUS-A.ENERGIZED','STATE'; ...
    'bus_b_voltage_pu','BUS-B.ENERGIZED','STATE'};
for specification = 1:size(numericFields,1)
    field = numericFields{specification,1};
    values = trend.(field);
    changed = find(values(2:end)~=values(1:end-1))+1;
    for row = changed.'
        event = newEvent(trend.source_time_ms(row),string(numericFields{specification,2}), ...
            string(values(row-1)),string(values(row)), ...
            string(numericFields{specification,3}), ...
            "Observed MATLAB ECMS state transition","E_OBSERVED_TRANSITION");
        event.quality = trend.quality(row);
        events = appendUniqueEvent(events,event);
    end
end
stringFields = { ...
    'gt_main_transformer_direction','TR-GT.DIRECTION'; ...
    'st_main_transformer_direction','TR-ST.DIRECTION'};
for specification = 1:size(stringFields,1)
    field = stringFields{specification,1};
    values = string(trend.(field));
    changed = find(values(2:end)~=values(1:end-1))+1;
    for row = changed.'
        event = newEvent(trend.source_time_ms(row),string(stringFields{specification,2}), ...
            values(row-1),values(row),"STATE", ...
            "Observed MATLAB ECMS direction transition","E_OBSERVED_TRANSITION");
        event.quality = trend.quality(row);
        events = appendUniqueEvent(events,event);
    end
end
end

function events = appendUniqueEvent(events,event)
duplicate = false;
for index = 1:numel(events)
    if events(index).time_ms==event.time_ms && events(index).tag==event.tag && ...
            events(index).new_value==event.new_value
        duplicate = true;
        break;
    end
end
if ~duplicate
    events(end+1) = event;
end
end

function events = addUndervoltageEvents(events,trend,pickup,delayMs)
fields = ["bus_a_voltage_pu","bus_b_voltage_pu"];
labels = ["BUS-A","BUS-B"];
for busIndex = 1:2
    lowStart = NaN;
    operated = false;
    for row = 1:height(trend)
        if trend.(char(fields(busIndex)))(row) < pickup
            if isnan(lowStart)
                lowStart = trend.source_time_ms(row);
            end
            operateAt = lowStart + delayMs;
            if trend.source_time_ms(row)>=operateAt
                event = newEvent(operateAt,labels(busIndex)+".27UV.OPERATE", ...
                    "0","1","OPERATE",labels(busIndex)+ ...
                    " undervoltage persisted for "+string(delayMs)+" ms","E_DERIVED");
                event.quality = trend.quality(row);
                events(end+1) = event; %#ok<AGROW>
                operated = true;
                break;
            end
        else
            lowStart = NaN;
        end
    end
    if operated
        continue;
    end
end
end

function output = eventsToTable(events,clockOffsetMs)
if isempty(events)
    output = table();
    return;
end
[~,order] = sortrows([[events.time_ms].', (1:numel(events)).'],[1 2]);
events = events(order);
count = numel(events);
sourceTime = zeros(count,1);
tag = strings(count,1);
oldValue = strings(count,1);
newValue = strings(count,1);
eventClass = strings(count,1);
quality = strings(count,1);
provenance = strings(count,1);
description = strings(count,1);
for index = 1:count
    sourceTime(index) = events(index).time_ms;
    tag(index) = events(index).tag;
    oldValue(index) = events(index).old_value;
    newValue(index) = events(index).new_value;
    eventClass(index) = events(index).event_class;
    quality(index) = events(index).quality;
    provenance(index) = events(index).provenance;
    description(index) = events(index).description;
end
eventTime = sourceTime + clockOffsetMs;
system = repmat("ECMS",count,1);
output = table(eventTime,sourceTime,system,tag,oldValue,newValue,eventClass, ...
    quality,provenance,description, ...
    'VariableNames',{'event_time_ms','source_time_ms','system','tag', ...
    'old_value','new_value','event_class','quality','provenance','description'});
end

function feederTrend = makeFeederTrend(trend,equipment,commands,settings,packageRoot, ...
        feederProtection)
nTime = height(trend);
nEquipment = numel(equipment.id);
n = nTime*nEquipment;
ecmsTime = zeros(n,1);
sourceTime = zeros(n,1);
quality = strings(n,1);
configStatus = strings(n,1);
equipmentId = strings(n,1);
label = strings(n,1);
bus = strings(n,1);
feederId = strings(n,1);
configuredKv = zeros(n,1);
ratedKw = strings(n,1);
breakerClosed = zeros(n,1);
runEnable = zeros(n,1);
runCommandFeedback = zeros(n,1);
runFeedback = zeros(n,1);
speedProven = zeros(n,1);
tripLatched = zeros(n,1);
tripCommanded = zeros(n,1);
stateCode = zeros(n,1);
faultPresent = zeros(n,1);
faultCurrentA = strings(n,1);
relay50Operated = zeros(n,1);
relay51Operated = zeros(n,1);
energized = zeros(n,1);
busVoltageKv = zeros(n,1);
terminalVoltageKv = zeros(n,1);
currentA = strings(n,1);
priority = strings(n,1);
equipmentStatus = strings(n,1);
mLinkId = strings(n,1);
sourceMTag = strings(n,1);
provenance = repmat("A_CONFIGURED_E_DERIVED",n,1);
[linkIds,linkTags] = equipmentLinks(packageRoot,equipment.id);

row = 0;
for timeIndex = 1:nTime
    currentMs = trend.source_time_ms(timeIndex);
    for equipmentIndex = 1:nEquipment
        row = row+1;
        isProtected = feederProtection.enabled && ...
            equipment.id(equipmentIndex)==feederProtection.equipment_id;
        automaticTripMs = inf;
        if isProtected
            automaticTripMs = feederProtection.trip_command_ms;
        end
        motor = motorFeederState(equipment.normal_closed(equipmentIndex), ...
            equipment.normal_running(equipmentIndex),currentMs,commands, ...
            equipment.id(equipmentIndex),equipment.feeder(equipmentIndex), ...
            round(settings.MOTOR_BREAKER_OPEN_DELAY_MS),automaticTripMs);
        if equipment.bus(equipmentIndex)=="BUS-A"
            voltage = trend.bus_a_voltage_kv(timeIndex);
        else
            voltage = trend.bus_b_voltage_kv(timeIndex);
        end
        live = motor.breaker_closed && voltage>0;
        hasFault = isProtected && currentMs>=feederProtection.fault_start_ms;
        faultEnergized = hasFault && live;
        terminalVoltage = voltage*double(motor.breaker_closed);
        if faultEnergized
            terminalVoltage = voltage*feederProtection.residual_voltage_pu;
        end

        ecmsTime(row) = trend.ecms_time_ms(timeIndex);
        sourceTime(row) = currentMs;
        quality(row) = trend.quality(timeIndex);
        configStatus(row) = trend.a_config_status(timeIndex);
        equipmentId(row) = equipment.id(equipmentIndex);
        label(row) = equipment.label(equipmentIndex);
        bus(row) = equipment.bus(equipmentIndex);
        feederId(row) = equipment.feeder(equipmentIndex);
        configuredKv(row) = equipment.voltage_kv(equipmentIndex);
        if isnan(equipment.rated_kw(equipmentIndex))
            ratedKw(row) = "";
        else
            ratedKw(row) = string(equipment.rated_kw(equipmentIndex));
        end
        breakerClosed(row) = double(motor.breaker_closed);
        runEnable(row) = double(motor.run_enable);
        runCommandFeedback(row) = double(motor.run_command_feedback);
        runFeedback(row) = double(motor.run_feedback);
        speedProven(row) = double(motor.speed_proven);
        tripLatched(row) = double(motor.trip_latched);
        tripCommanded(row) = double(motor.trip_commanded);
        stateCode(row) = motor.state_code;
        faultPresent(row) = double(hasFault);
        relay50Operated(row) = double(isProtected && ...
            isfinite(feederProtection.relay_50_operate_ms) && ...
            currentMs>=feederProtection.relay_50_operate_ms);
        relay51Operated(row) = double(isProtected && ...
            isfinite(feederProtection.relay_51_operate_ms) && ...
            currentMs>=feederProtection.relay_51_operate_ms && ...
            (~isfinite(feederProtection.breaker_open_ms) || ...
            feederProtection.relay_51_operate_ms<=feederProtection.breaker_open_ms));
        if isProtected
            amps = feederProtection.fault_current_a*double(faultEnergized);
            faultCurrentA(row) = string(amps);
            currentA(row) = string(amps);
        elseif isnan(equipment.rated_kw(equipmentIndex))
            faultCurrentA(row) = "";
            currentA(row) = "";
        else
            faultCurrentA(row) = "";
            if live
                amps = equipment.rated_kw(equipmentIndex)/ ...
                    (sqrt(3)*voltage*settings.POWER_FACTOR);
            else
                amps = 0;
            end
            currentA(row) = string(amps);
        end
        energized(row) = double(live);
        busVoltageKv(row) = voltage;
        terminalVoltageKv(row) = terminalVoltage;
        priority(row) = equipment.priority(equipmentIndex);
        equipmentStatus(row) = equipment.status(equipmentIndex);
        mLinkId(row) = linkIds(equipmentIndex);
        sourceMTag(row) = linkTags(equipmentIndex);
    end
end
feederTrend = table(ecmsTime,sourceTime,quality,configStatus,equipmentId,label, ...
    bus,feederId,configuredKv,ratedKw,breakerClosed,runEnable, ...
    runCommandFeedback,runFeedback,speedProven,tripLatched,tripCommanded, ...
    stateCode,faultPresent,faultCurrentA,relay50Operated,relay51Operated, ...
    energized,busVoltageKv,terminalVoltageKv,currentA,priority,equipmentStatus, ...
    mLinkId,sourceMTag,provenance, ...
    'VariableNames',{'ecms_time_ms','source_time_ms','quality','a_config_status', ...
    'equipment_id','label_ko','bus','feeder_id','configured_voltage_kv', ...
    'rated_kw','breaker_closed','run_enable','run_command_feedback', ...
    'run_feedback','speed_proven','trip_latched','trip_commanded','state_code', ...
    'fault_present','fault_current_a','relay_50_operated','relay_51_operated', ...
    'energized','bus_voltage_kv','terminal_voltage_kv','current_a','priority', ...
    'equipment_status','m_link_id','source_m_tag_id','provenance'});
end

function eventTable = addFeederTransitionRows(eventTable,feeders)
equipmentIds = unique(feeders.equipment_id,"stable");
extraRows = eventTable([],:);
for equipmentIndex = 1:numel(equipmentIds)
    rows = find(feeders.equipment_id==equipmentIds(equipmentIndex));
    values = feeders.breaker_closed(rows);
    changed = find(values(2:end)~=values(1:end-1))+1;
    for changedIndex = changed.'
        row = rows(changedIndex);
        next = table(feeders.ecms_time_ms(row),feeders.source_time_ms(row), ...
            "ECMS",equipmentIds(equipmentIndex)+".BREAKER.CLOSED", ...
            string(values(changedIndex-1)),string(values(changedIndex)), ...
            "POSITION",feeders.quality(row),"E_OBSERVED_TRANSITION", ...
            "Observed configured feeder breaker transition", ...
            'VariableNames',eventTable.Properties.VariableNames);
        extraRows = [extraRows;next]; %#ok<AGROW>
    end
end
if ~isempty(extraRows)
    eventTable = [eventTable;extraRows];
    % Keep the causal insertion order for equal timestamps. Alphabetically
    % sorting by tag can invert GT.TRIP -> relay pickup -> 86GT -> 52GT when
    % protection delays are configured to zero. The explicit ordinal also
    % avoids depending on release-specific sort stability in MATLAB Online.
    causalOrder = (1:height(eventTable)).';
    [~,order] = sortrows([eventTable.source_time_ms,causalOrder],[1 2]);
    eventTable = eventTable(order,:);
end
end

function [linkIds,linkTags] = equipmentLinks(packageRoot,equipmentIds)
linkIds = strings(numel(equipmentIds),1);
linkTags = strings(numel(equipmentIds),1);
pathValue = fullfile(packageRoot,"data","ecms_m_links.csv");
assert(isfile(pathValue),"TripLens:MissingMLinks", ...
    "Locked M-link table is required: %s",pathValue);
links = readCsv(pathValue);
requireColumns(links,{"link_id","ecms_equipment_id","source_m_tag_id","locked"}, ...
    "M links");
lockValues = lower(strtrim(string(links.locked)));
assert(all(ismember(lockValues,["1","true","yes","on"])), ...
    "TripLens:MLockViolation","Every ECMS M link must remain locked.");
linkIdValues = strtrim(string(links.link_id));
assert(numel(unique(linkIdValues))==height(links),"TripLens:DuplicateMLink", ...
    "M link_id values must be unique.");
ids = upper(strtrim(string(links.ecms_equipment_id)));
sourceTags = strtrim(string(links.source_m_tag_id));

mTagPath = fullfile(packageRoot,"data","thermo_vpp_m_locked_tags.csv");
assert(isfile(mTagPath),"TripLens:MissingMTags", ...
    "Locked M-tag catalog is required: %s",mTagPath);
mTags = readCsv(mTagPath);
requireColumns(mTags,{"tag_id","tag_class","value_basis"},"M-tag catalog");
mTagIds = strtrim(string(mTags.tag_id));
assert(numel(unique(mTagIds))==height(mTags),"TripLens:DuplicateMTag", ...
    "M tag_id values must be unique.");
assert(all(upper(strtrim(string(mTags.tag_class)))=="M" & ...
    upper(strtrim(string(mTags.value_basis)))=="M"), ...
    "TripLens:MLockViolation","M-tag catalog contains a non-M row.");
assert(all(ismember(sourceTags,mTagIds)),"TripLens:MissingMTagReference", ...
    "An ECMS M link references a tag absent from the locked M catalog.");

for index = 1:numel(equipmentIds)
    rows = find(ids==upper(equipmentIds(index)));
    assert(numel(rows)==1,"TripLens:EquipmentMLinkMismatch", ...
        "Equipment %s must have exactly one locked M link.",equipmentIds(index));
    row = rows(1);
    linkIds(index) = linkIdValues(row);
    linkTags(index) = sourceTags(row);
end
end

function copyReferenceFiles(packageRoot,stagingFolder)
for folder = ["topology","data"]
    source = fullfile(packageRoot,char(folder));
    if isfolder(source)
        copyfile(source,fullfile(stagingFolder,char(folder)));
    end
end
configFolder = fullfile(stagingFolder,"config");
for fileName = ["fault_presets.json","ecms_command_catalog.csv","signal_map.json", ...
        "common_trip_matrix.csv","tag_alias_contract.csv","dcs_alarm_rules.csv", ...
        "vpp_baseline_v1.json"]
    source = fullfile(packageRoot,"config",char(fileName));
    if isfile(source)
        copyfile(source,fullfile(configFolder,char(fileName)));
    end
end
end

function updateLatestRunPointer(packageRoot,runId)
pointerPath = fullfile(packageRoot,"latest_run.txt");
temporaryPath = fullfile(packageRoot,char(".latest_run_"+string(createRunId())+".tmp"));
temporaryCleanup = onCleanup(@() cleanupPointerTemporary(temporaryPath)); %#ok<NASGU>
runId = string(runId);
assert(isscalar(runId) && ...
    ~isempty(regexp(char(runId),"^MATLAB_[A-Za-z0-9_]+$","once")), ...
    "TripLens:InvalidRunId","Cannot create latest pointer for run ID: %s",runId);
% Construct exactly one scalar. FILEPARTS(stringPath) returns string name
% and extension values; horizontally concatenating [name extension] keeps
% an empty extension as a second string element. Passing that 1x2 value to
% FPRINTF produced '<run-path>runs/' in MATLAB Online.
relativePath = "runs/"+runId;
expectedText = sprintf('%s\n',char(relativePath));
file = fopen(temporaryPath,"w","n","UTF-8");
assert(file~=-1,"TripLens:PointerWriteFailed", ...
    "Could not write latest-run pointer: %s",temporaryPath);
cleanup = onCleanup(@() fclose(file));
fwrite(file,expectedText,'char');
clear cleanup;
assert(strcmp(fileread(temporaryPath),expectedText), ...
    "TripLens:PointerWriteFailed","Temporary latest-run pointer verification failed.");

% Avoid replacing a cloud-backed pointer in place. Move the prior pointer
% to a transaction backup, then rename the verified temporary file onto an
% absent destination. Restore the backup if commit or verification fails.
backupPath = fullfile(packageRoot,char(".latest_run_previous_"+ ...
    string(createRunId())+".tmp"));
hadPrevious = isfile(pointerPath);
if hadPrevious
    [saved,message] = movefile(pointerPath,backupPath);
    assert(saved,"TripLens:PointerBackupFailed", ...
        "Could not stage the previous latest-run pointer: %s",message);
end
[moved,message] = movefile(temporaryPath,pointerPath);
if ~moved
    restorePointerBackup(pointerPath,backupPath,hadPrevious);
    error("TripLens:PointerCommitFailed", ...
        "Run succeeded, but latest_run.txt could not be committed: %s",message);
end
if ~strcmp(fileread(pointerPath),expectedText)
    delete(pointerPath);
    restorePointerBackup(pointerPath,backupPath,hadPrevious);
    error("TripLens:PointerVerificationFailed", ...
        "Run succeeded, but latest_run.txt did not match the committed run.");
end
if hadPrevious && isfile(backupPath)
    delete(backupPath);
end
end

function restorePointerBackup(pointerPath,backupPath,hadPrevious)
if hadPrevious && isfile(backupPath) && ~isfile(pointerPath)
    [restored,message] = movefile(backupPath,pointerPath);
    if ~restored
        warning("TripLens:PointerRollbackFailed", ...
            "Previous latest-run pointer remains at %s: %s",backupPath,message);
    end
end
end

function cleanupPointerTemporary(pathValue)
if isfile(pathValue)
    delete(pathValue);
end
end

function manifest = makeManifest(runId,tripTime,stopTime,faultPreset, ...
        configStatus,auxiliaryVoltageKv,processRows,trendRows,eventRows, ...
        feederRows,commandRows,samplingProfile,normalPeriodMs,incidentPeriodMs, ...
        incidentStartMs,incidentStopMs)
try
    created = char(datetime("now","TimeZone","UTC", ...
        "Format","yyyy-MM-dd'T'HH:mm:ss.SSSXXX"));
catch
    created = [datestr(now,'yyyy-mm-ddTHH:MM:SS.FFF') 'Z'];
end
manifest = struct();
manifest.schema_version = "3.1";
manifest.created_at_utc = created;
manifest.run_id = runId;
manifest.scenario = struct("id","MATLAB_SYNTHETIC_GT_TRIP", ...
    "trip_time_s",tripTime,"stop_time_s",stopTime,"fault_preset",faultPreset);
manifest.runtime = struct("engine","MATLAB_NATIVE_SYNTHETIC_FALLBACK", ...
    "engine_contract","MATLAB_FALLBACK_1.0", ...
    "matlab_version",version,"thermosyspro_used",false, ...
    "python_used",false,"openmodelica_used",false);
if samplingProfile=="incident_1ms"
    activeIncidentPeriodMs = incidentPeriodMs;
    activeIncidentStartMs = incidentStartMs;
    activeIncidentStopMs = incidentStopMs;
else
    % JSONENCODE represents NaN as null, matching the cloud manifest's
    % inactive incident-window fields without producing a non-scalar struct.
    activeIncidentPeriodMs = NaN;
    activeIncidentStartMs = NaN;
    activeIncidentStopMs = NaN;
end
manifest.sampling = struct("profile",char(samplingProfile), ...
    "timing_source","MATLAB_NAME_VALUE_ARGUMENTS", ...
    "processbus",struct( ...
        "normal_period_ms",normalPeriodMs, ...
        "incident_period_ms",activeIncidentPeriodMs, ...
        "incident_window_start_ms",activeIncidentStartMs, ...
        "incident_window_end_ms",activeIncidentStopMs, ...
        "value_basis","SYNTHETIC_MATLAB_FALLBACK_DIRECT_SAMPLE"), ...
    "ecms",struct( ...
        "normal_period_ms",normalPeriodMs, ...
        "incident_period_ms",activeIncidentPeriodMs, ...
        "incident_window_start_ms",activeIncidentStartMs, ...
        "incident_window_end_ms",activeIncidentStopMs, ...
        "value_basis","MATLAB_ELECTRICAL_MODEL_ON_SHARED_SAMPLE_GRID"), ...
    "event_timestamp_unit","ms");
manifest.topology = struct("auxiliary_voltage_kv",auxiliaryVoltageKv, ...
    "identity","UAT-A/UAT-B taps on GT/ST main transformer paths", ...
    "sst_present",false);
manifest.provenance = struct( ...
    "processbus","SYNTHETIC_MATLAB_FALLBACK_NOT_THERMOSYSPRO", ...
    "ecms","A_CONFIGURED_MATLAB_ELECTRICAL_OBSERVATION_MODEL", ...
    "a_config_status",char(configStatus));
manifest.counts = struct("processbus_rows",processRows,"trend_rows",trendRows, ...
    "event_rows",eventRows,"feeder_rows",feederRows,"command_rows",commandRows);
manifest.warning = ...
    "Fallback data is synthetic and must not be represented as an approved plant drawing, " + ...
    "field measurement, or ThermoSysPro result.";
end

function writeJson(pathValue,value)
try
    text = jsonencode(value,"PrettyPrint",true);
catch
    text = jsonencode(value);
end
file = fopen(pathValue,"w","n","UTF-8");
assert(file~=-1,"TripLens:WriteFailed","Could not open %s for writing.",pathValue);
cleanup = onCleanup(@() fclose(file)); %#ok<NASGU>
fprintf(file,"%s\n",text);
end

function verifyStaging(stagingFolder,equipmentCount)
required = ["processbus.csv","ecms-trend.csv","ecms-events.csv", ...
    "ecms-feeders.csv","manifest.json"];
for index = 1:numel(required)
    pathValue = fullfile(stagingFolder,char(required(index)));
    assert(isfile(pathValue),"TripLens:IncompleteRun", ...
        "Staged run is missing %s",required(index));
    info = dir(pathValue);
    assert(info.bytes>0,"TripLens:IncompleteRun", ...
        "Staged run file is empty: %s",required(index));
end
trend = readCsv(fullfile(stagingFolder,"ecms-trend.csv"));
processBus = readCsv(fullfile(stagingFolder,"processbus.csv"));
events = readCsv(fullfile(stagingFolder,"ecms-events.csv"));
feeders = readCsv(fullfile(stagingFolder,"ecms-feeders.csv"));
requireColumns(processBus,{"time_s","gt_trip_cmd","data_origin"},"processbus.csv");
requireColumns(trend,{"source_time_ms","sampling_resolution"},"ecms-trend.csv");
requireColumns(feeders,{"source_time_ms","equipment_id","feeder_id", ...
    "breaker_closed","run_enable","run_command_feedback","run_feedback", ...
    "trip_latched","trip_commanded","fault_present","fault_current_a", ...
    "relay_50_operated","relay_51_operated","terminal_voltage_kv"}, ...
    "ecms-feeders.csv");
assert(all(string(processBus.data_origin)== ...
    "SYNTHETIC_MATLAB_FALLBACK_NOT_THERMOSYSPRO"), ...
    "TripLens:FalseProvenance", ...
    "MATLAB fallback ProcessBus must remain clearly labeled as synthetic.");
assert(height(processBus)==height(trend),"TripLens:IncompleteRun", ...
    "MATLAB fallback ProcessBus and ECMS trend must share one sample grid.");
assert(all(diff(trend.source_time_ms)>0),"TripLens:InvalidSamplingGrid", ...
    "ECMS trend sample times must be strictly increasing and duplicate-free.");
assert(height(feeders)==height(trend)*equipmentCount, ...
    "TripLens:IncompleteRun","Feeder row count does not match trend x equipment.");
assert(~any(contains(lower(string(trend.Properties.VariableNames)),"sst")), ...
    "TripLens:WrongTopology","SST fields are forbidden in the 6.9 kV topology.");
assert(~any(contains(upper(string(events.tag)),"SST")), ...
    "TripLens:WrongTopology","SST event tags are forbidden in the 6.9 kV topology.");
assert(all(diff(events.source_time_ms)>=0),"TripLens:UnsortedEvents", ...
    "ECMS events must be sorted by source_time_ms.");
assert(all(events.source_time_ms>=trend.source_time_ms(1) & ...
    events.source_time_ms<=trend.source_time_ms(end)), ...
    "TripLens:EventOutsideHorizon","ECMS event lies outside the trend horizon.");
end

function id = createRunId()
try
    stamp = char(datetime("now","TimeZone","UTC","Format","yyyyMMdd_HHmmss_SSS"));
catch
    stamp = datestr(now,"yyyymmdd_HHMMSSFFF");
end
id = sprintf("MATLAB_%s_%06d",stamp,randi(999999));
end

function cleanupStaging(pathValue)
if isfolder(pathValue)
    rmdir(pathValue,"s");
end
end
