# AKFES v2 Migration

이 브랜치는 AKFES를 다음 구조로 리팩터링하기 위한 전용 작업 공간입니다.

- Desktop: Tauri v2 + Rust + React + TypeScript
- Server: FastAPI + Uvicorn
- Hardware: Arduino UNO + USB Serial
- Security: 서버 중심 권한 검증, 장치 바인딩, 일회용 챌린지, 요청 서명, AES-256-GCM

## 목표 구조

```text
apps/
  desktop/
    src/
    src-tauri/
server/
  app/
firmware/
  arduino/
docs/
```

## 현재 단계

- [x] v2 전용 브랜치 생성
- [ ] Tauri 프로젝트 초기화
- [ ] 기존 Electron/PySide6 코드 제거
- [ ] FastAPI 서버 이전
- [ ] Arduino 통신 모듈 이전
- [ ] 빌드 및 배포 구성
