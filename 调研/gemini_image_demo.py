"""
Gemini 图片模型出图 demo（2026-08-05 实测通过）

关键结论（与需求文档 23.4.3 的假设不同，务必按实测方式实现）：
1. gemini-3.1-flash-image 不走标准 /v1/images/generations 接口。
   该接口只支持 imagen 系列，调 gemini 图片模型会报
   "not supported model for image generation, only imagen models are supported"。
2. 正确方式：走 /v1/chat/completions（和文本 Agent 同一个 chat 接口），
   平台强制 stream:true，SSE 流式返回。
3. 图片以 markdown 内嵌 base64 的形式出现在 delta.content 里：
   ![image](data:image/jpeg;base64,<很长的 base64>)
   需要拼接所有 chunk 的 content，再用正则把 base64 抽出来解码存文件。
4. 单次返回约 1MB+（base64 后），落地为文件存 media 目录，不要塞进 DB 字段。
5. Key 与文本模型同平台（moretokens），可复用现有 AI_API_KEY / AI_BASE_URL，
   只需在全局设置新增图片模型名 GEMINI_IMAGE_MODEL=gemini-3.1-flash-image。

运行：python gemini_image_demo.py
"""
import base64
import json
import re

import requests

BASE_URL = "https://moretokens.ai/v1"
API_KEY = "sk-yYkPulZaWOs0NuNsNITZyaIxmLpEW4YG1s3M4RaPb2Ms617Y"  # 测试 Key
IMAGE_MODEL = "gemini-3.1-flash-image"


def generate_image(prompt: str, out_path: str = "cover_out.jpeg") -> str:
    """调 Gemini 图片模型出图，保存为文件，返回文件路径。"""
    resp = requests.post(
        f"{BASE_URL}/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
        json={
            "model": IMAGE_MODEL,
            "stream": True,  # 平台强制流式
            "messages": [{"role": "user", "content": f"Generate an image: {prompt}"}],
        },
        stream=True,
        timeout=120,
    )
    resp.raise_for_status()

    content = ""
    # 注意：按原始字节切行再 UTF-8 解码，避免 requests 用 ISO-8859-1 造成乱码
    for raw_line in resp.iter_lines(decode_unicode=False):
        if not raw_line:
            continue
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
        except Exception:
            continue
        choices = obj.get("choices") or []
        if not choices:
            continue
        piece = (choices[0].get("delta") or {}).get("content")
        if piece:
            content += piece

    m = re.search(r"data:image/(\w+);base64,([A-Za-z0-9+/=]+)", content)
    if not m:
        raise RuntimeError(f"未返回图片，content 开头：{content[:200]}")
    img = base64.b64decode(m.group(2))
    with open(out_path, "wb") as f:
        f.write(img)
    return out_path


if __name__ == "__main__":
    path = generate_image(
        "a cute cat sitting on a red sofa, photorealistic, high quality",
        "cover_out.jpeg",
    )
    print("已生成封面：", path)
