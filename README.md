# 🐰 RabbitHaru Translator

VRChat 전용 음성 인식 번역기. 마이크로 말하면 인식 → 번역 → VRChat 채팅박스(OSC)로 자동 전송합니다.
한국어 / 日本語 / English 지원.

## 사용법
1. VRChat 액션 메뉴 → Options → OSC → **Enabled** 켜기
2. `RabbitHaruTranslator.exe` 실행 → 번역할 언어 선택 → **시작**

## 특징
- 로컬 Whisper(faster-whisper)로 인식: 사용량 한도 없음
- GPU가 있으면 자동 가속, 없으면 CPU로 자동 전환
- VRChat 뮤트 연동, 일시정지, 직접 입력 번역, 밝은/어두운 테마, 앱 언어 선택

## 개발
```
pip install -r requirements.txt
python RabbitHaruTranslator.py
```
exe 빌드는 `build.bat`. 설정과 모델은 `%APPDATA%\RabbitHaru` 에 저장됩니다.
업데이트 내역은 [CHANGELOG.md](CHANGELOG.md) 를 참고하세요.
