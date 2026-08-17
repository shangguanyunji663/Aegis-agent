import requests
import json

def login(username, password):
    url = "http://localhost:8091/api/login"
    headers = {"Content-Type": "application/json"}
    data = {"username": username, "password": password}
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        if response.status_code == 200:
            return response.json().get("session_id")
        else:
            print(f"Login failed: {response.status_code}")
            print(response.text)
            return None
    except Exception as e:
        print(f"Login request failed: {e}")
        return None

# 使用默认用户登录
session_id = login("student", "student123!")
if session_id:
    print(f"登录成功，session_id: {session_id}")
else:
    print("登录失败")