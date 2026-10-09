# Release checklist / 릴리스 체크리스트

Every release keeps **English and Korean** documents in sync (Japanese later).
모든 릴리스는 **영어와 한국어** 문서를 함께 갱신해요 (일본어는 나중에).

## 1. Prepare / 준비
- [ ] Bump `APP_VERSION` in `rh/config.py` / `rh/config.py`의 `APP_VERSION` 올리기
- [ ] Add the new version at the top of **both** `CHANGELOG.md` (English) and `CHANGELOG.ko.md` (한국어)
      `CHANGELOG.md`(영어)와 `CHANGELOG.ko.md`(한국어) **둘 다** 맨 위에 새 버전 추가
- [ ] If network access, downloads or stored data changed, update `PRIVACY.en.md`, `PRIVACY.ko.md` (and `PRIVACY.ja.md`)
      네트워크 접속·다운로드·저장 데이터가 바뀌었다면 PRIVACY 문서(en/ko/ja)도 갱신
- [ ] If dependencies changed, regenerate `THIRD_PARTY_NOTICES.txt` / 의존 패키지가 바뀌었다면 `THIRD_PARTY_NOTICES.txt` 다시 생성
- [ ] README.md and README.ko.md still match each other / README 영어·한국어가 서로 맞는지 확인

## 2. Check before publishing / 올리기 전 확인
- [ ] No personal data in files or commit history (email, local paths, keys): commits use the GitHub `noreply` address
      파일·커밋 기록에 개인정보(이메일, 로컬 경로, 키) 없음: 커밋은 GitHub `noreply` 주소 사용
- [ ] `build.bat` succeeds and the exe starts / 빌드 후 exe 실행 확인

## 3. Publish / 공개
- [ ] Commit and push to `main` / 커밋 후 `main`에 push
- [ ] Tag `vX.Y.Z` and create a GitHub Release with notes in **both languages**: English first, then Korean (separate headings)
      `vX.Y.Z` 태그 후 GitHub Release 생성, 릴리스 노트는 **영어 → 한국어** 순서로 제목을 나눠서 작성
- [ ] Attach the zipped `dist/HaruMimi` folder / `dist/HaruMimi` 폴더를 zip으로 묶어 첨부
