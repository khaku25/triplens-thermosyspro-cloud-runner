function ECMS_START()
%ECMS_START Open the authoritative TripLens ECMS VPP 3.1 editor.

packageRoot = fileparts(mfilename("fullpath"));
matlabDir = fullfile(packageRoot,"matlab");
editorFile = fullfile(matlabDir,"triplens_ecms_vpp_editor.m");
assert(isfile(editorFile),"TripLens:MissingEditor","Editor file not found: %s",editorFile);

addpath(matlabDir,"-begin");
drawnow;
editorNames = ["TripLens ECMS VPP Editor 2.0","TripLens ECMS VPP Editor 2.1", ...
    "TripLens ECMS VPP Editor 3.0","TripLens ECMS VPP Editor 3.1"];
for index = 1:numel(editorNames)
    delete(findall(groot,"Type","figure","Name",editorNames(index)));
end
drawnow;
clear triplens_ecms_vpp_editor;
rehash;
resolvedEditor = string(which("triplens_ecms_vpp_editor"));
assert(resolvedEditor == string(editorFile), ...
    "TripLens:WrongEditor","Wrong editor is shadowing ECMS 3.1: %s",resolvedEditor);

triplens_ecms_vpp_editor();
drawnow;
editorFigure = findall(groot,"Type","figure","Name","TripLens ECMS VPP Editor 3.1");
assert(numel(editorFigure)==1,"TripLens:EditorLaunchFailed","ECMS Editor 3.1 did not open exactly once.");
fprintf("PASS: TripLens ECMS VPP Editor 3.1 opened from %s\n",resolvedEditor);
end
