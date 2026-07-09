"""登录页文案词典。英文原文即 key（与 noVNC 的 gettext 式约定一致）。

`en` 不需要条目 —— 缺译时 t() 直接回落原文。
新增文案时：先在代码里写英文原文，再往这四个字典各补一条。缺了不会崩，只会显示英文。

品牌名「察元AI工舱」不在此表内 —— 它是品牌，所有语言下保持不变。
"""

MESSAGES = {
    "zh_CN": {
        # 登录页骨架
        "Sign in": "登录",
        "Activate and sign in": "激活并登录",
        "Username": "用户名",
        "Password": "密码",
        "Captcha": "验证码",
        "Click to refresh": "点击刷新",
        "Agent-powered AI cloud desktop": "智能体驱动的 AI 云桌面",
        "Language": "语言",
        "Follow system": "跟随系统",
        # 序列号激活
        "Serial number": "序列号",
        "Machine fingerprint": "本机指纹",
        "Copy": "复制",
        "Copied": "已复制",
        "Unavailable": "（不可用）",
        "Follow our official account to get a serial number":
            "请关注下方公众号获取序列号",
        "Enter this fingerprint to obtain your serial number":
            "输入本机指纹即可获取序列号",
        "License valid until": "授权有效期至",
        # 页脚
        "Follow us": "关注我们",
        "All rights reserved": "版权所有",
        "Official account QR code": "关注我们二维码",
        # 错误码 1-9（与 gate.py 的 ERR_* 对齐）
        "Incorrect username or password": "用户名或密码错误",
        "Captcha is wrong or expired": "验证码错误或已过期",
        "Invalid serial number, please check it is complete":
            "序列号无效，请检查是否输入完整",
        "This serial number was not issued for this machine":
            "该序列号不是为本机签发的（指纹不匹配）",
        "This serial number does not include a workstation license":
            "该序列号不包含「察元AI工舱」授权",
        "Count-based serial numbers are not supported, please use a time-based one":
            "次数型序列号不适用于工舱，请使用时长型",
        "This serial number has expired": "该序列号已过期",
        "Your license has expired, please enter a new serial number":
            "授权已到期，请输入新序列号",
        "System clock error, please correct it and retry":
            "系统时间异常，请校正后重试",
        # 语言切换提示
        "Desktop language applies after restart":
            "桌面语言将在重启工舱后生效",
    },

    "zh_TW": {
        "Sign in": "登入",
        "Activate and sign in": "啟用並登入",
        "Username": "使用者名稱",
        "Password": "密碼",
        "Captcha": "驗證碼",
        "Click to refresh": "點擊重新整理",
        "Agent-powered AI cloud desktop": "智慧體驅動的 AI 雲端桌面",
        "Language": "語言",
        "Follow system": "跟隨系統",
        "Serial number": "序號",
        "Machine fingerprint": "本機指紋",
        "Copy": "複製",
        "Copied": "已複製",
        "Unavailable": "（無法使用）",
        "Follow our official account to get a serial number":
            "請關注下方公眾號取得序號",
        "Enter this fingerprint to obtain your serial number":
            "輸入本機指紋即可取得序號",
        "License valid until": "授權有效期至",
        "Follow us": "關注我們",
        "All rights reserved": "版權所有",
        "Official account QR code": "關注我們 QR Code",
        "Incorrect username or password": "使用者名稱或密碼錯誤",
        "Captcha is wrong or expired": "驗證碼錯誤或已過期",
        "Invalid serial number, please check it is complete":
            "序號無效，請檢查是否輸入完整",
        "This serial number was not issued for this machine":
            "此序號並非為本機簽發（指紋不符）",
        "This serial number does not include a workstation license":
            "此序號不包含「察元AI工舱」授權",
        "Count-based serial numbers are not supported, please use a time-based one":
            "次數型序號不適用於工舱，請使用時長型",
        "This serial number has expired": "此序號已過期",
        "Your license has expired, please enter a new serial number":
            "授權已到期，請輸入新序號",
        "System clock error, please correct it and retry":
            "系統時間異常，請校正後重試",
        "Desktop language applies after restart":
            "桌面語言將在重新啟動工舱後生效",
    },

    "ja": {
        "Sign in": "ログイン",
        "Activate and sign in": "認証してログイン",
        "Username": "ユーザー名",
        "Password": "パスワード",
        "Captcha": "認証コード",
        "Click to refresh": "クリックで再読み込み",
        "Agent-powered AI cloud desktop": "エージェント駆動の AI クラウドデスクトップ",
        "Language": "言語",
        "Follow system": "システムに従う",
        "Serial number": "シリアル番号",
        "Machine fingerprint": "マシン指紋",
        "Copy": "コピー",
        "Copied": "コピーしました",
        "Unavailable": "（利用不可）",
        "Follow our official account to get a serial number":
            "下の公式アカウントをフォローしてシリアル番号を取得してください",
        "Enter this fingerprint to obtain your serial number":
            "このマシン指紋を入力するとシリアル番号を取得できます",
        "License valid until": "ライセンス有効期限",
        "Follow us": "フォローする",
        "All rights reserved": "All rights reserved",
        "Official account QR code": "公式アカウントの QR コード",
        "Incorrect username or password": "ユーザー名またはパスワードが違います",
        "Captcha is wrong or expired": "認証コードが違うか、有効期限が切れています",
        "Invalid serial number, please check it is complete":
            "シリアル番号が無効です。入力内容をご確認ください",
        "This serial number was not issued for this machine":
            "このシリアル番号は本機向けに発行されていません（指紋が一致しません）",
        "This serial number does not include a workstation license":
            "このシリアル番号にはワークステーションのライセンスが含まれていません",
        "Count-based serial numbers are not supported, please use a time-based one":
            "回数制のシリアル番号は利用できません。期間制をご使用ください",
        "This serial number has expired": "このシリアル番号は有効期限が切れています",
        "Your license has expired, please enter a new serial number":
            "ライセンスの有効期限が切れました。新しいシリアル番号を入力してください",
        "System clock error, please correct it and retry":
            "システム時刻が異常です。修正してから再試行してください",
        "Desktop language applies after restart":
            "デスクトップの言語は再起動後に反映されます",
    },

    "ko": {
        "Sign in": "로그인",
        "Activate and sign in": "인증 후 로그인",
        "Username": "사용자 이름",
        "Password": "비밀번호",
        "Captcha": "보안 문자",
        "Click to refresh": "클릭하여 새로 고침",
        "Agent-powered AI cloud desktop": "에이전트 기반 AI 클라우드 데스크톱",
        "Language": "언어",
        "Follow system": "시스템 설정 따름",
        "Serial number": "시리얼 번호",
        "Machine fingerprint": "장치 지문",
        "Copy": "복사",
        "Copied": "복사됨",
        "Unavailable": "(사용 불가)",
        "Follow our official account to get a serial number":
            "아래 공식 계정을 팔로우하여 시리얼 번호를 받으세요",
        "Enter this fingerprint to obtain your serial number":
            "장치 지문을 입력하면 시리얼 번호를 받을 수 있습니다",
        "License valid until": "라이선스 만료일",
        "Follow us": "팔로우하기",
        "All rights reserved": "All rights reserved",
        "Official account QR code": "공식 계정 QR 코드",
        "Incorrect username or password": "사용자 이름 또는 비밀번호가 올바르지 않습니다",
        "Captcha is wrong or expired": "보안 문자가 올바르지 않거나 만료되었습니다",
        "Invalid serial number, please check it is complete":
            "시리얼 번호가 올바르지 않습니다. 전부 입력했는지 확인하세요",
        "This serial number was not issued for this machine":
            "이 시리얼 번호는 본 장치용으로 발급되지 않았습니다(지문 불일치)",
        "This serial number does not include a workstation license":
            "이 시리얼 번호에는 워크스테이션 라이선스가 포함되어 있지 않습니다",
        "Count-based serial numbers are not supported, please use a time-based one":
            "횟수형 시리얼 번호는 지원되지 않습니다. 기간형을 사용하세요",
        "This serial number has expired": "이 시리얼 번호는 만료되었습니다",
        "Your license has expired, please enter a new serial number":
            "라이선스가 만료되었습니다. 새 시리얼 번호를 입력하세요",
        "System clock error, please correct it and retry":
            "시스템 시간이 올바르지 않습니다. 수정 후 다시 시도하세요",
        "Desktop language applies after restart":
            "데스크톱 언어는 재시작 후 적용됩니다",
    },
}
