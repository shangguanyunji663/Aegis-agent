"""本地联调脚本:模拟学生登录并跑一段配合型对话。

HTTP 层统一走 _post_json(校验 http(s) 环回基址;基址经 AEGIS_BASE_URL 环境变量覆盖)。
凭据来自 Settings 默认值,可经 .env 修改后直接使用——克隆项目改配置即可跑。
"""
import os
import re
import json
import urllib.parse
import urllib.request


_ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _post_json(endpoint: str, payload: dict, cookie: tuple[str, str] | None = None) -> tuple[int, dict, dict]:
    """构造并发送请求:基址每次解析并校验,阻止访问内网/非环回地址。"""
    base = os.environ.get("AEGIS_BASE_URL", "http://localhost:8091")
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme not in {"http", "https"} or (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
        raise ValueError(f"base url must be http(s) loopback, got: {base!r}")
    headers = {"Content-Type": "application/json"}
    if cookie is not None:
        headers["Cookie"] = f"{cookie[0]}={cookie[1]}"
    req = urllib.request.Request(
        f"{parsed.scheme}://{parsed.netloc}{endpoint}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=8) as resp:
        status = resp.status
        body = json.loads(resp.read().decode("utf-8"))
    return status, body, dict(resp.headers)


def login(username: str, password: str) -> dict | None:
    try:
        status, body, headers = _post_json("/api/auth/login", {"username": username, "password": password})
        if status == 200:
            match = re.search(r"aegis_session=([^;]+)", headers.get("set-cookie", ""))
            if match:
                body["cookie_value"] = match.group(1)
            return body
        print(f"登录失败: {status}\n{body}")
        return None
    except Exception as exc:
        print(f"登录请求失败: {exc}")
        return None


def create_session(cookie: tuple[str, str]) -> str | None:
    try:
        status, body, _ = _post_json("/api/sessions", {}, cookie=cookie)
        if status == 200:
            return body.get("session", {}).get("id")
        print(f"创建会话失败: {status}\n{body}")
        return None
    except Exception as exc:
        print(f"创建会话请求失败: {exc}")
        return None


def test_chat(message: str, session_id: str, cookie: tuple[str, str]) -> dict | None:
    try:
        status, body, _ = _post_json("/api/chat", {"message": message, "session_id": session_id}, cookie=cookie)
        if status == 200:
            return body
        print(f"聊天失败: {status}\n{body}")
        return None
    except Exception as exc:
        print(f"聊天请求失败: {exc}")
        return None


# 配合型对话测试
print("=== 配合型对话测试 ===")
messages = [
    "我最近考试压力很大，晚上睡不着",
    "是的，我最近确实很焦虑，担心考试会不及格",
    "我尝试过一些放松方法，但效果不太好",
    "你有什么好的建议吗？",
    "我觉得运动可能会有帮助，但总是坚持不下来",
    "我应该如何安排时间呢？",
    "我需要平衡学习和休息",
    "你觉得我应该制定一个详细的学习计划吗？",
    "我担心计划执行不了",
    "你有什么鼓励的话吗？"
]

# 使用默认学生账户登录(凭据从 Settings 取,可经 .env 修改)
from app.config import Settings
_auth = Settings(_env_file=None)
login_result = login(_auth.auth_default_student_username, _auth.auth_default_student_password)
if not login_result:
    print("登录失败，测试终止")
else:
    print("登录成功")
    cookie = ("aegis_session", login_result.get("cookie_value", ""))
    if not cookie[1]:
        print("未取到会话 cookie，测试终止")
    else:
        session_id = create_session(cookie)
        print(f"会话创建: {session_id}")
        for message in messages:
            reply = test_chat(message, session_id, cookie)
            if reply:
                print(f"\n用户: {message}\n助手: {reply.get('reply', reply)}")
            else:
                print(f"\n用户: {message}\n(无回复)")