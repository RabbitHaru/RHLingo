"""앱 화면 언어 (ko / ja / en) 와 언어 이름 표시."""
LANGS = ("ko", "ja", "en")
NATIVE = {"ko": "한국어", "ja": "日本語", "en": "English"}
NAME_IN = {
    "ko": {"ko": "한국어", "ja": "일본어", "en": "영어"},
    "ja": {"ko": "韓国語", "ja": "日本語", "en": "英語"},
    "en": {"ko": "Korean", "ja": "Japanese", "en": "English"},
}

STR = {
    "en": {
        "title": "RabbitHaru Translator", "start": "Start", "stop": "Stop", "stopping": "Stopping…",
        "st_idle": "Idle", "st_loading": "Loading model… (first run downloads it)",
        "st_listening": "Listening", "st_paused": "Paused", "st_muted": "Muted in VRChat",
        "pause": "Pause", "resume": "Resume", "translate_to": "Translate to",
        "type_hint": "Type here to translate & send…", "send": "Send",
        "empty": "Speak into your mic.\nTranslations will show up here.",
        "info_gpu": "Running with GPU acceleration", "info_cpu": "Running on CPU (GPU unavailable)",
        "info_osc_busy": "OSC port is in use, VRChat mute sync is off", "err": "Error",
        "settings": "Settings", "sec_general": "General", "ui_lang": "App language", "theme": "Theme",
        "theme_system": "System", "theme_light": "Light", "theme_dark": "Dark",
        "always_on_top": "Always on top", "sec_audio": "Speech recognition", "mic": "Microphone",
        "mic_default": "Default device", "refresh": "Refresh", "speech_lang": "Language I speak",
        "auto": "Auto detect", "model": "Recognition model", "device": "Processor",
        "dev_auto": "Auto", "dev_gpu": "GPU", "dev_cpu": "CPU",
        "m_tiny": "tiny · fastest, lowest accuracy", "m_base": "base · fast",
        "m_small": "small · balanced (recommended)", "m_medium": "medium · accurate, slower",
        "m_large-v3-turbo": "large-v3-turbo · best (GPU recommended)",
        "sensitivity": "Mic sensitivity", "silence": "Pause before sending", "sec_vrc": "VRChat",
        "show_original": "Show original text too", "vrc_mute": "Sync with VRChat mute (ignore speech while muted)",
        "osc_port": "OSC port", "restart_note": "Model / mic / processor changes restart automatically.",
        "close": "Close", "tr_failed": "Translation failed",
        "about": "Info", "tab_new": "What's new", "tab_fb": "Feedback", "tab_support": "Support",
        "fb_hint": "Found a bug or have an idea? Tell me!", "fb_box": "Write your feedback here…",
        "fb_github": "Send via GitHub", "fb_form": "Open feedback form", "fb_log": "Open log folder",
        "fb_none": "Feedback link is not set up yet.",
        "support_text": "RabbitHaru Translator is free. If it helps you, a little support keeps updates coming. Thank you!",
        "support_none": "Support links are coming soon.",
        "update_avail": "New version available", "version": "Version", "no_changelog": "No update notes.",
    },
    "ko": {
        "title": "RabbitHaru 번역기", "start": "시작", "stop": "중지", "stopping": "중지 중…",
        "st_idle": "대기 중", "st_loading": "모델 준비 중… (처음엔 다운로드로 오래 걸려요)",
        "st_listening": "듣는 중", "st_paused": "일시정지", "st_muted": "VRChat 뮤트 중",
        "pause": "일시정지", "resume": "다시 듣기", "translate_to": "번역할 언어",
        "type_hint": "직접 입력해서 번역·전송…", "send": "보내기",
        "empty": "마이크에 대고 말해보세요.\n번역 결과가 여기에 쌓여요.",
        "info_gpu": "GPU 가속으로 실행 중", "info_cpu": "CPU로 실행 중 (GPU 사용 불가)",
        "info_osc_busy": "OSC 포트가 사용 중이라 VRChat 뮤트 연동을 껐어요", "err": "오류",
        "settings": "설정", "sec_general": "일반", "ui_lang": "앱 언어", "theme": "테마",
        "theme_system": "시스템", "theme_light": "밝게", "theme_dark": "어둡게",
        "always_on_top": "항상 위에 표시", "sec_audio": "음성 인식", "mic": "마이크",
        "mic_default": "기본 장치", "refresh": "새로고침", "speech_lang": "내가 말하는 언어",
        "auto": "자동 감지", "model": "인식 모델", "device": "연산 장치",
        "dev_auto": "자동", "dev_gpu": "GPU", "dev_cpu": "CPU",
        "m_tiny": "tiny · 가장 빠름 (정확도 낮음)", "m_base": "base · 빠름",
        "m_small": "small · 균형 (추천)", "m_medium": "medium · 정확 (느림)",
        "m_large-v3-turbo": "large-v3-turbo · 최고 정확 (GPU 권장)",
        "sensitivity": "마이크 민감도", "silence": "말 끝 판단 시간", "sec_vrc": "VRChat",
        "show_original": "원문도 함께 표시", "vrc_mute": "VRChat 뮤트와 연동 (뮤트 중엔 인식 안 함)",
        "osc_port": "OSC 포트", "restart_note": "모델·마이크·장치를 바꾸면 자동으로 다시 시작돼요.",
        "close": "닫기", "tr_failed": "번역 실패",
        "about": "정보", "tab_new": "업데이트 내역", "tab_fb": "피드백", "tab_support": "후원",
        "fb_hint": "버그나 아이디어가 있나요? 알려주세요!", "fb_box": "피드백을 여기에 적어주세요…",
        "fb_github": "GitHub로 보내기", "fb_form": "피드백 폼 열기", "fb_log": "로그 폴더 열기",
        "fb_none": "피드백 링크가 아직 준비되지 않았어요.",
        "support_text": "RabbitHaru 번역기는 무료예요. 도움이 되셨다면 작은 후원이 업데이트에 큰 힘이 돼요. 감사합니다!",
        "support_none": "후원 링크는 준비 중이에요.",
        "update_avail": "새 버전이 있어요", "version": "버전", "no_changelog": "업데이트 내역이 없어요.",
    },
    "ja": {
        "title": "RabbitHaru 翻訳機", "start": "開始", "stop": "停止", "stopping": "停止中…",
        "st_idle": "待機中", "st_loading": "モデル準備中… (初回はダウンロードで時間がかかります)",
        "st_listening": "聞き取り中", "st_paused": "一時停止", "st_muted": "VRChatでミュート中",
        "pause": "一時停止", "resume": "再開", "translate_to": "翻訳先",
        "type_hint": "入力して翻訳・送信…", "send": "送信",
        "empty": "マイクに向かって話してください。\n翻訳結果がここに表示されます。",
        "info_gpu": "GPUで実行中", "info_cpu": "CPUで実行中 (GPU使用不可)",
        "info_osc_busy": "OSCポートが使用中のため、VRChatミュート連動をオフにしました", "err": "エラー",
        "settings": "設定", "sec_general": "一般", "ui_lang": "アプリの言語", "theme": "テーマ",
        "theme_system": "システム", "theme_light": "ライト", "theme_dark": "ダーク",
        "always_on_top": "常に手前に表示", "sec_audio": "音声認識", "mic": "マイク",
        "mic_default": "既定のデバイス", "refresh": "更新", "speech_lang": "話す言語",
        "auto": "自動検出", "model": "認識モデル", "device": "演算装置",
        "dev_auto": "自動", "dev_gpu": "GPU", "dev_cpu": "CPU",
        "m_tiny": "tiny · 最速 (精度低)", "m_base": "base · 高速",
        "m_small": "small · バランス (推奨)", "m_medium": "medium · 高精度 (遅い)",
        "m_large-v3-turbo": "large-v3-turbo · 最高精度 (GPU推奨)",
        "sensitivity": "マイク感度", "silence": "発話終了の判定時間", "sec_vrc": "VRChat",
        "show_original": "原文も一緒に表示", "vrc_mute": "VRChatのミュートと連動 (ミュート中は認識しない)",
        "osc_port": "OSCポート", "restart_note": "モデル・マイク・装置の変更は自動で再起動します。",
        "close": "閉じる", "tr_failed": "翻訳に失敗しました",
        "about": "情報", "tab_new": "更新履歴", "tab_fb": "フィードバック", "tab_support": "応援",
        "fb_hint": "バグやアイデアがあれば教えてください!", "fb_box": "ここにフィードバックを書いてください…",
        "fb_github": "GitHubで送る", "fb_form": "フィードバックフォームを開く", "fb_log": "ログフォルダを開く",
        "fb_none": "フィードバックのリンクはまだ準備中です。",
        "support_text": "RabbitHaru翻訳機は無料です。役に立ったら、ささやかな応援がアップデートの力になります。ありがとうございます!",
        "support_none": "応援リンクは準備中です。",
        "update_avail": "新しいバージョンがあります", "version": "バージョン", "no_changelog": "更新履歴はありません。",
    },
}

_lang = "en"


def set_lang(code):
    global _lang
    _lang = code if code in STR else "en"


def T(key):
    return STR[_lang].get(key) or STR["en"].get(key, key)


def lang_label(code):
    """UI 언어와 같으면 '한국어', 다르면 'English (영어)' 처럼 직관적으로 표시."""
    if code == "auto":
        return T("auto")
    if code == _lang:
        return NATIVE[code]
    return f"{NATIVE[code]} ({NAME_IN[_lang][code]})"
