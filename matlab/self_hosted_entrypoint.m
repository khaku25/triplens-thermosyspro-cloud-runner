function self_hosted_entrypoint(mode)
%SELF_HOSTED_ENTRYPOINT Entry point for TripLens self-hosted MATLAB runner.
%   mode="smoke" validates the real MATLAB environment and package.
%   mode="ecms" runs the current MATLAB-native ECMS pipeline.

if nargin < 1 || strlength(string(mode)) == 0
    mode = "smoke";
end
mode = lower(string(mode));

repoRoot = fileparts(fileparts(mfilename("fullpath")));
cd(repoRoot);
addpath(repoRoot,"-begin");
addpath(fullfile(repoRoot,"matlab"),"-begin");

fprintf("TripLens self-hosted MATLAB runner\n");
fprintf("MATLAB version: %s\n", version);
fprintf("Computer: %s\n", computer);
fprintf("Repository: %s\n", repoRoot);

products = ver;
fprintf("Installed MathWorks products:\n");
for k = 1:numel(products)
    fprintf("  - %s %s\n", products(k).Name, products(k).Version);
end

assert(exist("ECMS_SELF_TEST","file") == 2, ...
    "TripLens:MissingSelfTest", "ECMS_SELF_TEST.m is missing from repository root.");
assert(exist("ECMS_RUN","file") == 2, ...
    "TripLens:MissingRunner", "ECMS_RUN.m is missing from repository root.");

switch mode
    case "smoke"
        ECMS_SELF_TEST;
        fprintf("PASS: real MATLAB self-hosted smoke test completed.\n");

    case "ecms"
        ECMS_SELF_TEST;
        result = ECMS_RUN;
        save(fullfile(repoRoot,"self_hosted_last_result.mat"),"result","-v7.3");
        fprintf("PASS: ECMS run completed in real MATLAB.\n");

    otherwise
        error("TripLens:UnknownMode", "Unknown self-hosted mode: %s", mode);
end
end
