# 🐰 HaruMimi — by RabbitHaru

VRChat 전용 음성 인식(STT) 번역기. 마이크로 말하면 인식 → (번역) → VRChat 채팅박스(OSC)로 자동 전송합니다.
한국어 / 日本語 / English 지원. **정확성 · 신속성 · 가벼움**을 최우선으로 만들었어요.

## 사용법
1. VRChat 액션 메뉴 → Options → OSC → **Enabled** 켜기
2. `HaruMimi.exe` 실행 → 첫 실행 안내 확인 → 번역할 언어(또는 받아쓰기) 선택 → **시작**
3. 처음에는 음성 모델 다운로드 허락을 물어봐요 (크기를 알려드려요)

## 특징
- 로컬 Whisper(faster-whisper)로 인식: 사용량 한도 없음, 음성은 PC 밖으로 나가지 않음
- 오프라인 번역(M2M100): 한도 없음, 문장당 약 0.2초, 문장도 PC 밖으로 나가지 않음. VRChat 용어·이름 보호, 표준/고품질 선택 (DeepL 등 공식 API 키 연결도 가능)
- 받아쓰기(STT) 모드: 번역 없이 인식 결과만 표시/전송
- 말하는 중 실시간 미리보기, 모델 미리 로드로 빠른 시작
- 노이즈 제거 + 주변 소음에 맞춘 마이크 자동 조절, 마이크 레벨/기준선 표시
- PC 사양에 맞는 모델 자동 선택, GPU가 없으면 CPU로 자동 전환
- VRChat 뮤트 연동, 직접 입력 번역, 밝은/어두운 테마, 앱 언어 선택

## 개인정보
개발자는 개인정보를 수집하지 않아요. 온라인 번역 서비스 사용과 새 버전 확인은 **동의한 경우에만**
동작하고, 모델 다운로드는 **매번 허락을 받아요**. 자세한 내용: [한국어](PRIVACY.ko.md) · [English](PRIVACY.en.md) · [日本語](PRIVACY.ja.md)

## 개발
```
pip install -r requirements.txt
python HaruMimi.py
```
exe 빌드는 `build.bat`. 설정과 모델은 `%APPDATA%\RabbitHaru` 에 저장됩니다.
업데이트 내역은 [CHANGELOG.md](CHANGELOG.md) 를 참고하세요.

## 고지 (Notices)
- 이 프로젝트는 VRChat Inc., OpenAI, Google LLC와 제휴·후원·보증 관계가 없는 개인 프로젝트입니다.
  "VRChat"은 VRChat Inc.의, "Google"/"Google 번역"은 Google LLC의 상표입니다.
- 번역은 기본적으로 내 PC에서 도는 오프라인 모델(M2M100, MIT 라이선스)을 쓰며, 온라인 서비스(MyMemory/DeepL/Google Cloud)는
  사용자가 직접 고르고 동의한 경우에만 공식 API로 이용합니다. 번역·인식 결과의 정확성은 보증하지 않으며,
  VRChat 채팅박스에 보낸 내용의 책임은 사용자에게 있습니다.
- 마이크에 다른 사람의 목소리가 들어올 수 있는 환경에서는 상대방의 동의와 관련 법규(통신비밀보호법 등)에 유의하세요.
- 사용한 오픈소스와 라이선스는 [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt) 에 있습니다.
- 소프트웨어는 "있는 그대로" 제공되며, 사용으로 인한 어떤 손해에도 책임을 지지 않습니다.
