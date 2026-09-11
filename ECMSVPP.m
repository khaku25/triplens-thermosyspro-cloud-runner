function app = ECMSVPP()
%ECMSVPP Open the one-touch TripLens ECMS VPP 3.1 control panel.
% This uniquely named entry point avoids collisions with older ECMS folders.

packageRoot = fileparts(mfilename("fullpath"));
addpath(packageRoot,"-begin");
addpath(fullfile(packageRoot,"matlab"),"-begin");
clear ECMS_START ECMS_RUN ECMS_RESULT ECMS_GITHUB ECMS_DIAGNOSE;
rehash;

helperNames = ["ECMS_START","ECMS_RUN","ECMS_RESULT","ECMS_GITHUB","ECMS_DIAGNOSE"];
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
grid = uigridlayout(app,[9 1]);
grid.RowHeight = {54,40,58,58,58,58,58,'1x',34};
grid.Padding = [18 18 18 18];
grid.RowSpacing = 10;

uilabel(grid,"Text","TripLens ECMS VPP 3.1", ...
    "FontSize",24,"FontWeight","bold","HorizontalAlignment","center");
uilabel(grid,"Text","6.9 kV · GT/ST 주 변압기 역수전 · 별도 SST 없음", ...
    "FontSize",13,"HorizontalAlignment","center","FontColor",[0.32 0.42 0.48]);

makeButton("1 · ECMS 배선·A·Command 편집",@(~,~)runAction("편집기",@ECMS_START));
makeButton("2 · 현재 기본값으로 VPP 실행",@(~,~)runAction("실행",@ECMS_RUN));
makeButton("3 · 최신 계산 결과 열기",@(~,~)runAction("결과",@ECMS_RESULT));
makeButton("4 · GitHub OPC UA 물리 실행·가져오기", ...
    @(~,~)runAction("GitHub OPC UA",@ECMS_GITHUB));
makeButton("5 · 설치·경로 진단",@(~,~)runAction("진단",@ECMS_DIAGNOSE));

uilabel(grid,"Text",join([ ...
    "배선을 직접 누른 뒤 직각 경로와 꺾임 좌표를 바꿀 수 있습니다."; ...
    "Run은 로컬 합성 계산, GitHub OPC UA는 실제 ThermoSysPro 3.1 물리 실행입니다."],newline), ...
    "HorizontalAlignment","center","FontColor",[0.35 0.43 0.48]);
status = uilabel(grid,"Text","준비됨","HorizontalAlignment","center", ...
    "FontWeight","bold","FontColor",[0.10 0.46 0.33]);

try
    app.WindowState = "maximized";
catch
end

    function makeButton(label,callback)
        button = uibutton(grid,"Text",label,"FontSize",16,"FontWeight","bold", ...
            "ButtonPushedFcn",callback);
        button.BackgroundColor = [0.12 0.38 0.62];
        button.FontColor = [1 1 1];
    end

    function runAction(label,callback)
        try
            status.Text = label+" 처리 중…";
            status.FontColor = [0.80 0.42 0.05];
            drawnow;
            callback();
            status.Text = label+" 완료";
            status.FontColor = [0.10 0.46 0.33];
        catch caught
            status.Text = label+" 실패";
            status.FontColor = [0.76 0.16 0.14];
            uialert(app,caught.message,"TripLens "+label+" 오류","Icon","error");
        end
    end
end

function position = initialPosition()
screen = get(groot,"ScreenSize");
screenWidth = max(360,double(screen(3)));
screenHeight = max(640,double(screen(4)));
widthValue = min(620,max(340,screenWidth-30));
heightValue = min(720,max(600,screenHeight-50));
position = [max(1,round((screenWidth-widthValue)/2)), ...
    max(1,round((screenHeight-heightValue)/2)),widthValue,heightValue];
end
