import os
import time
import hmac
import hashlib
import base64
from dotenv import load_dotenv
from datetime import datetime, timedelta
from pathlib import Path

# 显式加载 .env（注意括号）
load_dotenv(Path(__file__).parent / ".env")

SECRET_KEY = os.getenv("SECRET_KEY")

def generate_code(duration_hours=24):
    timestamp = int(time.time())
    expiry = duration_hours
    data = f"{timestamp}|{expiry}"
    signature = hmac.new(
        SECRET_KEY.encode('utf-8'),
        data.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()[:16]
    code_raw = f"{timestamp}|{expiry}|{signature}"
    code = base64.urlsafe_b64encode(code_raw.encode()).decode().rstrip("=")
    expire_time = datetime.fromtimestamp(timestamp) + timedelta(hours=expiry)
    return {
        "code": code,
        "expire_time": expire_time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration": f"{expiry}小时"
    }

if __name__ == "__main__":
    if not SECRET_KEY:
        raise RuntimeError("请在 .env 中配置 SECRET_KEY")
    print("\n" + "="*50)
    print("兑换码生成器")
    print("="*50)
    r24 = generate_code(24)
    print(f"\n24小时兑换码: {r24['code']}")
    print(f"有效期: {r24['duration']}")
    print(f"过期时间: {r24['expire_time']}")
    print("\n" + "-"*50)
    r7d = generate_code(168)
    print(f"7天有效兑换码: {r7d['code']}")
    print(f"过期时间: {r7d['expire_time']}")
    print("="*50 + "\n")