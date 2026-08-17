import requests
import json
import re

def login(username, password):
    url = "http://localhost:8091/api/auth/login"
    headers = {"Content-Type": "application/json"}
    data = {"username": username, "password": password}
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        if response.status_code == 200:
            # 提取cookie
            set_cookie_header = response.headers.get('set-cookie')
            if set_cookie_header:
                # 解析cookie
                cookie_match = re.search(r'aegis_session=([^;]+)', set_cookie_header)
                if cookie_match:
                    cookie_value = cookie_match.group(1)
                    return {
                        "user": response.json().get("user"),
                        "expires_at": response.json().get("expires_at"),
                        "cookie_value": cookie_value
                    }
            return response.json()
        else:
            print(f"登录失败: {response.status_code}")
            print(response.text)
            return None
    except Exception as e:
        print(f"登录请求失败: {e}")
        return None

def create_session(session, cookie_name, cookie_value):
    url = "http://localhost:8091/api/sessions"
    headers = {"Content-Type": "application/json"}
    data = {}  # 使用默认标题
    
    try:
        response = session.post(url, headers=headers, data=json.dumps(data), cookies={cookie_name: cookie_value})
        if response.status_code == 200:
            return response.json().get("session", {}).get("id")
        else:
            print(f"创建会话失败: {response.status_code}")
            print(response.text)
            return None
    except Exception as e:
        print(f"创建会话请求失败: {e}")
        return None

def test_chat(session, message, session_id, cookie_name, cookie_value):
    url = "http://localhost:8091/api/chat"
    headers = {"Content-Type": "application/json"}
    data = {"message": message, "session_id": session_id}
    
    try:
        response = session.post(url, headers=headers, data=json.dumps(data), cookies={cookie_name: cookie_value})
        if response.status_code == 200:
            return response.json()
        else:
            print(f"聊天失败: {response.status_code}")
            print(response.text)
            return None
    except Exception as e:
        print(f"聊天请求失败: {e}")
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

# 使用默认学生账户登录
session = requests.Session()
login_data = {
    "username": "student", 
    "password": "student123!"
}
login_result = login(login_data["username"], login_data["password"])
if not login_result:
    print("登录失败，测试终止")
else:
    print("登录成功")
    cookie_name = "aegis_session"
    cookie_value = login_result.get("cookie_value", "")
    
    if not cookie_value:
        print("无法获取cookie值，测试终止")
    else:
        print(f"获取到cookie: {cookie_value[:20]}...")
        
        session_id = create_session(session, cookie_name, cookie_value)
        if not session_id:
            print("无法创建会话，测试终止")
        else:
            print(f"会话创建成功，session_id: {session_id}")
            
            for i, message in enumerate(messages):
                print(f"\n=== 第{i+1}轮 ===")
                print(f"用户: {message}")
                result = test_chat(session, message, session_id, cookie_name, cookie_value)
                if result:
                    print(f"AI: {result.get('answer', 'No answer')}")
                else:
                    break

# 对抗型对话测试
print("\n\n=== 对抗型对话测试 ===")
messages = [
    "我最近考试压力很大，晚上睡不着",
    "我觉得你说的都不对，考试压力根本不是问题",
    "我不需要你的建议，我自己能解决",
    "你的建议一点用都没有",
    "我觉得你根本不了解我的情况",
    "我不想听你说这些",
    "你能说点有用的吗？",
    "我觉得你很烦人",
    "我不想和你聊天了",
    "再见"
]

# 创建新会话
session_id = create_session(session, cookie_name, cookie_value)
if not session_id:
    print("无法创建会话，测试终止")
else:
    print(f"会话创建成功，session_id: {session_id}")
    
    for i, message in enumerate(messages):
        print(f"\n=== 第{i+1}轮 ===")
        print(f"用户: {message}")
        result = test_chat(session, message, session_id, cookie_name, cookie_value)
        if result:
            print(f"AI: {result.get('answer', 'No answer')}")
        else:
            break

print("\n测试完成！")