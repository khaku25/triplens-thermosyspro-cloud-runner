function app = ECMSVPP()
% TRIPLENS_DUAL_LOG_V7_SAFE
%ECMSVPP Open the one-touch TripLens ECMS VPP 3.1 control panel.

packageRoot = fileparts(mfilename("fullpath"));
addpath(packageRoot,"-begin");
addpath(fullfile(packageRoot,"matlab"),"-begin");
clear ECMS_START ECMS_RUN ECMS_RESULT ECMS_LIVE ECMS_VALVES ECMS_TRENDS ECMS_OPERATOR_PROOF ECMS_BFP_ALARMS ECMS_DIAGNOSE;
rehash;

helperNames = ["ECMS_START","ECMS_RUN","ECMS_RESULT","ECMS_LIVE", ...
    "ECMS_VALVES","ECMS_TRENDS","ECMS_OPERATOR_PROOF","ECMS_BFP_ALARMS","ECMS_DIAGNOSE"];
for helperIndex = 1:numel(helperNames)
    expectedHelper = string(fullfile(packageRoot,helperNames(helperIndex)+".m"));
    resolvedHelper = string(which(helperNames(helperIndex)));
    assert(resolvedHelper==expectedHelper,"TripLens:PathShadowing", ...
        "A previous ECMS package is shadowing %s. Expected %s, resolved %s", ...
        helperNames(helperIndex),expectedHelper,resolvedHelper);
end

oldPanels = findall(groot,"Type","figure","Name","TripLens ECMS VPP 3.1 Control");
delete(oldPanels);

app = uifigure("Name","TripLens ECMS VPP 3.1 Control", ...
    "Position",initialPosition(),"Color",[0.95 0.97 0.98]);
grid = uigridlayout(app,[13 1]);
grid.RowHeight = {54,40,52,52,52,52,52,52,52,52,52,'1x',34};
grid.Padding = [18 18 18 18]; grid.RowSpacing = 9;

uilabel(grid,"Text","TripLens ECMS VPP 3.1", ...
    "FontSize",24,"FontWeight","bold","HorizontalAlignment","center");
uilabel(grid,"Text","6.9 kV · GT/ST 주 변압기 역수전 · 별도 SST 없음", ...
    "FontSize",13,"HorizontalAlignment","center","FontColor",[0.32 0.42 0.48]);

makeButton("1 · ECMS 배선·A·Command 편집",@(~,~)runAction("편집기",@ECMS_START));
makeButton("2 · 오프라인 결과 계산 (ECMS_RUN)",@(~,~)runAction("오프라인 계산",@ECMS_RUN));
makeButton("3 · 최신 계산 결과 열기",@(~,~)runAction("결과",@ECMS_RESULT));
makeButton("4 · 로컬 OMEdit OPC UA 연결 확인", ...
    @(~,~)runAction("로컬 OPC UA",@()ECMS_LIVE("Check")));
makeButton("5 · 12밸브 실시간 조작·감시",@(~,~)runAction("12밸브",@ECMS_VALVES));
makeButton("6 · 설치·경로 진단",@(~,~)runAction("진단",@ECMS_DIAGNOSE));
makeButton("7 · 12밸브 실시간 트렌드 · 1초",@(~,~)runAction("트렌드",@ECMS_TRENDS));
makeButton("8 · 12밸브 조작 검증·1초 트렌드", ...
    @(~,~)runAction("조작 검증",@ECMS_OPERATOR_PROOF));
makeButton("9 · LP BFP TRIP · Dual Log 분석", ...
    @(~,~)runAction("BFP Dual Log",@ECMS_BFP_ALARMS));

uilabel(grid,"Text",join([ ...
    "12밸브 조작창과 검증창은 같은 OPC UA 서버를 사용합니다."; ...
    "Dual Log = 사건 중심 EVENT.csv + 1초 전체 Historian RAW.csv입니다."],newline), ...
    "HorizontalAlignment","center","FontColor",[0.35 0.43 0.48]);
status = uilabel(grid,"Text","준비됨","HorizontalAlignment","center", ...
    "FontWeight","bold","FontColor",[0.10 0.46 0.33]);

try, app.WindowState = "maximized"; catch, end

    function makeButton(label,callback)
        button = uibutton(grid,"Text",label,"FontSize",16,"FontWeight","bold", ...
            "ButtonPushedFcn",callback);
        button.BackgroundColor = [0.12 0.38 0.62]; button.FontColor = [1 1 1];
    end

    function runAction(label,callback)
        try
            status.Text = label+" 처리 중…"; status.FontColor = [0.80 0.42 0.05];
            drawnow; callback();
            status.Text = label+" 완료"; status.FontColor = [0.10 0.46 0.33];
        catch caught
            status.Text = label+" 실패"; status.FontColor = [0.76 0.16 0.14];
            uialert(app,caught.message,"TripLens "+label+" 오류","Icon","error");
        end
    end
end

function position = initialPosition()
screen = get(groot,"ScreenSize");
screenWidth = max(360,double(screen(3))); screenHeight = max(640,double(screen(4)));
widthValue = min(620,max(340,screenWidth-30));
heightValue = min(790,max(650,screenHeight-50));
position = [max(1,round((screenWidth-widthValue)/2)), ...
    max(1,round((screenHeight-heightValue)/2)),widthValue,heightValue];
end
