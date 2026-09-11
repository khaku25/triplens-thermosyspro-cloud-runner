function result = ECMS_GITHUB(varargin)
%ECMS_GITHUB Run the proven GitHub OPC UA physics loop and import it to ECMS.
%   RESULT = ECMS_GITHUB() dispatches matlab-native-opcua-ecms.yml in the
%   TripLens MATLAB co-simulation repository. The GitHub job owns only the
%   running 52GT-open -> derived Trip -> OPC UA/ThermoSysPro physical exchange.
%   Actual plant logic is deliberately excluded. This Cloud package then
%   converts the downloaded receive capture into ProcessBus, DCS and ECMS.
%
%   Before calling, set TRIPLENS_GITHUB_TOKEN to a fine-grained GitHub token
%   that has Actions read/write access to khaku25/triplens-matlab-cosim-runner.
%   The token is read by Python from the environment and is never put on the
%   command line or written to a result file.

parser = inputParser;
parser.FunctionName = mfilename;
packageRoot = fileparts(mfilename("fullpath"));
addParameter(parser,"PackageRoot",packageRoot,@isTextScalar);
addParameter(parser,"Repository","khaku25/triplens-matlab-cosim-runner",@isTextScalar);
addParameter(parser,"Ref","codex/matlab-opcua-vpp-20260910",@isTextScalar);
addParameter(parser,"Workflow","matlab-native-opcua-ecms.yml",@isTextScalar);
addParameter(parser,"TimeoutMinutes",240,@isPositiveScalar);
addParameter(parser,"PollSeconds",15,@isPositiveScalar);
addParameter(parser,"SettingsTable",table(),@(x) isempty(x) || istable(x));
addParameter(parser,"EquipmentTable",table(),@(x) isempty(x) || istable(x));
addParameter(parser,"OpenResult",true,@(x) islogical(x) && isscalar(x));
parse(parser,varargin{:});
options = parser.Results;

packageRoot = char(string(options.PackageRoot));
assert(isfolder(packageRoot),"TripLens:MissingPackageRoot", ...
    "ECMS package root does not exist: %s",packageRoot);
bridge = fullfile(packageRoot,"scripts","github_opcua_cloud_bridge.py");
assert(isfile(bridge),"TripLens:MissingGitHubBridge", ...
    "GitHub OPC UA bridge not found: %s",bridge);
token = getenv("TRIPLENS_GITHUB_TOKEN");
assert(~isempty(token),"TripLens:MissingGitHubToken",join([ ...
    "TRIPLENS_GITHUB_TOKEN 환경변수가 없습니다."; ...
    "GitHub fine-grained token에 triplens-matlab-cosim-runner의 Actions read/write 권한을 준 뒤"; ...
    "토큰 값은 파일에 쓰지 말고 환경변수에만 저장하세요."],newline));

python = resolvePython();
temporaryRoot = tempname;
mkdir(temporaryRoot);
cleanup = onCleanup(@()removeTemporary(temporaryRoot)); %#ok<NASGU>

settingsPath = fullfile(packageRoot,"config","ecms_a_settings.csv");
equipmentPath = fullfile(packageRoot,"config","ecms_a_equipment.csv");
if ~isempty(options.SettingsTable)
    settingsPath = fullfile(temporaryRoot,"ecms_a_settings.csv");
    writetable(options.SettingsTable,settingsPath,"Delimiter",",", ...
        "WriteVariableNames",true);
end
if ~isempty(options.EquipmentTable)
    equipmentPath = fullfile(temporaryRoot,"ecms_a_equipment.csv");
    writetable(options.EquipmentTable,equipmentPath,"Delimiter",",", ...
        "WriteVariableNames",true);
end

arguments = [ ...
    shellQuote(python),shellQuote(bridge), ...
    "--package-root",shellQuote(packageRoot), ...
    "--output-root",shellQuote(fullfile(packageRoot,"runs")), ...
    "--repository",shellQuote(options.Repository), ...
    "--ref",shellQuote(options.Ref), ...
    "--workflow",shellQuote(options.Workflow), ...
    "--timeout-minutes",string(options.TimeoutMinutes), ...
    "--poll-seconds",string(options.PollSeconds), ...
    "--a-settings",shellQuote(settingsPath), ...
    "--a-equipment",shellQuote(equipmentPath)];
fprintf("GitHub OPC UA 물리 실행을 요청합니다. 완료까지 시간이 걸릴 수 있습니다.\n");
[status,output] = system(join(arguments," "));
fprintf("%s",output);
assert(status==0,"TripLens:GitHubBridgeFailed", ...
    "GitHub OPC UA Cloud bridge failed (exit %d).\n%s",status,output);

marker = "TRIPLENS_GITHUB_BRIDGE_RESULT=";
lines = splitlines(string(output));
matches = lines(startsWith(lines,marker));
assert(numel(matches)==1,"TripLens:MissingGitHubBridgeResult", ...
    "GitHub bridge did not return exactly one result record.");
result = jsondecode(extractAfter(matches(1),marker));
result.RunFolder = string(result.RunFolder);
result.RunUrl = string(result.RunUrl);
result.ArtifactName = string(result.ArtifactName);
result.Engine = string(result.Engine);

if options.OpenResult
    matlabDir = fullfile(packageRoot,"matlab");
    addpath(matlabDir,"-begin");
    rehash;
    clear run_cloud_result;
    expectedViewer = string(fullfile(matlabDir,"run_cloud_result.m"));
    assert(string(which("run_cloud_result"))==expectedViewer, ...
        "TripLens:WrongViewer","A different result viewer is shadowing this package.");
    result.View = run_cloud_result(result.RunFolder);
end
fprintf("PASS: GitHub OPC UA physics imported into Cloud ECMS: %s\n",result.RunFolder);
end

function value = isTextScalar(input)
value = (ischar(input) && (isrow(input) || isempty(input))) || ...
    (isstring(input) && isscalar(input));
end

function value = isPositiveScalar(input)
value = isnumeric(input) && isscalar(input) && isfinite(input) && input>0;
end

function executable = resolvePython()
configured = string(getenv("TRIPLENS_PYTHON"));
if strlength(configured)>0
    candidates = configured;
elseif ispc
    candidates = "python";
else
    candidates = ["python3","python"];
end
for index = 1:numel(candidates)
    candidate = candidates(index);
    [status,~] = system(shellQuote(candidate)+" --version");
    if status==0
        executable = candidate;
        return;
    end
end
error("TripLens:PythonUnavailable",join([ ...
    "Python 3를 찾지 못했습니다."; ...
    "Python 3 실행 경로를 TRIPLENS_PYTHON 환경변수로 지정하세요."],newline));
end

function value = shellQuote(input)
value = string(input);
assert(~contains(value,'"'),"TripLens:UnsafePath", ...
    "A GitHub bridge path or argument contains an unsupported double quote.");
value = '"'+value+'"';
end

function removeTemporary(folder)
if isfolder(folder)
    try
        rmdir(folder,"s");
    catch
    end
end
end
