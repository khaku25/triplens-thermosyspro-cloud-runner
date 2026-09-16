# TripLens Demo Guide
## Local V8 + Gemini

## 1. 데모 목표

현장 시연의 목표는 전체 Virtual Plant 개발환경을 보여주는 것이 아니다.

보여줄 핵심:
1. 사고 데이터가 생성/존재함
2. EVENT와 RAW가 분리되어 있음
3. TripLens가 동일 입력계약으로 분석함
4. Gemini가 Evidence 기반 결과를 냄
5. 결과에 근거와 복구 확인사항이 있음

## 2. 권장 시연 순서

### A. Runtime Ready 화면
- Local V8 Ready
- OPC UA Connected
- Alarm Runtime Ready
- EVENT/RAW Ready
- Gemini Ready

### B. Incident
대표 사고 1건 실행 또는 Verified Replay 선택

### C. Input 확인
- EVENT.csv
- RAW.csv
- Run ID

### D. TripLens 분석
보여줄 화면:
- Incident Summary
- Critical Events
- Causal Timeline
- Evidence
- Recovery Check
- Gemini Analysis

### E. Generalization
GT/Feeder/Third Case 결과를 Scorecard로 비교.

## 3. Live / Replay 전략

### Live
- 이미 실행 준비가 끝난 V8 Runtime 사용
- 모델/서버 설치 과정을 발표 중 수행하지 않음
- 20~40초 안에 사고/데이터/분석으로 이동

### Verified Replay
- 미리 봉인한 EVENT/RAW Run 사용
- Live와 동일 TripLens Engine으로 분석
- 인터넷/API 장애 시 결과 재현

Replay는 숨기는 fallback이 아니라 **검증된 시험 데이터 재생 모드**로 설명한다.

## 4. 발표장에서 숨길 것

- 긴 solver debug log
- 개발중 patch script 목록
- 오래된 v5/v6/v7 설명
- 과거 실패 trace
- GitHub Action 중심 화면
- 불필요한 NodeId/port 상세
- 후보 Logic Master 전체 목록

질문이 들어오면 Appendix/Evidence로 보여준다.

## 5. 질문 대응 핵심

### Q. AI가 그냥 요약하는 것 아닌가?
A. EVENT와 RAW를 deterministic engineering layer가 먼저 정렬·검증하고, Gemini는 그 Evidence를 이용해 원인/파급/복구 정보를 구성한다.

### Q. 정답을 미리 넣은 것 아닌가?
A. Blind Test에서는 Scenario ID, Expected Cause, Ground Truth를 분석 입력에서 분리한다.

### Q. 현장제어도 하나?
A. 아니다. READ-ONLY decision support이며 OT write/automatic restoration은 없다.

### Q. 실제 발전소 정확도인가?
A. 아니다. 현재는 Virtual Plant/Synthetic validation이며 현장정확도는 별도 검증이 필요하다.

### Q. GT Trip 하나에 맞춘 것 아닌가?
A. 동일 RC Engine으로 여러 사고군 Blind Run을 수행하고 Code Change=0 및 Scorecard로 제시한다.

## 6. 제출 전 데모 체크리스트

- [ ] RC1 Freeze
- [ ] 대표 Live Case 결정
- [ ] Verified Replay 3개 이상
- [ ] Gemini model/connection 안정화
- [ ] 인터넷 OFF fallback 확인
- [ ] Clean-folder 실행
- [ ] 화면 확대/DPI 확인
- [ ] 발표 10분 내 시연 완료
