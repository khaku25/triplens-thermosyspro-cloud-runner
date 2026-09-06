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

periodMs = round(settings.TREND_PERIOD_MS);
assert(periodMs > 0,"TripLens:InvalidTrendPeriod","TREND_PERIOD_MS must be positive.");
stopMs = round(stopTime*1000);
estimatedTrendRows = floor(stopMs/periodMs)+2;
assert(estimatedTrendRows<=50000,"TripLens:FallbackRunTooLarge", ...
    "The MATLAB fallback would create about %d trend rows and too many feeder rows. " + ...
    "Shorten StopTime or increase TREND_PERIOD_MS.",estimatedTrendRows);
timeMs = (0:periodMs:stopMs).';
if timeMs(end) ~= stopMs
    timeMs(end+1,1) = stopMs;
end
timeSeconds = timeMs./1000;

processBus = makeSyntheticProcessBus(timeSeconds,tripTime);
[trend,events] = simulateElectrical(processBus,timeMs,tripTime,settings, ...
    configStatus,fault,faultPreset,commands);
feeders = makeFeederTrend(trend,equipment,commands,settings,packageRoot);
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
    height(events),height(feeders),height(resolvedCommandTable));
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
    "TREND_PERIOD_MS"];
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
delayNames = ["TRIP_RECEIVE_DELAY_MS","LOCKOUT_OPERATE_DELAY_MS", ...
    "GT_BREAKER_OPEN_DELAY_MS","GT_POWER_DECAY_MS", ...
    "ST_BREAKER_OPEN_DELAY_MS","CLOCK_OFFSET_MS"];
for index = 1:numel(delayNames)-1
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
    "rated_kw","normal_breaker_state","priority","status"};
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
        configStatus,fault,faultPreset,commands)
n = numel(timeMs);
tripMs = round(tripTime*1000);
relayTripMs = tripMs + round(settings.TRIP_RECEIVE_DELAY_MS);
lockoutMs = relayTripMs + round(settings.LOCKOUT_OPERATE_DELAY_MS);
gtOpenMs = tripMs + round(settings.GT_BREAKER_OPEN_DELAY_MS);
relayOperates = ~faultEnabled(fault,"relay_fail");
gtBreakerOpens = relayOperates && ~faultEnabled(fault,"gtg_breaker_fail");

stReference = max(abs(processBus.stg_power_w(1)),1);
lowIndex = find(abs(processBus.stg_power_w) < stReference*settings.ST_TRIP_POWER_PU,1);
if isempty(lowIndex)
    stOpenMs = inf;
else
    stOpenMs = timeMs(lowIndex)+round(settings.ST_BREAKER_OPEN_DELAY_MS);
end
stTripCommands = commands.time_s(commands.equipment_id=="STG" & commands.command=="TRIP");
if ~isempty(stTripCommands)
    stOpenMs = min(stOpenMs,round(min(stTripCommands)*1000)+round(settings.ST_BREAKER_OPEN_DELAY_MS));
end

ecmsTime = timeMs + round(settings.CLOCK_OFFSET_MS);
quality = repmat("GOOD",n,1);
config = repmat(string(configStatus),n,1);
gtTrip = double(timeMs>=tripMs);
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
    if afterTrip
        duration = settings.GT_POWER_DECAY_MS;
        if duration<=0 || currentMs>=tripMs+duration
            decay = 0;
        else
            decay = max(0,1-(currentMs-tripMs)/duration);
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
trend = table(ecmsTime,timeMs,quality,config,gtTrip,relay86,cb52gt,cb52st, ...
    cbInA,cbInB,cbTie,gtDirection,stDirection,gtMw,gtCurrent,stMw,stCurrent, ...
    gridPu,frequency,busAPu,busAKv,busBPu,busBKv,gridKv,parallelAllowed, ...
    sourceParallelActive, ...
    'VariableNames',{'ecms_time_ms','source_time_ms','quality','a_config_status', ...
    'gt_trip_cmd','relay_86gt_operated','cb_52gt_closed','cb_52st_closed', ...
    'cb_in_a_closed','cb_in_b_closed','cb_tie_ab_closed', ...
    'gt_main_transformer_direction','st_main_transformer_direction', ...
    'gtg_power_mw','gtg_current_a','stg_power_mw','stg_current_a', ...
    'grid_voltage_pu','frequency_hz','bus_a_voltage_pu','bus_a_voltage_kv', ...
    'bus_b_voltage_pu','bus_b_voltage_kv','grid_voltage_kv', ...
    'source_parallel_allowed','source_parallel_active'});

events = baseEvents(tripMs,relayTripMs,lockoutMs,gtOpenMs,stOpenMs, ...
    relayOperates,gtBreakerOpens,fault,faultPreset,commands,settings.CLOCK_OFFSET_MS);
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
    elseif any(action==["OPEN","TRIP","STOP","OUT_OF_SERVICE","LOSS"])
        state = false;
        if action=="TRIP"
            latched = true;
        end
    elseif any(action==["CLOSE","START","IN_SERVICE","RESTORE"]) && ~latched
        state = true;
    end
end
if ~automaticApplied && automaticTripMs<=currentMs
    state = false;
end
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

function events = baseEvents(tripMs,relayTripMs,lockoutMs,gtOpenMs,stOpenMs, ...
        relayOperates,gtBreakerOpens,fault,faultPreset,commands,clockOffset)
events = repmat(newEvent(0,"","","","","",""),0,1);
tripProvenance = "SYNTHETIC_SCENARIO";
if any(commands.equipment_id=="GTG" & commands.command=="TRIP" & ...
        round(commands.time_s*1000)==tripMs)
    tripProvenance = "USER_COMMAND";
end
events(end+1) = newEvent(tripMs,"GT.TRIP.CMD","0","1","TRIP", ...
    "Synthetic MATLAB fallback GT Trip asserted",tripProvenance);
if relayOperates
    events(end+1) = newEvent(relayTripMs,"86GT.TRIP.RECEIVED","0","1", ...
        "PICKUP","GT Trip received","E_DERIVED");
    events(end+1) = newEvent(lockoutMs,"86GT.OPERATE","0","1", ...
        "OPERATE","GT lockout relay operated","E_DERIVED");
else
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
        "POSITION","ST generator breaker opened after rundown","E_DERIVED");
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

function feederTrend = makeFeederTrend(trend,equipment,commands,settings,packageRoot)
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
energized = zeros(n,1);
busVoltageKv = zeros(n,1);
currentA = strings(n,1);
priority = strings(n,1);
equipmentStatus = strings(n,1);
mLinkId = strings(n,1);
sourceMTag = strings(n,1);
provenance = repmat("A_CONFIGURED_E_DERIVED",n,1);
[linkIds,linkTags] = equipmentLinks(packageRoot,equipment.id);

row = 0;
for timeIndex = 1:nTime
    for equipmentIndex = 1:nEquipment
        row = row+1;
        closed = breakerWithAutomaticTrip(equipment.normal_closed(equipmentIndex), ...
            inf,trend.source_time_ms(timeIndex),commands,equipment.id(equipmentIndex));
        if equipment.bus(equipmentIndex)=="BUS-A"
            voltage = trend.bus_a_voltage_kv(timeIndex);
        else
            voltage = trend.bus_b_voltage_kv(timeIndex);
        end
        live = closed && voltage>0;
        ecmsTime(row) = trend.ecms_time_ms(timeIndex);
        sourceTime(row) = trend.source_time_ms(timeIndex);
        quality(row) = trend.quality(timeIndex);
        configStatus(row) = trend.a_config_status(timeIndex);
        equipmentId(row) = equipment.id(equipmentIndex);
        label(row) = equipment.label(equipmentIndex);
        bus(row) = equipment.bus(equipmentIndex);
        feederId(row) = equipment.feeder(equipmentIndex);
        configuredKv(row) = equipment.voltage_kv(equipmentIndex);
        if isnan(equipment.rated_kw(equipmentIndex))
            ratedKw(row) = "";
            currentA(row) = "";
        else
            ratedKw(row) = string(equipment.rated_kw(equipmentIndex));
            if live
                amps = equipment.rated_kw(equipmentIndex)/(sqrt(3)*voltage*settings.POWER_FACTOR);
            else
                amps = 0;
            end
            currentA(row) = string(amps);
        end
        breakerClosed(row) = double(closed);
        energized(row) = double(live);
        busVoltageKv(row) = voltage;
        priority(row) = equipment.priority(equipmentIndex);
        equipmentStatus(row) = equipment.status(equipmentIndex);
        mLinkId(row) = linkIds(equipmentIndex);
        sourceMTag(row) = linkTags(equipmentIndex);
    end
end
feederTrend = table(ecmsTime,sourceTime,quality,configStatus,equipmentId,label, ...
    bus,feederId,configuredKv,ratedKw,breakerClosed,energized,busVoltageKv, ...
    currentA,priority,equipmentStatus,mLinkId,sourceMTag,provenance, ...
    'VariableNames',{'ecms_time_ms','source_time_ms','quality','a_config_status', ...
    'equipment_id','label_ko','bus','feeder_id','configured_voltage_kv', ...
    'rated_kw','breaker_closed','energized','bus_voltage_kv','current_a', ...
    'priority','equipment_status','m_link_id','source_m_tag_id','provenance'});
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
    % Older MATLAB releases reject a cell array containing string scalars as
    % a table-variable subscript.  Use a character-vector cell array so the
    % same package runs in MATLAB Online releases with the stricter API.
    eventTable = sortrows(eventTable,{'source_time_ms','tag'});
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
for fileName = ["fault_presets.json","ecms_command_catalog.csv","signal_map.json"]
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
        feederRows,commandRows)
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
assert(all(string(processBus.data_origin)== ...
    "SYNTHETIC_MATLAB_FALLBACK_NOT_THERMOSYSPRO"), ...
    "TripLens:FalseProvenance", ...
    "MATLAB fallback ProcessBus must remain clearly labeled as synthetic.");
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
