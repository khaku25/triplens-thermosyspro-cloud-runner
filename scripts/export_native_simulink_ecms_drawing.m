function export_native_simulink_ecms_drawing()
% Export actual TripLens_ECMS_DigitalTwin Simulink rendering without rearranging it.

repoRoot = getenv('GITHUB_WORKSPACE');
if isempty(repoRoot), repoRoot = pwd; end
outDir = fullfile(repoRoot,'outputs','native_simulink_drawing');
if ~isfolder(outDir), mkdir(outDir); end

assert(license('test','Simulink'),'TripLens:SimulinkUnavailable','Simulink license unavailable.');

mdrive = '';
try
    if exist('matlabdrive','file') == 2, mdrive = matlabdrive; end
catch
end
if isempty(mdrive)
    candidate = fullfile(getenv('USERPROFILE'),'MATLAB Drive');
    if isfolder(candidate), mdrive = candidate; end
end
assert(~isempty(mdrive) && isfolder(mdrive),'TripLens:MATLABDriveUnavailable','MATLAB Drive folder unavailable.');

modelName = 'TripLens_ECMS_DigitalTwin';
modelPath = fullfile(mdrive,'TripLens_ECMS_DigitalTwin',[modelName '.slx']);
assert(isfile(modelPath),'TripLens:MissingECMSModel','Missing ECMS model: %s',modelPath);

if bdIsLoaded(modelName), close_system(modelName,0); end
load_system(modelPath);
cleanup = onCleanup(@() close_system(modelName,0)); %#ok<NASGU>

% Render the actual model; do not call arrangeSystem, set Position, or save_system.
open_system(modelName);
try, set_param(modelName,'ZoomFactor','FitSystem'); catch, end
drawnow;

svgPath = fullfile(outDir,'TripLens_ECMS_DigitalTwin.svg');
pngPath = fullfile(outDir,'TripLens_ECMS_DigitalTwin.png');

print(['-s' modelName],'-dsvg',svgPath);
print(['-s' modelName],'-dpng','-r200',pngPath);

blocks = find_system(modelName,'SearchDepth',1,'Type','Block');
rows = cell(numel(blocks),5);
for k=1:numel(blocks)
    pos = get_param(blocks{k},'Position');
    rows{k,1}=get_param(blocks{k},'Name');
    rows{k,2}=pos(1); rows{k,3}=pos(2); rows{k,4}=pos(3); rows{k,5}=pos(4);
end
T = cell2table(rows,'VariableNames',{'Block','Left','Top','Right','Bottom'});
writetable(T,fullfile(outDir,'top_level_block_positions.csv'));

report = struct('status','PASS','model',modelName,'model_path',modelPath, ...
    'svg',svgPath,'png',pngPath,'top_level_blocks',height(T), ...
    'geometry_source','SIMULINK_NATIVE_RENDER','model_modified',false);
fid=fopen(fullfile(outDir,'export_report.json'),'w');
assert(fid>=0); fwrite(fid,jsonencode(report,'PrettyPrint',true),'char'); fclose(fid);

fprintf('SIMULINK_NATIVE_DRAWING_EXPORT_PASS\n');
fprintf('SVG=%s\n',svgPath);
fprintf('PNG=%s\n',pngPath);
end
