function app = ECMS_BFP_ALARMS()
% TRIPLENS_GUI_V8_2_LAYOUT_HOTFIX
%ECMS_BFP_ALARMS Plant-wide alarm/event window with LP BFP demo controls.
% TRIPLENS_DUAL_LOG_V7_SAFE
% TRIPLENS_DUAL_LOG_UI_V7_1_HOTFIX
% TRIPLENS_DUAL_LOG_UI_V7_2_HOTFIX
% TRIPLENS_DUAL_LOG_UI_V7_3_PROGRESS
% TRIPLENS_DUAL_LOG_UI_V7_3_TABLE_CELL_TYPES
% TRIPLENS_PLANT_ALARM_COVERAGE_V7_4_SAFE
% TRIPLENS_PLANT_ALARM_RUNTIME_V7_5_COMPLETE
% TRIPLENS_PLANT_ALARM_RUNTIME_V7_5_1_HEADER_HOTFIX
% TRIPLENS_PROTECTION_DASHBOARD_V8_COMPLETE
% TRIPLENS_PROTECTION_DASHBOARD_V8_1_HEADER_LAYOUT
% TRIPLENS_PROTECTION_DASHBOARD_V8_5_LOGIC_STABLE

repoRoot=fileparts(mfilename("fullpath"));
launcher=fullfile(repoRoot,"scripts","ecms_bfp_alarm_engine.ps1");
resetScript=fullfile(repoRoot,"RESET_TRIPLENS_SIMULATION_V7.ps1");
assert(isfile(launcher),"TripLens:MissingBFPAlarmEngine", ...
    "BFP 알람 수집기가 없습니다: %s",launcher);
assert(isfile(resetScript),"TripLens:MissingRuntimeReset", ...
    "시뮬레이션 초기화 스크립트가 없습니다: %s",resetScript);

old=findall(groot,"Type","figure","Name","TripLens Plant Alarm/Event");
delete(old);
app=uifigure("Name","TripLens Plant Alarm/Event", ...
    "Position",initialPosition(),"Color",[0.95 0.97 0.98]);
root=uigridlayout(app,[6 1]);
% Reserve enough logical pixels for Windows 125-200% display scaling.
% The former 72 px header exactly matched its children and could lose the
% complete second row after MATLAB/Windows DPI rounding.
root.RowHeight={112,210,72,76,'1x',42};
root.Padding=[14 12 14 12]; root.RowSpacing=8;


header=uigridlayout(root,[2 6]);
header.RowHeight={38,48}; header.ColumnWidth={150,'1x',150,135,110,110};
header.Padding=[2 2 2 2]; header.RowSpacing=6; header.ColumnSpacing=8;

titleLabel=uilabel(header,"Text","Plant Protection V8.5 Stable · Dual Log (EVENT + RAW)", ...
    "FontSize",20,"FontWeight","bold");
titleLabel.Layout.Row=1; titleLabel.Layout.Column=[1 6];
uilabel(header,"Text","단일 OPC UA 서버","FontColor",[0.35 0.43 0.48]);
endpointField=uieditfield(header,"text","Value","opc.tcp://127.0.0.1:4841");
resetRuntimeButton=uibutton(header,"Text","시간 0 재시작", ...
    "Tooltip","검증된 서버를 종료하고 모델시간 0초부터 새로 시작", ...
    "ButtonPushedFcn",@resetRuntime);
resumeRuntimeButton=uibutton(header,"Text","시간 진행 재개", ...
    "Tooltip","멈춘 OpenModelica Run 상태를 다시 진행", ...
    "ButtonPushedFcn",@resumeRuntime);
connectButton=uibutton(header,"Text","재연결", ...
    "Tooltip","OPC UA 수집기를 다시 연결","ButtonPushedFcn",@restartMonitor);
stopButton=uibutton(header,"Text","수집 정지", ...
    "Tooltip","EVENT/RAW 실시간 수집 중지","ButtonPushedFcn",@stopMonitorButton);

controlGrid=uigridlayout(root,[1 2]); controlGrid.ColumnWidth={'1x','1x'};
operatorPanel=uipanel(controlGrid,"Title","BFP OPERATOR CONTROLS · 운전자 EVENT 기록", ...
    "FontWeight","bold","ForegroundColor",[0.05 0.42 0.26]);
operatorGrid=uigridlayout(operatorPanel,[3 4]);
operatorGrid.RowHeight={'1x','1x','1x'};
operatorGrid.ColumnWidth={75,'1x',130,120};
uilabel(operatorGrid,"Text","HP FWP","FontWeight","bold");
uilabel(operatorGrid,"Text","PB → HP 보호계전 → VCB-A01", ...
    "FontColor",[0.25 0.35 0.40]);
hpTripButton=uibutton(operatorGrid,"Text","HP TRIP PB","FontWeight","bold", ...
    "BackgroundColor",[0.82 0.20 0.16],"FontColor",[1 1 1], ...
    "ButtonPushedFcn",@(~,~)pumpTrip("HP"));
hpResetButton=uibutton(operatorGrid,"Text","HP RESET/CLOSE", ...
    "ButtonPushedFcn",@(~,~)pumpReset("HP"));
uilabel(operatorGrid,"Text","IP FWP","FontWeight","bold");
uilabel(operatorGrid,"Text","PB → IP 보호계전 → VCB-B01", ...
    "FontColor",[0.25 0.35 0.40]);
ipTripButton=uibutton(operatorGrid,"Text","IP TRIP PB","FontWeight","bold", ...
    "BackgroundColor",[0.82 0.20 0.16],"FontColor",[1 1 1], ...
    "ButtonPushedFcn",@(~,~)pumpTrip("IP"));
ipResetButton=uibutton(operatorGrid,"Text","IP RESET/CLOSE", ...
    "ButtonPushedFcn",@(~,~)pumpReset("IP"));
uilabel(operatorGrid,"Text","LP BFP","FontWeight","bold");
uilabel(operatorGrid,"Text","PB → LP 보호계전 → VCB-A02", ...
    "FontColor",[0.25 0.35 0.40]);
tripButton=uibutton(operatorGrid,"Text","LP TRIP PB","FontWeight","bold", ...
    "BackgroundColor",[0.82 0.20 0.16],"FontColor",[1 1 1], ...
    "ButtonPushedFcn",@(~,~)pumpTrip("LP"));
resetButton=uibutton(operatorGrid,"Text","LP RESET/CLOSE", ...
    "ButtonPushedFcn",@(~,~)pumpReset("LP"));

faultPanel=uipanel(controlGrid,"Title","FAULT INJECTION · 내부 시험용 / AI 입력 제외", ...
    "FontWeight","bold","ForegroundColor",[0.68 0.32 0.02]);
faultGrid=uigridlayout(faultPanel,[1 5]);
faultGrid.RowHeight={42}; faultGrid.Padding=[8 34 8 34];
faultGrid.ColumnWidth={95,80,35,'1x',145};
uilabel(faultGrid,"Text","모델시간 지연","FontWeight","bold");
delayField=uieditfield(faultGrid,"numeric","Value",10,"Limits",[0 3600]);
uilabel(faultGrid,"Text","초");
uilabel(faultGrid,"Text","내부 VCB OPEN 주입", ...
    "FontColor",[0.45 0.38 0.30]);
armButton=uibutton(faultGrid,"Text","내부 Fault 예약","FontWeight","bold", ...
    "ButtonPushedFcn",@armScenario);

cards=uigridlayout(root,[1 7]);
cards.ColumnWidth={'1x','1x','1x','1x','1x','1x','1x'}; cards.ColumnSpacing=6;
connectionCard=makeCard(cards,"OPC UA","연결 중",[0.74 0.43 0.05]);
timeCard=makeCard(cards,"MODEL TIME","- s",[0.23 0.36 0.48]);
drumCard=makeCard(cards,"LP DRUM","- m",[0.23 0.36 0.48]);
gtCard=makeCard(cards,"GT / 52GT","-",[0.23 0.36 0.48]);
stCard=makeCard(cards,"ST / 52ST","-",[0.23 0.36 0.48]);
pumpCard=makeCard(cards,"LP BFP / VCB-A02","-",[0.23 0.36 0.48]);
flowCard=makeCard(cards,"LP FW FLOW","- t/h",[0.23 0.36 0.48]);

pathGrid=uigridlayout(root,[2 5]);
pathGrid.RowHeight={28,28}; pathGrid.ColumnWidth={105,'1x',90,100,110};
eventPathLabel=uilabel(pathGrid,"Text","EVENT.csv","FontWeight","bold");
eventPathLabel.Layout.Row=1; eventPathLabel.Layout.Column=1;
csvField=uieditfield(pathGrid,"text","Editable","off", ...
    "Value",fullfile(repoRoot,"runtime","events","EVENT.csv"));
csvField.Layout.Row=1; csvField.Layout.Column=2;
openCsvButton=uibutton(pathGrid,"Text","EVENT 열기","ButtonPushedFcn",@openCsv);
openCsvButton.Layout.Row=1; openCsvButton.Layout.Column=3;
openFolderButton=uibutton(pathGrid,"Text","폴더 열기","ButtonPushedFcn",@openFolder);
openFolderButton.Layout.Row=[1 2]; openFolderButton.Layout.Column=4;
ackButton=uibutton(pathGrid,"Text","선택 알람 ACK","ButtonPushedFcn",@ackSelected);
ackButton.Layout.Row=[1 2]; ackButton.Layout.Column=5;
rawPathLabel=uilabel(pathGrid,"Text","RAW.csv","FontWeight","bold");
rawPathLabel.Layout.Row=2; rawPathLabel.Layout.Column=1;
rawField=uieditfield(pathGrid,"text","Editable","off", ...
    "Value",fullfile(repoRoot,"runtime","events","RAW.csv"));
rawField.Layout.Row=2; rawField.Layout.Column=2;
openRawButton=uibutton(pathGrid,"Text","RAW 열기","ButtonPushedFcn",@openRaw);
openRawButton.Layout.Row=2; openRawButton.Layout.Column=3;

tabs=uitabgroup(root);
eventTab=uitab(tabs,"Title","EVENT Timeline");
eventGrid=uigridlayout(eventTab,[2 1]);
eventGrid.RowHeight={27,'1x'}; eventGrid.Padding=[4 4 4 4]; eventGrid.RowSpacing=4;
eventSummary=uilabel(eventGrid,"Text","PLANT-WIDE · 현재 세션 EVENT 0건 · 새 사건 대기 중", ...
    "FontWeight","bold","FontColor",[0.35 0.43 0.48]);
alarmTable=uitable(eventGrid,"ColumnName", ...
    {"순번","Model Time","UTC 발생시각","구분","우선순위","설비","Tag","상태","값","메시지","ACK"}, ...
    "RowName",{},"ColumnWidth",{60,90,185,85,80,100,145,85,100,'1x',50}, ...
    "CellSelectionCallback",@selectEvent);

analysisTab=uitab(tabs,"Title","Dual-input Analysis");
analysisGrid=uigridlayout(analysisTab,[2 2]);
analysisGrid.RowHeight={'1x',100}; analysisGrid.ColumnWidth={'1x','1x'};
[eventEvidence,eventEvidencePanel]=makeEvidencePanel(analysisGrid, ...
    "EVENT Evidence · 사고 시작점",[0.05 0.42 0.26]);
eventEvidencePanel.Layout.Row=1; eventEvidencePanel.Layout.Column=1;
[rawEvidence,rawEvidencePanel]=makeEvidencePanel(analysisGrid, ...
    "RAW Evidence · 동작 chain / 공정 응답",[0.12 0.32 0.58]);
rawEvidencePanel.Layout.Row=1; rawEvidencePanel.Layout.Column=2;
combinedPanel=uipanel(analysisGrid,"Title","TripLens Combined Analysis", ...
    "FontWeight","bold","ForegroundColor",[0.42 0.20 0.62]);
combinedPanel.Layout.Row=2; combinedPanel.Layout.Column=[1 2];
combinedLayout=uigridlayout(combinedPanel,[1 1]);
combinedLayout.Padding=[6 6 6 6];
combinedText=uitextarea(combinedLayout,"Editable","off", ...
    "Value","EVENT에서 사고 시작점 식별 → RAW에서 실제 동작 chain과 공정 응답 검증");

protectionTab=uitab(tabs,"Title","Protection Logic");
protectionGrid=uigridlayout(protectionTab,[3 2]);
protectionGrid.RowHeight={30,36,'1x'};
protectionGrid.ColumnWidth={'6x','5x'};
protectionGrid.Padding=[4 4 4 4]; protectionGrid.RowSpacing=4;
protectionSummary=uilabel(protectionGrid, ...
    "Text","PLANT PROTECTION · Cause → Request → Latch → Breaker Command → Position", ...
    "FontWeight","bold","FontColor",[0.35 0.43 0.48]);
protectionSummary.Layout.Row=1; protectionSummary.Layout.Column=[1 2];
protectionFlow=uilabel(protectionGrid, ...
    "Text","Trip Cause → Request → 독립 Latch → Breaker OPEN 명령 → 위치 · HP/IP 물리입력은 V7 보존", ...
    "HorizontalAlignment","center","FontWeight","bold", ...
    "BackgroundColor",[0.90 0.94 0.97],"FontColor",[0.18 0.31 0.42]);
protectionFlow.Layout.Row=2; protectionFlow.Layout.Column=[1 2];
causeTable=uitable(protectionGrid,"ColumnName", ...
    {"영역","Trip Cause","Source / 현재값","상태"},"RowName",{}, ...
    "ColumnWidth",{70,220,'1x',80});
causeTable.Layout.Row=3; causeTable.Layout.Column=1;
chainTable=uitable(protectionGrid,"ColumnName", ...
    {"Train / Breaker","Request","Latch","Breaker Cmd","Breaker Position"}, ...
    "RowName",{},"ColumnWidth",{135,85,85,110,'1x'});
chainTable.Layout.Row=3; chainTable.Layout.Column=2;

historianTab=uitab(tabs,"Title","Live Historian");
historianGrid=uigridlayout(historianTab,[2 1]);
historianGrid.RowHeight={34,'1x'}; historianGrid.Padding=[4 4 4 4];
historianToolbar=uigridlayout(historianGrid,[1 7]);
historianToolbar.ColumnWidth={55,'1x',55,145,105,80,220};
historianToolbar.Padding=[0 0 0 0]; historianToolbar.ColumnSpacing=6;
uilabel(historianToolbar,"Text","검색","FontWeight","bold");
historianSearch=uieditfield(historianToolbar,"text","Placeholder","tag / group", ...
    "ValueChangedFcn",@filterHistorian);
uilabel(historianToolbar,"Text","분류","FontWeight","bold");
historianFilter=uidropdown(historianToolbar, ...
    "Items",["전체","Protection","Breaker","Pump","Valve","Process","Command","Analog","Digital","System","Other"], ...
    "Value","전체","ValueChangedFcn",@filterHistorian);
changedOnly=uicheckbox(historianToolbar,"Text","변경만 보기", ...
    "ValueChangedFcn",@filterHistorian);
refreshHistoryButton=uibutton(historianToolbar,"Text","새로고침", ...
    "ButtonPushedFcn",@filterHistorian);
historianSummary=uilabel(historianToolbar,"Text","Historian 표본 대기", ...
    "HorizontalAlignment","right","FontWeight","bold", ...
    "FontColor",[0.35 0.43 0.48]);
historianTable=uitable(historianGrid,"ColumnName", ...
    {"Tag / BrowseName","분류","값","단위","Quality","변경"}, ...
    "RowName",{},"ColumnWidth",{310,100,130,80,90,60});

coverageTab=uitab(tabs,"Title","Alarm Coverage");
coverageGrid=uigridlayout(coverageTab,[2 1]);
coverageGrid.RowHeight={30,'1x'}; coverageGrid.Padding=[4 4 4 4];
coverageSummary=uilabel(coverageGrid,"Text","알람 레지스트리 연결 확인 중…", ...
    "FontWeight","bold","FontColor",[0.74 0.43 0.05]);
coverageTable=uitable(coverageGrid,"ColumnName", ...
    {"Rule ID","구분","우선순위","설비","Tag","OPC UA Source","연결","현재 상태"}, ...
    "RowName",{},"ColumnWidth",{170,90,80,130,150,235,60,110});

footer=uigridlayout(root,[1 1]);
status=uilabel(footer,"Text","알람 수집기 시작 중…", ...
    "FontWeight","bold","FontColor",[0.74 0.43 0.05]);

workerTimer=[]; workerRunning=false; workerFiles=emptyFiles();
resetTimer=[]; resetRunning=false; resetFiles=emptyResetFiles();
eventRows=struct([]); selectedEventId=""; lastEventCount=-1;
historianRows=struct([]);
historianPrevious=containers.Map('KeyType','char','ValueType','any');
pumpControlSupport=struct("HP",false,"IP",false,"LP",true);
pendingAction=""; pendingStarted=[]; pendingSawBusy=false; lastCommandState="IDLE";
app.CloseRequestFcn=@closeApp;
setScenarioEnabled(false);
try, app.WindowState="maximized"; catch, end
startMonitor();

    function card=makeCard(parent,name,value,color)
        panel=uipanel(parent,"BorderType","line");
        grid=uigridlayout(panel,[2 1]);
        grid.RowHeight={18,'1x'}; grid.RowSpacing=0; grid.Padding=[4 2 4 2];
        uilabel(grid,"Text",name,"HorizontalAlignment","center", ...
            "FontWeight","bold","FontColor",[0.38 0.45 0.50]);
        card=uilabel(grid,"Text",value,"HorizontalAlignment","center", ...
            "FontSize",16,"FontWeight","bold","FontColor",color);
    end

    function restartMonitor(~,~)
        if resetRunning, return; end
        stopWorker(true); startMonitor();
    end

    function startMonitor()
        try
            stopWorker(true); workerFiles=createFiles();
            launchWorker(string(endpointField.Value),workerFiles);
            workerRunning=true; lastEventCount=-1; selectedEventId="";
            historianRows=struct([]);
            historianPrevious=containers.Map('KeyType','char','ValueType','any');
            historianTable.Data=cell(0,6);
            endpointField.Enable="off"; connectButton.Enable="off";
            resetRuntimeButton.Enable="off"; resumeRuntimeButton.Enable="off"; stopButton.Enable="on";
            status.Text="OPC UA 연결 및 첫 표본 대기 중…";
            status.FontColor=[0.74 0.43 0.05];
            workerTimer=timer("ExecutionMode","fixedSpacing","Period",0.25, ...
                "BusyMode","drop","TimerFcn",@pollWorker);
            start(workerTimer);
        catch caught
            stopWorker(true); endpointField.Enable="on"; connectButton.Enable="on";
            resetRuntimeButton.Enable="on"; resumeRuntimeButton.Enable="off";
            status.Text="알람 수집 시작 실패 · "+string(caught.message);
            status.FontColor=[0.76 0.18 0.15];
        end
    end

    function pollWorker(~,~)
        if ~isvalid(app), stopWorker(false); return; end
        try
        if isfile(workerFiles.done)
            code=str2double(strtrim(readOptional(workerFiles.done)));
            detail=strtrim(readOptional(workerFiles.error));
            if strlength(detail)>220, detail=extractBefore(detail,221); end
            stopWorker(true); setScenarioEnabled(false);
            status.Text="알람 수집기 종료(code="+string(code)+") · "+detail;
            status.FontColor=[0.76 0.18 0.15]; return;
        end
        if ~isfile(workerFiles.snapshot), return; end
        try
            snapshot=jsondecode(fileread(workerFiles.snapshot));
        catch
            return
        end
        if isfield(snapshot,"event_csv"), csvField.Value=char(string(snapshot.event_csv)); end
        if isfield(snapshot,"raw_csv"), rawField.Value=char(string(snapshot.raw_csv)); end
        if ~isfield(snapshot,"status") || string(snapshot.status)~="PASS"
            connectionCard.Text="재접속 중"; connectionCard.FontColor=[0.76 0.18 0.15];
            resetRuntimeButton.Enable="on"; resumeRuntimeButton.Enable="off";
            detail=""; if isfield(snapshot,"error"), detail=string(snapshot.error); end
            status.Text="OPC UA 재접속 중 · "+detail;
            status.FontColor=[0.76 0.18 0.15]; setScenarioEnabled(false); return;
        end
        connectionCard.Text="CONNECTED"; connectionCard.FontColor=[0.08 0.48 0.31];
        connectButton.Enable="on"; resetRuntimeButton.Enable="on";
        resumeRuntimeButton.Enable="on";
        updatePumpControlSupport(snapshot); setScenarioEnabled(true);
        modelStalled=false; stalledSeconds=0;
        if isfield(snapshot,"model_time_stalled_s")
            stalledSeconds=double(snapshot.model_time_stalled_s);
            modelStalled=stalledSeconds>=3;
        end
        if isfield(snapshot,"model_time_s")
            timeCard.Text=compose("%.3f s",double(snapshot.model_time_s));
            if modelStalled, timeCard.FontColor=[0.76 0.18 0.15];
            else, timeCard.FontColor=[0.23 0.36 0.48]; end
        end
        updateCards(snapshot);
        commandState="IDLE";
        if isfield(snapshot,"command_state"), commandState=string(snapshot.command_state); end
        commandBusy=false;
        if isfield(snapshot,"command_busy"), commandBusy=logical(snapshot.command_busy); end
        if commandBusy
            pendingSawBusy=true;
            setScenarioEnabled(false);
        end
        if modelStalled, setScenarioEnabled(false); end
        elapsed=0;
        if ~isempty(pendingStarted), elapsed=toc(pendingStarted); end
        if modelStalled
            watchdog="";
            if isfield(snapshot,"watchdog_state"), watchdog=" · watchdog="+string(snapshot.watchdog_state); end
            status.Text="MODEL TIME 정지 · "+compose("%.1f",stalledSeconds)+ ...
                "초간 변화 없음"+watchdog+" · [시간 진행 재개] 또는 [시간 0 재시작]";
            status.FontColor=[0.76 0.18 0.15];
        elseif isfield(snapshot,"trip_at_s") && ~isempty(snapshot.trip_at_s)
            status.Text="LP BFP TRIP 예약 · 모델시간 "+compose("%.3f",double(snapshot.trip_at_s))+" s";
            status.FontColor=[0.74 0.43 0.05];
        elseif commandBusy
            status.Text="BFP 제어 처리 중 · "+pendingAction+" · "+commandState+" · "+compose("%.1f",elapsed)+"초";
            status.FontColor=[0.74 0.43 0.05];
        elseif strlength(pendingAction)>0 && pendingSawBusy && endsWith(commandState,"_PASS")
            status.Text="BFP 제어 및 보호동작 반영 PASS · "+pendingAction+" · "+commandState;
            status.FontColor=[0.08 0.48 0.31];
            pendingAction=""; pendingStarted=[]; pendingSawBusy=false;
        elseif strlength(pendingAction)>0 && pendingSawBusy && endsWith(commandState,"_FAIL")
            status.Text="BFP 제어 실패 · "+pendingAction+" · "+commandState+" · EVENT의 CONTROL_PATH_FAILURE 확인";
            status.FontColor=[0.76 0.18 0.15];
            pendingAction=""; pendingStarted=[]; pendingSawBusy=false;
        elseif strlength(pendingAction)>0 && elapsed>=5
            status.Text="BFP 요청 전송 후 수집기 수신 확인 지연 · "+pendingAction+" · "+ ...
                compose("%.1f",elapsed)+"초 · 재연결을 누르세요";
            status.FontColor=[0.76 0.18 0.15];
        elseif strlength(pendingAction)>0
            status.Text="BFP 요청 파일 전달 중 · "+pendingAction+" · "+compose("%.1f",elapsed)+"초";
            status.FontColor=[0.74 0.43 0.05];
        else
            totalCount=0; sessionCount=0;
            if isfield(snapshot,"event_count_total"), totalCount=double(snapshot.event_count_total); end
            if isfield(snapshot,"event_count_session"), sessionCount=double(snapshot.event_count_session); end
            rawCount=0; tagCount=0;
            if isfield(snapshot,"raw_count_session"), rawCount=double(snapshot.raw_count_session); end
            if isfield(snapshot,"historian_tag_count"), tagCount=double(snapshot.historian_tag_count); end
            boundCount=0; ruleCount=0; activeCount=0;
            if isfield(snapshot,"alarm_bound_count"), boundCount=double(snapshot.alarm_bound_count); end
            if isfield(snapshot,"alarm_rule_count"), ruleCount=double(snapshot.alarm_rule_count); end
            if isfield(snapshot,"alarm_active_count"), activeCount=double(snapshot.alarm_active_count); end
            status.Text="Plant Alarm 감시 중 · 현재 세션 EVENT "+string(sessionCount)+ ...
                "건 · RAW "+string(rawCount)+"행 · 알람 연결 "+string(boundCount)+ ...
                "/"+string(ruleCount)+" · 현재 Active "+string(activeCount)+ ...
                " · Historian "+string(tagCount)+" tags";
            status.FontColor=[0.08 0.48 0.31];
        end
        lastCommandState=commandState;
        updateEvents(snapshot);
        updateAnalysis(snapshot);
        updateProtection(snapshot);
        updateHistorian(snapshot);
        updateCoverage(snapshot);
        catch caught
            status.Text="화면 갱신 오류 · "+string(caught.message);
            status.FontColor=[0.76 0.18 0.15];
        end
    end

    function updateEvents(snapshot)
        sourceField="events";
        if isfield(snapshot,"session_events"), sourceField="session_events"; end
        if ~isfield(snapshot,char(sourceField)) || isempty(snapshot.(char(sourceField)))
            eventRows=struct([]); alarmTable.Data=cell(0,11); lastEventCount=0;
            activeCount=0;
            if isfield(snapshot,"alarm_active_count")
                activeCount=double(snapshot.alarm_active_count);
            end
            eventSummary.Text="PLANT-WIDE · 현재 세션 EVENT 0건 · 새 사건 대기 · 현재 Active "+ ...
                string(activeCount)+"개는 Alarm Coverage에서 확인 · 과거 기록 제외";
            eventSummary.FontColor=[0.35 0.43 0.48];
            return;
        end
        eventRows=snapshot.(char(sourceField));
        if iscell(eventRows), eventRows=[eventRows{:}]; end
        count=numel(eventRows); data=cell(count,11);
        for row=1:count
            item=eventRows(row);
            sequence=firstField(item,{"event_sequence"},row);
            modelTime=firstField(item,{"model_time_s"},[]);
            acknowledged=firstField(item,{"acknowledged"},false);
            [isAck,~]=asLogicalKnown(acknowledged,[]);
            data(row,:)={tableScalar(sequence),fmtTime(modelTime), ...
                char(firstFieldText(item,{"wall_time_utc"},"")), ...
                char(firstFieldText(item,{"event_class"},"")), ...
                char(firstFieldText(item,{"priority"},"")), ...
                char(firstFieldText(item,{"equipment"},"")), ...
                char(firstFieldText(item,{"tag"},"")), ...
                char(firstFieldText(item,{"state"},"")),fmtValue(item), ...
                char(firstFieldText(item,{"message"},"")),pick(isAck,"Y","")};
        end
        alarmTable.Data=sanitizeTableData(data);
        sessionName="";
        if isfield(snapshot,"session_id"), sessionName=string(snapshot.session_id); end
        eventSummary.Text="PLANT-WIDE · 현재 세션 EVENT "+string(count)+"건 · "+sessionName+ ...
            " · 최신: "+firstFieldText(eventRows(end),{"message"},"");
        eventSummary.FontColor=[0.05 0.42 0.26];
        styleTable();
        if count>lastEventCount
            try, scroll(alarmTable,"bottom"); catch, end
        end
        lastEventCount=count;
    end

    function updateCoverage(snapshot)
        if ~isfield(snapshot,"alarm_coverage") || isempty(snapshot.alarm_coverage)
            coverageTable.Data=cell(0,8);
            coverageSummary.Text="알람 레지스트리 연결 확인 중…";
            coverageSummary.FontColor=[0.74 0.43 0.05];
            return
        end
        rows=snapshot.alarm_coverage;
        if iscell(rows), rows=[rows{:}]; end
        data=cell(numel(rows),8);
        boundCount=0; activeCount=0;
        for row=1:numel(rows)
            item=rows(row);
            [bound,~]=asLogicalKnown(firstField(item,{"bound"},false),[]);
            state=char(firstFieldText(item,{"state"},"UNKNOWN"));
            boundCount=boundCount+double(bound);
            activeCount=activeCount+double(strcmp(state,"ACTIVE") || strcmp(state,"ACTIVE_AT_ATTACH"));
            data(row,:)={char(firstFieldText(item,{"rule_id"},"")), ...
                char(firstFieldText(item,{"event_class"},"")), ...
                char(firstFieldText(item,{"priority"},"")), ...
                char(firstFieldText(item,{"equipment"},"")), ...
                char(firstFieldText(item,{"tag"},"")), ...
                char(firstFieldText(item,{"source_node"},"")), ...
                pick(bound,"OK","MISSING"),state};
        end
        coverageTable.Data=sanitizeTableData(data);
        coverageSummary.Text="정의 "+string(numel(rows))+"개 · OPC UA 연결 "+ ...
            string(boundCount)+"개 · 현재 Active "+string(activeCount)+ ...
            "개 · 앱 시작 전 상태는 EVENT로 재발행하지 않음";
        coverageSummary.FontColor=pickColor(boundCount==numel(rows));
    end

    function updateAnalysis(snapshot)
        if ~isfield(snapshot,"analysis") || isempty(snapshot.analysis)
            eventEvidence.Value="EVENT evidence 대기";
            rawEvidence.Value="RAW evidence 대기";
            return
        end
        analysis=snapshot.analysis;
        if isfield(analysis,"event_evidence")
            eventEvidence.Value=toTextLines(analysis.event_evidence,"EVENT evidence 대기");
        end
        if isfield(analysis,"raw_evidence")
            rawEvidence.Value=toTextLines(analysis.raw_evidence,"RAW evidence 대기");
        end
        state="WAITING"; if isfield(analysis,"status"), state=string(analysis.status); end
        conclusion="EVENT에서 사고 시작점 식별 → RAW에서 실제 동작 chain과 공정 응답 검증";
        if isfield(analysis,"conclusion"), conclusion=string(analysis.conclusion);
        elseif isfield(analysis,"message"), conclusion=string(analysis.message); end
        combinedText.Value=["분석 상태: "+state; conclusion];
    end

    function updateCards(snapshot)
        drum=lookupSnapshotNumber(snapshot,{"DRUM_LEVEL_M","vppLPDrumLevelM"});
        if isnan(drum), drumCard.Text="N/A";
        else, drumCard.Text=char(compose("%.3f m",drum)); end

        gtLatch=lookupSnapshotNumber(snapshot,{"GT_TRIP_LATCH","vppGTTripLatchNative","vppGTTripLatch"});
        gtClosed=lookupSnapshotNumber(snapshot,{"GT_BREAKER_CLOSED","vppECMS52GTClosed","vpp52GTClosed"});
        gtCard.Text=trainCardText(gtLatch,gtClosed,"52GT");
        gtCard.FontColor=trainCardColor(gtLatch,gtClosed);

        stLatch=lookupSnapshotNumber(snapshot,{"ST_TRIP_LATCH","vppSTTripLatchPublished", ...
            "vppSTTripLatchNative","vppSTTripLatch"});
        stClosed=lookupSnapshotNumber(snapshot,{"ST_BREAKER_CLOSED","vppECMS52STClosed","vpp52STClosed"});
        stCard.Text=trainCardText(stLatch,stClosed,"52ST");
        stCard.FontColor=trainCardColor(stLatch,stClosed);

        breakerClosed=lookupSnapshotNumber(snapshot,{"BREAKER_CLOSED","vppECMSVCBA02Closed"});
        running=lookupSnapshotNumber(snapshot,{"RUNNING","vppLPFWPRunning"});
        pumpCard.Text=pumpCardText(running,breakerClosed);
        if (~isnan(running) && running<0.5) || (~isnan(breakerClosed) && breakerClosed<0.5)
            pumpCard.FontColor=[0.76 0.18 0.15];
        elseif isnan(running) && isnan(breakerClosed)
            pumpCard.FontColor=[0.35 0.43 0.48];
        else
            pumpCard.FontColor=[0.08 0.48 0.31];
        end
        flow=lookupSnapshotNumber(snapshot,{"MASS_FLOW_TH","vppLPFWPMassFlowTH"});
        if isnan(flow), flowCard.Text="N/A";
        else, flowCard.Text=char(compose("%.3f t/h",flow)); end
    end

    function updatePumpControlSupport(snapshot)
        pumpControlSupport=struct("HP",false,"IP",false,"LP",true);
        fields={"pump_control_trains","operator_control_trains"};
        for fieldIndex=1:numel(fields)
            field=fields{fieldIndex};
            if ~isfield(snapshot,field), continue; end
            raw=snapshot.(field);
            if iscell(raw), names=string(raw(:));
            elseif isstring(raw), names=raw(:);
            elseif ischar(raw), names=string({raw});
            else, names=string.empty; end
            keys=arrayfun(@chainKey,names,"UniformOutput",false);
            pumpControlSupport.HP=any(contains(keys,'HP'));
            pumpControlSupport.IP=any(contains(keys,'IP'));
            pumpControlSupport.LP=any(contains(keys,'LP')) || pumpControlSupport.LP;
            return
        end
        if isfield(snapshot,"operator_controls") && isstruct(snapshot.operator_controls)
            controls=snapshot.operator_controls;
            pumpControlSupport.HP=controlFlag(controls,"HP",pumpControlSupport.HP);
            pumpControlSupport.IP=controlFlag(controls,"IP",pumpControlSupport.IP);
            pumpControlSupport.LP=controlFlag(controls,"LP",pumpControlSupport.LP);
        end
    end

    function updateProtection(snapshot)
        matrixRows=struct([]);
        if isfield(snapshot,"protection_matrix") && ~isempty(snapshot.protection_matrix)
            matrixRows=flattenStructRows(snapshot.protection_matrix);
        end
        if isempty(matrixRows)
            matrixRows=defaultProtectionMatrix(snapshot);
        end
        causeData=cell(numel(matrixRows),4);
        activeCount=0; knownCount=0;
        for index=1:numel(matrixRows)
            item=matrixRows(index);
            domain=firstFieldText(item,{"domain","target","train"},"-");
            cause=firstFieldText(item,{"cause","name","cause_id"},"-");
            source=firstFieldText(item,{"source","source_node","tag"},"-");
            rawValue=firstField(item,{"value","current_value"},[]);
            activeRaw=firstField(item,{"active","asserted","state"},[]);
            [active,known]=asLogicalKnown(activeRaw,rawValue);
            activeCount=activeCount+double(active && known);
            knownCount=knownCount+double(known);
            causeData(index,:)={char(domain),char(cause), ...
                char(source+" = "+displayScalar(rawValue)),stateText(active,known)};
        end
        causeTable.Data=sanitizeTableData(causeData);
        styleBooleanRows(causeTable,causeData,4);

        chainRows=normalizeProtectionChain(snapshot);
        chainData=cell(numel(chainRows),5);
        for index=1:numel(chainRows)
            item=chainRows(index);
            train=firstFieldText(item,{"train","domain","name"},"-");
            request=firstField(item,{"request","trip_request","request_value"},[]);
            latch=firstField(item,{"latch","trip_latch","latch_value"},[]);
            command=firstField(item,{"breaker_command","trip_command","open_command"},[]);
            closed=firstField(item,{"breaker_closed","closed","position"},[]);
            chainData(index,:)={char(train),onOffText(request),onOffText(latch), ...
                commandText(command),breakerText(closed)};
        end
        chainTable.Data=sanitizeTableData(chainData);
        styleChainRows(chainTable,chainRows);
        if knownCount==0
            protectionSummary.Text="PLANT PROTECTION · 보호 로직 스냅샷 대기 (노드 누락은 N/A 표시)";
            protectionSummary.FontColor=[0.74 0.43 0.05];
        else
            protectionSummary.Text="PLANT PROTECTION · 원인 "+string(numel(matrixRows))+ ...
                "개 중 Active "+string(activeCount)+"개 · V8.5 LOGIC STABLE / HP·IP 물리 V7 보존";
            protectionSummary.FontColor=[0.05 0.42 0.26];
        end
    end

    function updateHistorian(snapshot)
        if ~isfield(snapshot,"historian_rows") || isempty(snapshot.historian_rows)
            historianRows=struct([]);
            historianTable.Data=cell(0,6);
            historianSummary.Text="Historian 스냅샷 대기";
            return
        end
        incoming=flattenStructRows(snapshot.historian_rows);
        template=struct("name",'',"group",'',"kind",'',"value",[], ...
            "unit",'',"quality",'',"changed",false);
        normalized=repmat(template,numel(incoming),1);
        for index=1:numel(incoming)
            item=incoming(index);
            name=char(firstFieldText(item,{"name","tag","browse_name","source_node"},"-"));
            group=char(firstFieldText(item,{"group","category"},""));
            kind=char(firstFieldText(item,{"kind","type"},""));
            rawValue=firstField(item,{"value","current_value"},[]);
            changedRaw=firstField(item,{"changed"},[]);
            if isempty(changedRaw)
                changed=isKey(historianPrevious,name) && valuesDiffer(historianPrevious(name),rawValue);
            else
                [changed,~]=asLogicalKnown(changedRaw,[]);
            end
            normalized(index)=struct("name",name,"group",group,"kind",kind, ...
                "value",rawValue,"unit",char(firstFieldText(item,{"unit"},"")), ...
                "quality",char(firstFieldText(item,{"quality"},"GOOD")),"changed",logical(changed));
            historianPrevious(name)=rawValue;
        end
        historianRows=normalized;
        filterHistorian();
    end

    function filterHistorian(varargin) %#ok<INUSD>
        if isempty(historianRows)
            historianTable.Data=cell(0,6); historianSummary.Text="Historian 스냅샷 대기"; return
        end
        query=lower(strtrim(char(string(historianSearch.Value))));
        selected=char(string(historianFilter.Value));
        visible=false(numel(historianRows),1);
        for index=1:numel(historianRows)
            item=historianRows(index);
            category=historianCategory(item);
            textMatch=isempty(query) || contains(lower([item.name ' ' item.group ' ' item.kind]),query);
            groupMatch=strcmp(selected,"전체") || strcmpi(category,selected) || ...
                strcmpi(item.group,selected) || strcmpi(item.kind,selected);
            changedMatch=~logical(changedOnly.Value) || logical(item.changed);
            visible(index)=textMatch && groupMatch && changedMatch;
        end
        indices=find(visible); data=cell(numel(indices),6);
        for row=1:numel(indices)
            item=historianRows(indices(row));
            data(row,:)={item.name,historianCategory(item),tableScalar(item.value), ...
                item.unit,item.quality,pick(item.changed,"Y","")};
        end
        historianTable.Data=sanitizeTableData(data);
        try
            removeStyle(historianTable);
            for row=1:numel(indices)
                if historianRows(indices(row)).changed
                    addStyle(historianTable,uistyle("BackgroundColor",[1.00 0.94 0.70], ...
                        "FontWeight","bold"),"row",row);
                end
            end
        catch
        end
        changedCount=sum([historianRows.changed]);
        historianSummary.Text="표시 "+string(numel(indices))+" / 전체 "+ ...
            string(numel(historianRows))+" · 최근 변경 "+string(changedCount);
    end

    function styleTable()
        try
            removeStyle(alarmTable);
            for row=1:numel(eventRows)
                priority=upper(firstFieldText(eventRows(row),{"priority"},""));
                state=upper(firstFieldText(eventRows(row),{"state"},""));
                if priority=="CRITICAL"
                    style=uistyle("BackgroundColor",[0.72 0.08 0.08],"FontColor",[1 1 1],"FontWeight","bold");
                elseif priority=="HIGH" && state=="ACTIVE"
                    style=uistyle("BackgroundColor",[1.00 0.78 0.76],"FontColor",[0.55 0.05 0.04],"FontWeight","bold");
                elseif state=="RETURN"
                    style=uistyle("BackgroundColor",[0.82 0.94 0.84],"FontColor",[0.08 0.40 0.20]);
                elseif state=="ACK"
                    style=uistyle("BackgroundColor",[0.86 0.90 0.94],"FontColor",[0.28 0.34 0.40]);
                else
                    continue
                end
                addStyle(alarmTable,style,"row",row);
            end
        catch
        end
    end

    function selectEvent(~,event)
        selectedEventId="";
        if isempty(event.Indices), return; end
        row=event.Indices(1,1);
        if row>=1 && row<=numel(eventRows)
            selectedEventId=firstFieldText(eventRows(row),{"event_id"},"");
        end
    end

    function resumeRuntime(~,~)
        try
            sendControl(struct("action","RESUME_RUNTIME"));
            status.Text="OpenModelica Run 재개 요청 전송 · 모델시간 변화 확인 중";
            status.FontColor=[0.74 0.43 0.05];
            resumeRuntimeButton.Enable="off";
        catch caught
            resumeRuntimeButton.Enable="on";
            uialert(app,string(caught.message),"시간 진행 재개 실패");
        end
    end

    function resetRuntime(~,~)
        if resetRunning, return; end
        choice=uiconfirm(app, ...
            "현재 시뮬레이션 궤적을 끝내고 검증된 OPC UA 서버를 모델시간 0초부터 다시 시작합니다."+newline+ ...
            "기존 EVENT.csv와 RAW.csv는 삭제하지 않습니다.", ...
            "시뮬레이션 시간 초기화", ...
            "Options",["시간 0 재시작","취소"],"DefaultOption",2,"CancelOption",2);
        if string(choice)~="시간 0 재시작", return; end
        try
            stopWorker(true);
            resetFiles=createResetFiles();
            launchRuntimeReset(resetFiles);
            resetRunning=true;
            resetRuntimeButton.Enable="off"; resumeRuntimeButton.Enable="off"; connectButton.Enable="off";
            stopButton.Enable="off"; endpointField.Enable="off";
            setScenarioEnabled(false);
            connectionCard.Text="RESTARTING"; connectionCard.FontColor=[0.74 0.43 0.05];
            timeCard.Text="RESETTING"; timeCard.FontColor=[0.74 0.43 0.05];
            eventSummary.Text="새 실행 세션 준비 중 · 기존 EVENT/RAW 기록 보존";
            status.Text="검증된 OPC UA 서버 종료 후 모델시간 0초로 재시작 중…";
            status.FontColor=[0.74 0.43 0.05];
            resetTimer=timer("ExecutionMode","fixedSpacing","Period",0.5, ...
                "BusyMode","drop","TimerFcn",@pollRuntimeReset);
            start(resetTimer);
        catch caught
            resetRunning=false; resetRuntimeButton.Enable="on"; resumeRuntimeButton.Enable="off";
            connectButton.Enable="on"; stopButton.Enable="on"; endpointField.Enable="on";
            status.Text="시간 초기화 시작 실패 · "+string(caught.message);
            status.FontColor=[0.76 0.18 0.15];
        end
    end

    function launchRuntimeReset(files)
        values=[string(resetScript),string(repoRoot),files.done,files.error];
        assert(~any(contains(values,'"')),"TripLens:UnsafeResetArgument", ...
            "초기화 실행 인수에 큰따옴표를 사용할 수 없습니다.");
        shell="start """" /B powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "+ ...
            quoteShell(values(1))+" -RepoRoot "+quoteShell(values(2))+ ...
            " -DoneFile "+quoteShell(values(3))+" -ErrorFile "+quoteShell(values(4));
        code=system(shell);
        assert(code==0,"TripLens:RuntimeResetLaunchFailed", ...
            "시간 초기화 프로세스를 시작하지 못했습니다(code=%d).",code);
    end

    function pollRuntimeReset(~,~)
        if ~isvalid(app), stopResetTimer(); return; end
        if ~isfile(resetFiles.done), return; end
        code=str2double(strtrim(readOptional(resetFiles.done)));
        detail=strtrim(readOptional(resetFiles.error));
        stopResetTimer(); resetRunning=false; stopButton.Enable="on";
        if code==0
            status.Text="모델시간 0초 재시작 PASS · 새 EVENT/RAW 수집 세션 연결 중…";
            status.FontColor=[0.08 0.48 0.31];
            startMonitor();
        else
            resetRuntimeButton.Enable="on"; resumeRuntimeButton.Enable="off"; connectButton.Enable="on";
            endpointField.Enable="on"; setScenarioEnabled(false);
            if strlength(detail)>260, detail=extractBefore(detail,261); end
            status.Text="시간 초기화 실패 · "+detail;
            status.FontColor=[0.76 0.18 0.15];
            uialert(app,detail,"TripLens 시간 초기화 실패");
        end
    end

    function stopResetTimer()
        if ~isempty(resetTimer) && isvalid(resetTimer)
            stop(resetTimer); delete(resetTimer);
        end
        resetTimer=[];
    end

    function armScenario(~,~)
        sendControl(struct("action","ARM","delay_s",double(delayField.Value)));
        status.Text="내부 Fault Injection 예약 · AI용 EVENT/RAW에는 원인 메타데이터 제외";
        status.FontColor=[0.74 0.43 0.05];
    end

    function pumpTrip(train)
        try
            train=upper(string(train));
            assert(isfield(pumpControlSupport,char(train)) && pumpControlSupport.(char(train)), ...
                "TripLens:PumpControlUnavailable",train+" FWP 운전자 PB가 현재 엔진에서 지원되지 않습니다.");
            pendingAction=train+"_OPERATOR_TRIP"; pendingStarted=tic; pendingSawBusy=false;
            sendControl(struct("action","PUMP_TRIP","train",train));
            status.Text="운전자 "+train+" FWP TRIP PB 요청 전송 · 수집기 수신 대기";
            status.FontColor=[0.74 0.43 0.05];
        catch caught
            pendingAction=""; pendingStarted=[]; pendingSawBusy=false;
            uialert(app,string(caught.message),"BFP TRIP 요청 실패");
        end
    end

    function pumpReset(train)
        try
            train=upper(string(train));
            assert(isfield(pumpControlSupport,char(train)) && pumpControlSupport.(char(train)), ...
                "TripLens:PumpControlUnavailable",train+" FWP 운전자 RESET이 현재 엔진에서 지원되지 않습니다.");
            pendingAction=train+"_RESET"; pendingStarted=tic; pendingSawBusy=false;
            sendControl(struct("action","PUMP_RESET","train",train));
            status.Text=train+" FWP RESET/CLOSE 요청 전송"; status.FontColor=[0.74 0.43 0.05];
        catch caught
            pendingAction=""; pendingStarted=[]; pendingSawBusy=false;
            uialert(app,string(caught.message),"BFP RESET 요청 실패");
        end
    end

    function ackSelected(~,~)
        if strlength(selectedEventId)==0
            uialert(app,"먼저 알람 표에서 한 행을 선택하세요.","ACK 대상 없음"); return;
        end
        sendControl(struct("action","ACK","event_id",selectedEventId));
    end

    function sendControl(command)
        assert(workerRunning,"TripLens:BFPAlarmNotRunning","알람 수집기가 실행 중이 아닙니다.");
        temporary=workerFiles.control+".tmp";
        writelines(string(jsonencode(command)),temporary);
        movefile(temporary,workerFiles.control,"f");
    end

    function openCsv(~,~)
        pathValue=string(csvField.Value);
        if isfile(pathValue), winopen(char(pathValue));
        else, uialert(app,"아직 EVENT.csv가 생성되지 않았습니다.","파일 없음"); end
    end

    function openRaw(~,~)
        pathValue=string(rawField.Value);
        if isfile(pathValue), winopen(char(pathValue));
        else, uialert(app,"아직 RAW.csv가 생성되지 않았습니다.","파일 없음"); end
    end

    function openFolder(~,~)
        folder=fileparts(string(csvField.Value));
        if isfolder(folder), winopen(char(folder));
        else, uialert(app,"Dual Log 출력 폴더가 아직 없습니다.","폴더 없음"); end
    end

    function stopMonitorButton(~,~)
        stopWorker(true); setScenarioEnabled(false);
        resumeRuntimeButton.Enable="off";
        status.Text="알람 수집 정지 · OpenModelica 서버는 계속 실행 중";
        status.FontColor=[0.35 0.43 0.48];
    end

    function launchWorker(endpoint,files)
        values=[string(launcher),string(repoRoot),endpoint,files.snapshot, ...
            files.control,files.done,files.error];
        assert(~any(contains(values,'"')),"TripLens:UnsafeBFPArgument", ...
            "실행 인수에 큰따옴표를 사용할 수 없습니다.");
        shell="start """" /B powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "+ ...
            quoteShell(values(1))+" -RepoRoot "+quoteShell(values(2))+ ...
            " -Endpoint "+quoteShell(values(3))+" -SnapshotFile "+quoteShell(values(4))+ ...
            " -ControlFile "+quoteShell(values(5))+" -DoneFile "+quoteShell(values(6))+ ...
            " -ErrorFile "+quoteShell(values(7));
        code=system(shell);
        assert(code==0,"TripLens:BFPAlarmLaunchFailed", ...
            "BFP 알람 수집기를 시작하지 못했습니다(code=%d).",code);
    end

    function stopWorker(waitForExit)
        if ~isempty(workerTimer) && isvalid(workerTimer), stop(workerTimer); delete(workerTimer); end
        workerTimer=[]; files=workerFiles; wasRunning=workerRunning;
        if wasRunning && strlength(string(files.control))>0
            try
                writelines(string(jsonencode(struct("action","STOP"))),files.control);
            catch
            end
            if waitForExit
                deadline=tic;
                while toc(deadline)<3 && ~isfile(files.done), pause(0.05); end
            end
        end
        workerRunning=false; workerFiles=emptyFiles();
        endpointField.Enable="on"; connectButton.Enable="on";
        resumeRuntimeButton.Enable="off";
    end

    function setScenarioEnabled(enabled)
        state="off"; if enabled, state="on"; end
        delayField.Enable=state; armButton.Enable=state; ackButton.Enable=state;
        tripButton.Enable=enabledState(enabled && pumpControlSupport.LP);
        resetButton.Enable=enabledState(enabled && pumpControlSupport.LP);
        hpTripButton.Enable=enabledState(enabled && pumpControlSupport.HP);
        hpResetButton.Enable=enabledState(enabled && pumpControlSupport.HP);
        ipTripButton.Enable=enabledState(enabled && pumpControlSupport.IP);
        ipResetButton.Enable=enabledState(enabled && pumpControlSupport.IP);
        hpTripButton.Tooltip=controlTooltip("HP",pumpControlSupport.HP);
        hpResetButton.Tooltip=hpTripButton.Tooltip;
        ipTripButton.Tooltip=controlTooltip("IP",pumpControlSupport.IP);
        ipResetButton.Tooltip=ipTripButton.Tooltip;
    end

    function closeApp(~,~)
        stopResetTimer();
        stopWorker(true); delete(app);
    end
end

function files=createFiles()
token=string(tempname);
files=struct("snapshot",token+".bfp-alarm.json","control",token+".bfp-control.json", ...
    "done",token+".done.txt","error",token+".stderr.txt");
end

function files=emptyFiles()
files=struct("snapshot","","control","","done","","error","");
end

function files=createResetFiles()
token=string(tempname);
files=struct("done",token+".runtime-reset.done.txt", ...
    "error",token+".runtime-reset.stderr.txt");
end

function files=emptyResetFiles()
files=struct("done","","error","");
end

function value=quoteShell(value)
value=""""+string(value)+"""";
end

function value=readOptional(pathValue)
if isfile(pathValue), value=string(fileread(pathValue)); else, value=""; end
end

function value=fmtTime(raw)
number=scalarNumber(raw,NaN);
if isnan(number), value=''; else, value=char(compose("%.3f s",number)); end
end

function value=fmtValue(item)
number=firstField(item,{"value"},[]);
unit=firstFieldText(item,{"unit"},"");
if isnumeric(number) && isscalar(number)
    value=char(strtrim(compose("%.6g %s",double(number),unit)));
else
    value=char(strtrim(displayScalar(number)+" "+unit));
end
end

function value=pick(condition,yesValue,noValue)
if condition, value=char(string(yesValue)); else, value=char(string(noValue)); end
end

function color=pickColor(normal)
if normal, color=[0.08 0.48 0.31]; else, color=[0.76 0.18 0.15]; end
end

function position=initialPosition()
screen=get(groot,"ScreenSize");
widthValue=min(1550,max(1050,double(screen(3))-40));
heightValue=min(920,max(720,double(screen(4))-70));
position=[max(1,round((double(screen(3))-widthValue)/2)), ...
    max(1,round((double(screen(4))-heightValue)/2)),widthValue,heightValue];
end

function [field,panel]=makeEvidencePanel(parent,titleValue,color)
panel=uipanel(parent,"Title",titleValue,"FontWeight","bold", ...
    "ForegroundColor",color);
layout=uigridlayout(panel,[1 1]);
layout.Padding=[6 6 6 6];
field=uitextarea(layout,"Editable","off","Value","증거 수집 대기");
end

function lines=toTextLines(raw,fallback)
if isempty(raw), lines=string(fallback); return; end
if iscell(raw)
    lines=string(raw(:));
elseif isstring(raw)
    lines=raw(:);
elseif ischar(raw)
    lines=string(raw);
else
    lines=string(raw(:));
end
end

function result=flattenStructRows(raw)
if isempty(raw), result=struct([]); return; end
if isstruct(raw) && isscalar(raw) && isfield(raw,"rows")
    result=flattenStructRows(raw.rows); return
end
if iscell(raw)
    try, result=[raw{:}]; catch, result=struct([]); end
elseif isstruct(raw)
    result=raw(:);
else
    result=struct([]);
end
end

function raw=firstField(item,names,fallback)
raw=fallback;
if ~isstruct(item), return; end
for index=1:numel(names)
    name=char(string(names{index}));
    if isfield(item,name)
        candidate=item.(name);
        if ~isempty(candidate), raw=candidate; return; end
    end
end
end

function value=firstFieldText(item,names,fallback)
raw=firstField(item,names,fallback);
try
    converted=string(raw);
    if isempty(converted), value=string(fallback);
    else, value=converted(1); end
catch
    value=string(fallback);
end
end

function value=scalarNumber(raw,fallback)
value=fallback;
try
    if islogical(raw) || isnumeric(raw)
        if isscalar(raw), value=double(raw); end
    elseif ischar(raw) || (isstring(raw) && isscalar(raw))
        parsed=str2double(string(raw));
        if ~isnan(parsed), value=double(parsed); end
    end
catch
end
end

function value=lookupSnapshotNumber(snapshot,names)
value=NaN;
containers={};
if isstruct(snapshot) && isfield(snapshot,"values"), containers{end+1}=snapshot.values; end %#ok<AGROW>
if isstruct(snapshot) && isfield(snapshot,"protection_values"), containers{end+1}=snapshot.protection_values; end %#ok<AGROW>
containers{end+1}=snapshot;
for outer=1:numel(containers)
    item=containers{outer};
    if ~isstruct(item), continue; end
    for index=1:numel(names)
        name=char(string(names{index}));
        if isfield(item,name)
            value=scalarNumber(item.(name),NaN);
            if ~isnan(value), return; end
        end
    end
end
if ~isstruct(snapshot) || ~isfield(snapshot,"historian_rows"), return; end
rows=flattenStructRows(snapshot.historian_rows);
for row=1:numel(rows)
    rowName=firstFieldText(rows(row),{"name","tag","browse_name","source_node"},"");
    if any(strcmpi(rowName,string(names)))
        value=scalarNumber(firstField(rows(row),{"value","current_value"},[]),NaN);
        return
    end
end
end

function value=trainCardText(latch,closed,breakerName)
if isnan(latch), tripText="N/A";
elseif latch>=0.5, tripText="TRIPPED";
else, tripText="NORMAL"; end
if isnan(closed), breakerState="N/A";
elseif closed>=0.5, breakerState="CLOSED";
else, breakerState="OPEN"; end
value=char(tripText+" · "+string(breakerName)+" "+breakerState);
end

function color=trainCardColor(latch,closed)
if isnan(latch) && isnan(closed), color=[0.35 0.43 0.48];
elseif (~isnan(latch) && latch>=0.5) || (~isnan(closed) && closed<0.5)
    color=[0.76 0.18 0.15];
else, color=[0.08 0.48 0.31]; end
end

function value=pumpCardText(running,closed)
if isnan(running), runningText="N/A";
elseif running>=0.5, runningText="RUNNING";
else, runningText="TRIPPED"; end
if isnan(closed), breakerTextValue="N/A";
elseif closed>=0.5, breakerTextValue="VCB CLOSED";
else, breakerTextValue="VCB OPEN"; end
value=char(runningText+" · "+breakerTextValue);
end

function rows=defaultProtectionMatrix(snapshot)
spec={ ...
    'GT','DIRECT_GT_TRIP','vppGTTripPushbuttonNative',{"DIRECT_GT_TRIP","vppGTTripPushbuttonNative","vppExternalTripCommandNative"}; ...
    'GT+ST','GT_BREAKER_OPEN_RUNNING','vppGTBreakerOpenWhileRunning',{"GT_BREAKER_OPEN_RUNNING","vppGTBreakerOpenWhileRunning"}; ...
    'ST','DIRECT_ST_TRIP','vppSTTripPushbuttonNative',{"DIRECT_ST_TRIP","vppSTTripPushbuttonNative","vppExternalSTTripCommandNative"}; ...
    'ST','HP_DRUM_HH','vppHPDrumLevelHH',{"HP_DRUM_HH","vppHPDrumLevelHH"}; ...
    'GT+ST','HP_DRUM_LL','vppHPDrumLevelLL',{"HP_DRUM_LL","vppHPDrumLevelLL"}; ...
    'ST','IP_DRUM_HH','vppIPDrumLevelHH',{"IP_DRUM_HH","vppIPDrumLevelHH"}; ...
    'GT+ST','IP_DRUM_LL','vppIPDrumLevelLL',{"IP_DRUM_LL","vppIPDrumLevelLL"}; ...
    'ST','LP_DRUM_HH','vppLPDrumLevelHH',{"LP_DRUM_HH","vppLPDrumLevelHH"}; ...
    'GT+ST','LP_DRUM_LL','vppLPDrumLevelLL',{"LP_DRUM_LL","vppLPDrumLevelLL"}};
rows=repmat(struct("domain",'',"cause",'',"source",'',"value",[],"active",[]),size(spec,1),1);
for index=1:size(spec,1)
    number=lookupSnapshotNumber(snapshot,spec{index,4});
    if isnan(number), raw=[]; active=[]; else, raw=number; active=number>=0.5; end
    rows(index)=struct("domain",spec{index,1},"cause",spec{index,2}, ...
        "source",spec{index,3},"value",raw,"active",active);
end
end

function rows=normalizeProtectionChain(snapshot)
raw=[];
if isstruct(snapshot) && isfield(snapshot,"protection_chain"), raw=snapshot.protection_chain; end
incoming=flattenStructRows(raw);
if isstruct(raw) && isscalar(raw) && (isfield(raw,"GT") || isfield(raw,"ST"))
    incoming=struct([]);
    names={"GT","ST","HP_FWP","IP_FWP"};
    for index=1:numel(names)
        field=char(names{index});
        if ~isfield(raw,field) || ~isstruct(raw.(field)), continue; end
        item=raw.(field); item.train=field;
        if isempty(incoming), incoming=item; else, incoming(end+1)=item; end %#ok<AGROW>
    end
end
rows=repmat(struct("train",'',"request",[],"latch",[], ...
    "breaker_command",[],"breaker_closed",[]),4,1);
rows(1)=selectOrDefaultChain(incoming,snapshot,'GT / 52GT',{'GT'}, ...
    {"GT_TRIP_REQUEST","vppGTTripRequest","vppGTTripRequestNative"}, ...
    {"GT_TRIP_LATCH","vppGTTripLatchNative","vppGTTripLatch"}, ...
    {"GT_BREAKER_TRIP_CMD","vpp52GTTripCmd","vpp52GTTripCommandNative"}, ...
    {"GT_BREAKER_CLOSED","vppECMS52GTClosed","vpp52GTClosed"});
rows(2)=selectOrDefaultChain(incoming,snapshot,'ST / 52ST',{'ST'}, ...
    {"ST_TRIP_REQUEST","vppSTTripRequest","vppSTTripRequestNative"}, ...
    {"ST_TRIP_LATCH","vppSTTripLatchPublished","vppSTTripLatchNative","vppSTTripLatch"}, ...
    {"ST_BREAKER_TRIP_CMD","vpp52STTripCmd","vpp52STTripCommandNative"}, ...
    {"ST_BREAKER_CLOSED","vppECMS52STClosed","vpp52STClosed"});
rows(3)=selectOrDefaultChain(incoming,snapshot,'HP FWP / VCB-A01', ...
    {'HPFWP','HPBFP','HP FWP','VCBA01'}, ...
    {"HP_FWP_TRIP_REQUEST","vppHPFWPTripRequest","vppHPFWPTripCommandNative","vppHPFWPTripCmd"}, ...
    {"HP_FWP_TRIP_LATCH","vppHPFWPTripLatch","vppHPFWPTripLatchNative"}, ...
    {"VCB_A01_TRIP_CMD","vppVCBA01TripCommandNative","vppVCBA01TripCmd"}, ...
    {"VCB_A01_CLOSED","vppECMSVCBA01Closed","vppVCBA01Closed"});
rows(4)=selectOrDefaultChain(incoming,snapshot,'IP FWP / VCB-B01', ...
    {'IPFWP','IPBFP','IP FWP','VCBB01'}, ...
    {"IP_FWP_TRIP_REQUEST","vppIPFWPTripRequest","vppIPFWPTripCommandNative","vppIPFWPTripCmd"}, ...
    {"IP_FWP_TRIP_LATCH","vppIPFWPTripLatch","vppIPFWPTripLatchNative"}, ...
    {"VCB_B01_TRIP_CMD","vppVCBB01TripCommandNative","vppVCBB01TripCmd"}, ...
    {"VCB_B01_CLOSED","vppECMSVCBB01Closed","vppVCBB01Closed"});
end

function row=selectOrDefaultChain(incoming,snapshot,label,aliases,requestNames,latchNames,commandNames,closedNames)
matched=[];
for index=1:numel(incoming)
    name=firstFieldText(incoming(index),{"train","domain","name"},"");
    key=chainKey(name);
    if any(cellfun(@(candidate) contains(key,chainKey(candidate)),aliases))
        matched=incoming(index); break
    end
end
if isempty(matched)
    row=makeDefaultChain(snapshot,label,requestNames,latchNames,commandNames,closedNames);
else
    row=struct("train",label, ...
        "request",firstField(matched,{"request","trip_request","request_value"},[]), ...
        "latch",firstField(matched,{"latch","trip_latch","latch_value"},[]), ...
        "breaker_command",firstField(matched,{"breaker_command","trip_command","open_command"},[]), ...
        "breaker_closed",firstField(matched,{"breaker_closed","closed","position"},[]));
end
end

function value=chainKey(raw)
value=regexprep(upper(char(string(raw))),'[^A-Z0-9]','');
end

function value=controlFlag(controls,train,fallback)
value=fallback;
if ~isstruct(controls), return; end
names={char(train),lower(char(train)),char(string(train)+"_FWP")};
for index=1:numel(names)
    if ~isfield(controls,names{index}), continue; end
    raw=controls.(names{index});
    if isstruct(raw), raw=firstField(raw,{"supported","enabled","available"},[]); end
    [flag,known]=asLogicalKnown(raw,[]);
    if known, value=flag; return; end
end
end

function value=enabledState(enabled)
if enabled, value='on'; else, value='off'; end
end

function value=controlTooltip(train,supported)
if supported
    value=char(string(train)+" FWP 실제 운전자 PB · EVENT 기록");
else
    value=char(string(train)+" FWP 제어 API/OPC UA 입력을 확인 중입니다.");
end
end

function row=makeDefaultChain(snapshot,train,requestNames,latchNames,commandNames,closedNames)
row=struct("train",train,"request",numberOrEmpty(lookupSnapshotNumber(snapshot,requestNames)), ...
    "latch",numberOrEmpty(lookupSnapshotNumber(snapshot,latchNames)), ...
    "breaker_command",numberOrEmpty(lookupSnapshotNumber(snapshot,commandNames)), ...
    "breaker_closed",numberOrEmpty(lookupSnapshotNumber(snapshot,closedNames)));
end

function value=numberOrEmpty(number)
if isnan(number), value=[]; else, value=number; end
end

function [value,known]=asLogicalKnown(raw,fallbackRaw)
if isempty(raw), raw=fallbackRaw; end
known=~isempty(raw); value=false;
if ~known, return; end
if islogical(raw) || isnumeric(raw)
    if isscalar(raw), value=double(raw)>=0.5; else, known=false; end
    return
end
text=upper(strtrim(char(string(raw))));
if any(strcmp(text,{"ACTIVE","ASSERTED","ON","TRUE","TRIPPED","OPEN","1"})), value=true;
elseif any(strcmp(text,{"NORMAL","RETURN","OFF","FALSE","CLOSED","0"})), value=false;
else
    parsed=str2double(text);
    if isnan(parsed), known=false; else, value=parsed>=0.5; end
end
end

function value=stateText(active,known)
if ~known, value='N/A'; elseif active, value='ACTIVE'; else, value='NORMAL'; end
end

function value=onOffText(raw)
[active,known]=asLogicalKnown(raw,[]);
if ~known, value='N/A'; elseif active, value='ON'; else, value='OFF'; end
end

function value=commandText(raw)
[active,known]=asLogicalKnown(raw,[]);
if ~known, value='N/A'; elseif active, value='TRIP/OPEN'; else, value='NORMAL'; end
end

function value=breakerText(raw)
[closed,known]=asLogicalKnown(raw,[]);
if ~known, value='N/A'; elseif closed, value='CLOSED'; else, value='OPEN'; end
end

function styleBooleanRows(tableHandle,data,stateColumn)
try
    removeStyle(tableHandle);
    for row=1:size(data,1)
        if strcmp(data{row,stateColumn},'ACTIVE')
            addStyle(tableHandle,uistyle("BackgroundColor",[1.00 0.78 0.76], ...
                "FontColor",[0.55 0.05 0.04],"FontWeight","bold"),"row",row);
        elseif strcmp(data{row,stateColumn},'N/A')
            addStyle(tableHandle,uistyle("FontColor",[0.48 0.50 0.52]),"row",row);
        end
    end
catch
end
end

function styleChainRows(tableHandle,rows)
try
    removeStyle(tableHandle);
    for row=1:numel(rows)
        [latched,latchKnown]=asLogicalKnown(firstField(rows(row),{"latch","trip_latch","latch_value"},[]),[]);
        [closed,closedKnown]=asLogicalKnown(firstField(rows(row),{"breaker_closed","closed","position"},[]),[]);
        if (latchKnown && latched) || (closedKnown && ~closed)
            addStyle(tableHandle,uistyle("BackgroundColor",[1.00 0.78 0.76], ...
                "FontColor",[0.55 0.05 0.04],"FontWeight","bold"),"row",row);
        end
    end
catch
end
end

function category=historianCategory(item)
if ~isempty(item.group)
    category=char(item.group);
    return
end
label=upper(string(item.group)+" "+string(item.kind)+" "+string(item.name));
if contains(label,"PROTECT") || contains(label,"TRIP_LATCH") || contains(label,"TRIPREQUEST")
    category='Protection';
elseif contains(label,"BREAKER") || contains(label,"VCB") || contains(label,"52GT") || contains(label,"52ST")
    category='Breaker';
elseif contains(label,"PUMP") || contains(label,"FWP") || contains(label,"BFP")
    category='Pump';
elseif contains(label,"VALVE") || contains(label,"VLV") || contains(label,"CV")
    category='Valve';
elseif contains(label,"COMMAND") || contains(label,"_CMD") || contains(label,"CMDNATIVE")
    category='Command';
elseif contains(label,"BOOL") || contains(label,"DIGITAL") || contains(label,"ACTIVE") || contains(label,"CLOSED")
    category='Digital';
else
    category='Analog';
end
end

function changed=valuesDiffer(left,right)
try
    if isnumeric(left) && isnumeric(right) && isscalar(left) && isscalar(right)
        scale=max([1,abs(double(left)),abs(double(right))]);
        changed=abs(double(left)-double(right))>1e-10*scale;
    else
        changed=~strcmp(char(displayScalar(left)),char(displayScalar(right)));
    end
catch
    changed=true;
end
end

function value=displayScalar(raw)
if isempty(raw), value="N/A";
elseif isnumeric(raw) && isscalar(raw), value=compose("%.9g",double(raw));
elseif islogical(raw) && isscalar(raw), value=string(double(raw));
elseif ischar(raw), value=string(raw);
elseif isstring(raw) && isscalar(raw), value=raw;
elseif isnumeric(raw) || islogical(raw), value=string(mat2str(raw));
else
    try, value=string(raw); value=value(1); catch, value="N/A"; end
end
end

function value=tableScalar(raw)
if isnumeric(raw) && isscalar(raw) && ~isnan(double(raw)) && ~isinf(double(raw)), value=double(raw);
elseif islogical(raw) && isscalar(raw), value=logical(raw);
else, value=char(displayScalar(raw)); end
end

function data=sanitizeTableData(data)
if isempty(data), data=cell(0,size(data,2)); return; end
for row=1:size(data,1)
    for column=1:size(data,2)
        data{row,column}=tableScalar(data{row,column});
    end
end
end
