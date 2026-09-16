# TripLens Demo Guide

## 1. 시연에서 보여줄 것

1. EVENT.csv + RAW.csv 입력
2. TripLens 분석 시작
3. Critical Events
4. Causal Timeline
5. Key Evidence
6. Gemini 사고해석
7. Recovery Check
8. 다른 사고 Replay 결과 또는 Scorecard

## 2. 시연에서 길게 보여주지 않을 것

- OpenModelica 설치/빌드 과정
- 긴 solver log
- OPC UA node 전체
- Protection Matrix 세부
- 과거 v5/v6/v7 개발이력
- GitHub Action 디버깅

이 내용은 질문 시 Appendix로 제시한다.

## 3. Live + Verified Replay

### Live
준비가 끝난 Local Runtime 또는 검증된 EVENT/RAW 입력으로 TripLens 실제 분석을 실행한다.

### Verified Replay
미리 저장한 Run ID의 EVENT/RAW를 동일 TripLens Engine으로 재분석한다. 인터넷/API 장애 등 현장리스크를 줄이는 보조경로다.

## 4. 예상 질문 핵심답변

**Q. AI가 그냥 요약하는 것 아닌가?**  
EVENT와 RAW를 Engineering Layer가 시간정렬·Evidence 구조화한 후 Gemini가 그 근거를 사용한다.

**Q. 정답을 미리 넣은 것 아닌가?**  
Blind Test에서는 Scenario ID, Expected Cause, Ground Truth를 입력에서 분리한다.

**Q. 현장제어도 하나?**  
아니다. READ-ONLY decision support이고 OT write/automatic restoration은 없다.

**Q. GT Trip 전용 아닌가?**  
동일 RC Engine으로 서로 다른 사고군을 Blind Run하고 Code Change=0 및 정량 Scorecard로 확인한다.

## 5. 제출 전 체크

- [ ] RC Freeze
- [ ] 대표 Demo Case 확정
- [ ] Verified Replay 준비
- [ ] Gemini 연결상태 확인
- [ ] API 장애 fallback 확인
- [ ] Clean-folder 실행
- [ ] 발표 10분 이내 확인
