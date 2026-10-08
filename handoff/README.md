# TripLens ThermoSysPro 4.2 실패 분석 인수인계

기준일: 2026-10-08  
목적: 다음 채팅에서 원인 분석을 이어갈 수 있도록 확인된 증거, 아직 검증되지 않은 가설, 다음 조사 순서를 기록합니다.

## 현재 상태

- 진단 대상 브랜치: experiment/thermosyspro-4.2
- 조사 기준 커밋: 56be93386b9d573ee86f6f19cd08f811b3d752e6
- 커밋 메시지: diagnose: propagate model caller into Ph errors
- 위 커밋의 GitHub Actions Run 71은 초기화 단계에서 실패했습니다: [Run 71 결과와 로그](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/actions/runs/37578442178)
- 워크플로는 ThermoSysPro 커밋 a896ab75ce22162369e7fa4ce79927eeca44ad4a와 OpenModelica 1.27.1을 사용합니다.
- 이 인수인계 문서는 별도 브랜치 handoff/thermosyspro-42-20261008에서 관리합니다. 이번 인수인계 변경은 이 README 하나뿐이며, 진단 브랜치의 코드와 워크플로는 수정하지 않았습니다.

## 재현된 실패와 직접 관측

TripLens_CombinedCycle_TripTAC 모델의 t=0 초기화 중 KINSOL 비선형 시스템 5693(size 321)이 수렴하지 않았습니다. 시작 상태 값은 대체로 그럴듯했지만, 반복 중 물성 함수에 IF97 유효 영역 밖의 압력·엔탈피 값이 전달되었고 recoverable function error와 line-search 실패가 반복됐습니다.

Run 71에서 가장 먼저 식별된 잘못된 물성 호출은 다음 위치입니다.

- 모델 인스턴스: TripLens_CombinedCycle_TripTAC.SurchauffeurBP.TwoPhaseFlowPipe
- ThermoSysPro 소스: WaterSteam/HeatExchangers/DynamicTwoPhaseFlowPipe.mo
- 호출 위치: pro1[i], 첫 번째 호출(call 1)
- 실패한 solver trial: p=562367 Pa, h=1.1135e10 J/kg, mode=0
- 뒤이은 backtracking 엔탈피 trial: 5.56899e9, 2.78601e9, 1.39452e9, 6.98771e8 J/kg
- 초기 압력 약 0.51 MPa와 초기 엔탈피 약 2.68–2.92 MJ/kg는 합리적인 범위였습니다.

추가로 다음 호출도 잘못된 상태를 받았습니다.

- VolumeC 인스턴스 MelangeurPostTMP1에서 p=476800 Pa일 때 h=1.56206e7 J/kg 및 9.39055e6 J/kg
- 다른 pipe trial에서는 음의 압력 또는 매우 큰 엔탈피 값도 관측됐습니다.

관측된 값은 초기 상태 자체가 모두 비현실적이라기보다, 초기화 solver가 반복하는 동안 IF97 물성 영역을 벗어난 trial 값을 만든 상황과 일치합니다. 이 사실만으로 solver가 실패한 최초 원인까지 확정되지는 않습니다.

## 조사 과정에서 확인한 점

- Run 68은 물성 함수 호출 위치까지만 보여 주었습니다.
- Run 69의 모델 equation assertion은 KINSOL 로그에서 유효한 caller 진단을 제공하지 못했습니다.
- Run 70의 직접 Water_Ph 계측도 호출자를 충분히 좁히지 못했습니다.
- Run 71에서 caller 정보를 물성 오류까지 전달해 첫 번째 문제 호출과 모델 인스턴스를 식별했습니다.
- 별도로 실행한 unseeded upstream ThermoSysPro 예제도 초기화 중 압력이 IF97 triple point 611.657 Pa 아래로 내려가는 실패가 있었습니다. 다만 이는 다른 실행이며 TripLens의 직접 원인을 입증하지 않습니다.
- IF97 압력 영역 회귀 확인은 10–16.5292 MPa 범위에서 통과했습니다. 이는 물성 영역 검사 자체에 대한 숫자 회귀일 뿐, TripLens 전체 모델의 수렴 검증은 아닙니다.

## 미확정 가설: 엔탈피 변수 스케일

변수 표에서 일부 specific enthalpy 초기화 unknown의 nominal이 1로 보였습니다. 예를 들면 TurbineMP.Cs.h, MelangeurPostTMP1.h, pipe hb[] 및 일부 connector 엔탈피입니다. 같은 pipe 내부 상태 h[]에는 nominal 약 1e6이 지정되어 있었습니다. 이 차이는 엔탈피가 수 MJ/kg인 문제에서 초기화 방정식 스케일을 나쁘게 만들 가능성이 있습니다.

이전 작업 공간에서 ThermoSysPro.Units.SI.SpecificEnthalpy nominal을 1e6으로 바꾸는 후보 수정과 합성 단위 검사 5개를 시험했으며, 그 검사들은 통과했습니다. 그러나 후보 수정은 커밋되지 않았고 작업 공간 정리 후 초안도 남아 있지 않습니다. 실제 TripLens 물리 시뮬레이션으로 검증되지 않았으므로 해결책으로 간주하면 안 됩니다.

## 다음 채팅에서 권장하는 순서

1. Run 71 로그와 artifact를 내려받아 위 수치와 모델 인스턴스를 확인합니다.
2. 워크플로가 고정한 ThermoSysPro 소스에서 Units/SI/SpecificEnthalpy 선언을 확인하고, 모델 변수 nominal 및 start/fixed 값을 실제 소스와 대조합니다.
3. 우선 작은 초기화 재현 또는 테스트로 nominal 스케일 변경의 효과를 분리해 확인합니다.
4. 임시 작업 브랜치에서만 후보 변경을 적용한 뒤 단위 검사와 전체 물리 시뮬레이션을 실행합니다. 성공 여부뿐 아니라 첫 IF97 오류와 VolumeC 오류가 사라지는지 확인합니다.
5. 스케일 변경으로 해결되지 않으면 초기 잔차, Jacobian 조건, initialization constraint, start/fixed 설정을 조사합니다.
6. solver가 만든 유효 영역 밖 trial 값을 원인과 혼동하지 않습니다. 경계 검사나 입력 clamp만 추가하면 실제 초기화 불일치를 숨길 수 있습니다.

## 현재 기준선과 작업 경계

다음 조사 기준은 experiment/thermosyspro-4.2의 56be93386b9d573ee86f6f19cd08f811b3d752e6입니다. 이 커밋 이후 진단 브랜치에는 추가 수정이 없습니다. Run 71은 실패한 상태이며, nominal 스케일 후보는 물리 시뮬레이션에서 검증되지 않았습니다.

문서 전용 handoff 브랜치의 push는 ThermoSysPro 물리 시뮬레이션 워크플로의 브랜치 조건에 해당하지 않습니다. 새 채팅에서는 위 증거를 바탕으로 원인 검증을 계속하고, 검증 전에는 후보 가설을 확정된 해결로 기록하지 마세요.
