import os
import requests
from fastapi import FastAPI
from pydantic import BaseModel, constr
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")
if not api_key:
    raise ValueError("请在.env文件中设置 DEEPSEEK_API_KEY")

app = FastAPI(
    title="AI提示词优化API",
    description="将模糊的提示词优化为更清晰、更具可操作性的高质量提示词。"
)

class PromptRequest(BaseModel):
    prompt: constr(min_length=1, max_length=2000)

SYSTEM_PROMPT = (
    "你是一个世界级的AI提示词优化专家。"
    "你的任务是将用户提供的提示词优化得更清晰、更具可操作性，"
    "并且直接返回优化后的提示词，不要添加任何解释或前缀。"
)

@app.post("/optimize")
def optimize_prompt(request: PromptRequest):
    print(f"[请求] 用户输入: {request.prompt[:50]}...")

    try:
        response = requests.post(
            url="https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": request.prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 1024
            },
            timeout=15
        )

        response.raise_for_status()
        result = response.json()
        optimized = result["choices"][0]["message"]["content"].strip()

        print(f"[响应] 优化结果: {optimized[:50]}...")

        return {
            "code": 0,
            "msg": "success",
            "data": {"optimized_prompt": optimized}
        }

    except requests.exceptions.Timeout:
        return {"code": -1, "msg": "调用AI服务超时，请稍后重试", "data": None}
    except requests.exceptions.ConnectionError:
        return {"code": -1, "msg": "无法连接AI服务，请检查网络", "data": None}
    except requests.exceptions.HTTPError:
        return {"code": -1, "msg": f"AI服务返回错误: {response.status_code}", "data": None}
    except Exception:
        return {"code": -1, "msg": "服务内部错误", "data": None}

@app.get("/")
def root():
    return {"code": 0, "msg": "服务运行中", "data": None}