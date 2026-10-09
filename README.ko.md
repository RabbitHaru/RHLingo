# 🐰 HaruMimi — by RabbitHaru

🇺🇸 English: [README.md](README.md)

VRChat 채팅박스용 음성 인식(STT) 번역기예요. 마이크로 말하면 인식 → (번역) → VRChat 채팅박스(OSC)로 자동 전송해요. 한국어 / 日本語 / English. **정확성 · 신속성 · 가벼움**을 최우선으로 만들었어요.

## 사용법
1. VRChat 액션 메뉴 → Options → OSC → **Enabled** 켜기
2. `HaruMimi.exe` 실행 → 첫 실행 개인정보 안내 확인 → 번역할 언어(또는 "받아쓰기") 선택 → **시작**
3. 처음에는 음성 모델을 받기 전에 크기를 알려드리고 허락을 물어봐요. 모델은 설정 → 음성 인식에서 직접 받고 지울 수도 있어요

## 특징
- 로컬 음성 인식(faster-whisper): 사용 한도 없음, 목소리는 PC 밖으로 나가지 않음
- 오프라인 번역(M2M100): 한도 없음, 문장당 약 0.2초, 문장도 PC 밖으로 나가지 않음. DeepL / Google Cloud는 내 API 키로 연결 가능
- 말이 끝난 뒤 번역 결과까지 약 0.9초 (16코어 PC, `small` 모델 기준. PC마다 달라요)
- 번역에서 VRChat 용어와 내 이름 보호, 한국어 조사 교정
- 노이즈 제거, 목소리 대역 감지(책상 치는 소리 무시), 마이크 자동 맞춤
- 말하는 중 실시간 미리보기, 받아쓰기 모드, VRChat 뮤트 연동, 직접 입력 번역
- 밝은/어두운 테마, 한국어 / 日本語 / English 화면

## 개인정보
개발자는 개인정보를 수집하지 않아요. 온라인 번역 서비스와 새 버전 확인은 **동의한 경우에만** 동작하고, 다운로드는 **매번 허락을 받아요**. 자세한 내용: [한국어](PRIVACY.ko.md) · [English](PRIVACY.en.md) · [日本語](PRIVACY.ja.md)

## 개발
```
pip install -r requirements.txt
python HaruMimi.py
```
exe 빌드는 `build.bat`. 설정과 모델은 `%APPDATA%\RabbitHaru`에 저장돼요.
업데이트 내역: [CHANGELOG.ko.md](CHANGELOG.ko.md). 릴리스 체크리스트: [RELEASING.md](RELEASING.md).

## 고지
- 이 프로젝트는 VRChat Inc., OpenAI, Google LLC와 제휴·후원·보증 관계가 없는 개인 프로젝트예요. "VRChat"은 VRChat Inc.의, "Google"은 Google LLC의 상표예요.
- 번역은 기본적으로 내 PC에서 도는 오프라인 모델(M2M100, MIT 라이선스)을 써요. 온라인 서비스(MyMemory / DeepL / Google Cloud)는 사용자가 직접 고르고 동의한 경우에만 공식 API로 이용해요.
- 번역·인식 결과의 정확성은 보증하지 않으며, VRChat 채팅박스에 보낸 내용의 책임은 사용자에게 있어요.
- 마이크에 다른 사람의 목소리가 들어올 수 있는 환경에서는 상대방의 동의와 관련 법규(통신비밀보호법 등)에 유의하세요.
- 사용한 오픈소스와 라이선스: [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt)
- [MIT 라이선스](LICENSE)로 배포돼요. 소프트웨어는 "있는 그대로" 제공되며 어떤 보증도 하지 않아요.
