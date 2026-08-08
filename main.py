import os
import json
import re
import time
import secrets
import string
from datetime import datetime
from collections import defaultdict
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, constr
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv
import httpx
from user_agents import parse

load_dotenv()

# ========== 配置 ==========
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")          # 保留给未来扩展
FREE_LIMIT = int(os.getenv("FREE_LIMIT", 3))
PRICE = os.getenv("PRICE", "¥9.9")
SITE_URL = os.getenv("SITE_URL", "https://ai-prompt-api-production.up.railway.app")

if not DEEPSEEK_API_KEY:
    raise RuntimeError("缺少环境变量 DEEPSEEK_API_KEY")

# ========== 文件路径 ==========
CODES_FILE = "used_codes.json"
AUDIT_FILE = "audit.log"
BLACKLIST_FILE = "blacklist.json"
FAILED_ATTEMPTS_FILE = "failed_attempts.json"

for filepath in [CODES_FILE, BLACKLIST_FILE, FAILED_ATTEMPTS_FILE]:
    if not os.path.exists(filepath):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2, ensure_ascii=False)

# ========== 安全配置 ==========
MAX_CLAIM_PER_IP_DAY = 3
MAX_VERIFY_FAILURES = 5
VERIFY_LOCK_MINUTES = 10
EXPIRE_HOURS = 24

# ========== 限流与防刷 ==========
# 用于记录验证失败次数的内存存储（仅适用于单进程，生产环境建议用Redis）
failed_attempts = defaultdict(lambda: {"count": 0, "first_fail": 0})

# ========== 工具函数 ==========
def get_device_fingerprint(request: Request):
    ua_string = request.headers.get("user-agent", "")
    ua = parse(ua_string)
    fingerprint = f"{ua.browser.family}|{ua.browser.version_string}|{ua.os.family}|{ua.os.version_string}|{ua.device.family}"
    screen = request.headers.get("x-screen", "unknown")
    return hashlib.md5(f"{fingerprint}|{screen}".encode()).hexdigest()

def is_blacklisted(fingerprint: str):
    with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return fingerprint in data and data[fingerprint].get("active", False)

def add_to_blacklist(fingerprint: str, reason: str):
    with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    data[fingerprint] = {"active": True, "reason": reason, "created_at": datetime.now().isoformat()}
    with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def log_audit(event: str, details: dict):
    with open(AUDIT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"timestamp": datetime.now().isoformat(), "event": event, **details}, ensure_ascii=False) + "\n")

def is_verify_locked(ip: str):
    if ip not in failed_attempts:
        return False
    info = failed_attempts[ip]
    if info["count"] >= MAX_VERIFY_FAILURES:
        if time.time() - info["first_fail"] < VERIFY_LOCK_MINUTES * 60:
            return True
        else:
            failed_attempts[ip] = {"count": 0, "first_fail": 0}
            return False
    return False

def record_verify_failure(ip: str):
    if ip not in failed_attempts:
        failed_attempts[ip] = {"count": 0, "first_fail": int(time.time())}
    failed_attempts[ip]["count"] += 1

def reset_verify_failures(ip: str):
    failed_attempts[ip] = {"count": 0, "first_fail": 0}

# ========== FastAPI 应用 ==========
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="PromptOpt AI提示词优化API",
    description="专业级AI提示词优化服务"
)
app.state.limiter = limiter
httpx_client = httpx.AsyncClient(timeout=15.0)

# ========== 请求模型 ==========
class PromptRequest(BaseModel):
    prompt: constr(min_length=1, max_length=2000)
    style: str = "precise"

class VerifyCodeRequest(BaseModel):
    code: str

class ClaimCodeRequest(BaseModel):
    order_id: str
    device_fingerprint: str

# ========== 风格预设 ==========
STYLE_PROMPTS = {
    "precise": """你是世界级的AI提示词优化专家，风格严谨精准。
请将用户提供的提示词优化为结构清晰、约束明确、可执行性极强的专业指令，补充角色设定、输出格式、质量要求，确保AI输出稳定可控。
直接返回优化后的提示词，不要添加任何解释或前缀。""",
    "creative": """你是富有创意的AI提示词优化专家，风格开放发散。
请将用户提供的提示词优化为更具想象力、引导性的指令，保留核心需求的同时拓展创意空间，激发AI产出更多新颖视角。
直接返回优化后的提示词，不要添加任何解释或前缀。""",
    "concise": """你是高效简洁的AI提示词优化专家，风格凝练直接。
请将用户提供的提示词精简为核心指令，去除冗余表述，用最短的文字精准传达需求，确保AI快速理解并输出。
直接返回优化后的提示词，不要添加任何解释或前缀。"""
}

EXAMPLE_TEMPLATES = [
    {"name": "📝 文案写作", "content": "帮我写一篇关于职场效率提升的公众号文章，标题吸引人，结构清晰，包含3个实用方法，字数1500字左右"},
    {"name": "💻 代码开发", "content": "用Python写一个批量重命名文件的脚本，支持自定义前缀和序号，带异常处理和进度显示"},
    {"name": "📊 活动策划", "content": "策划一场618线上产品促销活动方案，包含活动主题、玩法规则、宣传渠道、预算分配和效果预期"}
]

# ========== 健康检查 ==========
@app.get("/")
def root():
    return {"code": 0, "msg": "PromptOpt 服务运行中", "data": None}

# ========== 核心优化接口 ==========
@app.post("/optimize")
@limiter.limit("20/minute")
async def optimize_prompt(request: Request, prompt_req: PromptRequest):
    system_prompt = STYLE_PROMPTS.get(prompt_req.style, STYLE_PROMPTS["precise"])
    print(f"[请求] 风格:{prompt_req.style} 输入:{prompt_req.prompt[:50]}...")
    try:
        resp = await httpx_client.post(
            url="https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt_req.prompt}
                ],
                "temperature": 0.3 if prompt_req.style == "precise" else 0.7,
                "max_tokens": 1024
            }
        )
        resp.raise_for_status()
        result = resp.json()
        if not result.get("choices") or len(result["choices"]) == 0:
            return {"code": -1, "msg": "AI返回数据为空，请重试", "data": None}
        choice = result["choices"][0]
        msg_data = choice.get("message")
        if not msg_data or "content" not in msg_data:
            return {"code": -1, "msg": "AI返回格式异常", "data": None}
        optimized = msg_data["content"].strip()
        print(f"[响应] 优化结果:{optimized[:50]}...")
        return {"code": 0, "msg": "success", "data": {"optimized_prompt": optimized}}
    except httpx.TimeoutException:
        return {"code": -1, "msg": "调用AI服务超时，请稍后重试", "data": None}
    except httpx.NetworkError:
        return {"code": -1, "msg": "无法连接AI服务，请检查网络", "data": None}
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response else 0
        return {"code": -1, "msg": f"AI服务返回错误: {status_code}", "data": None}
    except Exception as e:
        print(f"[内部异常] {repr(e)}")
        return {"code": -1, "msg": "服务内部错误", "data": None}

# ========== 兑换码接口 ==========
@app.post("/claim_code")
async def claim_code(request: Request, req: ClaimCodeRequest):
    client_ip = request.client.host
    fingerprint = req.device_fingerprint or "unknown"
    order_id = req.order_id.strip()

    # 1. 格式校验
    if not re.match(r"^\d{20,32}$", order_id):
        return {"code": -1, "msg": "交易单号格式不正确（应为20-32位数字）"}

    # 2. 黑名单检查
    if is_blacklisted(fingerprint):
        log_audit("blacklist_block", {"fingerprint": fingerprint, "ip": client_ip})
        return {"code": -1, "msg": "您的设备已被限制使用，请联系管理员"}

    # 3. 读取已有数据
    with open(CODES_FILE, "r", encoding="utf-8") as f:
        used_codes = json.load(f)

    today = datetime.now().date().isoformat()

    # 4. IP限流（每天最多3次）
    ip_claims = [info for info in used_codes.values() if info.get("client_ip") == client_ip and info.get("claimed_date") == today]
    if len(ip_claims) >= MAX_CLAIM_PER_IP_DAY:
        return {"code": -1, "msg": f"今日领取次数已达上限（{MAX_CLAIM_PER_IP_DAY}次）"}

    # 5. 交易单号去重
    for info in used_codes.values():
        if info.get("order_id") == order_id:
            return {"code": -1, "msg": "该交易单号已被使用"}

    # 6. 设备指纹去重
    for info in used_codes.values():
        if info.get("device_fingerprint") == fingerprint:
            return {"code": -1, "msg": "该设备已领取过兑换码"}

    # 7. 生成兑换码
    code = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(24))
    while code in used_codes:
        code = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(24))

    used_codes[code] = {
        "order_id": order_id,
        "client_ip": client_ip,
        "device_fingerprint": fingerprint,
        "used": False,
        "claimed_date": today,
        "created_at": datetime.now().isoformat(),
        "expires_at": datetime.now().timestamp() + EXPIRE_HOURS * 3600
    }

    with open(CODES_FILE, "w", encoding="utf-8") as f:
        json.dump(used_codes, f, indent=2, ensure_ascii=False)

    log_audit("code_claimed", {"ip": client_ip, "fingerprint": fingerprint, "order_id": order_id})

    return {
        "code": 0,
        "msg": "兑换码领取成功！请在24小时内验证",
        "data": {"code": code, "expire_hours": EXPIRE_HOURS}
    }

@app.post("/verify_code")
def verify_code(request: Request, req: VerifyCodeRequest):
    client_ip = request.client.host
    code = req.code.strip()

    # 防暴力破解
    if is_verify_locked(client_ip):
        return {"code": -1, "msg": f"验证失败次数过多，已锁定{VERIFY_LOCK_MINUTES}分钟"}

    with open(CODES_FILE, "r", encoding="utf-8") as f:
        used_codes = json.load(f)

    if code not in used_codes:
        record_verify_failure(client_ip)
        log_audit("verify_failed", {"ip": client_ip, "code": code, "reason": "code_not_exists"})
        return {"code": -1, "msg": "兑换码无效，请检查是否输入正确", "data": {"unlocked": False}}

    info = used_codes[code]

    if info.get("used", False):
        record_verify_failure(client_ip)
        return {"code": -1, "msg": "该兑换码已被使用", "data": {"unlocked": False}}

    if time.time() > info.get("expires_at", 0):
        record_verify_failure(client_ip)
        return {"code": -1, "msg": f"兑换码已过期（有效期{EXPIRE_HOURS}小时）", "data": {"unlocked": False}}

    # 验证通过，标记已使用
    info["used"] = True
    info["used_at"] = datetime.now().isoformat()
    info["used_ip"] = client_ip

    with open(CODES_FILE, "w", encoding="utf-8") as f:
        json.dump(used_codes, f, indent=2, ensure_ascii=False)

    reset_verify_failures(client_ip)
    log_audit("verify_success", {"ip": client_ip, "code": code})

    return {"code": 0, "msg": "解锁成功！畅享无限次优化", "data": {"unlocked": True}}

# ========== 管理员接口 ==========
@app.post("/admin/blacklist/add")
def add_blacklist(request: Request):
    token = request.headers.get("X-Admin-Token", "")
    if token != os.getenv("ADMIN_TOKEN", "admin123"):
        return {"code": -1, "msg": "未授权"}
    data = request.json()
    fingerprint = data.get("fingerprint")
    reason = data.get("reason", "手动封禁")
    add_to_blacklist(fingerprint, reason)
    log_audit("blacklist_add", {"fingerprint": fingerprint, "reason": reason})
    return {"code": 0, "msg": "已加入黑名单"}

# ========== 网页页面 ==========
@app.get("/app", response_class=HTMLResponse)
def app_page():
    import json
    template_path = os.path.join(os.path.dirname(__file__), "templates", "app.html")
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    template_buttons = "".join([
        f'<button class="template-btn" data-content="{t["content"]}">{t["name"]}</button>'
        for t in EXAMPLE_TEMPLATES
    ])
    templates_json = json.dumps(EXAMPLE_TEMPLATES, ensure_ascii=False)

    content = content.replace("{FREE_LIMIT}", str(FREE_LIMIT))
    content = content.replace("{PRICE}", PRICE)
    content = content.replace("{template_buttons}", template_buttons)
    content = content.replace("{templates_json}", templates_json)

    return HTMLResponse(content)

@app.get("/api-docs", response_class=HTMLResponse)
def api_docs():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "api-docs.html")
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = content.replace("{SITE_URL}", SITE_URL)
    return HTMLResponse(content)

# ========== 异常处理 ==========
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"code": -2, "msg": "请求过于频繁，请稍后再试", "data": None}
    )

@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"code": -1, "msg": "输入内容不合法，请检查字数是否超限", "data": None}
    )

@app.on_event("shutdown")
async def shutdown_event():
    await httpx_client.aclose()

# ========== 静态文件挂载（必须在所有路由之后） ==========
app.mount("/", StaticFiles(directory="."), name="static")

# ========== 启动入口 ==========
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
