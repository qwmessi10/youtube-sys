"""
流程3 服务层（与 content_gen 完全隔离，零跨 app import）。
底层 AI/设置工具复制自 keywords.services，避免删除流程1/2 时受牵连。

能力：
  - _call_ai_stream / _extract_json / get_setting：moretokens OpenAI 兼容 SSE 基础能力
  - 各 Agent 文案生成（hook / narration / blur_bg / tail_image / metadata）
  - 双生图（模糊底图 + 尾图），走 chat 接口 base64 内嵌
  - 印式英语 TTS
  - ffmpeg：SegC zoompan 微动、三段 concat、BGM 混音、防封去重
  - ffprobe 探测时长、zip 打包
"""
import base64
import json
import os
import re
import subprocess
import time

import requests
from django.core.files.base import ContentFile

# 全局设置表属 keywords（全系统基础设施，不随流程1/2 删除），可安全依赖。
from keywords.models import GlobalSetting

from .models import Flow3Agent


# ===========================================================================
# 基础能力（复制自 keywords.services，流程3 自持一份）
# ===========================================================================
def get_setting(key, default=""):
    """读取全局设置：DB（keywords.GlobalSetting）优先，回退环境变量。
    说明：全局设置表属于基础设施（全系统共用，非流程1/2 专属），直接依赖 keywords.GlobalSetting，
    不 import content_gen，删除流程1/2 不受影响。"""
    value = GlobalSetting.objects.filter(key=key).values_list("value", flat=True).first()
    return value if value not in (None, "") else os.getenv(key, default)


def _call_ai_stream(messages, timeout=180, max_retries=3):
    """
    调用 moretokens（OpenAI 兼容）聊天接口，强制 stream:true，拼接返回完整文本。
    该平台模型响应较慢（10~30s）且偶发中途断连（SSL EOF / ChunkedEncoding），
    故对「连接类错误」或「拿到空内容」做指数退避重试，提升长链路任务的稳定性。
    """
    base_url = get_setting("AI_BASE_URL", "https://moretokens.ai/v1").rstrip("/")
    api_key = get_setting("AI_API_KEY")
    model = get_setting("AI_MODEL", "gemini-3.6-flash-medium")
    if not api_key:
        raise RuntimeError("未配置 AI_API_KEY")

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "stream": True, "messages": messages},
                timeout=timeout,
                stream=True,
            )
            response.raise_for_status()

            chunks = []
            for raw_line in response.iter_lines(decode_unicode=False):
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="replace")
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if payload == "[DONE]":
                    break
                try:
                    delta = json.loads(payload)["choices"][0].get("delta", {})
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                content = delta.get("content")
                if content:
                    chunks.append(content)
            text = "".join(chunks)
            if text.strip():
                return text
            # 拿到空内容（服务端中途断开但未抛异常）：视为失败，重试。
            last_error = RuntimeError("AI 返回空内容（可能被服务端中途断开）")
        except (requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.SSLError) as exc:
            last_error = exc
        except requests.exceptions.HTTPError as exc:
            # 5xx 可重试；4xx（鉴权/参数）直接抛，避免浪费额度。
            status = getattr(exc.response, "status_code", 0)
            if status and status < 500:
                raise
            last_error = exc
        if attempt < max_retries:
            time.sleep(2 ** attempt)  # 2s, 4s 指数退避
    raise RuntimeError(f"AI 调用失败（已重试 {max_retries} 次）：{last_error}")


def _extract_json(text):
    """从 AI 返回文本中提取 JSON 对象（容忍 ```json 代码块或前后多余文字）。"""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


# ===========================================================================
# 默认提示词（可在 Agent 管理页覆盖）。占位符：[input]=关键词；
# {PROMO_CODE}/{COUNTRY}/{EVENT_NAME} 为全局变量注入；[output]=固定输出格式说明。
# ===========================================================================
DEFAULT_HOOK_PROMPT = """# 角色
你是一位务实的品牌推广视频编导，服务于面向南亚（印度）市场的平台推广。
你擅长写克制、可信、有官方感的开场 Hook，而不是浮夸的大奖炫技画面。

# 目标
根据给定的关键词和优惠码，生成一段约 7-8 秒 Hook 视频的「文生视频」英文 Prompt，
用于外部 AI 视频生成引擎（如 Runway/Kling/Sora 类）渲染开场画面。

# 风格要求（重要）
- 官方、务实、可信，像平台官方公告或正规教程的开场，不要浮夸奢华、不要满屏金币/烟花/爆炸。
- 南亚（印度）本地化：真实的印度日常/城市/居家或手机操作场景，普通印度人物，自然光线，纪实感。
- 画面干净、克制、专业；镜头平稳（轻微推进或手持感即可），不要炫技运镜。
- 必须与关键词强相关：围绕「[input]」所指的平台/产品/操作主题来构图。
- 必须自然体现优惠码 {PROMO_CODE}：可以让优惠码以简洁的屏幕文字/界面输入框/卡片形式出现在画面中（清晰可读），不夸张。
- 若优惠码为空则不强行展示优惠码。

# 输入
关键词：[input]
国家：{COUNTRY}
优惠码：{PROMO_CODE}

# 输出
[output]"""

HOOK_OUTPUT_SPEC = """严格只输出一个 JSON 对象，不要输出任何解释文字或 markdown 代码块标记，格式如下：
{"video_prompt": "用于外部 AI 视频引擎的英文提示词（一段连贯描述，含画面、运镜、风格、时长约8秒）"}"""

DEFAULT_NARRATION_PROMPT = """# 角色
你是一位务实、可信的印度英语口播文案师，语气像正规教程/官方介绍，不浮夸。

# 目标
根据给定的关键词，撰写一段用于视频配音（TTS 朗读）的印度英语旁白，
目的是自然介绍并引导观众使用优惠码 {PROMO_CODE} 完成注册。
画面由固定模板呈现，你只需产出要被朗读的旁白文字。

# 要求
- 与关键词「[input]」强相关，围绕该平台/产品/操作讲清楚「怎么做、用什么码、有什么好处」。
- 语气务实、可信、口语自然，贴合印度本地观众；不要浮夸承诺和夸张煽动。
- 必须自然地把优惠码读出来：在要提到优惠码处原样写占位符 {{promo_code}}（不要自己编造、不要改写），
  系统会在渲染时替换成真实优惠码，TTS 会把真实码读出来。

# 输入
关键词：[input]
国家：{COUNTRY}

# 输出
[output]"""

NARRATION_OUTPUT_SPEC = """严格只输出一个 JSON 对象，不要输出任何解释文字或 markdown 代码块标记。
需要把旁白拆成 {shot_count} 段，每段约 {shot_duration} 秒，总时长约 {total_duration} 秒。格式如下：
{{"shots": [{{"index": 1, "duration": {shot_duration}, "narration": "该段旁白文案（英文）"}}]}}
shots 数组恰好包含 {shot_count} 个元素，index 从 1 递增。
重要：每段 narration 必须简短，**每段不超过 {narration_word_limit} 个英文单词**，确保朗读时长不超过 {shot_duration} 秒。
如需提及优惠码，请原样写占位符 {{promo_code}}（不要自己编造），系统会在渲染时替换成真实优惠码。"""

DEFAULT_BLUR_BG_PROMPT = """# 角色
你是一位视觉设计师，为面向南亚（印度）市场的平台推广视频设计背景底图。

# 目标
根据关键词，生成一张「高质感、可用作高斯模糊底图」的英文生图 Prompt。
该图将作为视频中段的背景（会被高斯模糊处理），要求色调统一、干净专业、与关键词主题相关，
避免画面中出现清晰文字（会被模糊）。

# 风格
- 务实、克制、可信，不要浮夸奢华、不要金币/大奖/炫光堆砌。
- 南亚（印度）本地化氛围：真实城市/居家/手机操作/体育生活等自然场景皆可，按关键词主题取舍。
- 默认修饰词可含 8k, photorealistic, clean, professional, soft natural lighting。

# 输入
关键词：[input]
国家：{COUNTRY}

# 输出
[output]"""

DEFAULT_TAIL_IMAGE_PROMPT = """# 角色
你是一位视觉设计师，为面向南亚（印度）市场的平台推广视频设计尾部主视觉图。

# 目标
根据关键词，生成一张「清晰、专业、与关键词主题强相关」的高清尾图英文生图 Prompt。
该图将作为视频尾部背景（带呼吸/抖动微动效果），要求主题鲜明、画质高清、观感可信。

# 风格
- 务实、官方、可信，像正规平台的收尾画面；不要浮夸奢华、不要大奖/金币/爆炸特效。
- 南亚（印度）本地化：围绕关键词所指的平台/产品/操作主题，真实自然的人物或场景。
- 注意：本提示词与「模糊底图」不同，这是清晰的尾部主视觉，不要做成模糊背景。
- 默认修饰词可含 8k, photorealistic, clean, professional, dramatic but realistic lighting。

# 输入
关键词：[input]
国家：{COUNTRY}

# 输出
[output]"""

IMAGE_OUTPUT_SPEC = """严格只输出一个 JSON 对象，不要输出任何解释文字或 markdown 代码块标记，格式如下：
{"image_prompt": "用于图片生成模型的英文提示词"}"""

DEFAULT_METADATA_PROMPT = """# 角色
你是一位资深的 YouTube 内容运营，擅长为博彩/娱乐类视频撰写高点击率的标题、描述与封面创意。

# 目标
根据给定的关键词，生成一条 YouTube 视频的元数据：标题、描述、封面提示词。
标题围绕关键词做自然搜索截流；描述为视频描述区文案；封面提示词用英文描述一张吸引点击的缩略图画面。

# 输入
关键词：[input]

# 输出
[output]"""

METADATA_OUTPUT_SPEC = """严格只输出一个 JSON 对象，不要输出任何解释文字或 markdown 代码块标记，格式如下：
{"title": "YouTube 视频标题", "description": "YouTube 视频描述文案", "thumbnail_prompt": "用于图片模型的英文封面提示词"}"""

# agent_type → 内置默认提示词。用于种子回填与「恢复系统默认」。
DEFAULT_AGENT_PROMPTS = {
    Flow3Agent.AGENT_HOOK: DEFAULT_HOOK_PROMPT,
    Flow3Agent.AGENT_NARRATION: DEFAULT_NARRATION_PROMPT,
    Flow3Agent.AGENT_BLUR_BG: DEFAULT_BLUR_BG_PROMPT,
    Flow3Agent.AGENT_TAIL_IMAGE: DEFAULT_TAIL_IMAGE_PROMPT,
    Flow3Agent.AGENT_METADATA: DEFAULT_METADATA_PROMPT,
}


def get_default_agent_prompt(agent_type):
    """返回某 Agent 的内置默认提示词；未登记返回空串。"""
    return DEFAULT_AGENT_PROMPTS.get(agent_type, "")


def _inject_globals(text, run):
    """把 {PROMO_CODE}/{COUNTRY}/{EVENT_NAME} 全局占位符替换成任务实际值。"""
    if not text:
        return text
    return (text
            .replace("{PROMO_CODE}", run.promo_code or "")
            .replace("{COUNTRY}", run.country or "")
            .replace("{EVENT_NAME}", run.event_name or ""))


def _get_prompt(agent_type):
    """从 Flow3Agent 读提示词；留空或未配置回退默认。返回 (prompt, agent)。被停用返回 (None, agent)。"""
    agent = Flow3Agent.objects.filter(agent_type=agent_type).first()
    if agent and not agent.enabled:
        return None, agent
    fallback = DEFAULT_AGENT_PROMPTS.get(agent_type, "")
    prompt = (agent.prompt if agent and agent.prompt.strip() else "") or fallback
    return prompt, agent


# ===========================================================================
# 各 Agent 文案生成
# ===========================================================================
def generate_hook_prompt(run):
    """Hook 文案 Agent → 产出外部视频引擎用的英文 video_prompt。返回 (prompt_text, log)。"""
    prompt, agent = _get_prompt(Flow3Agent.AGENT_HOOK)
    if prompt is None:
        raise RuntimeError("Hook 视频文案 Agent 已停用")
    full = _inject_globals(prompt, run).replace("[input]", run.keyword).replace("[output]", HOOK_OUTPUT_SPEC)
    raw = _call_ai_stream([{"role": "user", "content": full}])
    data = _extract_json(raw)
    video_prompt = (data.get("video_prompt") or "").strip()
    log = {"model": get_setting("AI_MODEL", "gemini-3.6-flash-medium"), "prompt": full, "raw_output": raw, "parsed": data}
    return video_prompt, log


def generate_narration_script(run, shot_count, shot_duration):
    """语音文案 Agent → 产出分段旁白（印式英语）。返回 (data, log)。data={shots:[{index,duration,narration}]}。"""
    prompt, agent = _get_prompt(Flow3Agent.AGENT_NARRATION)
    if prompt is None:
        raise RuntimeError("语音文案 Agent 已停用")
    total = shot_count * shot_duration
    narration_word_limit = max(1, int(shot_duration * 2.5))
    output_spec = NARRATION_OUTPUT_SPEC.format(
        shot_count=shot_count, shot_duration=shot_duration,
        total_duration=total, narration_word_limit=narration_word_limit,
    )
    full = _inject_globals(prompt, run).replace("[input]", run.keyword).replace("[output]", output_spec)
    raw = _call_ai_stream([{"role": "user", "content": full}])
    data = _extract_json(raw)
    shots = data.get("shots") if isinstance(data.get("shots"), list) else []
    normalized = []
    for i, shot in enumerate(shots[:shot_count], 1):
        shot = shot if isinstance(shot, dict) else {}
        text = (shot.get("narration") or "").strip()
        # 关键：把 AI 写的 {promo_code} 占位符替换成真实优惠码，TTS 才会念出真实码。
        # 兼容大小写与有无花括号的几种写法。
        if run.promo_code:
            for ph in ("{promo_code}", "{PROMO_CODE}", "{{promo_code}}", "[promo_code]", "PROMO_CODE"):
                text = text.replace(ph, run.promo_code)
        normalized.append({
            "index": shot.get("index", i),
            "duration": shot.get("duration", shot_duration),
            "narration": text,
        })
    result = {"keyword": run.keyword, "total_duration": total, "shots": normalized}
    log = {"model": get_setting("AI_MODEL", "gemini-3.6-flash-medium"), "prompt": full, "raw_output": raw, "parsed": data}
    return result, log


def generate_metadata(run):
    """元数据 Agent → 标题/描述/封面提示词。返回 (data, log)。"""
    prompt, agent = _get_prompt(Flow3Agent.AGENT_METADATA)
    if prompt is None:
        raise RuntimeError("元数据生成 Agent 已停用")
    full = _inject_globals(prompt, run).replace("[input]", run.keyword).replace("[output]", METADATA_OUTPUT_SPEC)
    raw = _call_ai_stream([{"role": "user", "content": full}])
    data = _extract_json(raw)
    result = {
        "title": (data.get("title") or "").strip(),
        "description": (data.get("description") or "").strip(),
        "thumbnail_prompt": (data.get("thumbnail_prompt") or "").strip(),
    }
    log = {"model": get_setting("AI_MODEL", "gemini-3.6-flash-medium"), "prompt": full, "raw_output": raw, "parsed": data}
    return result, log


def _generate_image_prompt(run, agent_type):
    """模糊底图 / 尾图 Agent → 产出英文生图 prompt。返回 (image_prompt, log)。"""
    prompt, agent = _get_prompt(agent_type)
    if prompt is None:
        raise RuntimeError(f"{dict(Flow3Agent.AGENT_TYPE_CHOICES).get(agent_type, agent_type)} 已停用")
    full = _inject_globals(prompt, run).replace("[input]", run.keyword).replace("[output]", IMAGE_OUTPUT_SPEC)
    raw = _call_ai_stream([{"role": "user", "content": full}])
    data = _extract_json(raw)
    image_prompt = (data.get("image_prompt") or "").strip()
    log = {"model": get_setting("AI_MODEL", "gemini-3.6-flash-medium"), "prompt": full, "raw_output": raw, "parsed": data}
    return image_prompt, log


# ===========================================================================
# 生图：走 moretokens /chat/completions（强制 stream:true），图片以 base64 内嵌在 SSE content。
# ===========================================================================
def generate_image(image_prompt):
    """
    调 Gemini 图片模型出图。返回 (django ContentFile, ext)；未拿到图片抛 RuntimeError。
    与流程1/2 的 generate_thumbnail 同机制，flow3 自持一份。
    """
    base_url = get_setting("AI_BASE_URL", "https://moretokens.ai/v1").rstrip("/")
    api_key = get_setting("GEMINI_IMAGE_API_KEY") or get_setting("AI_API_KEY")
    model = get_setting("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
    if not api_key:
        raise RuntimeError("未配置 GEMINI_IMAGE_API_KEY 或 AI_API_KEY")

    max_retries = 3
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "stream": True, "messages": [
                    {"role": "user", "content": f"Generate an image: {image_prompt}"},
                ]},
                timeout=240,
                stream=True,
            )
            response.raise_for_status()

            content = ""
            for raw_line in response.iter_lines(decode_unicode=False):
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="replace")
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

            match = re.search(r"data:image/(\w+);base64,([A-Za-z0-9+/=]+)", content)
            if match:
                ext = match.group(1)
                if ext == "jpeg":
                    ext = "jpg"
                return ContentFile(base64.b64decode(match.group(2))), ext
            last_error = RuntimeError(f"图片模型未返回图片，返回开头：{content[:200]}")
        except (requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.SSLError) as exc:
            last_error = exc
        except requests.exceptions.HTTPError as exc:
            status = getattr(exc.response, "status_code", 0)
            if status and status < 500:
                raise
            last_error = exc
        if attempt < max_retries:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"生图失败（已重试 {max_retries} 次）：{last_error}")


# ===========================================================================
# 印式英语 TTS（Edge TTS 免费，印式音色）。失败降级 elevenlabs，再失败跳过该段。
# ===========================================================================
# 印式英语音色（默认男声 Prabhat）。全局设置 FLOW3_TTS_VOICE 优先。
_INDIAN_EN_VOICES = ["en-IN-PrabhatNeural", "en-IN-NeerjaNeural"]


def _edge_voice(language):
    """取 TTS 音色：全局设置 FLOW3_TTS_VOICE 优先，否则印式英语默认。"""
    configured = get_setting("FLOW3_TTS_VOICE")
    if configured:
        return configured
    # 流程3 固定印式英语；language 预期为 en-IN。
    return _INDIAN_EN_VOICES[0]


def _tts_edge(text, language, out_path):
    """用 edge-tts 合成一段旁白到 out_path（mp3）。"""
    import asyncio

    import edge_tts

    voice = _edge_voice(language)

    async def _run():
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(out_path)

    asyncio.run(_run())
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError("edge-tts 未产出音频")


def _tts_elevenlabs(text, out_path):
    """用 ElevenLabs REST API 合成一段旁白到 out_path（mp3）。"""
    api_key = get_setting("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("未配置 ELEVENLABS_API_KEY")
    voice_id = get_setting("ELEVENLABS_VOICE_ID") or "21m00Tcm4TlvDq8ikWAM"
    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": text, "model_id": "eleven_multilingual_v2"},
        timeout=120,
    )
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(resp.content)
    if os.path.getsize(out_path) == 0:
        raise RuntimeError("elevenlabs 未产出音频")


def generate_narration_audio(shots, language, out_dir, filename_prefix):
    """
    为每段 narration 合成印式英语旁白音频。edge 优先，失败降级 elevenlabs，再失败跳过该段。
    返回 (audio_list, log)：audio_list=[{"index","file":绝对路径,"provider"}]（跳过的不在内）。
    """
    os.makedirs(out_dir, exist_ok=True)
    audio_list, seg_logs = [], []
    for shot in shots:
        idx = shot.get("index")
        text = (shot.get("narration") or "").strip()
        seg = {"index": idx}
        if not text:
            seg.update({"status": "skipped", "error": "该段无旁白文案"})
            seg_logs.append(seg)
            continue
        out_path = os.path.join(out_dir, f"{filename_prefix}_{idx}.mp3")
        done, errors = False, []
        for prov in ("edge", "elevenlabs"):
            try:
                if prov == "edge":
                    _tts_edge(text, language, out_path)
                else:
                    _tts_elevenlabs(text, out_path)
                audio_list.append({"index": idx, "file": out_path, "provider": prov})
                seg.update({"status": "success" if prov == "edge" else "fallback", "provider": prov})
                if errors:
                    seg["error"] = "；".join(errors)
                done = True
                break
            except Exception as exc:
                errors.append(f"{prov}: {exc}")
        if not done:
            seg.update({"status": "skipped", "error": "；".join(errors)})
        seg_logs.append(seg)
    return audio_list, {"provider": "edge", "segments": seg_logs}


# ===========================================================================
# 媒体探测
# ===========================================================================
def probe_duration(abs_path):
    """用 ffprobe 读视频/音频真实时长（秒 float）。读不到返回 None。"""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", abs_path],
            capture_output=True, text=True, timeout=60,
        )
        val = (out.stdout or "").strip()
        return float(val) if val else None
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


# ===========================================================================
# SegB：调 Remotion 渲染服务，出左右分屏画中画（文字+录屏+高斯模糊底图）。
# 左右位置由 layout_seed 决定（偶数=录屏在右，奇数=录屏在左）。
# ===========================================================================
def render_segment_b(*, promo_code, blur_bg_abs, screen_abs, screen_duration,
                     shots, narration_audio, segb_duration, layout_seed,
                     output_abs_path, promo_variant=0, render_url=None, timeout=1200):
    """
    通过 HTTP 调 render 容器的 Remotion 服务渲染 SegB（compositionId=Flow3SegmentB）。
    所有路径用 render 容器可见的共享卷绝对路径（/app/media/...）。
    返回 render 响应 dict（含 durationInFrames）。失败抛异常。
    """
    render_url = render_url or get_setting("FLOW3_RENDER_URL",
                                           get_setting("REMOTION_RENDER_URL", "http://render:3000/render"))
    audio_by_index = {a.get("index"): a.get("file") for a in (narration_audio or [])}
    prop_shots = []
    for shot in shots or []:
        idx = shot.get("index")
        prop_shots.append({
            "index": idx,
            "duration": shot.get("duration") or 8,
            "narration": (shot.get("narration") or "").strip(),
            "audioSrc": audio_by_index.get(idx, ""),
        })
    # 录屏左右：seed 偶数→录屏在右（文字在左），奇数→录屏在左（文字在右）。
    screen_on_right = (int(layout_seed) % 2 == 0)
    input_props = {
        "promoCode": promo_code or "",
        "blurBgSrc": blur_bg_abs or "",
        "screenSrc": screen_abs or "",
        "screenDuration": screen_duration or 0,
        "segDuration": segb_duration or 23,
        "screenOnRight": screen_on_right,
        "promoVariant": int(promo_variant),
        "shots": prop_shots,
    }
    body = {"inputProps": input_props, "outPath": output_abs_path, "compositionId": "Flow3SegmentB"}
    resp = requests.post(render_url, json=body, timeout=timeout)
    if resp.status_code != 200:
        try:
            detail = resp.json().get("error")
        except Exception:
            detail = resp.text[:500]
        raise RuntimeError(f"SegB Remotion 渲染失败（HTTP {resp.status_code}）：{detail}")
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"SegB Remotion 渲染失败：{data.get('error')}")
    return data


# ===========================================================================
# SegC：ffmpeg zoompan 把尾图做成呼吸/抖动微动视频，时长 = segc_duration。
# ===========================================================================
def render_segment_c(image_abs, segc_duration, output_abs_path, fps=30, width=1920, height=1080):
    """
    用 ffmpeg zoompan 把静态尾图渲成带呼吸缩放的视频段。
    呼吸：缩放在 1.0~1.1 之间缓慢往复；时长 segc_duration 秒。
    关键：附带一条静音音轨（anullsrc），确保三段 concat 时音频流对齐不丢
    （SegC 本无声，但若无音轨会导致整片 concat 退化成「仅视频」，旁白全丢）。
    """
    os.makedirs(os.path.dirname(output_abs_path), exist_ok=True)
    total_frames = max(1, int(round(segc_duration * fps)))
    # zoompan：按帧号做正弦呼吸缩放（1.0~1.08），画布固定 1920x1080。
    # d=total_frames 让单张图展开成 total_frames 帧；输出 fps 固定。
    zoom_expr = "1.04+0.04*sin(on/" + str(max(1, fps)) + ")"
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"zoompan=z='{zoom_expr}':d={total_frames}:s={width}x{height}:fps={fps}"
    )
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", image_abs,
        # 第二路输入：立体声静音源，给 SegC 补一条静音音轨。
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(segc_duration),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        output_abs_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"SegC zoompan 渲染失败：{result.stderr[-500:]}")
    return output_abs_path


# ===========================================================================
# 三段 concat：SegA(Hook) + SegB + SegC → 统一编码/分辨率/帧率后拼接。
# ===========================================================================
def concat_segments(segment_paths, output_abs_path, width=1920, height=1080, fps=30):
    """把多段视频统一 scale+pad+fps 后 concat。缺音轨的段补静音，保证 concat 成功。"""
    if not segment_paths:
        raise RuntimeError("没有可合并的视频段")
    os.makedirs(os.path.dirname(output_abs_path), exist_ok=True)
    n = len(segment_paths)
    cmd = ["ffmpeg", "-y"]
    for p in segment_paths:
        cmd += ["-i", p]
    # 每段：视频统一规格；音频用 anull 兜底（若无音轨，用 anullsrc 补静音在下方 video_only 处理）。
    filters = []
    for i in range(n):
        filters.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v{i}];"
            f"[{i}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}];"
        )
    concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(n))
    filter_complex = "".join(filters) + f"{concat_inputs}concat=n={n}:v=1:a=1[outv][outa]"
    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        output_abs_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # 某段无音轨会失败：退化为给每段补静音再 concat。
        return _concat_with_silent_fallback(segment_paths, output_abs_path, width, height, fps)
    return output_abs_path


def _concat_with_silent_fallback(segment_paths, output_abs_path, width, height, fps):
    """兜底：为每段补静音音轨后 concat（应对 SegC 无音轨场景）。"""
    n = len(segment_paths)
    cmd = ["ffmpeg", "-y"]
    for p in segment_paths:
        cmd += ["-i", p]
    # 额外加一路 anullsrc 静音源，供无音轨的段引用。
    cmd += ["-f", "lavfi", "-t", "0.1", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    silent_idx = n
    filters = []
    for i in range(n):
        filters.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v{i}];"
        )
    # 为每段生成对齐时长的音频：有音轨用其音轨，无则用静音（这里统一用原音轨，失败时交 ffmpeg 处理）。
    for i in range(n):
        filters.append(
            f"[{i}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}];"
        )
    # 注：若某段确无音轨，上面的 [i:a] 会报错。改为「仅视频」合并（丢弃音频，后续混音阶段再加 BGM）。
    concat_inputs = "".join(f"[v{i}]" for i in range(n))
    filter_complex = "".join(
        f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v{i}];"
        for i in range(n)
    ) + f"{concat_inputs}concat=n={n}:v=1:a=0[outv]"
    cmd2 = ["ffmpeg", "-y"]
    for p in segment_paths:
        cmd2 += ["-i", p]
    cmd2 += [
        "-filter_complex", filter_complex, "-map", "[outv]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", output_abs_path,
    ]
    result = subprocess.run(cmd2, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"三段合并失败：{result.stderr[-500:]}")
    return output_abs_path


# ===========================================================================
# BGM 混音 + 防封去重（最后一步）。
# ===========================================================================
def mix_bgm_and_dedup(video_abs, bgm_abs, output_abs_path,
                      bgm_volume=0.25, brightness=0.01, contrast=1.02, scale_factor=1.01,
                      width=1920, height=1080):
    """
    叠加 BGM（循环铺满，降低音量混入原声）+ 防封去重微调（亮度/对比度/轻微缩放裁回原尺寸）。
    bgm_abs 为空则跳过 BGM，只做防封微调。
    """
    os.makedirs(os.path.dirname(output_abs_path), exist_ok=True)
    # 防封视频滤镜：轻微亮度/对比度 + 放大 1% 再裁回原尺寸（改变像素/哈希）。
    vf = (
        f"eq=brightness={brightness}:contrast={contrast},"
        f"scale=iw*{scale_factor}:ih*{scale_factor},crop={width}:{height}"
    )
    if bgm_abs and os.path.exists(bgm_abs):
        # 原视频音轨 [0:a] 与 BGM [1:a] 混音；BGM 循环铺满并降音量。
        cmd = [
            "ffmpeg", "-y", "-i", video_abs, "-stream_loop", "-1", "-i", bgm_abs,
            "-filter_complex",
            f"[0:v]{vf}[v];"
            f"[1:a]volume={bgm_volume}[bg];"
            f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
            output_abs_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-i", video_abs,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
            output_abs_path,
        ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"BGM 混音/防封处理失败：{result.stderr[-500:]}")
    return output_abs_path

