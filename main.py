import os
import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, constr

# 直接写死 API Key（临时测试用）
api_key = "sk-45e2702088df44ef9d85bbdf3c2133de"

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
    except requests.exceptions.HTTPError as e:
        return {"code": -1, "msg": f"AI服务返回错误: {response.status_code}", "data": None}
    except Exception as e:
        return {"code": -1, "msg": "服务内部错误", "data": None}

@app.get("/")
def root():
    return {"code": 0, "msg": "服务运行中", "data": None}

# ========== 网页版入口 ==========
@app.get("/app", response_class=HTMLResponse)
def app_page():
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI提示词优化</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f7f7f8;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 700px;
            width: 100%;
            background: white;
            border-radius: 24px;
            padding: 40px 35px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.08);
        }
        h1 { font-size: 28px; font-weight: 600; color: #1a1a1a; margin-bottom: 8px; }
        .subtitle { color: #6b6b6b; font-size: 15px; margin-bottom: 30px; }
        .counter { text-align: right; font-size: 14px; color: #888; margin-bottom: 12px; }
        .counter span { font-weight: 600; color: #333; }
        textarea {
            width: 100%;
            min-height: 120px;
            padding: 16px 18px;
            font-size: 16px;
            border: 1.5px solid #e5e5e5;
            border-radius: 16px;
            resize: vertical;
            font-family: inherit;
            outline: none;
            transition: border 0.2s;
        }
        textarea:focus { border-color: #4f46e5; }
        .btn-row { display: flex; gap: 12px; margin-top: 16px; flex-wrap: wrap; }
        .btn {
            padding: 12px 28px;
            font-size: 16px;
            font-weight: 500;
            border: none;
            border-radius: 40px;
            cursor: pointer;
            transition: all 0.2s;
            flex: 1;
            min-width: 120px;
        }
        .btn-primary { background: #4f46e5; color: white; }
        .btn-primary:hover { background: #4338ca; }
        .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-secondary { background: #f3f4f6; color: #1f2937; }
        .btn-secondary:hover { background: #e5e7eb; }
        .result-box {
            margin-top: 24px;
            padding: 20px 22px;
            background: #f9fafb;
            border-radius: 16px;
            border: 1px solid #f0f0f0;
            display: none;
            white-space: pre-wrap;
            word-break: break-word;
            line-height: 1.7;
            font-size: 15px;
            color: #1a1a1a;
        }
        .result-box.show { display: block; }
        .result-box .label { font-size: 13px; font-weight: 500; color: #6b6b6b; margin-bottom: 8px; }
        .toast {
            position: fixed;
            top: 30px;
            left: 50%;
            transform: translateX(-50%);
            background: #1f2937;
            color: white;
            padding: 14px 28px;
            border-radius: 40px;
            font-size: 15px;
            box-shadow: 0 12px 40px rgba(0,0,0,0.2);
            display: none;
            z-index: 999;
        }
        .toast.show { display: block; }
        .modal-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.4);
            backdrop-filter: blur(4px);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
        .modal-overlay.show { display: flex; }
        .modal {
            background: white;
            border-radius: 32px;
            padding: 40px 35px;
            max-width: 420px;
            width: 90%;
            text-align: center;
            box-shadow: 0 30px 80px rgba(0,0,0,0.2);
        }
        .modal h2 { font-size: 22px; margin-bottom: 8px; }
        .modal p { color: #6b6b6b; font-size: 15px; margin-bottom: 20px; line-height: 1.6; }
        .modal .price { font-size: 32px; font-weight: 700; color: #4f46e5; margin: 12px 0 6px; }
        .modal .price-desc { font-size: 14px; color: #888; margin-bottom: 24px; }
        .modal .qrcode {
            width: 180px;
            height: 180px;
            background: #f3f4f6;
            border-radius: 16px;
            margin: 0 auto 18px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            color: #999;
        }
        .modal .btn-pay {
            background: #4f46e5;
            color: white;
            border: none;
            padding: 14px 40px;
            border-radius: 40px;
            font-size: 16px;
            font-weight: 500;
            cursor: pointer;
        }
        .modal .btn-pay:hover { background: #4338ca; }
        .modal .close-modal { margin-top: 16px; background: none; border: none; color: #999; font-size: 14px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="toast" id="toast"></div>
    <div class="container">
        <h1>✨ 提示词优化</h1>
        <p class="subtitle">让你的 AI 提示更清晰、更高效</p>
        <div class="counter">今日剩余：<span id="remain">3</span> 次</div>
        <textarea id="inputArea" placeholder="输入你想要优化的提示词，例如：帮我写一个关于时间管理的公众号文章大纲"></textarea>
        <div class="btn-row">
            <button class="btn btn-primary" id="optimizeBtn">🚀 优化</button>
            <button class="btn btn-secondary" id="copyBtn" style="flex:0.5;min-width:80px;">📋 复制</button>
        </div>
        <div class="result-box" id="resultBox">
            <div class="label">✅ 优化结果</div>
            <div id="resultContent"></div>
        </div>
    </div>
    <div class="modal-overlay" id="payModal">
        <div class="modal">
            <h2>🔒 免费次数已用完</h2>
            <p>继续使用仅需 <strong>¥9.9</strong>，永久解锁无限次优化。</p>
            <div class="price">¥9.9</div>
            <div class="price-desc">一次性付费，永久使用</div>
            <div class="qrcode">📱 微信/支付宝 扫码支付</div>
            <button class="btn-pay" id="payBtn">我已支付，立即解锁</button>
            <br>
            <button class="close-modal" id="closeModalBtn">✕ 关闭</button>
        </div>
    </div>
    <script>
        const STORAGE_KEY = 'prompt_optimizer_usage';
        const FREE_LIMIT = 3;
        const UNLOCKED_KEY = 'prompt_optimizer_unlocked';
        function getUsage() { const raw = localStorage.getItem(STORAGE_KEY); return raw ? parseInt(raw, 10) : 0; }
        function setUsage(val) { localStorage.setItem(STORAGE_KEY, String(val)); }
        function isUnlocked() { return localStorage.getItem(UNLOCKED_KEY) === 'true'; }
        function getRemain() { if (isUnlocked()) return Infinity; const used = getUsage(); return Math.max(0, FREE_LIMIT - used); }
        function showToast(msg, duration = 2500) {
            const el = document.getElementById('toast');
            el.textContent = msg;
            el.classList.add('show');
            clearTimeout(el._timer);
            el._timer = setTimeout(() => el.classList.remove('show'), duration);
        }
        function updateUI() {
            const remain = getRemain();
            document.getElementById('remain').textContent = remain === Infinity ? '∞' : remain;
            const btn = document.getElementById('optimizeBtn');
            if (remain <= 0 && !isUnlocked()) {
                btn.disabled = true;
                btn.textContent = '🔒 已用尽，请解锁';
            } else {
                btn.disabled = false;
                btn.textContent = '🚀 优化';
            }
        }
        function showPayModal() { document.getElementById('payModal').classList.add('show'); }
        function hidePayModal() { document.getElementById('payModal').classList.remove('show'); }
        document.getElementById('payBtn').addEventListener('click', function() {
            localStorage.setItem(UNLOCKED_KEY, 'true');
            hidePayModal();
            updateUI();
            showToast('🎉 解锁成功！现在可以无限次使用');
        });
        document.getElementById('closeModalBtn').addEventListener('click', hidePayModal);
        document.getElementById('payModal').addEventListener('click', function(e) { if (e.target === this) hidePayModal(); });
        document.getElementById('optimizeBtn').addEventListener('click', async function() {
            const remain = getRemain();
            if (remain <= 0 && !isUnlocked()) { showPayModal(); return; }
            const input = document.getElementById('inputArea').value.trim();
            if (!input) { showToast('⚠️ 请先输入提示词'); return; }
            this.disabled = true;
            this.textContent = '⏳ 优化中...';
            try {
                const res = await fetch('/optimize', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt: input })
                });
                const data = await res.json();
                if (data.code === 0) {
                    const result = data.data.optimized_prompt;
                    document.getElementById('resultContent').textContent = result;
                    document.getElementById('resultBox').classList.add('show');
                    if (!isUnlocked()) { const used = getUsage(); setUsage(used + 1); updateUI(); }
                } else {
                    showToast('❌ ' + (data.msg || '服务异常，请重试'));
                }
            } catch (e) {
                showToast('❌ 网络错误，请检查连接');
            } finally {
                this.disabled = false;
                this.textContent = '🚀 优化';
            }
        });
        document.getElementById('copyBtn').addEventListener('click', function() {
            const content = document.getElementById('resultContent').textContent;
            if (!content) { showToast('⚠️ 没有可复制的内容'); return; }
            navigator.clipboard.writeText(content).then(() => { showToast('✅ 已复制到剪贴板'); }).catch(() => {
                const ta = document.createElement('textarea');
                ta.value = content;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                ta.remove();
                showToast('✅ 已复制到剪贴板');
            });
        });
        updateUI();
        if (isUnlocked()) { document.getElementById('remain').textContent = '∞'; }
    </script>
</body>
</html>
    """