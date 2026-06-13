import json
import ssl
import urllib.error
import urllib.request


LLM_CONFIG: dict[str, str] = {}


def llm_status() -> str:
    required = ["base_url", "api_key", "model"]
    return "configured" if all(LLM_CONFIG.get(key) for key in required) else "not_configured"


def public_llm_config() -> dict[str, object]:
    return {
        "configured": llm_status() == "configured",
        "base_url": LLM_CONFIG.get("base_url", ""),
        "model": LLM_CONFIG.get("model", ""),
        "api_key_present": bool(LLM_CONFIG.get("api_key")),
        "verify_ssl": LLM_CONFIG.get("verify_ssl", "true") != "false",
    }


def normalize_base_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if not base:
        raise ValueError("请填写 Base URL。")
    if not base.startswith(("http://", "https://")):
        raise ValueError("Base URL 必须以 http:// 或 https:// 开头。")
    return base


def readable_http_error(exc: urllib.error.HTTPError) -> str:
    detail = exc.read().decode("utf-8", errors="replace")
    try:
        parsed = json.loads(detail)
        if isinstance(parsed, dict):
            error = parsed.get("error", parsed)
            if isinstance(error, dict):
                message = error.get("message") or error.get("type") or error
                code = error.get("code")
                if code:
                    return f"LLM 服务返回 HTTP {exc.code}: {message}（{code}）"
                return f"LLM 服务返回 HTTP {exc.code}: {message}"
            return f"LLM 服务返回 HTTP {exc.code}: {error}"
    except json.JSONDecodeError:
        pass
    return f"LLM 服务返回 HTTP {exc.code}: {detail[:300]}"


def ssl_context(verify_ssl: bool) -> ssl.SSLContext | None:
    if not verify_ssl:
        return ssl._create_unverified_context()
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def readable_url_error(exc: urllib.error.URLError) -> str:
    reason = str(exc.reason)
    if "CERTIFICATE_VERIFY_FAILED" in reason:
        return (
            "无法连接到 LLM 服务：本机无法确认这个 HTTPS 服务的身份。"
            "请先确认 Base URL 来自官方或你信任的服务；如果确认可信，"
            "可以勾选“跳过 SSL 证书验证”后重试。"
        )
    return f"无法连接到 LLM 服务：{reason}"


def post_llm_payload(
    base_url: str,
    api_key: str,
    payload: dict[str, object],
    *,
    timeout: int,
    verify_ssl: bool,
) -> tuple[dict[str, object], bool]:
    body = json.dumps(payload).encode("utf-8")
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    def send(should_verify_ssl: bool) -> dict[str, object]:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(
            request,
            timeout=timeout,
            context=ssl_context(should_verify_ssl),
        ) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)

    return send(verify_ssl), verify_ssl


def test_llm_connection(config: dict[str, object]) -> dict[str, object]:
    base_url = normalize_base_url(str(config.get("base_url", "")))
    api_key = str(config.get("api_key", "")).strip()
    model = str(config.get("model", "")).strip()
    verify_ssl = bool(config.get("verify_ssl", True))
    if not api_key:
        raise ValueError("请填写 API Key。")
    if not model:
        raise ValueError("请填写模型名。")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a connection test endpoint. Reply briefly.",
            },
            {"role": "user", "content": "Reply with OK."},
        ],
        "temperature": 0,
        "max_tokens": 8,
        "stream": False,
    }
    try:
        data, used_verify_ssl = post_llm_payload(
            base_url,
            api_key,
            payload,
            timeout=20,
            verify_ssl=verify_ssl,
        )
    except urllib.error.HTTPError as exc:
        raise RuntimeError(readable_http_error(exc)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(readable_url_error(exc)) from exc
    except TimeoutError as exc:
        raise RuntimeError("连接 LLM 服务超时。") from exc

    LLM_CONFIG.clear()
    LLM_CONFIG.update(
        {
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
            "verify_ssl": "true" if used_verify_ssl else "false",
        }
    )
    message = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    return {
        "ok": True,
        "message": (
            (message or "连接成功。")
            if used_verify_ssl
            else f"{message or '连接成功。'}（已按你的选择跳过 SSL 证书验证）"
        ),
        "config": public_llm_config(),
    }


def call_llm_json(messages: list[dict[str, str]], max_tokens: int = 900) -> dict[str, object]:
    if llm_status() != "configured":
        raise ValueError("LLM 尚未配置。请先在设置页测试连接。")

    payload = {
        "model": LLM_CONFIG["model"],
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": False,
    }
    try:
        data, used_verify_ssl = post_llm_payload(
            LLM_CONFIG["base_url"],
            LLM_CONFIG["api_key"],
            payload,
            timeout=60,
            verify_ssl=LLM_CONFIG.get("verify_ssl", "true") != "false",
        )
        LLM_CONFIG["verify_ssl"] = "true" if used_verify_ssl else "false"
    except urllib.error.HTTPError as exc:
        raise RuntimeError(readable_http_error(exc)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(readable_url_error(exc)) from exc

    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM 没有返回合法 JSON：{content[:300]}") from exc
