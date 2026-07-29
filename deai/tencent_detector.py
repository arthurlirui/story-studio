#!/usr/bin/env python3
"""
腾讯云 AIGC 文本鉴伪后端

API: tms.tencentcloudapi.com, Action=TextModeration, Type=TEXT_AIGC
价格: 0.05元/条, 限制: 50次/秒

密钥来源: TENCENT_SECRET_ID/TENCENT_SECRET_KEY 环境变量 或 .env 文件
"""

import os
import json
import hashlib
import hmac
import base64
import time
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("deai.tencent")

API_ENDPOINT = "https://tms.tencentcloudapi.com"


def load_credentials():
    sid = os.environ.get("TENCENT_SECRET_ID")
    skey = os.environ.get("TENCENT_SECRET_KEY")
    if sid and skey:
        return sid, skey

    env_paths = [
        Path(__file__).resolve().parent.parent / ".env",
        Path.home() / ".tencentcloud" / ".env",
    ]
    for f in env_paths:
        if f.exists():
            for line in f.read_text("utf-8").splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k == "TENCENT_SECRET_ID":
                    sid = v
                elif k == "TENCENT_SECRET_KEY":
                    skey = v
            if sid and skey:
                return sid, skey
    return None, None


def sign_v3(sid, skey, payload, service="tms", region="ap-guangzhou"):
    algorithm = "TC3-HMAC-SHA256"
    host = f"{service}.tencentcloudapi.com"
    timestamp = int(time.time())
    date = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")

    ct = "application/json; charset=utf-8"
    payload_str = json.dumps(payload)
    canonical_headers = f"content-type:{ct}\nhost:{host}\n"
    signed_headers = "content-type;host"
    hashed_payload = hashlib.sha256(payload_str.encode()).hexdigest()
    canonical_request = (
        f"POST\n/\n\n{canonical_headers}\n{signed_headers}\n{hashed_payload}"
    )

    credential_scope = f"{date}/{service}/tc3_request"
    hashed_canonical = hashlib.sha256(canonical_request.encode()).hexdigest()
    string_to_sign = (
        f"{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical}"
    )

    def _sign(key, msg):
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    secret_date = _sign(b"TC3" + skey.encode(), date)
    secret_service = _sign(secret_date, service)
    secret_signing = _sign(secret_service, "tc3_request")
    signature = hmac.new(
        secret_signing, string_to_sign.encode(), hashlib.sha256
    ).hexdigest()

    authorization = (
        f"{algorithm} Credential={sid}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    return {
        "Authorization": authorization,
        "Content-Type": ct,
        "Host": host,
        "X-TC-Action": payload.get("Action", ""),
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Version": payload.get("Version", ""),
        "X-TC-Region": region,
    }


_last_call = 0.0


async def rate_limit():
    global _last_call
    now = time.time()
    gap = 1.0 / 40  # 保守点, 40次/秒
    if now - _last_call < gap:
        import asyncio
        await asyncio.sleep(gap - (now - _last_call))
    _last_call = time.time()


async def check(text, biz_type=""):
    """调用腾讯云 AI 生成识别"""
    sid, skey = load_credentials()
    if not sid or not skey:
        return {"score": 0, "label": "Error", "detail": "未配置腾讯云密钥", "raw": {}}

    content_b64 = base64.b64encode(text.encode()).decode()

    payload = {
        "Action": "TextModeration",
        "Version": "2020-12-29",
        "Content": content_b64,
        "Type": "TEXT_AIGC",
    }
    if biz_type:
        payload["BizType"] = biz_type

    headers = sign_v3(sid, skey, payload)

    await rate_limit()

    import httpx
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(API_ENDPOINT, json=payload, headers=headers)
        resp.raise_for_status()
        result = resp.json()

    if "Response" not in result:
        return {"score": 0, "label": "Error", "detail": str(result), "raw": result}

    r = result["Response"]
    if "Error" in r:
        return {
            "score": 0, "label": "Error",
            "detail": f"{r['Error'].get('Code')}: {r['Error'].get('Message')}",
            "raw": r,
        }

    label = r.get("Label", "")
    score = float(r.get("Score", 0))
    if score > 1:
        score /= 100.0

    return {
        "score": score,
        "label": label,
        "detail": r.get("Detail", ""),
        "raw": r,
    }


async def check_before_after(original, polished):
    """对比润色前后"""
    before = await check(original)
    after = await check(polished)
    delta = before["score"] - after["score"]
    return {
        "before": before,
        "after": after,
        "improvement": delta,
        "verdict": "effective" if delta > 0.05 else (
            "slight" if delta > 0.01 else "ineffective"
        ),
    }
