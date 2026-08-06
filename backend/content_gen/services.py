"""
内容生成系统服务层。
复用关键词系统 keywords.services 已验证的能力：
  - _call_ai_stream()：moretokens（OpenAI 兼容）SSE 流式文本对话
  - _extract_json()：容错解析 AI 返回的 JSON
  - get_setting()：全局设置读取（DB 优先，回退环境变量）
本模块新增：元数据生成、封面出图（图片模型走 chat 接口）、分镜脚本生成、ffmpeg 合并。
"""
import base64
import json
import os
import re
import subprocess

import requests
from django.core.files.base import ContentFile

# 直接复用关键词系统的底层能力，避免重复实现
from keywords.services import _call_ai_stream, _extract_json, get_setting

from .models import ContentAgent

# ---------------------------------------------------------------------------
# 默认提示词（可在「内容生成 Agent 管理」页覆盖）。[input] 会替换成关键词，
# [output] 会替换成固定 JSON 输出格式说明。
# ---------------------------------------------------------------------------
DEFAULT_METADATA_PROMPT = """# 角色
你是一位资深的 YouTube 内容运营，擅长为博彩/娱乐类视频撰写高点击率的标题、描述与封面创意。

# 目标
根据给定的搜索关键词，生成一条 YouTube 视频的元数据：标题、描述、封面提示词。
标题要围绕关键词做自然搜索截流；描述为视频描述区文案；封面提示词用英文，描述一张吸引点击的缩略图画面。

# 输入
关键词：[input]

# 输出
[output]"""

METADATA_OUTPUT_SPEC = """严格只输出一个 JSON 对象，不要输出任何解释文字或 markdown 代码块标记，格式如下：
{"keyword": "原样的关键词", "title": "YouTube 视频标题", "description": "YouTube 视频描述文案", "thumbnail_prompt": "用于图片模型的英文封面提示词"}"""

DEFAULT_STORYBOARD_PROMPT = """# 角色
你是一位短视频分镜脚本师，擅长把一个主题拆成若干个连贯的短镜头，用于 AI 视频生成工具出片。

# 目标
根据给定的搜索关键词，生成一个短视频的分镜脚本，目的是推广 promo code。
分镜要求见下方输出格式，请严格按指定的分镜段数和每段时长来拆分。

# 输入
关键词：[input]

# 输出
[output]"""

STORYBOARD_OUTPUT_SPEC = """严格只输出一个 JSON 对象，不要输出任何解释文字或 markdown 代码块标记。
需要生成 {shot_count} 个分镜，每个分镜时长 {shot_duration} 秒，总时长 {total_duration} 秒。格式如下：
{{"keyword": "原样的关键词", "total_duration": {total_duration}, "shots": [{{"index": 1, "duration": {shot_duration}, "scene": "分镜画面描述", "prompt": "用于外部 AI 视频工具的英文生成提示词"}}]}}
shots 数组必须恰好包含 {shot_count} 个元素，index 从 1 递增。"""

# 流程一（全自动）额外要求每段旁白文案 narration。旁白由 TTS 转音频，必须控制字数
# 以贴合每段时长（约每秒 2.5 个英文词，留余量后按 {narration_word_limit} 词封顶）。
STORYBOARD_OUTPUT_SPEC_WITH_NARRATION = """严格只输出一个 JSON 对象，不要输出任何解释文字或 markdown 代码块标记。
需要生成 {shot_count} 个分镜，每个分镜时长 {shot_duration} 秒，总时长 {total_duration} 秒。格式如下：
{{"keyword": "原样的关键词", "total_duration": {total_duration}, "shots": [{{"index": 1, "duration": {shot_duration}, "scene": "分镜画面描述", "prompt": "用于视频渲染的英文生成提示词", "narration": "该段旁白文案（英文）"}}]}}
shots 数组必须恰好包含 {shot_count} 个元素，index 从 1 递增。
重要：每段 narration 是要被朗读的旁白，必须简短，**每段不超过 {narration_word_limit} 个英文单词**，确保朗读时长不超过 {shot_duration} 秒。"""

# (agent_type) → 内置默认提示词。用于种子回填与「恢复系统默认」。
DEFAULT_AGENT_PROMPTS = {
    ContentAgent.AGENT_METADATA: DEFAULT_METADATA_PROMPT,
    ContentAgent.AGENT_STORYBOARD: DEFAULT_STORYBOARD_PROMPT,
}


def get_default_agent_prompt(agent_type):
    """返回某个 Agent 的内置默认提示词；未登记则返回空串。"""
    return DEFAULT_AGENT_PROMPTS.get(agent_type, "")


def _get_prompt(agent_type, fallback):
    """从 ContentAgent 表读提示词；留空或未配置时回退到代码内默认。返回 (prompt, agent)。"""
    agent = ContentAgent.objects.filter(agent_type=agent_type).first()
    if agent and not agent.enabled:
        return None, agent  # Agent 被停用
    prompt = (agent.prompt if agent and agent.prompt.strip() else "") or fallback
    return prompt, agent


def generate_metadata(keyword):
    """
    调元数据生成 Agent，产出标题/描述/封面提示词。
    返回 (data, log)：data 为 {title, description, thumbnail_prompt}；log 为 AI 调用日志。
    Agent 被停用时抛 RuntimeError。
    """
    prompt, agent = _get_prompt(ContentAgent.AGENT_METADATA, DEFAULT_METADATA_PROMPT)
    if prompt is None:
        raise RuntimeError("元数据生成 Agent 已停用")
    full_prompt = prompt.replace("[input]", keyword).replace("[output]", METADATA_OUTPUT_SPEC)
    raw = _call_ai_stream([{"role": "user", "content": full_prompt}])
    data = _extract_json(raw)
    result = {
        "title": (data.get("title") or "").strip(),
        "description": (data.get("description") or "").strip(),
        "thumbnail_prompt": (data.get("thumbnail_prompt") or "").strip(),
    }
    log = {"model": get_setting("AI_MODEL", "gemini-3.6-flash-medium"), "prompt": full_prompt, "raw_output": raw, "parsed": data}
    return result, log


def generate_storyboard(keyword, shot_count=2, shot_duration=8, with_narration=False):
    """
    调脚本分镜生成 Agent，产出固定 JSON 分镜脚本。
    段数/每段时长为参数（默认 8+8）。返回 (data, log)。
    with_narration=True（流程一）时，每段额外产出旁白文案 narration，并按每段时长约束字数。
    """
    prompt, agent = _get_prompt(ContentAgent.AGENT_STORYBOARD, DEFAULT_STORYBOARD_PROMPT)
    if prompt is None:
        raise RuntimeError("脚本分镜生成 Agent 已停用")
    total = shot_count * shot_duration
    if with_narration:
        # 约每秒 2.5 词，留余量后封顶，避免 TTS 音频超过画面段长（对齐问题）。
        narration_word_limit = max(1, int(shot_duration * 2.5))
        output_spec = STORYBOARD_OUTPUT_SPEC_WITH_NARRATION.format(
            shot_count=shot_count, shot_duration=shot_duration, total_duration=total,
            narration_word_limit=narration_word_limit,
        )
    else:
        output_spec = STORYBOARD_OUTPUT_SPEC.format(
            shot_count=shot_count, shot_duration=shot_duration, total_duration=total,
        )
    full_prompt = prompt.replace("[input]", keyword).replace("[output]", output_spec)
    raw = _call_ai_stream([{"role": "user", "content": full_prompt}])
    data = _extract_json(raw)
    # 兜底：确保 shots 是列表且带 index/duration，避免 AI 少字段导致前端渲染异常。
    shots = data.get("shots") if isinstance(data.get("shots"), list) else []
    normalized = []
    for i, shot in enumerate(shots[:shot_count], 1):
        shot = shot if isinstance(shot, dict) else {}
        entry = {
            "index": shot.get("index", i),
            "duration": shot.get("duration", shot_duration),
            "scene": (shot.get("scene") or "").strip(),
            "prompt": (shot.get("prompt") or "").strip(),
        }
        if with_narration:
            entry["narration"] = (shot.get("narration") or "").strip()
        normalized.append(entry)
    result = {"keyword": keyword, "total_duration": total, "shots": normalized}
    log = {"model": get_setting("AI_MODEL", "gemini-3.6-flash-medium"), "prompt": full_prompt, "raw_output": raw, "parsed": data}
    return result, log


def generate_thumbnail(thumbnail_prompt):
    """
    调 Gemini 图片模型出封面图。
    关键：图片模型走 /v1/chat/completions（不是 /v1/images/generations），
    平台强制 stream:true，图片以 ![image](data:image/...;base64,...) 内嵌在 SSE content 里。
    返回 (django ContentFile, ext)；未拿到图片时抛 RuntimeError。
    """
    base_url = get_setting("AI_BASE_URL", "https://moretokens.ai/v1").rstrip("/")
    # 图片 Key 留空则复用文本模型的 AI_API_KEY（同平台 moretokens）
    api_key = get_setting("GEMINI_IMAGE_API_KEY") or get_setting("AI_API_KEY")
    model = get_setting("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
    if not api_key:
        raise RuntimeError("未配置 GEMINI_IMAGE_API_KEY 或 AI_API_KEY")

    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "stream": True, "messages": [
            {"role": "user", "content": f"Generate an image: {thumbnail_prompt}"},
        ]},
        timeout=180,
        stream=True,
    )
    response.raise_for_status()

    content = ""
    # 按原始字节切行再 UTF-8 解码，避免 requests 用 ISO-8859-1 造成乱码（同 keywords 的处理）。
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
    if not match:
        raise RuntimeError(f"图片模型未返回图片，返回开头：{content[:200]}")
    ext = match.group(1)
    if ext == "jpeg":
        ext = "jpg"
    image_bytes = base64.b64decode(match.group(2))
    return ContentFile(image_bytes), ext


# ---------------------------------------------------------------------------
# 旁白音频（TTS）——流程一专用。LLM 只出旁白文字，出声音必须接 TTS。
# 默认 Edge TTS（微软免费、无 key、多语言），可切 elevenlabs（付费、需 key）。
# 做成失败自动降级：edge 失败→尝试 elevenlabs→再失败则跳过该段（不中断整批任务）。
# ---------------------------------------------------------------------------

# 语言 → Edge TTS 默认音色。未命中的语言回退英文音色。
_EDGE_VOICE_BY_LANG = {
    "en": "en-US-GuyNeural",
    "zh": "zh-CN-YunxiNeural",
    "es": "es-ES-AlvaroNeural",
    "pt": "pt-BR-AntonioNeural",
    "fr": "fr-FR-HenriNeural",
    "hi": "hi-IN-MadhurNeural",
    "id": "id-ID-ArdiNeural",
    "vi": "vi-VN-NamMinhNeural",
}


def _edge_voice_for(language):
    """按任务语言取 Edge TTS 音色，全局设置 TTS_VOICE 优先。"""
    configured = get_setting("TTS_VOICE")
    if configured:
        return configured
    lang = (language or "en").split("-")[0].lower()
    return _EDGE_VOICE_BY_LANG.get(lang, _EDGE_VOICE_BY_LANG["en"])


def _tts_edge(text, language, out_path):
    """用 edge-tts 合成一段旁白到 out_path（mp3）。同步封装（内部 asyncio.run）。"""
    import asyncio

    import edge_tts  # 延迟导入，未装依赖时只影响流程一

    voice = _edge_voice_for(language)

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
    voice_id = get_setting("ELEVENLABS_VOICE_ID") or "21m00Tcm4TlvDq8ikWAM"  # 默认音色 Rachel
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


def generate_narration_audio(shots, language, provider, out_dir, filename_prefix):
    """
    为分镜的每段 narration 合成旁白音频（流程一）。
    provider：'edge'（默认免费）或 'elevenlabs'。失败自动降级，最后跳过该段。
    返回 (audio_list, log)：
      audio_list = [{"index":1, "file":"<绝对路径>", "provider":"edge"}, ...]（跳过的段不在列表里）
      log = {"provider": ..., "segments": [{"index":1,"status":"success/fallback/skipped","provider":...,"error":...}]}
    """
    os.makedirs(out_dir, exist_ok=True)
    audio_list = []
    seg_logs = []
    for shot in shots:
        idx = shot.get("index")
        text = (shot.get("narration") or "").strip()
        seg = {"index": idx}
        if not text:
            seg.update({"status": "skipped", "error": "该段无旁白文案"})
            seg_logs.append(seg)
            continue
        out_path = os.path.join(out_dir, f"{filename_prefix}_{idx}.mp3")
        # 先按选定 provider 尝试，失败按 edge<->elevenlabs 互为降级。
        order = ["edge", "elevenlabs"] if provider == "edge" else ["elevenlabs", "edge"]
        done = False
        errors = []
        for prov in order:
            try:
                if prov == "edge":
                    _tts_edge(text, language, out_path)
                else:
                    _tts_elevenlabs(text, out_path)
                audio_list.append({"index": idx, "file": out_path, "provider": prov})
                status = "success" if prov == order[0] else "fallback"
                seg.update({"status": status, "provider": prov})
                if errors:
                    seg["error"] = "；".join(errors)
                done = True
                break
            except Exception as exc:
                errors.append(f"{prov}: {exc}")
        if not done:
            # 两个引擎都失败：跳过该段音频（渲染时该段为无声），不中断任务。
            seg.update({"status": "skipped", "error": "；".join(errors)})
        seg_logs.append(seg)
    log = {"provider": provider, "segments": seg_logs}
    return audio_list, log


def merge_clips(clip_paths, output_path):
    """
    用 ffmpeg 把多段视频合并为一个成品。
    统一转码后合并（各段先转成统一编码/分辨率/帧率，再 concat），
    避免各段编码/分辨率不一致导致 concat 失败或成品异常。
    clip_paths：按顺序的视频文件绝对路径列表；output_path：成品输出绝对路径。
    """
    if not clip_paths:
        raise RuntimeError("没有可合并的视频片段")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    # 统一转码目标：1080x1920 竖屏（YouTube Shorts），30fps，H.264 + AAC。
    # 用 filter_complex 的 concat 滤镜，天然对不同输入做统一重编码，规避编码不一致问题。
    target_w, target_h, fps = 1080, 1920, 30
    n = len(clip_paths)
    cmd = ["ffmpeg", "-y"]
    for path in clip_paths:
        cmd += ["-i", path]
    # 每一路先 scale+pad 到统一分辨率、统一帧率、重采样音频，再按顺序 concat。
    filters = []
    for i in range(n):
        filters.append(
            f"[{i}:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v{i}];"
            f"[{i}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}];"
        )
    concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(n))
    filter_complex = "".join(filters) + f"{concat_inputs}concat=n={n}:v=1:a=1[outv][outa]"
    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]
    # 音频轨可能缺失（纯画面视频）。先尝试带音频合并，失败再退化为仅视频合并。
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return _merge_clips_video_only(clip_paths, output_path, target_w, target_h, fps)
    return output_path


def _merge_clips_video_only(clip_paths, output_path, target_w, target_h, fps):
    """兜底：某些片段没有音轨会导致上面的合并失败，这里只合并视频轨、不处理音频。"""
    n = len(clip_paths)
    cmd = ["ffmpeg", "-y"]
    for path in clip_paths:
        cmd += ["-i", path]
    filters = []
    for i in range(n):
        filters.append(
            f"[{i}:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v{i}];"
        )
    concat_inputs = "".join(f"[v{i}]" for i in range(n))
    filter_complex = "".join(filters) + f"{concat_inputs}concat=n={n}:v=1:a=0[outv]"
    cmd += [
        "-filter_complex", filter_complex, "-map", "[outv]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-movflags", "+faststart", output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 合并失败：{result.stderr[-500:]}")
    return output_path


# ---------------------------------------------------------------------------
# 流程一：调用 Remotion 渲染服务，把封面 + 分镜字幕 + 旁白音频合成为竖屏成品视频。
# ---------------------------------------------------------------------------
def render_video(*, title, keyword, promo_code, cover_abs_path, shots,
                 narration_audio, output_abs_path, render_url=None, timeout=1200):
    """
    通过 HTTP 调用 render 容器的 Remotion 服务渲染成品视频。

    参数都用 render 容器可见的绝对路径（共享卷 /app/media/...），
    render 服务内部会把这些绝对路径改写成 HTTP URL 供 Chromium 加载。

    - title / keyword / promo_code：注入模板的文字
    - cover_abs_path：封面图绝对路径（可为空，空则模板用纯色背景）
    - shots：分镜列表 [{"index","duration","scene","narration"}, ...]
    - narration_audio：旁白音频列表 [{"index","file":"<绝对路径>","provider"}, ...]
    - output_abs_path：成品 mp4 输出绝对路径（render 容器写入共享卷）

    返回 render 服务响应 dict（含 durationInFrames）。失败抛异常。
    """
    render_url = render_url or get_setting("REMOTION_RENDER_URL", "http://render:3000/render")

    # 把每段旁白音频按 index 映射，拼进 shots，供模板逐段播放。
    audio_by_index = {a.get("index"): a.get("file") for a in (narration_audio or [])}
    total_duration = 0
    prop_shots = []
    for shot in shots or []:
        idx = shot.get("index")
        duration = shot.get("duration") or 8
        total_duration += duration
        prop_shots.append({
            "index": idx,
            "duration": duration,
            "scene": (shot.get("scene") or "").strip(),
            "narration": (shot.get("narration") or "").strip(),
            "audioSrc": audio_by_index.get(idx, ""),
        })

    input_props = {
        "title": title or "",
        "keyword": keyword or "",
        "promoCode": promo_code or "",
        "coverSrc": cover_abs_path or "",
        "totalDuration": total_duration or 16,
        "shots": prop_shots,
    }

    resp = requests.post(
        render_url,
        json={"inputProps": input_props, "outPath": output_abs_path},
        timeout=timeout,
    )
    if resp.status_code != 200:
        # 尽量把 render 服务返回的错误信息带出来，便于排查
        try:
            detail = resp.json().get("error")
        except Exception:
            detail = resp.text[:500]
        raise RuntimeError(f"Remotion 渲染失败（HTTP {resp.status_code}）：{detail}")
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Remotion 渲染失败：{data.get('error')}")
    return data
