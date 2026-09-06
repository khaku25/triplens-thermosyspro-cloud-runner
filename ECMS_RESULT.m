function result = ECMS_RESULT()
%ECMS_RESULT Open the latest committed ECMS 3.1 run or bundled demo.

packageRoot = fileparts(mfilename("fullpath"));
matlabDir = fullfile(packageRoot,"matlab");
viewerFile = fullfile(matlabDir,"run_cloud_result.m");
assert(isfile(viewerFile),"TripLens:MissingViewer","Viewer file not found: %s",viewerFile);

addpath(matlabDir,"-begin");
rehash;
clear run_cloud_result;
resolvedViewer = string(which("run_cloud_result"));
assert(resolvedViewer == string(viewerFile), ...
    "TripLens:WrongViewer","Wrong result viewer is shadowing ECMS 3.1: %s",resolvedViewer);

pointerFile = fullfile(packageRoot,"latest_run.txt");
resultFolder = "";
if isfile(pointerFile)
    relativeRun = strtrim(string(fileread(pointerFile)));
    normalizedRun = replace(relativeRun,"\","/");
    safePattern = "^runs/MATLAB_[A-Za-z0-9_]+$";
    pointerIsSafe = isscalar(normalizedRun) && ...
        ~isempty(regexp(char(normalizedRun),safePattern,"once"));
    if pointerIsSafe
        runName = extractAfter(normalizedRun,"runs/");
        candidate = fullfile(packageRoot,"runs",char(runName));
        if isCommittedRun(candidate)
            resultFolder = string(candidate);
        else
            warning("TripLens:MissingLatestRun", ...
                "latest_run.txt points to an incomplete or missing run; scanning committed runs.");
        end
    else
        warning("TripLens:InvalidLatestRunPointer", ...
            "latest_run.txt is malformed; scanning committed runs instead: %s",relativeRun);
    end
end
if strlength(resultFolder)==0
    resultFolder = findLatestCommittedRun(packageRoot);
end
if strlength(resultFolder)>0
    result = run_cloud_result(resultFolder);
    fprintf("PASS: latest committed ECMS run opened.\n");
else
    result = run_cloud_result(packageRoot);
    fprintf("NOTICE: no MATLAB-native run exists yet; bundled demo opened.\n");
end
end

function resultFolder = findLatestCommittedRun(packageRoot)
resultFolder = "";
runsFolder = fullfile(packageRoot,"runs");
if ~isfolder(runsFolder)
    return;
end
entries = dir(fullfile(runsFolder,"MATLAB_*"));
names = strings(0,1);
for index = 1:numel(entries)
    if entries(index).isdir && ...
            ~isempty(regexp(entries(index).name,"^MATLAB_[A-Za-z0-9_]+$","once"))
        candidate = fullfile(runsFolder,entries(index).name);
        if isCommittedRun(candidate)
            names(end+1,1) = string(entries(index).name); %#ok<AGROW>
        end
    end
end
if isempty(names)
    return;
end
names = sort(names,"descend");
resultFolder = string(fullfile(runsFolder,char(names(1))));
end

function value = isCommittedRun(folder)
required = ["processbus.csv","ecms-trend.csv","ecms-events.csv", ...
    "ecms-feeders.csv","manifest.json"];
value = isfolder(folder);
for index = 1:numel(required)
    value = value && isfile(fullfile(folder,required(index)));
end
end
