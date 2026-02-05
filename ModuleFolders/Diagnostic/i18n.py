"""
诊断模块国际化文本
"""

DIAGNOSTIC_I18N = {
    # 错误类型
    "error_type_auth": {
        "zh_CN": "认证错误",
        "en": "Authentication Error",
        "ja": "認証エラー"
    },
    "error_type_permission": {
        "zh_CN": "权限错误",
        "en": "Permission Error",
        "ja": "権限エラー"
    },
    "error_type_rate_limit": {
        "zh_CN": "请求限流",
        "en": "Rate Limited",
        "ja": "レート制限"
    },
    "error_type_server": {
        "zh_CN": "服务器错误",
        "en": "Server Error",
        "ja": "サーバーエラー"
    },
    "error_type_gateway": {
        "zh_CN": "网关错误",
        "en": "Gateway Error",
        "ja": "ゲートウェイエラー"
    },
    "error_type_unavailable": {
        "zh_CN": "服务不可用",
        "en": "Service Unavailable",
        "ja": "サービス利用不可"
    },
    "error_type_ssl": {
        "zh_CN": "SSL证书错误",
        "en": "SSL Certificate Error",
        "ja": "SSL証明書エラー"
    },
    "error_type_connection": {
        "zh_CN": "网络连接错误",
        "en": "Connection Error",
        "ja": "接続エラー"
    },
    "error_type_timeout": {
        "zh_CN": "请求超时",
        "en": "Request Timeout",
        "ja": "リクエストタイムアウト"
    },
    "error_type_model_not_found": {
        "zh_CN": "模型不存在",
        "en": "Model Not Found",
        "ja": "モデルが見つかりません"
    },
    "error_type_invalid_key": {
        "zh_CN": "API Key无效",
        "en": "Invalid API Key",
        "ja": "無効なAPIキー"
    },
    "error_type_insufficient_balance": {
        "zh_CN": "余额不足",
        "en": "Insufficient Balance",
        "ja": "残高不足"
    },
    "error_type_context_limit": {
        "zh_CN": "上下文超限",
        "en": "Context Length Exceeded",
        "ja": "コンテキスト長超過"
    },
    "error_type_file_not_found": {
        "zh_CN": "文件不存在",
        "en": "File Not Found",
        "ja": "ファイルが見つかりません"
    },
    "error_type_permission_denied": {
        "zh_CN": "权限不足",
        "en": "Permission Denied",
        "ja": "権限がありません"
    },
    "error_type_json_error": {
        "zh_CN": "JSON解析错误",
        "en": "JSON Parse Error",
        "ja": "JSON解析エラー"
    },
    "error_type_encoding": {
        "zh_CN": "编码错误",
        "en": "Encoding Error",
        "ja": "エンコードエラー"
    },
    "error_type_dependency": {
        "zh_CN": "依赖缺失",
        "en": "Missing Dependency",
        "ja": "依存関係の欠落"
    },
    "error_type_config_missing": {
        "zh_CN": "配置缺失",
        "en": "Configuration Missing",
        "ja": "設定が見つかりません"
    },
    "error_type_code_import": {
        "zh_CN": "代码导入错误",
        "en": "Code Import Error",
        "ja": "コードインポートエラー"
    },
    "error_type_unknown": {
        "zh_CN": "未知错误",
        "en": "Unknown Error",
        "ja": "不明なエラー"
    },

    # 根本原因
    "cause_invalid_key": {
        "zh_CN": "API Key 无效或已过期",
        "en": "API Key is invalid or expired",
        "ja": "APIキーが無効または期限切れです"
    },
    "cause_no_permission": {
        "zh_CN": "API Key 没有访问该模型/接口的权限",
        "en": "API Key lacks permission to access this model/endpoint",
        "ja": "APIキーにこのモデル/エンドポイントへのアクセス権限がありません"
    },
    "cause_rate_limit": {
        "zh_CN": "请求过于频繁，触发了 API 限流",
        "en": "Too many requests, API rate limit triggered",
        "ja": "リクエストが多すぎてAPIレート制限がトリガーされました"
    },
    "cause_server_error": {
        "zh_CN": "API 服务器内部错误",
        "en": "API server internal error",
        "ja": "APIサーバー内部エラー"
    },
    "cause_gateway_error": {
        "zh_CN": "API 网关错误，通常是服务器过载",
        "en": "API gateway error, usually server overload",
        "ja": "APIゲートウェイエラー、通常はサーバー過負荷"
    },
    "cause_service_unavailable": {
        "zh_CN": "API 服务暂时不可用",
        "en": "API service temporarily unavailable",
        "ja": "APIサービスが一時的に利用できません"
    },
    "cause_ssl": {
        "zh_CN": "SSL证书验证失败，通常由代理、VPN或网络环境导致",
        "en": "SSL certificate verification failed, usually caused by proxy, VPN or network environment",
        "ja": "SSL証明書の検証に失敗しました。通常、プロキシ、VPN、またはネットワーク環境が原因です"
    },
    "cause_connection": {
        "zh_CN": "无法连接到 API 服务器",
        "en": "Cannot connect to API server",
        "ja": "APIサーバーに接続できません"
    },
    "cause_timeout": {
        "zh_CN": "API 请求超时，可能是网络慢或服务器响应慢",
        "en": "API request timeout, possibly slow network or server response",
        "ja": "APIリクエストがタイムアウトしました。ネットワークまたはサーバーの応答が遅い可能性があります"
    },
    "cause_model_not_found": {
        "zh_CN": "请求的模型名称不正确或该模型不可用",
        "en": "Requested model name is incorrect or model unavailable",
        "ja": "リクエストされたモデル名が正しくないか、モデルが利用できません"
    },
    "cause_invalid_key_format": {
        "zh_CN": "API Key 格式错误或已失效",
        "en": "API Key format error or invalidated",
        "ja": "APIキーの形式エラーまたは無効化されています"
    },
    "cause_insufficient_balance": {
        "zh_CN": "API 账户余额不足",
        "en": "Insufficient API account balance",
        "ja": "APIアカウントの残高が不足しています"
    },
    "cause_context_limit": {
        "zh_CN": "输入文本超过模型的最大上下文长度",
        "en": "Input text exceeds model's maximum context length",
        "ja": "入力テキストがモデルの最大コンテキスト長を超えています"
    },
    "cause_file_not_found": {
        "zh_CN": "指定的文件或路径不存在",
        "en": "Specified file or path does not exist",
        "ja": "指定されたファイルまたはパスが存在しません"
    },
    "cause_permission_denied": {
        "zh_CN": "没有读写文件的权限",
        "en": "No permission to read/write file",
        "ja": "ファイルの読み書き権限がありません"
    },
    "cause_json_error": {
        "zh_CN": "配置文件或API响应的JSON格式错误",
        "en": "JSON format error in config file or API response",
        "ja": "設定ファイルまたはAPIレスポンスのJSON形式エラー"
    },
    "cause_encoding": {
        "zh_CN": "文件编码格式不正确",
        "en": "Incorrect file encoding format",
        "ja": "ファイルのエンコード形式が正しくありません"
    },
    "cause_dependency": {
        "zh_CN": "缺少必要的 Python 依赖包",
        "en": "Missing required Python dependency",
        "ja": "必要なPython依存関係が不足しています"
    },
    "cause_model_not_selected": {
        "zh_CN": "未选择翻译模型",
        "en": "Translation model not selected",
        "ja": "翻訳モデルが選択されていません"
    },
    "cause_api_key_not_set": {
        "zh_CN": "未配置 API Key",
        "en": "API Key not configured",
        "ja": "APIキーが設定されていません"
    },
    "cause_prompt_not_selected": {
        "zh_CN": "未选择提示词",
        "en": "Prompt not selected",
        "ja": "プロンプトが選択されていません"
    },
    "cause_local_import": {
        "zh_CN": "项目内部模块导入失败，可能是开发者代码问题",
        "en": "Internal module import failed, possibly a developer code issue",
        "ja": "内部モジュールのインポートに失敗しました。開発者のコードの問題の可能性があります"
    },
    "cause_third_party": {
        "zh_CN": "缺少第三方依赖包",
        "en": "Missing third-party dependency",
        "ja": "サードパーティの依存関係が不足しています"
    },
    "cause_unknown": {
        "zh_CN": "无法自动诊断此错误",
        "en": "Unable to automatically diagnose this error",
        "ja": "このエラーを自動診断できません"
    },

    # 解决方案
    "solution_check_key": {
        "zh_CN": "请检查配置中的 API Key 是否正确，确认账户余额充足",
        "en": "Please check if API Key is correct and account balance is sufficient",
        "ja": "APIキーが正しいか、アカウント残高が十分かご確認ください"
    },
    "solution_check_permission": {
        "zh_CN": "请确认您的 API Key 有权访问所选模型，部分模型需要额外申请权限",
        "en": "Please confirm your API Key has access to the selected model, some models require additional permission",
        "ja": "APIキーが選択したモデルにアクセスできるかご確認ください。一部のモデルは追加の権限が必要です"
    },
    "solution_rate_limit": {
        "zh_CN": "请降低并发数，或等待一段时间后重试。也可能是账户余额不足",
        "en": "Please reduce concurrency or wait before retrying. May also indicate insufficient balance",
        "ja": "並行数を減らすか、しばらく待ってから再試行してください。残高不足の可能性もあります"
    },
    "solution_server_error": {
        "zh_CN": "这是 API 提供商的问题，请稍后重试。如果持续出现，可以尝试更换模型",
        "en": "This is an API provider issue, please retry later. If persistent, try a different model",
        "ja": "これはAPIプロバイダーの問題です。後で再試行してください。継続する場合は別のモデルをお試しください"
    },
    "solution_gateway": {
        "zh_CN": "请稍后重试，或降低并发数",
        "en": "Please retry later or reduce concurrency",
        "ja": "後で再試行するか、並行数を減らしてください"
    },
    "solution_maintenance": {
        "zh_CN": "API 服务可能正在维护，请稍后重试",
        "en": "API service may be under maintenance, please retry later",
        "ja": "APIサービスがメンテナンス中の可能性があります。後で再試行してください"
    },
    "solution_ssl": {
        "zh_CN": "1. 检查代理设置是否正确\n2. 尝试关闭VPN\n3. 如果使用公司网络，可能需要配置证书",
        "en": "1. Check proxy settings\n2. Try disabling VPN\n3. Corporate networks may require certificate configuration",
        "ja": "1. プロキシ設定を確認\n2. VPNを無効にしてみる\n3. 企業ネットワークでは証明書の設定が必要な場合があります"
    },
    "solution_connection": {
        "zh_CN": "1. 检查网络连接\n2. 检查代理设置\n3. 确认 API 地址是否正确\n4. 部分地区可能需要代理才能访问",
        "en": "1. Check network connection\n2. Check proxy settings\n3. Verify API address\n4. Some regions may require proxy",
        "ja": "1. ネットワーク接続を確認\n2. プロキシ設定を確認\n3. APIアドレスを確認\n4. 一部の地域ではプロキシが必要な場合があります"
    },
    "solution_timeout": {
        "zh_CN": "1. 检查网络连接\n2. 尝试增加超时时间\n3. 降低单次请求的文本量",
        "en": "1. Check network connection\n2. Try increasing timeout\n3. Reduce text per request",
        "ja": "1. ネットワーク接続を確認\n2. タイムアウト時間を増やす\n3. リクエストごとのテキスト量を減らす"
    },
    "solution_model": {
        "zh_CN": "1. 检查模型名称是否拼写正确\n2. 确认您的账户有权访问该模型\n3. 尝试使用其他可用模型",
        "en": "1. Check model name spelling\n2. Confirm account has model access\n3. Try other available models",
        "ja": "1. モデル名のスペルを確認\n2. アカウントがモデルにアクセスできるか確認\n3. 他の利用可能なモデルを試す"
    },
    "solution_key_format": {
        "zh_CN": "1. 检查 API Key 是否完整复制（无多余空格）\n2. 确认 API Key 未过期\n3. 重新生成新的 API Key",
        "en": "1. Check API Key is fully copied (no extra spaces)\n2. Confirm API Key not expired\n3. Generate a new API Key",
        "ja": "1. APIキーが完全にコピーされているか確認（余分なスペースなし）\n2. APIキーが期限切れでないか確認\n3. 新しいAPIキーを生成"
    },
    "solution_balance": {
        "zh_CN": "请充值您的 API 账户，或检查是否有免费额度可用",
        "en": "Please top up your API account or check for available free quota",
        "ja": "APIアカウントにチャージするか、利用可能な無料枠を確認してください"
    },
    "solution_context": {
        "zh_CN": "1. 减少单次翻译的文本量\n2. 使用支持更长上下文的模型\n3. 调整分段设置",
        "en": "1. Reduce text per translation\n2. Use model with longer context\n3. Adjust segmentation settings",
        "ja": "1. 翻訳ごとのテキスト量を減らす\n2. より長いコンテキストをサポートするモデルを使用\n3. セグメント設定を調整"
    },
    "solution_file": {
        "zh_CN": "1. 检查文件路径是否正确\n2. 确认文件未被移动或删除\n3. 检查路径中是否有特殊字符",
        "en": "1. Check file path is correct\n2. Confirm file not moved/deleted\n3. Check for special characters in path",
        "ja": "1. ファイルパスが正しいか確認\n2. ファイルが移動/削除されていないか確認\n3. パスに特殊文字がないか確認"
    },
    "solution_permission": {
        "zh_CN": "1. 以管理员身份运行程序\n2. 检查文件是否被其他程序占用\n3. 检查文件夹权限设置",
        "en": "1. Run as administrator\n2. Check if file is in use\n3. Check folder permissions",
        "ja": "1. 管理者として実行\n2. ファイルが使用中でないか確認\n3. フォルダの権限を確認"
    },
    "solution_json": {
        "zh_CN": "1. 不要手动编辑配置文件\n2. 尝试删除配置文件让程序重新生成\n3. 如果是API响应错误，可能是网络问题",
        "en": "1. Don't manually edit config files\n2. Try deleting config to regenerate\n3. API response errors may be network issues",
        "ja": "1. 設定ファイルを手動で編集しない\n2. 設定ファイルを削除して再生成を試す\n3. APIレスポンスエラーはネットワークの問題の可能性があります"
    },
    "solution_encoding": {
        "zh_CN": "1. 确保源文件使用 UTF-8 编码\n2. 尝试用记事本另存为 UTF-8 格式\n3. 检查文件是否损坏",
        "en": "1. Ensure source file uses UTF-8\n2. Try saving as UTF-8 in Notepad\n3. Check if file is corrupted",
        "ja": "1. ソースファイルがUTF-8を使用していることを確認\n2. メモ帳でUTF-8として保存してみる\n3. ファイルが破損していないか確認"
    },
    "solution_dependency": {
        "zh_CN": "请运行以下命令安装依赖:\nuv sync\n\n或单独安装缺失的包:\nuv add <包名>",
        "en": "Please run the following to install dependencies:\nuv sync\n\nOr install missing package:\nuv add <package>",
        "ja": "以下のコマンドで依存関係をインストールしてください:\nuv sync\n\nまたは不足しているパッケージを個別にインストール:\nuv add <パッケージ名>"
    },
    "solution_select_model": {
        "zh_CN": "请在设置页面选择一个模型，然后点击保存",
        "en": "Please select a model in settings and save",
        "ja": "設定ページでモデルを選択して保存してください"
    },
    "solution_select_key": {
        "zh_CN": "请在设置页面填写 API Key，然后点击保存",
        "en": "Please enter API Key in settings and save",
        "ja": "設定ページでAPIキーを入力して保存してください"
    },
    "solution_select_prompt": {
        "zh_CN": "请在设置页面选择一个提示词模板，然后点击保存",
        "en": "Please select a prompt template in settings and save",
        "ja": "設定ページでプロンプトテンプレートを選択して保存してください"
    },
    "solution_code_bug": {
        "zh_CN": "这是代码问题，请提交Issue给开发者",
        "en": "This is a code issue, please submit an Issue to developers",
        "ja": "これはコードの問題です。開発者にIssueを提出してください"
    },
    "solution_unknown": {
        "zh_CN": "请检查错误信息，或在GitHub提交Issue寻求帮助",
        "en": "Please check error message or submit an Issue on GitHub for help",
        "ja": "エラーメッセージを確認するか、GitHubでIssueを提出してください"
    },

    # 自查清单
    "self_check_1": {
        "zh_CN": "您是否手动修改过 config 文件夹下的文件？",
        "en": "Did you manually modify files in the config folder?",
        "ja": "configフォルダ内のファイルを手動で変更しましたか？"
    },
    "self_check_2": {
        "zh_CN": "在运行程序前，您是否已经在界面上选择并保存了所有必要设置？",
        "en": "Did you select and save all necessary settings before running?",
        "ja": "実行前に必要な設定をすべて選択して保存しましたか？"
    },
    "self_check_3": {
        "zh_CN": "如果这是您第一次运行新版本，建议删除旧配置文件让程序重新生成",
        "en": "If this is your first time running a new version, try deleting old config files",
        "ja": "新バージョンを初めて実行する場合は、古い設定ファイルを削除してみてください"
    },

    # 格式化输出标签
    "label_error_type": {
        "zh_CN": "错误类型",
        "en": "Error Type",
        "ja": "エラータイプ"
    },
    "label_root_cause": {
        "zh_CN": "根本原因",
        "en": "Root Cause",
        "ja": "根本原因"
    },
    "label_solution": {
        "zh_CN": "解决方案",
        "en": "Solution",
        "ja": "解決策"
    },
    "label_self_check": {
        "zh_CN": "自查清单",
        "en": "Self-Check",
        "ja": "セルフチェック"
    },
    "label_code_bug_hint": {
        "zh_CN": "此为代码问题，若您有代码基础可自行修改，否则请提交Issue",
        "en": "This is a code bug. Fix it yourself if able, otherwise submit an Issue",
        "ja": "これはコードのバグです。可能であれば自分で修正するか、Issueを提出してください"
    },
    "label_diagnosis_source": {
        "zh_CN": "诊断来源",
        "en": "Diagnosis Source",
        "ja": "診断ソース"
    },
    "label_token_cost": {
        "zh_CN": "Token消耗",
        "en": "Token Cost",
        "ja": "トークン消費"
    },
    "label_unknown_error": {
        "zh_CN": "无法自动诊断此错误，请检查错误信息或提交Issue寻求帮助",
        "en": "Unable to diagnose automatically. Check error or submit Issue for help",
        "ja": "自動診断できません。エラーを確認するかIssueを提出してください"
    },

    # 知识库相关
    "kb_context_header": {
        "zh_CN": "相关知识参考:",
        "en": "Related Knowledge Reference:",
        "ja": "関連知識参照:"
    },

    # 回退结果
    "fallback_self_check_1": {
        "zh_CN": "检查网络连接是否正常",
        "en": "Check if network connection is working",
        "ja": "ネットワーク接続が正常か確認"
    },
    "fallback_self_check_2": {
        "zh_CN": "确认所有配置已正确保存",
        "en": "Confirm all settings are saved correctly",
        "ja": "すべての設定が正しく保存されているか確認"
    },
    "fallback_self_check_3": {
        "zh_CN": "尝试重启程序",
        "en": "Try restarting the program",
        "ja": "プログラムを再起動してみる"
    },
}


def get_text(key: str, lang: str = "zh_CN") -> str:
    """获取翻译文本"""
    item = DIAGNOSTIC_I18N.get(key, {})
    return item.get(lang, item.get("en", key))
