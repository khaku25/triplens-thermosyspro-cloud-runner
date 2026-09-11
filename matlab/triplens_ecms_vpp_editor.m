function triplens_ecms_vpp_editor()
%TRIPLENS_ECMS_VPP_EDITOR Edit ECMS geometry, A assumptions and commands.
% Version 3.1: CommandBus plus MATLAB Online-safe, responsive editing.
% M-tag links are read-only. A settings/equipment placement are editable.
% Command buttons create a device-neutral CSV queue; they never modify M.
% Clicking BUS-A or BUS-B opens the corresponding 6.9 kV feeder window.

baseDir = fileparts(mfilename("fullpath"));
rootDir = fileparts(baseDir);
settingsFile = fullfile(rootDir,"config","ecms_a_settings.csv");
equipmentFile = fullfile(rootDir,"config","ecms_a_equipment.csv");
linksFile = fullfile(rootDir,"data","ecms_m_links.csv");
mTagsFile = fullfile(rootDir,"data","thermo_vpp_m_locked_tags.csv");
commandFile = fullfile(rootDir,"config","ecms_command_catalog.csv");

mustExist(settingsFile); mustExist(equipmentFile); mustExist(linksFile); mustExist(mTagsFile); mustExist(commandFile);
settings = readCsvText(settingsFile);
equipment = readCsvText(equipmentFile);
mLinks = readCsvText(linksFile);
mTags = readCsvText(mTagsFile);
commandCatalog = readCsvText(commandFile);
mustHaveColumns(settings,["setting_id","value","status","notes"]);
mustHaveColumns(equipment,["equipment_id","label_ko","bus","feeder_id","voltage_kv","rated_kw","normal_breaker_state"]);
mustHaveColumns(mLinks,["link_id","ecms_equipment_id","source_m_tag_id","locked"]);
mustHaveColumns(mTags,["tag_id","tag_class","value_basis"]);
lockValues=lower(strtrim(string(mLinks.locked)));
assert(all(lockValues=="true" | lockValues=="1"),"TripLens:MLockViolation","M link lock flag is not true.");
assert(all(mTags.tag_class=="M" & mTags.value_basis=="M"),"TripLens:MLockViolation","M catalog contains non-M rows.");
assert(all(ismember(mLinks.source_m_tag_id,mTags.tag_id)),"TripLens:MLockViolation","M link references a missing M tag.");
validateCommandCatalog(commandCatalog,mTags);
[nodes,edges] = buildOverviewModel();
initialNodes = nodes; initialEdges = edges;
selectedEdge = 1; dragNode = 0;
selectedQueueRow = 0;
commandQueue = emptyCommandQueue();

fig = uifigure("Name","TripLens ECMS VPP Editor 3.1", ...
    "Position",initialFigurePosition(),"Color",[0.95 0.97 0.98]);
% A custom phone/desktop layout is driven by resizeEditor.  MATLAB Online
% suppresses SizeChangedFcn while the uifigure's automatic child resizing
% remains enabled, so turn the automatic mode off before installing it.
try, fig.AutoResizeChildren = 'off'; catch, end
fig.WindowButtonMotionFcn = @dragMotion;
fig.WindowButtonUpFcn = @endDrag;

% Keep a fixed 2x2 grid. Resizing only changes row/column sizes, so a
% currently occupied row or column is never deleted during phone rotation.
outer = uigridlayout(fig,[2 2]);
outer.RowHeight = {'1x',0}; outer.ColumnWidth = {390,'1x'};
outer.Padding = [8 8 8 8]; outer.ColumnSpacing = 8;
tabs = uitabgroup(outer); tabs.Layout.Column = 1;

editTab = uitab(tabs,"Title","도면");
controls = uigridlayout(editTab,[16 2]);
controls.RowHeight = {30,30,30,30,30,32,32,32,32,32,32,32,'1x',25,25,25};
controls.ColumnWidth = {120,'1x'}; controls.Padding = [10 10 10 10];
try, controls.Scrollable = "on"; catch, end
edgeLabel = uilabel(controls,"Text","배선 선택","FontWeight","bold");
edgeLabel.Layout.Column = [1 2];
edgeDrop = uidropdown(controls,"Items",[edges.name],"ItemsData",1:numel(edges), ...
    "Value",selectedEdge,"ValueChangedFcn",@edgeChanged);
edgeDrop.Layout.Column = [1 2];
uilabel(controls,"Text","직각 경로");
routeDrop = uidropdown(controls,"Items",["가로→세로","세로→가로","세로→가로→세로","가로→세로→가로"], ...
    "ItemsData",["HV","VH","VHV","HVH"],"Value",edges(1).route,"ValueChangedFcn",@routeChanged);
uilabel(controls,"Text","꺾임 좌표");
bendSpin = uispinner(controls,"Limits",[0 1400],"Step",10,"Value",edges(1).bend,"ValueChangedFcn",@bendChanged);
uilabel(controls,"Text","격자 간격");
gridSpin = uispinner(controls,"Limits",[5 100],"Step",5,"Value",10);
addButton(controls,"선택 배선 자동 직각",@autoRoute);
addButton(controls,"전체 배선 자동 정리",@autoRouteAll);
addButton(controls,"BUS-A 6.9 kV 상세 열기",@(~,~)openBusDetail("BUS-A"));
addButton(controls,"BUS-B 6.9 kV 상세 열기",@(~,~)openBusDetail("BUS-B"));
addButton(controls,"초기 배치로 복원",@resetLayout);
addButton(controls,"Overview SVG 저장",@saveOverviewSvg);
addButton(controls,"6.9 kV 상세 SVG 저장",@saveDetailSvg);
helpBox = uitextarea(controls,"Editable","off","Value",[ ...
    "M / A 분리 원칙"; ...
    "• M 태그 ID·단위·연결은 읽기 전용"; ...
    "• A 탭에서 배치·정격·로직값 수정"; ...
    "• BUS를 클릭하면 새 상세 창이 열림"; ...
    "• 배선을 터치하면 경로·꺾임을 즉시 편집"; ...
    "• 설비를 드래그해 위치만 변경"; ...
    "• 전기 접속관계는 잠금"; ...
    "• 별도 SST 없음: GT/ST 변압기 역수전"]);
helpBox.Layout.Column = [1 2];
statusLabel = uilabel(controls,"Text","준비됨","FontColor",[0.10 0.40 0.37]);
statusLabel.Layout.Column = [1 2];
lockLabel = uilabel(controls,"Text","M lock: ON · Topology lock: ON","FontWeight","bold","FontColor",[0.10 0.48 0.36]);
lockLabel.Layout.Column = [1 2];
versionLabel = uilabel(controls,"Text","TripLens ECMS Editor 3.1 · CommandBus · 6.9 kV · no SST");
versionLabel.Layout.Column = [1 2];

commandTab = uitab(tabs,"Title","Command");
commandGrid = uigridlayout(commandTab,[10 2]);
commandGrid.RowHeight = {28,32,28,32,28,100,28,'1x',34,34};
commandGrid.ColumnWidth = {120,'1x'}; commandGrid.Padding = [8 8 8 8];
try, commandGrid.Scrollable = "on"; catch, end
commandTitle = uilabel(commandGrid,"Text","CommandBus — 조작 명령 예약","FontWeight","bold");
commandTitle.Layout.Column = [1 2];
uilabel(commandGrid,"Text","대상 설비");
commandEquipmentIds = unique(string(commandCatalog.equipment_id),"stable");
commandEquipmentLabels = strings(size(commandEquipmentIds));
for q=1:numel(commandEquipmentIds)
    row = commandCatalog(string(commandCatalog.equipment_id)==commandEquipmentIds(q),:);
    commandEquipmentLabels(q) = string(row.label_ko(1))+"  ["+commandEquipmentIds(q)+"]";
end
commandEquipmentDrop = uidropdown(commandGrid,"Items",cellstr(commandEquipmentLabels), ...
    "ItemsData",cellstr(commandEquipmentIds),"Value",char(commandEquipmentIds(1)), ...
    "ValueChangedFcn",@commandEquipmentChanged);
uilabel(commandGrid,"Text","실행 시각 (s)");
commandTimeSpin = uispinner(commandGrid,"Limits",[0 86400],"Step",1,"Value",100);
uilabel(commandGrid,"Text","설정값");
commandValueSpin = uispinner(commandGrid,"Limits",[0 100],"Step",1,"Value",50);
commandLayerLabel = uilabel(commandGrid,"Text","연결계층 확인 중","FontColor",[0.38 0.43 0.47]);
commandLayerLabel.Layout.Column = [1 2];
commandButtonGrid = uigridlayout(commandGrid,[2 4]);
commandButtonGrid.Layout.Row=6; commandButtonGrid.Layout.Column=[1 2];
commandButtonGrid.RowHeight={45,45}; commandButtonGrid.ColumnWidth={'1x','1x','1x','1x'};
commandButtons=cell(1,8);
for q=1:numel(commandButtons)
    commandButtons{q}=uibutton(commandButtonGrid,"Text","-","Visible","off", ...
        "ButtonPushedFcn",@(~,~)queueSelectedCommand(q));
end
queueLabel = uilabel(commandGrid,"Text","명령 큐 — 시간순 CSV로 저장","FontWeight","bold");
queueLabel.Layout.Row=7; queueLabel.Layout.Column=[1 2];
queueTable = uitable(commandGrid,"Data",commandQueue,"CellSelectionCallback",@queueCellSelected);
queueTable.Layout.Row=8; queueTable.Layout.Column=[1 2]; queueTable.ColumnEditable=false(1,width(commandQueue));
removeCommandButton=uibutton(commandGrid,"Text","선택 명령 삭제","ButtonPushedFcn",@removeQueuedCommand);
removeCommandButton.Layout.Row=9; removeCommandButton.Layout.Column=1;
clearCommandButton=uibutton(commandGrid,"Text","전체 명령 지우기","ButtonPushedFcn",@clearCommandQueue);
clearCommandButton.Layout.Row=9; clearCommandButton.Layout.Column=2;
loadCommandButton=uibutton(commandGrid,"Text","Command CSV 불러오기","ButtonPushedFcn",@loadCommandQueue);
loadCommandButton.Layout.Row=10; loadCommandButton.Layout.Column=1;
saveCommandButton=uibutton(commandGrid,"Text","Command CSV 저장","FontWeight","bold","ButtonPushedFcn",@saveCommandQueue);
saveCommandButton.Layout.Row=10; saveCommandButton.Layout.Column=2;
refreshCommandPanel();

aTab = uitab(tabs,"Title","A 설정");
aGrid = uigridlayout(aTab,[4 1]); aGrid.RowHeight = {32,'1x',32,'1x'}; aGrid.Padding = [8 8 8 8];
try, aGrid.Scrollable = "on"; catch, end
uilabel(aGrid,"Text","A 설정값 — value/status/notes만 편집","FontWeight","bold");
settingsTable = uitable(aGrid,"Data",settings);
settingsTable.ColumnEditable = ismember(settings.Properties.VariableNames,{'value','status','notes'});
uilabel(aGrid,"Text","A 설비배치 — equipment_id를 제외한 설계값 편집","FontWeight","bold");
equipmentTable = uitable(aGrid,"Data",equipment);
equipmentTable.ColumnEditable = ~strcmp(equipment.Properties.VariableNames,'equipment_id');

mTab = uitab(tabs,"Title","M 잠금");
mGrid = uigridlayout(mTab,[2 1]); mGrid.RowHeight = {55,'1x'}; mGrid.Padding = [8 8 8 8];
try, mGrid.Scrollable = "on"; catch, end
uilabel(mGrid,"Text",["ThermoSysPro M 201개와 ECMS 연결 10개 — 모두 편집 불가"; ...
    "유량은 공정부하 연결점이며 전동기 전력/차단기 상태를 의미하지 않음"], ...
    "FontWeight","bold");
mSubTabs = uitabgroup(mGrid);
mLinkTab = uitab(mSubTabs,"Title","ECMS 연결");
mLinkGrid = uigridlayout(mLinkTab,[1 1]); mLinkGrid.Padding = [0 0 0 0];
mTable = uitable(mLinkGrid,"Data",mLinks); mTable.ColumnEditable = false(1,width(mLinks));
mAllTab = uitab(mSubTabs,"Title","전체 M");
mAllGrid = uigridlayout(mAllTab,[1 1]); mAllGrid.Padding = [0 0 0 0];
mAllTable = uitable(mAllGrid,"Data",mTags); mAllTable.ColumnEditable = false(1,width(mTags));

actionTab = uitab(tabs,"Title","저장");
actionGrid = uigridlayout(actionTab,[8 1]); actionGrid.RowHeight = repmat({38},1,8); actionGrid.Padding = [10 10 10 10];
try, actionGrid.Scrollable = "on"; catch, end
uibutton(actionGrid,"Text","A 설정 검증","ButtonPushedFcn",@validateA);
uibutton(actionGrid,"Text","A 설정 CSV 저장","FontWeight","bold","ButtonPushedFcn",@saveA);
uibutton(actionGrid,"Text","현재 A/Command로 실행","FontWeight","bold","ButtonPushedFcn",@runCurrentCase);
uibutton(actionGrid,"Text","GitHub OPC UA 검증 GT Trip 실행","FontWeight","bold","ButtonPushedFcn",@runGitHubCase);
uibutton(actionGrid,"Text","레이아웃 JSON 저장","ButtonPushedFcn",@saveLayout);
uibutton(actionGrid,"Text","레이아웃 JSON 불러오기","ButtonPushedFcn",@loadLayout);
uilabel(actionGrid,"Text","M CSV는 저장 버튼이 없습니다.","FontWeight","bold","FontColor",[0.12 0.48 0.34]);
uilabel(actionGrid,"Text","A 변경 후 Python/Actions ECMS 결과를 다시 생성하세요.");

ax = uiaxes(outer); ax.Layout.Column = 2; ax.XLim = [0 1400]; ax.YLim = [0 800];
ax.XTick = 0:50:1400; ax.YTick = 0:50:800; ax.XGrid = "on"; ax.YGrid = "on";
ax.GridAlpha = 0.10; ax.Color = [0.98 0.99 0.995]; ax.DataAspectRatio = [1 1 1];
try, ax.Toolbar.Visible = "off"; catch, end
title(ax,"TripLens ECMS VPP Editor 3.1 — M locked / A editable / click 6.9 kV bus");
hold(ax,"on"); redraw();
fig.SizeChangedFcn = @resizeEditor;
resizeEditor();
try
    fig.WindowState = "maximized";
catch
    % Older releases do not expose WindowState for uifigure.
end

    function addButton(parent,label,callback)
        button = uibutton(parent,"Text",label,"ButtonPushedFcn",callback);
        button.Layout.Column = [1 2];
    end

    function resizeEditor(varargin)
        % Keep both the controls and drawing usable inside MATLAB Online's
        % browser canvas instead of relying on a desktop-sized position.
        figureWidth = fig.Position(3);
        figureHeight = fig.Position(4);
        if figureWidth < 900
            controlHeight = min(600,max(440,round(figureHeight*0.76)));
            if figureHeight > 180
                controlHeight = min(controlHeight,figureHeight-120);
            end
            tabs.Layout.Row=1; tabs.Layout.Column=1;
            ax.Layout.Row=2; ax.Layout.Column=1;
            outer.RowHeight = {max(360,controlHeight),'1x'};
            outer.ColumnWidth = {'1x',0};
        else
            tabs.Layout.Row=1; tabs.Layout.Column=1;
            ax.Layout.Row=1; ax.Layout.Column=2;
            outer.ColumnWidth = {390,'1x'};
            outer.RowHeight = {'1x',0};
        end
    end

    function redraw()
        delete(ax.Children);
        for k = 1:numel(edges)
            [x,y] = edgePolyline(edges(k));
            % A five-pixel base line is intentionally wider than a print
            % SLD line so it can be selected reliably in MATLAB Mobile.
            color = wireColor(edges(k).system); widthValue = 5;
            if k == selectedEdge, color = [0.95 0.38 0.08]; widthValue = 9; end
            line(ax,x,y,"Color",color,"LineWidth",widthValue,"HitTest","on", ...
                "PickableParts","all","ButtonDownFcn",@(~,~)selectEdge(k));
        end
        for k = 1:numel(nodes), drawNode(k); end
        text(ax,25,770,"GT/ST main transformers: generation ↕ reverse receiving", ...
            "FontSize",13,"FontWeight","bold","Color",[0.32 0.24 0.55],"HitTest","off");
        text(ax,25,742,"M = locked physics · A = editable topology/rating/logic · no separate SST", ...
            "FontSize",11,"Color",[0.40 0.47 0.52],"HitTest","off");
        drawnow limitrate;
    end

    function drawNode(k)
        n = nodes(k);
        if startsWith(n.id,"BUS_")
            callback = @(~,~)openBusDetail(strrep(n.id,"_","-"));
        else
            callback = @(~,~)beginNodeDrag(k);
        end
        switch n.kind
            case "generator"
                rectangle(ax,"Position",[n.x-26 n.y-26 52 52],"Curvature",[1 1], ...
                    "FaceColor","white","EdgeColor",[0.12 0.39 0.65],"LineWidth",3, ...
                    "ButtonDownFcn",callback,"PickableParts","all");
                text(ax,n.x,n.y,"G","HorizontalAlignment","center","FontWeight","bold","FontSize",17, ...
                    "ButtonDownFcn",callback,"PickableParts","all");
            case "breaker_closed"
                rectangle(ax,"Position",[n.x-18 n.y-21 36 42],"Curvature",[0.1 0.1], ...
                    "FaceColor",[0.87 0.30 0.27],"EdgeColor",[0.57 0.13 0.12],"LineWidth",2, ...
                    "ButtonDownFcn",callback,"PickableParts","all");
            case "breaker_open"
                rectangle(ax,"Position",[n.x-22 n.y-19 44 38],"Curvature",[0.1 0.1], ...
                    "FaceColor","white","EdgeColor",[0.48 0.54 0.58],"LineWidth",3, ...
                    "ButtonDownFcn",callback,"PickableParts","all");
            case "transformer"
                rectangle(ax,"Position",[n.x-28 n.y-19 38 38],"Curvature",[1 1],"FaceColor","white", ...
                    "EdgeColor",[0.35 0.28 0.66],"LineWidth",2.5,"ButtonDownFcn",callback,"PickableParts","all");
                rectangle(ax,"Position",[n.x-10 n.y-19 38 38],"Curvature",[1 1],"FaceColor","white", ...
                    "EdgeColor",[0.35 0.28 0.66],"LineWidth",2.5,"ButtonDownFcn",callback,"PickableParts","all");
            case "bus154"
                line(ax,[n.x-105 n.x+105],[n.y n.y],"Color",[0.79 0.27 0.24],"LineWidth",16, ...
                    "ButtonDownFcn",callback,"PickableParts","all");
            case "bus"
                line(ax,[n.x-105 n.x+105],[n.y n.y],"Color",[0.16 0.38 0.72],"LineWidth",16, ...
                    "ButtonDownFcn",callback,"PickableParts","all");
            otherwise
                scatter(ax,n.x,n.y,150,[0.14 0.25 0.31],"s","filled","ButtonDownFcn",callback);
        end
        text(ax,n.x,n.y+36,n.label,"HorizontalAlignment","center","FontWeight","bold","FontSize",10, ...
            "ButtonDownFcn",callback,"PickableParts","all");
        text(ax,n.x,n.y-38,n.tag,"HorizontalAlignment","center","FontSize",8.5,"Color",[0.38 0.46 0.49], ...
            "ButtonDownFcn",callback,"PickableParts","all");
    end

    function beginNodeDrag(k), dragNode = k; statusLabel.Text = "설비 이동: " + string(nodes(k).tag); end
    function dragMotion(~,~)
        if dragNode == 0, return; end
        p = ax.CurrentPoint; g = gridSpin.Value;
        nodes(dragNode).x = round(min(max(p(1,1),30),1370)/g)*g;
        nodes(dragNode).y = round(min(max(p(1,2),40),710)/g)*g;
        redraw();
    end
    function endDrag(~,~)
        if dragNode > 0, statusLabel.Text = "도면 위치 편집됨 — 저장 전"; end
        dragNode = 0;
    end
    function selectEdge(k), selectedEdge=k; edgeDrop.Value=k; refreshControls(); redraw(); end
    function edgeChanged(src,~), selectedEdge=src.Value; refreshControls(); redraw(); end
    function refreshControls()
        routeDrop.Value=edges(selectedEdge).route; bendSpin.Value=edges(selectedEdge).bend;
        statusLabel.Text="선택: "+string(edges(selectedEdge).name);
    end
    function routeChanged(src,~), edges(selectedEdge).route=src.Value; setDefaultBend(selectedEdge); refreshControls(); redraw(); end
    function bendChanged(src,~), edges(selectedEdge).bend=src.Value; redraw(); end
    function autoRoute(~,~), autoOne(selectedEdge); refreshControls(); redraw(); end
    function autoRouteAll(~,~)
        for q=1:numel(edges), autoOne(q); end
        refreshControls(); statusLabel.Text="전체 배선 직각 정리 완료"; redraw();
    end
    function autoOne(q)
        left=nodes(nodeIndex(edges(q).from)); right=nodes(nodeIndex(edges(q).to));
        if abs(left.x-right.x)>=abs(left.y-right.y), edges(q).route="HV"; else, edges(q).route="VH"; end
        setDefaultBend(q);
    end
    function setDefaultBend(q)
        left=nodes(nodeIndex(edges(q).from)); right=nodes(nodeIndex(edges(q).to));
        if edges(q).route=="VHV", edges(q).bend=(left.y+right.y)/2; end
        if edges(q).route=="HVH", edges(q).bend=(left.x+right.x)/2; end
    end
    function resetLayout(~,~)
        nodes=initialNodes; edges=initialEdges; selectedEdge=1; edgeDrop.Value=1;
        refreshControls(); statusLabel.Text="초기 배치 복원됨"; redraw();
    end
    function [x,y]=edgePolyline(edge)
        left=nodes(nodeIndex(edge.from)); right=nodes(nodeIndex(edge.to));
        switch edge.route
            case "VH", x=[left.x left.x right.x]; y=[left.y right.y right.y];
            case "VHV", x=[left.x left.x right.x right.x]; y=[left.y edge.bend edge.bend right.y];
            case "HVH", x=[left.x edge.bend edge.bend right.x]; y=[left.y left.y right.y right.y];
            otherwise, x=[left.x right.x right.x]; y=[left.y left.y right.y];
        end
    end
    function idx=nodeIndex(id), idx=find([nodes.id]==string(id),1); assert(~isempty(idx),"Unknown node: %s",id); end

    function openBusDetail(busId)
        rows = equipmentTable.Data;
        subset = rows(strcmp(string(rows.bus),busId),:);
        if isempty(subset), uialert(fig,"해당 BUS에 배치된 A 설비가 없습니다.","6.9 kV 상세"); return; end
        detail = uifigure("Name","TripLens 6.9 kV "+busId+" · Editor 3.1", ...
            "Position",initialFigurePosition(1280,760),"Color","white");
        detailGrid = uigridlayout(detail,[2 1]); detailGrid.RowHeight={'3x','1x'}; detailGrid.Padding=[10 10 10 10];
        detailAx = uiaxes(detailGrid); detailAx.XLim=[0 1200]; detailAx.YLim=[0 520]; detailAx.XTick=[]; detailAx.YTick=[]; hold(detailAx,"on");
        title(detailAx,"6.9 kV "+busId+" — feeder detail (A equipment / locked M links)");
        line(detailAx,[70 1130],[410 410],"Color",[0.16 0.38 0.72],"LineWidth",13);
        line(detailAx,[600 600],[500 410],"Color",[0.16 0.38 0.72],"LineWidth",4);
        rectangle(detailAx,"Position",[585 455 30 35],"FaceColor",[0.87 0.30 0.27],"EdgeColor",[0.57 0.13 0.12],"LineWidth",2);
        text(detailAx,650,472,"INCOMING","FontWeight","bold");
        xPositions=linspace(130,1070,height(subset));
        for z=1:height(subset)
            x=xPositions(z); eq=subset(z,:);
            commandCallback=@(~,~)focusCommand(eq.equipment_id);
            line(detailAx,[x x],[410 260],"Color",[0.16 0.38 0.72],"LineWidth",6, ...
                "ButtonDownFcn",commandCallback,"PickableParts","all");
            if strcmpi(string(eq.normal_breaker_state),"CLOSED")
                breakerFace=[0.87 0.30 0.27]; breakerEdge=[0.57 0.13 0.12];
            else
                breakerFace=[1 1 1]; breakerEdge=[0.48 0.54 0.58];
            end
            rectangle(detailAx,"Position",[x-18 326 36 42],"FaceColor",breakerFace,"EdgeColor",breakerEdge,"LineWidth",2, ...
                "ButtonDownFcn",commandCallback,"PickableParts","all");
            rectangle(detailAx,"Position",[x-75 190 150 60],"Curvature",[0.12 0.12],"FaceColor",[1.0 0.96 0.86], ...
                "EdgeColor",[0.84 0.60 0.17],"LineWidth",2,"ButtonDownFcn",commandCallback,"PickableParts","all");
            text(detailAx,x,220,eq.label_ko,"HorizontalAlignment","center","FontWeight","bold","FontSize",10, ...
                "ButtonDownFcn",commandCallback,"PickableParts","all");
            text(detailAx,x,170,string(eq.feeder_id)+" · Command","HorizontalAlignment","center","FontSize",9, ...
                "ButtonDownFcn",commandCallback,"PickableParts","all");
            linked=mLinks(mLinks.ecms_equipment_id==eq.equipment_id,:);
            if ~isempty(linked)
                rectangle(detailAx,"Position",[x-88 70 176 70],"Curvature",[0.12 0.12],"FaceColor",[0.91 0.97 0.93], ...
                    "EdgeColor",[0.23 0.58 0.39],"LineWidth",2);
                text(detailAx,x,112,"M LOCKED","HorizontalAlignment","center","FontWeight","bold","Color",[0.15 0.47 0.31]);
                text(detailAx,x,89,linked.source_m_tag_id(1),"HorizontalAlignment","center","FontSize",7.5,"Interpreter","none");
            end
        end
        linkedIds=subset.equipment_id;
        detailLinks=mLinks(ismember(mLinks.ecms_equipment_id,linkedIds),:);
        linkTable=uitable(detailGrid,"Data",detailLinks); linkTable.ColumnEditable=false(1,width(detailLinks));
        try, detail.WindowState="maximized"; catch, end
    end

    function focusCommand(equipmentId)
        equipmentId=string(equipmentId);
        if ~ismember(equipmentId,commandEquipmentIds)
            uialert(fig,"이 설비는 아직 Command Catalog에 등록되지 않았습니다.","Command 없음"); return;
        end
        commandEquipmentDrop.Value=char(equipmentId);
        tabs.SelectedTab=commandTab;
        refreshCommandPanel();
        statusLabel.Text=equipmentId+" Command 선택됨";
        try, figure(fig); catch, end
    end
    function commandEquipmentChanged(~,~), refreshCommandPanel(); end
    function rows=selectedCommandRows()
        rows=commandCatalog(string(commandCatalog.equipment_id)==string(commandEquipmentDrop.Value),:);
    end
    function refreshCommandPanel()
        rows=selectedCommandRows();
        for slot=1:numel(commandButtons)
            if slot<=height(rows)
                commandButtons{slot}.Text=char(string(rows.button_label(slot)));
                commandButtons{slot}.Visible="on";
                commandButtons{slot}.UserData=slot;
                [bg,fg]=commandButtonColor(rows.command(slot));
                commandButtons{slot}.BackgroundColor=bg; commandButtons{slot}.FontColor=fg;
            else
                commandButtons{slot}.Visible="off";
                commandButtons{slot}.UserData=[];
            end
        end
        analogRows=rows(string(rows.value_type)=="REAL",:);
        if isempty(analogRows)
            commandValueSpin.Enable="off"; commandValueSpin.Limits=[0 100]; commandValueSpin.Value=0;
        else
            low=str2double(string(analogRows.min_value(1)));
            high=str2double(string(analogRows.max_value(1)));
            initial=str2double(string(analogRows.default_value(1)));
            commandValueSpin.Limits=[low high];
            commandValueSpin.Value=min(max(initial,low),high);
            commandValueSpin.Enable="on";
        end
        layers=unique(string(rows.execution_layer),"stable");
        if any(layers=="THERMO_ADAPTER_REQUIRED")
            commandLayerLabel.Text="주황: CSV 생성 가능 · ThermoSysPro 입력 어댑터 연결 필요";
            commandLayerLabel.FontColor=[0.83 0.43 0.05];
        else
            commandLayerLabel.Text="녹색: ECMS 전기 상태엔진 또는 GT 경계조건에 연결됨";
            commandLayerLabel.FontColor=[0.10 0.48 0.34];
        end
    end
    function queueSelectedCommand(slot)
        rows=selectedCommandRows(); if slot>height(rows), return; end
        definition=rows(slot,:);
        if string(definition.value_type)=="REAL"
            value=string(commandValueSpin.Value);
        else
            value=string(definition.default_value);
        end
        nextSequence=height(commandQueue)+1;
        newRow=table(nextSequence,commandTimeSpin.Value,string(definition.equipment_id), ...
            string(definition.label_ko),string(definition.command),value,string(definition.unit), ...
            string(definition.execution_layer),string(definition.model_input),string(definition.feedback_tag), ...
            "QUEUED","",'VariableNames',commandQueue.Properties.VariableNames);
        commandQueue=[commandQueue;newRow];
        commandQueue=sortrows(commandQueue,{'time_s','sequence'});
        commandQueue.sequence=(1:height(commandQueue))';
        queueTable.Data=commandQueue; selectedQueueRow=0;
        statusLabel.Text=string(definition.equipment_id)+" "+string(definition.command)+" 명령이 CommandBus에 추가됨";
    end
    function queueCellSelected(~,event)
        if isempty(event.Indices), selectedQueueRow=0; else, selectedQueueRow=event.Indices(1,1); end
    end
    function removeQueuedCommand(~,~)
        if selectedQueueRow<1 || selectedQueueRow>height(commandQueue)
            uialert(fig,"삭제할 명령 행을 먼저 선택하세요.","Command"); return;
        end
        commandQueue(selectedQueueRow,:)=[];
        commandQueue.sequence=(1:height(commandQueue))';
        queueTable.Data=commandQueue; selectedQueueRow=0; statusLabel.Text="선택 명령 삭제됨";
    end
    function clearCommandQueue(~,~)
        commandQueue=emptyCommandQueue(); queueTable.Data=commandQueue; selectedQueueRow=0;
        statusLabel.Text="CommandBus 명령 큐 비움";
    end
    function loadCommandQueue(~,~)
        [file,path]=uigetfile("*.csv","Command CSV 불러오기"); if isequal(file,0), return; end
        try
            loaded=readCsvText(fullfile(path,file));
            loaded=normalizeCommandQueue(loaded);
            messages=collectCommandErrors(loaded);
        catch caught
            uialert(fig,"Command CSV를 읽을 수 없습니다."+newline+caught.message,"Command 불러오기 거부","Icon","error"); return;
        end
        if ~isempty(messages), uialert(fig,join(messages,newline),"Command 불러오기 거부","Icon","error"); return; end
        commandQueue=sortrows(loaded(:,commandQueue.Properties.VariableNames),{'time_s','sequence'});
        commandQueue.sequence=(1:height(commandQueue))';
        queueTable.Data=commandQueue; selectedQueueRow=0; statusLabel.Text="Command CSV 불러오기 완료";
    end
    function saveCommandQueue(~,~)
        messages=collectCommandErrors(commandQueue);
        if ~isempty(messages), uialert(fig,join(messages,newline),"Command 저장 중단","Icon","error"); return; end
        [file,path]=uiputfile("*.csv","Command CSV 저장","triplens_commands.csv"); if isequal(file,0), return; end
        writeCsvText(commandQueue,fullfile(path,file));
        statusLabel.Text="Command CSV 저장 완료 — M 파일은 변경되지 않음";
    end
    function messages=collectCommandErrors(queue)
        messages=strings(0,1); template=emptyCommandQueue(); required=string(template.Properties.VariableNames);
        available=string(queue.Properties.VariableNames);
        if ~all(ismember(required,available)), messages(end+1)="Command CSV 열 구성이 맞지 않습니다."; return; end
        if ~isnumeric(queue.sequence) || ~isnumeric(queue.time_s)
            messages(end+1)="sequence와 time_s는 숫자여야 합니다."; return;
        end
        if any(~isfinite(queue.sequence)) || any(queue.sequence<1 | fix(queue.sequence)~=queue.sequence)
            messages(end+1)="sequence는 1 이상의 유한 정수여야 합니다.";
        end
        if any(~isfinite(queue.time_s)) || any(queue.time_s<0)
            messages(end+1)="실행 시각은 0초 이상의 유한 숫자여야 합니다.";
        end
        for r=1:height(queue)
            equipmentId=string(queue.equipment_id(r)); commandName=string(queue.command(r));
            match=commandCatalog(string(commandCatalog.equipment_id)==equipmentId & string(commandCatalog.command)==commandName,:);
            if height(match)~=1, messages(end+1)="미등록 명령: "+equipmentId+"/"+commandName; continue; end
            if string(match.value_type(1))=="REAL"
                numericValue=str2double(string(queue.command_value(r)));
                low=str2double(string(match.min_value(1))); high=str2double(string(match.max_value(1)));
                if ~isfinite(numericValue) || numericValue<low || numericValue>high
                    messages(end+1)=equipmentId+" "+commandName+" 값이 허용범위를 벗어났습니다.";
                end
            elseif string(queue.command_value(r))~=string(match.default_value(1))
                messages(end+1)=equipmentId+" "+commandName+" DIGITAL 값이 Catalog와 다릅니다.";
            end
            canonicalFields=["equipment_label","unit","execution_layer","model_input","feedback_tag"];
            catalogFields=["label_ko","unit","execution_layer","model_input","feedback_tag"];
            for fieldIndex=1:numel(canonicalFields)
                queueColumn=queue.(char(canonicalFields(fieldIndex)));
                catalogColumn=match.(char(catalogFields(fieldIndex)));
                if string(queueColumn(r))~=string(catalogColumn(1))
                    messages(end+1)=equipmentId+" "+commandName+" 메타데이터가 Catalog와 다릅니다."; break;
                end
            end
        end
    end
    function queue=normalizeCommandQueue(queue)
        template=emptyCommandQueue(); required=string(template.Properties.VariableNames);
        available=string(queue.Properties.VariableNames);
        if ~all(ismember(required,available)), return; end
        if ~isnumeric(queue.sequence), queue.sequence=str2double(string(queue.sequence)); end
        if ~isnumeric(queue.time_s), queue.time_s=str2double(string(queue.time_s)); end
        stringFields=setdiff(required,["sequence","time_s"],"stable");
        for fieldIndex=1:numel(stringFields)
            name=stringFields(fieldIndex); queue.(name)=string(queue.(name));
        end
    end

    function runCurrentCase(~,~)
        messages=collectAErrors();
        messages=[messages;collectCommandErrors(commandQueue)];
        if ~isempty(messages)
            uialert(fig,join(messages,newline),"실행 중단","Icon","error"); return;
        end
        expectedEngine=fullfile(baseDir,"triplens_ecms_vpp_simulate.m");
        if ~isfile(expectedEngine)
            missingEngineMessage=join(["MATLAB VPP 실행 엔진 triplens_ecms_vpp_simulate.m을 찾지 못했습니다."; ...
                "편집기와 실행 엔진이 함께 있는 전체 패키지에서 ECMS_START를 실행하세요."],newline);
            uialert(fig,missingEngineMessage, ...
                "실행 엔진 없음","Icon","warning"); return;
        end
        try
            addpath(baseDir,"-begin"); rehash;
            clear triplens_ecms_vpp_simulate;
            resolvedEngine=string(which("triplens_ecms_vpp_simulate"));
            assert(resolvedEngine==string(expectedEngine),"TripLens:WrongNativeEngine", ...
                "다른 ECMS 실행기가 현재 패키지를 가리고 있습니다: %s",resolvedEngine);
            statusLabel.Text="현재 A/Command로 VPP 실행 중…"; drawnow;
            triplens_ecms_vpp_simulate("PackageRoot",rootDir, ...
                "SettingsTable",settingsTable.Data, ...
                "EquipmentTable",equipmentTable.Data,"CommandTable",commandQueue);
            statusLabel.Text="현재 A/Command 실행 완료 — 최신 결과를 확인하세요";
        catch caught
            statusLabel.Text="VPP 실행 실패";
            uialert(fig,caught.message,"VPP 실행 오류","Icon","error");
        end
    end

    function runGitHubCase(~,~)
        messages=collectAErrors();
        if ~isempty(messages)
            uialert(fig,join(messages,newline),"실행 중단","Icon","error"); return;
        end
        expectedBridge=fullfile(rootDir,"ECMS_GITHUB.m");
        if ~isfile(expectedBridge)
            uialert(fig,"ECMS_GITHUB.m을 찾지 못했습니다.", ...
                "GitHub bridge 없음","Icon","warning"); return;
        end
        try
            addpath(rootDir,"-begin"); rehash;
            clear ECMS_GITHUB;
            assert(string(which("ECMS_GITHUB"))==string(expectedBridge), ...
                "TripLens:WrongGitHubBridge", ...
                "다른 ECMS_GITHUB 함수가 현재 패키지를 가리고 있습니다.");
            statusLabel.Text="GitHub OPC UA ThermoSysPro 3.1 실행 중…"; drawnow;
            ECMS_GITHUB("PackageRoot",rootDir, ...
                "SettingsTable",settingsTable.Data, ...
                "EquipmentTable",equipmentTable.Data);
            statusLabel.Text="GitHub OPC UA 결과를 Cloud ECMS로 가져왔습니다";
        catch caught
            statusLabel.Text="GitHub OPC UA 실행 실패";
            uialert(fig,caught.message,"GitHub OPC UA 오류","Icon","error");
        end
    end

    function validateA(~,~)
        messages=collectAErrors();
        if isempty(messages), uialert(fig,"A 설정 구조 검증 통과\nPROVISIONAL 값의 공학적 승인을 의미하지는 않습니다.","검증 완료","Icon","success");
        else, uialert(fig,join(messages,newline),"A 설정 오류","Icon","error"); end
    end
    function messages=collectAErrors()
        settings=settingsTable.Data; equipment=equipmentTable.Data;
        messages=strings(0,1);
        if any(~ismember(equipment.bus,["BUS-A","BUS-B"])), messages(end+1)="bus는 BUS-A 또는 BUS-B여야 합니다."; end
        if numel(unique(equipment.feeder_id))~=height(equipment), messages(end+1)="feeder_id가 중복되었습니다."; end
        if any(strlength(equipment.equipment_id)==0), messages(end+1)="equipment_id가 비어 있습니다."; end
        auxRow=settings(string(settings.setting_id)=="AUX_BUS_VOLTAGE_KV",:);
        if height(auxRow)~=1 || ~isfinite(str2double(string(auxRow.value(1)))) || str2double(string(auxRow.value(1)))~=6.9
            messages(end+1)="현재 VPP 기준전압은 6.9 kV여야 합니다.";
        end
    end

    function saveA(~,~)
        settings=settingsTable.Data; equipment=equipmentTable.Data;
        messages=collectAErrors();
        if ~isempty(messages), uialert(fig,join(messages,newline),"저장 중단","Icon","error"); return; end
        [file,path]=uiputfile("*.csv","A 설정 저장","ecms_a_settings.csv"); if isequal(file,0), return; end
        writeCsvText(settings,fullfile(path,file));
        writeCsvText(equipment,fullfile(path,"ecms_a_equipment.csv"));
        statusLabel.Text="A 설정 저장 완료 — M 파일은 변경되지 않음";
    end
    function saveLayout(~,~)
        [file,path]=uiputfile("*.json","레이아웃 저장","triplens_ecms_layout_v3_1.json"); if isequal(file,0), return; end
        layout=struct("version","3.1","topologyId","GT_ST_REVERSE_RECEIVE_6P9KV","mLocked",true,"topologyLocked",true,"nodes",nodes,"edges",edges);
        writeText(fullfile(path,file),jsonencode(layout,"PrettyPrint",true)); statusLabel.Text="레이아웃 JSON 저장 완료";
    end
    function loadLayout(~,~)
        [file,path]=uigetfile("*.json","레이아웃 불러오기"); if isequal(file,0), return; end
        try
            loaded=jsondecode(fileread(fullfile(path,file)));
            rejection=validateLoadedLayout(loaded);
        catch caught
            uialert(fig,"레이아웃 JSON을 읽을 수 없습니다."+newline+caught.message,"불러오기 거부","Icon","error"); return;
        end
        if strlength(rejection)>0
            uialert(fig,rejection,"불러오기 거부","Icon","error"); return;
        end
        % Only editable geometry is imported. Locked identifiers, labels,
        % endpoints, systems and node kinds always remain the local model's.
        for q=1:numel(nodes)
            nodes(q).x=double(loaded.nodes(q).x);
            nodes(q).y=double(loaded.nodes(q).y);
        end
        for q=1:numel(edges)
            edges(q).route=string(loaded.edges(q).route);
            edges(q).bend=double(loaded.edges(q).bend);
        end
        selectedEdge=1; edgeDrop.Value=1; refreshControls(); redraw();
        statusLabel.Text="레이아웃 불러오기 완료 — 잠긴 접속관계 검증됨";
    end
    function saveOverviewSvg(~,~)
        [file,path]=uiputfile("*.svg","Overview SVG 저장","triplens_ecms_vpp.svg"); if isequal(file,0), return; end
        writeOverviewSvg(fullfile(path,file),nodes,edges); statusLabel.Text="Overview SVG 저장 완료";
    end
    function saveDetailSvg(~,~)
        [file,path]=uiputfile("*.svg","6.9 kV 상세 SVG 저장","triplens_ecms_6p9kv.svg"); if isequal(file,0), return; end
        currentEquipment=equipmentTable.Data;
        messages=collectAErrors();
        if ~isempty(messages), uialert(fig,join(messages,newline),"SVG 저장 중단","Icon","error"); return; end
        writeDetailSvg(fullfile(path,file),currentEquipment,mLinks);
        statusLabel.Text="현재 A 설비·잠긴 M 연결로 6.9 kV 상세 SVG 저장 완료";
    end

    function message=validateLoadedLayout(loaded)
        message="";
        requiredTop=["topologyId","mLocked","topologyLocked","nodes","edges"];
        if ~isstruct(loaded) || ~isscalar(loaded) || any(~isfield(loaded,cellstr(requiredTop)))
            message="필수 레이아웃 잠금 정보가 없습니다."; return;
        end
        if ~isTrueScalar(loaded.mLocked) || ~isTrueScalar(loaded.topologyLocked)
            message="M 잠금과 topologyLocked가 모두 true여야 합니다."; return;
        end
        loadedTopologyId=string(loaded.topologyId);
        if ~isscalar(loadedTopologyId) || loadedTopologyId~="GT_ST_REVERSE_RECEIVE_6P9KV"
            message="현재 토폴로지 ID와 일치하지 않습니다."; return;
        end
        requiredNode=["id","x","y"];
        if ~isstruct(loaded.nodes) || numel(loaded.nodes)~=numel(nodes) || any(~isfield(loaded.nodes,cellstr(requiredNode)))
            message="노드 구조 또는 개수가 현재 잠긴 토폴로지와 다릅니다."; return;
        end
        if ~isequal([loaded.nodes.id],[nodes.id])
            message="노드 ID 또는 순서가 현재 잠긴 토폴로지와 다릅니다."; return;
        end
        if any(~arrayfun(@(item)isnumeric(item.x) && isscalar(item.x) && isnumeric(item.y) && isscalar(item.y),loaded.nodes))
            message="노드 좌표는 숫자 스칼라여야 합니다."; return;
        end
        nodeX=double([loaded.nodes.x]); nodeY=double([loaded.nodes.y]);
        if any(~isfinite(nodeX)) || any(~isfinite(nodeY)) || any(nodeX<0 | nodeX>1400) || any(nodeY<0 | nodeY>800)
            message="노드 좌표가 유효한 편집영역 밖에 있습니다."; return;
        end
        requiredEdge=["name","from","to","system","route","bend"];
        if ~isstruct(loaded.edges) || numel(loaded.edges)~=numel(edges) || any(~isfield(loaded.edges,cellstr(requiredEdge)))
            message="배선 구조 또는 개수가 현재 잠긴 토폴로지와 다릅니다."; return;
        end
        lockedFields=["name","from","to","system"];
        for fieldName=lockedFields
            key=char(fieldName);
            if ~isequal(string({loaded.edges.(key)}),string({edges.(key)}))
                message="잠긴 배선 "+fieldName+" 값이 현재 토폴로지와 다릅니다."; return;
            end
        end
        loadedRoutes=string({loaded.edges.route});
        if any(~ismember(loadedRoutes,["HV","VH","VHV","HVH"]))
            message="지원되지 않는 직각 경로가 포함되어 있습니다."; return;
        end
        if any(~arrayfun(@(item)isnumeric(item.bend) && isscalar(item.bend),loaded.edges))
            message="꺾임 좌표는 숫자 스칼라여야 합니다."; return;
        end
        bends=double([loaded.edges.bend]);
        if any(~isfinite(bends)) || any(bends<0 | bends>1400)
            message="꺾임 좌표가 유효하지 않습니다."; return;
        end
        if any(bends(loadedRoutes=="VHV")>800)
            message="VHV 경로의 세로 꺾임 좌표는 0~800이어야 합니다."; return;
        end
    end
end

function mustExist(pathValue)
if ~isfile(pathValue), error("TripLens:MissingFile","Required file not found: %s",pathValue); end
end

function value=readCsvText(pathValue)
% Explicit CSV settings prevent MATLAB Online from promoting a data row to
% variable names when every column happens to contain text.
fid=fopen(pathValue,"r","n","UTF-8");
if fid<0, error("TripLens:CsvOpenFailed","Could not open CSV: %s",pathValue); end
headerCleanup=onCleanup(@()fclose(fid));
headerLine=fgetl(fid);
if ~ischar(headerLine), error("TripLens:EmptyCsv","CSV is empty: %s",pathValue); end
columnCount=count(string(headerLine),",")+1;
clear headerCleanup
value=readtable(pathValue,"Delimiter",",","ReadVariableNames",true, ...
    "Format",repmat('%s',1,columnCount),"TextType","string", ...
    "VariableNamingRule","preserve");
if width(value)~=columnCount
    error("TripLens:CsvColumnMismatch", ...
        "CSV header has %d columns but MATLAB imported %d: %s",columnCount,width(value),pathValue);
end
end

function writeCsvText(value,pathValue)
% Keep the command/A interchange contract identical across desktop and
% MATLAB Online: comma delimiter, UTF-8 text and an explicit header row.
writetable(value,pathValue,"FileType","text","Delimiter",",", ...
    "WriteVariableNames",true,"Encoding","UTF-8");
end

function mustHaveColumns(value,required)
available=string(value.Properties.VariableNames);
missing=required(~ismember(required,available));
if ~isempty(missing)
    error("TripLens:MissingCsvColumn","Missing CSV column(s): %s",join(missing,", "));
end
end

function queue=emptyCommandQueue()
names=["sequence","time_s","equipment_id","equipment_label","command","command_value","unit", ...
    "execution_layer","model_input","feedback_tag","status","note"];
types=["double","double","string","string","string","string","string","string","string","string","string","string"];
queue=table('Size',[0 numel(names)],'VariableTypes',cellstr(types),'VariableNames',cellstr(names));
end

function validateCommandCatalog(catalog,mTags)
required=["equipment_id","label_ko","system","equipment_type","command","button_label","value_type", ...
    "min_value","max_value","default_value","unit","execution_layer","model_input","feedback_tag","status","notes"];
mustHaveColumns(catalog,required);
keys=string(catalog.equipment_id)+"/"+string(catalog.command);
assert(all(strlength(strtrim(keys))>1),"TripLens:CommandCatalog","Command Catalog에 빈 키가 있습니다.");
assert(numel(unique(keys))==height(catalog),"TripLens:CommandCatalog","Command Catalog에 중복 명령이 있습니다.");
layers=string(catalog.execution_layer);
assert(all(ismember(layers,["ELECTRICAL_ENGINE","THERMO_BOUNDARY","THERMO_ADAPTER_REQUIRED"])), ...
    "TripLens:CommandCatalog","알 수 없는 execution_layer가 있습니다.");
valueTypes=string(catalog.value_type);
assert(all(ismember(valueTypes,["DIGITAL","REAL"])),"TripLens:CommandCatalog","알 수 없는 value_type이 있습니다.");
equipmentIds=unique(string(catalog.equipment_id));
for index=1:numel(equipmentIds)
    assert(sum(string(catalog.equipment_id)==equipmentIds(index))<=8, ...
        "TripLens:CommandCatalog","설비당 Command는 최대 8개까지 표시할 수 있습니다: %s",equipmentIds(index));
end
realRows=catalog(valueTypes=="REAL",:);
if ~isempty(realRows)
    low=str2double(string(realRows.min_value));
    high=str2double(string(realRows.max_value));
    initial=str2double(string(realRows.default_value));
    assert(all(isfinite(low) & isfinite(high) & isfinite(initial) & low<=initial & initial<=high), ...
        "TripLens:CommandCatalog","REAL Command 범위 또는 기본값이 유효하지 않습니다.");
end
tspFeedback=string(catalog.feedback_tag);
tspFeedback=tspFeedback(startsWith(tspFeedback,"TSP."));
assert(all(ismember(tspFeedback,string(mTags.tag_id))), ...
    "TripLens:CommandCatalog","Command가 존재하지 않는 M feedback 태그를 참조합니다.");
end

function [background,foreground]=commandButtonColor(command)
foreground=[1 1 1];
switch char(string(command))
    case {'TRIP','LOSS','OUT_OF_SERVICE'}, background=[0.78 0.18 0.16];
    case {'STOP','OPEN','CLOSE'}, background=[0.91 0.48 0.10];
    case {'START','RESTORE','IN_SERVICE'}, background=[0.10 0.52 0.34];
    case {'RESET','AUTO','MANUAL'}, background=[0.19 0.40 0.72];
    otherwise, background=[0.37 0.29 0.62];
end
end

function position=initialFigurePosition(varargin)
desiredWidth=1500; desiredHeight=900;
if nargin>=1, desiredWidth=varargin{1}; end
if nargin>=2, desiredHeight=varargin{2}; end
screen=get(groot,"ScreenSize");
screenWidth=double(screen(3)); screenHeight=double(screen(4));
if screenWidth<=1, screenWidth=1600; end
if screenHeight<=1, screenHeight=1000; end
widthValue=min(desiredWidth,max(320,screenWidth-40));
heightValue=min(desiredHeight,max(360,screenHeight-70));
position=[max(1,round((screenWidth-widthValue)/2)), ...
    max(1,round((screenHeight-heightValue)/2)),widthValue,heightValue];
end

function tf=isTrueScalar(value)
tf=islogical(value) && isscalar(value) && value;
end

function [nodes,edges]=buildOverviewModel()
nodes=[ ...
    N("GRID_A","154 kV BUS-A","GRID-BUS-A",330,680,"bus154"),N("GRID_B","154 kV BUS-B","GRID-BUS-B",1070,680,"bus154"), ...
    N("SECTION","154 kV Bus Section","CB-154-TIE",700,680,"breaker_open"), ...
    N("TR_GT","GT Main TR ↕","TR-GT",330,565,"transformer"),N("GT_TAP","GT 13.8 kV TAP","GT-TAP",330,465,"bus"), ...
    N("CB52GT","52GT","CB-52GT",190,465,"breaker_closed"),N("GTG","GT Generator","GTG",70,465,"generator"), ...
    N("UAT_A","UAT-A","UAT-A",330,355,"transformer"),N("IN_A","A Incoming","CB-IN-A",330,250,"breaker_closed"), ...
    N("BUS_A","6.9 kV BUS-A","BUS-A",330,115,"bus"),N("TIE","6.9 kV Bus Tie","CB-TIE-AB",700,115,"breaker_open"), ...
    N("BUS_B","6.9 kV BUS-B","BUS-B",1070,115,"bus"),N("IN_B","B Incoming","CB-IN-B",1070,250,"breaker_closed"), ...
    N("UAT_B","UAT-B","UAT-B",1070,355,"transformer"),N("ST_TAP","ST 13.8 kV TAP","ST-TAP",1070,465,"bus"), ...
    N("CB52ST","52ST","CB-52ST",1210,465,"breaker_closed"),N("STG","ST Generator · M","STG",1330,465,"generator"), ...
    N("TR_ST","ST Main TR ↕","TR-ST",1070,565,"transformer")];
edges=[ ...
    E("154 BUS-A to GT Main TR","GRID_A","TR_GT","grid","VH",0),E("GT Main TR to GT TAP","TR_GT","GT_TAP","main","VH",0), ...
    E("GT TAP to 52GT","GT_TAP","CB52GT","main","HV",0),E("52GT to GTG","CB52GT","GTG","main","HV",0), ...
    E("GT TAP to UAT-A","GT_TAP","UAT_A","aux","VH",0),E("UAT-A to A Incoming","UAT_A","IN_A","aux","VH",0), ...
    E("A Incoming to BUS-A","IN_A","BUS_A","aux","VH",0),E("BUS-A to Tie","BUS_A","TIE","bus","HV",0), ...
    E("Tie to BUS-B","TIE","BUS_B","bus","HV",0),E("B Incoming to BUS-B","IN_B","BUS_B","aux","VH",0), ...
    E("UAT-B to B Incoming","UAT_B","IN_B","aux","VH",0),E("ST TAP to UAT-B","ST_TAP","UAT_B","aux","VH",0), ...
    E("52ST to ST TAP","CB52ST","ST_TAP","main","HV",0),E("STG to 52ST","STG","CB52ST","main","HV",0), ...
    E("ST Main TR to ST TAP","TR_ST","ST_TAP","main","VH",0),E("154 BUS-B to ST Main TR","GRID_B","TR_ST","grid","VH",0), ...
    E("154 kV bus section A","GRID_A","SECTION","grid","HV",0),E("154 kV bus section B","SECTION","GRID_B","grid","HV",0)];
end

function s=N(id,label,tag,x,y,kind), s=struct("id",id,"label",label,"tag",tag,"x",x,"y",y,"kind",kind); end
function s=E(name,from,to,system,route,bend), s=struct("name",name,"from",from,"to",to,"system",system,"route",route,"bend",bend); end
function c=wireColor(system)
switch system, case "grid", c=[0.79 0.27 0.24]; case "aux", c=[0.24 0.44 0.75]; otherwise, c=[0.22 0.35 0.47]; end
end
function writeText(pathValue,textValue)
fid=fopen(pathValue,"w","n","UTF-8"); assert(fid>=0,"Could not open output file."); cleanup=onCleanup(@()fclose(fid)); fwrite(fid,textValue,"char");
end
function writeOverviewSvg(pathValue,nodes,edges)
fid=fopen(pathValue,"w","n","UTF-8"); assert(fid>=0,"Could not open SVG."); cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="800" viewBox="0 0 1400 800">\n');
fprintf(fid,'<rect width="1400" height="800" fill="#f4f7fa"/><text x="25" y="32" font-family="Arial" font-size="22" font-weight="700">TripLens ECMS VPP Editor 3.1 — M locked / A editable / CommandBus</text>\n');
for q=1:numel(edges)
    a=nodes([nodes.id]==string(edges(q).from)); b=nodes([nodes.id]==string(edges(q).to)); color="#385a70";
    if edges(q).system=="grid", color="#c94540"; elseif edges(q).system=="aux", color="#376fc7"; end
    [x,y]=routePoints(edges(q),a,b);
    fprintf(fid,'<path d="M %.0f %.0f',x(1),800-y(1));
    for pointIndex=2:numel(x), fprintf(fid,' L %.0f %.0f',x(pointIndex),800-y(pointIndex)); end
    fprintf(fid,'" fill="none" stroke="%s" stroke-width="4"/>\n',color);
end
for q=1:numel(nodes)
    n=nodes(q); yy=800-n.y;
    if n.kind=="generator", fprintf(fid,'<circle cx="%.0f" cy="%.0f" r="22" fill="white" stroke="#1d64a5" stroke-width="4"/><text x="%.0f" y="%.0f" text-anchor="middle" font-family="Arial" font-weight="700">G</text>\n',n.x,yy,n.x,yy+5);
    elseif n.kind=="transformer", fprintf(fid,'<circle cx="%.0f" cy="%.0f" r="15" fill="white" stroke="#5947a8" stroke-width="3"/><circle cx="%.0f" cy="%.0f" r="15" fill="white" stroke="#5947a8" stroke-width="3"/>\n',n.x-9,yy,n.x+9,yy);
    elseif contains(n.kind,"breaker"), fprintf(fid,'<rect x="%.0f" y="%.0f" width="30" height="28" fill="%s" stroke="#7b3030" stroke-width="2"/>\n',n.x-15,yy-14,ternary(n.kind=="breaker_closed","#e04f47","white"));
    else, fprintf(fid,'<line x1="%.0f" y1="%.0f" x2="%.0f" y2="%.0f" stroke="%s" stroke-width="11"/>\n',n.x-60,yy,n.x+60,yy,ternary(n.kind=="bus154","#c94540","#2862bb")); end
    fprintf(fid,'<text x="%.0f" y="%.0f" text-anchor="middle" font-family="Arial" font-size="12" font-weight="700">%s</text><text x="%.0f" y="%.0f" text-anchor="middle" font-family="Arial" font-size="10" fill="#657784">%s</text>\n',n.x,yy-30,n.label,n.x,yy+38,n.tag);
end
fprintf(fid,'<text x="25" y="780" font-family="Arial" font-size="11" fill="#687985">Virtual design reference · no SST · not for operation, maintenance or LOTO</text></svg>\n');
end

function [x,y]=routePoints(edge,a,b)
switch string(edge.route)
    case "HV"
        x=[a.x b.x b.x]; y=[a.y a.y b.y];
    case "VH"
        x=[a.x a.x b.x]; y=[a.y b.y b.y];
    case "VHV"
        x=[a.x a.x b.x b.x]; y=[a.y edge.bend edge.bend b.y];
    case "HVH"
        x=[a.x edge.bend edge.bend b.x]; y=[a.y a.y b.y b.y];
    otherwise
        error("TripLens:InvalidRoute","Unsupported orthogonal route: %s",string(edge.route));
end
end

function writeDetailSvg(pathValue,equipment,mLinks)
% Generate the detail from the live A table and immutable M-link table.
equipmentIds=string(equipment.equipment_id);
detailLinks=mLinks(ismember(string(mLinks.ecms_equipment_id),equipmentIds),:);
fid=fopen(pathValue,"w","n","UTF-8"); assert(fid>=0,"Could not open SVG."); cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="900" viewBox="0 0 1500 900" role="img">\n');
fprintf(fid,['<defs><style>.bg{fill:#f4f7fa}.panel{fill:#fff;stroke:#d8e1e8;stroke-width:2}' ...
    '.title{font:700 28px Arial,sans-serif;fill:#16324a}.sub{font:14px Arial,sans-serif;fill:#607384}' ...
    '.bus{stroke:#2862bb;stroke-width:16;stroke-linecap:round}.wire{stroke:#376fc7;stroke-width:4;fill:none}' ...
    '.closed{fill:#e04f47;stroke:#9e2925;stroke-width:2}.open{fill:#fff;stroke:#7b8994;stroke-width:3}' ...
    '.label{font:700 13px Arial,sans-serif;fill:#243746;text-anchor:middle}.tag{font:11px Arial,sans-serif;fill:#617584;text-anchor:middle}' ...
    '.small{font:8px Arial,sans-serif;fill:#617584;text-anchor:middle}' ...
    '.m{fill:#e8f5ee;stroke:#3b9464;stroke-width:2}.a{fill:#fff5df;stroke:#d79a2b;stroke-width:2}' ...
    '.note{font:12px Arial,sans-serif;fill:#5d7080}</style></defs>\n']);
fprintf(fid,'<rect class="bg" width="1500" height="900"/><rect class="panel" x="25" y="24" width="1450" height="835" rx="18"/>\n');
fprintf(fid,'<text class="title" x="55" y="67">TripLens ECMS VPP Editor 3.1 — 6.9 kV SWGR</text>\n');
fprintf(fid,'<text class="sub" x="55" y="94">현재 A 설비표와 잠긴 M 연결표에서 동적으로 생성됨</text>\n');
busNames=["BUS-A","BUS-B"];
busLeft=[80,820]; busRight=[680,1420]; incomingX=[380,1120]; incomingNames=["IN-A","IN-B"];
for busIndex=1:2
    busName=busNames(busIndex); x1=busLeft(busIndex); x2=busRight(busIndex); incoming=incomingX(busIndex);
    subset=equipment(string(equipment.bus)==busName,:);
    fprintf(fid,'<text class="label" x="%.0f" y="135">UAT-%s</text><path class="wire" d="M%.0f 150 V245"/>\n',incoming,char(extractAfter(busName,"BUS-")),incoming);
    fprintf(fid,'<rect class="closed" x="%.0f" y="185" width="30" height="32" rx="3"/><text class="tag" x="%.0f" y="207">%s · 인커밍</text>\n',incoming-15,incoming+65,char(incomingNames(busIndex)));
    fprintf(fid,'<line class="bus" x1="%.0f" y1="245" x2="%.0f" y2="245"/><text class="label" x="%.0f" y="275">6.9 kV %s</text>\n',x1,x2,(x1+x2)/2,char(busName));
    if isempty(subset)
        fprintf(fid,'<text class="note" x="%.0f" y="350">배치된 A 설비 없음</text>\n',(x1+x2)/2);
        continue;
    end
    xPositions=linspace(x1+70,x2-70,height(subset));
    boxWidth=min(145,max(90,(x2-x1-20)/height(subset)-10));
    for rowIndex=1:height(subset)
        x=xPositions(rowIndex); eq=subset(rowIndex,:);
        equipmentId=string(eq.equipment_id); feederId=string(eq.feeder_id);
        breakerState=upper(string(eq.normal_breaker_state));
        breakerClass="open"; if strcmpi(breakerState,"CLOSED"), breakerClass="closed"; end
        ratedValue=string(eq.rated_kw);
        if ismissing(ratedValue) || strlength(strtrim(ratedValue))==0, ratedText="정격 미입력"; else, ratedText=ratedValue+" kW"; end
        equipmentMeta=string(eq.voltage_kv)+" kV · "+breakerState+" · "+ratedText;
        fprintf(fid,'<path class="wire" d="M%.0f 245 V390"/><rect class="%s" x="%.0f" y="315" width="30" height="32" rx="3"/>\n',x,char(breakerClass),x-15);
        fprintf(fid,'<text class="tag" x="%.0f" y="305">%s</text><rect class="a" x="%.0f" y="390" width="%.0f" height="76" rx="8"/>\n',x,char(xmlText(feederId)),x-boxWidth/2,boxWidth);
        fprintf(fid,'<text class="label" x="%.0f" y="414">%s</text><text class="tag" x="%.0f" y="436">%s · A</text><text class="small" x="%.0f" y="456">%s</text>\n', ...
            x,char(xmlText(eq.label_ko)),x,char(xmlText(equipmentId)),x,char(xmlText(equipmentMeta)));
        linked=mLinks(string(mLinks.ecms_equipment_id)==equipmentId,:);
        if isempty(linked)
            fprintf(fid,'<rect class="open" x="%.0f" y="480" width="%.0f" height="66" rx="8"/><text class="tag" x="%.0f" y="518">잠긴 M 연결 없음</text>\n',x-boxWidth/2,boxWidth,x);
        else
            firstTag=string(linked.source_m_tag_id(1));
            fprintf(fid,'<rect class="m" x="%.0f" y="480" width="%.0f" height="66" rx="8"/><text class="label" x="%.0f" y="505">M LOCKED · %d</text><text class="small" x="%.0f" y="530">%s</text>\n', ...
                x-boxWidth/2,boxWidth,x,height(linked),x,char(xmlText(firstTag)));
        end
    end
end
fprintf(fid,'<path class="wire" d="M680 245 H710"/><rect class="open" x="710" y="230" width="80" height="30" rx="3"/><path class="wire" d="M790 245 H820"/><text class="tag" x="750" y="292">TIE-AB · OPEN</text>\n');
fprintf(fid,'<rect class="m" x="80" y="615" width="1340" height="175" rx="10"/><text class="label" x="750" y="642">현재 상세도에 연결된 잠긴 M 목록 · %d개</text>\n',height(detailLinks));
for linkIndex=1:height(detailLinks)
    column=double(linkIndex>ceil(height(detailLinks)/2)); row=linkIndex-column*ceil(height(detailLinks)/2);
    x=105+column*655; y=670+(row-1)*22;
    lineText=string(detailLinks.link_id(linkIndex))+" · "+string(detailLinks.ecms_equipment_id(linkIndex))+" ← "+string(detailLinks.source_m_tag_id(linkIndex));
    fprintf(fid,'<text class="note" x="%.0f" y="%.0f">%s</text>\n',x,y,char(xmlText(lineText)));
end
fprintf(fid,'<text class="note" x="55" y="835">Editor 3.1 dynamic export · 가상 설계 기준도 · 운전/정비/LOTO용 아님</text></svg>\n');
end

function out=xmlText(value)
out=string(value);
if any(ismissing(out)), out(ismissing(out))=""; end
out=replace(out,"&","&amp;");
out=replace(out,"<","&lt;");
out=replace(out,">","&gt;");
end
function out=ternary(condition,a,b), if condition, out=a; else, out=b; end, end
