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

# 流程一·音频脚本 Agent 默认提示词。画面由 Remotion 模板固定，此 Agent 只产出旁白文案。
DEFAULT_NARRATION_PROMPT = """# 角色
你是一位短视频口播文案师，擅长为推广类视频撰写自然、口语化、有号召力的旁白。

# 目标
根据给定的搜索关键词，撰写一段用于视频配音（TTS 朗读）的旁白文案，目的是推广 promo code、引导观众注册。
画面由固定模板呈现，你无需描述画面，只需产出要被朗读出来的旁白文字。
按下方输出格式，把旁白拆成若干段，每段对应视频的一个时间片段。

# 输入
关键词：[input]

# 输出
[output]"""

# 音频脚本输出格式：只出旁白分段（index/duration/narration），不含画面 scene/prompt。
NARRATION_OUTPUT_SPEC = """严格只输出一个 JSON 对象，不要输出任何解释文字或 markdown 代码块标记。
需要生成 {shot_count} 段旁白，每段时长 {shot_duration} 秒，总时长 {total_duration} 秒。格式如下：
{{"keyword": "原样的关键词", "total_duration": {total_duration}, "shots": [{{"index": 1, "duration": {shot_duration}, "narration": "该段旁白文案"}}]}}
shots 数组必须恰好包含 {shot_count} 个元素，index 从 1 递增。
重要：每段 narration 是要被朗读的旁白，必须简短，**每段不超过 {narration_word_limit} 个单词**，确保朗读时长不超过 {shot_duration} 秒。
如需在旁白中提及优惠码，请原样使用占位符 {{promo_code}}（不要自己编造优惠码），系统会在渲染时替换成真实优惠码。"""

# 视频分析 Agent 的默认提示词定义在下方 DEFAULT_VIDEO_ANALYSIS_PROMPT，
# 但那段常量在本行之后才定义，这里用惰性方式引用：见 DEFAULT_AGENT_PROMPTS 下方补挂。

# (agent_type) → 内置默认提示词。用于种子回填与「恢复系统默认」。
DEFAULT_AGENT_PROMPTS = {
    ContentAgent.AGENT_METADATA: DEFAULT_METADATA_PROMPT,
    ContentAgent.AGENT_STORYBOARD: DEFAULT_STORYBOARD_PROMPT,
    ContentAgent.AGENT_NARRATION: DEFAULT_NARRATION_PROMPT,
    # AGENT_VIDEO_ANALYSIS 的默认提示词在文件后半段定义，见文件末尾补挂。
}


def get_default_agent_prompt(agent_type):
    """返回某个 Agent 的内置默认提示词；未登记则返回空串。"""
    return DEFAULT_AGENT_PROMPTS.get(agent_type, "")


# 语言代码 → 输出语言中文名，用于在提示词里明确要求 AI 用该语言输出。
_LANG_NAME = {
    "en": "英语", "zh": "中文", "es": "西班牙语", "pt": "葡萄牙语", "fr": "法语",
    "hi": "印地语", "id": "印尼语", "vi": "越南语", "ar": "阿拉伯语", "ru": "俄语",
    "de": "德语", "ja": "日语", "ko": "韩语", "th": "泰语", "tr": "土耳其语",
}


def _lang_name(language):
    """把语言代码转成中文名，供提示词使用；未知则回退英语。"""
    lang = (language or "en").split("-")[0].lower()
    return _LANG_NAME.get(lang, "英语")


def _build_context_block(language, variables_schema):
    """
    构造注入 AI 提示词的「语言 + 变量」上下文说明。
    - language：要求 AI 用该语言输出正文（标题/描述/旁白）。
    - variables_schema：模板声明的变量清单。告诉 AI 可用 {key} 占位符引用，
      其中 ai_editable=false 的（如优惠码）绝不能自己编造，只能用占位符。
    返回一段中文说明文本；无内容时返回空串。
    """
    lines = []
    if language:
        lines.append(f"【输出语言】请用{_lang_name(language)}撰写标题、描述、旁白等所有面向观众的正文，"
                     f"无论本提示词用什么语言书写。")
    schema = variables_schema or []
    if schema:
        editable, locked = [], []
        for v in schema:
            if not isinstance(v, dict):
                continue
            key = (v.get("key") or "").strip()
            if not key:
                continue
            label = (v.get("label") or key).strip()
            (editable if v.get("ai_editable") else locked).append(f"{{{key}}}（{label}）")
        lines.append("【可用变量占位符】文案中如需体现下列信息，请原样写占位符（系统会在出片时替换成真实值）：")
        if locked:
            lines.append(f"  - 以下变量由人工提供，你【绝对不能自己编造具体值】，只能写占位符：{'、'.join(locked)}")
        if editable:
            lines.append(f"  - 以下变量可由你自行发挥或引用：{'、'.join(editable)}")
    return "\n".join(lines)


def _get_prompt(agent_type, fallback):
    """从 ContentAgent 表读提示词；留空或未配置时回退到代码内默认。返回 (prompt, agent)。"""
    agent = ContentAgent.objects.filter(agent_type=agent_type).first()
    if agent and not agent.enabled:
        return None, agent  # Agent 被停用
    prompt = (agent.prompt if agent and agent.prompt.strip() else "") or fallback
    return prompt, agent


def generate_metadata(keyword, language=None, variables_schema=None):
    """
    调元数据生成 Agent，产出标题/描述/封面提示词。
    - language：要求 AI 用该语言输出正文（标题/描述）。
    - variables_schema：模板变量清单，注入提示词让 AI 用 {key} 占位符、不编造锁定变量。
    返回 (data, log)：data 为 {title, description, thumbnail_prompt}；log 为 AI 调用日志。
    Agent 被停用时抛 RuntimeError。
    """
    prompt, agent = _get_prompt(ContentAgent.AGENT_METADATA, DEFAULT_METADATA_PROMPT)
    if prompt is None:
        raise RuntimeError("元数据生成 Agent 已停用")
    # 把「语言 + 变量」上下文拼进输出格式说明前面，让 AI 遵守。
    context = _build_context_block(language, variables_schema)
    output_spec = (context + "\n\n" + METADATA_OUTPUT_SPEC) if context else METADATA_OUTPUT_SPEC
    full_prompt = prompt.replace("[input]", keyword).replace("[output]", output_spec)
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


def generate_narration_script(keyword, shot_count=2, shot_duration=8, language=None, variables_schema=None):
    """
    调音频脚本 Agent（流程一），只产出旁白文案分段（不含画面分镜）。
    - language：要求 AI 用该语言撰写旁白。
    - variables_schema：模板变量清单，注入提示词让 AI 用 {key} 占位符、不编造锁定变量。
    返回 (data, log)。data 结构与分镜一致（shots 里每段有 index/duration/narration），
    便于复用后续 TTS 与渲染逻辑；但每段只有 narration，画面交给 Remotion 模板。
    """
    prompt, agent = _get_prompt(ContentAgent.AGENT_NARRATION, DEFAULT_NARRATION_PROMPT)
    if prompt is None:
        raise RuntimeError("音频脚本生成 Agent 已停用")
    total = shot_count * shot_duration
    # 约每秒 2.5 词，留余量后封顶，避免 TTS 音频超过画面段长。
    narration_word_limit = max(1, int(shot_duration * 2.5))
    output_spec = NARRATION_OUTPUT_SPEC.format(
        shot_count=shot_count, shot_duration=shot_duration, total_duration=total,
        narration_word_limit=narration_word_limit,
    )
    # 把「语言 + 变量」上下文拼进输出格式说明前面（变量说明覆盖了 promo_code 占位符规则）。
    context = _build_context_block(language, variables_schema)
    if context:
        output_spec = context + "\n\n" + output_spec
    full_prompt = prompt.replace("[input]", keyword).replace("[output]", output_spec)
    raw = _call_ai_stream([{"role": "user", "content": full_prompt}])
    data = _extract_json(raw)
    shots = data.get("shots") if isinstance(data.get("shots"), list) else []
    normalized = []
    for i, shot in enumerate(shots[:shot_count], 1):
        shot = shot if isinstance(shot, dict) else {}
        normalized.append({
            "index": shot.get("index", i),
            "duration": shot.get("duration", shot_duration),
            "narration": (shot.get("narration") or "").strip(),
        })
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
                 narration_audio, output_abs_path, composition_id="",
                 variables=None, assets=None, render_url=None, timeout=1200):
    """
    通过 HTTP 调用 render 容器的 Remotion 服务渲染成品视频。

    参数都用 render 容器可见的绝对路径（共享卷 /app/media/...），
    render 服务内部会把这些绝对路径改写成 HTTP URL 供 Chromium 加载。

    - title / keyword / promo_code：注入模板的文字
    - cover_abs_path：封面图绝对路径（可为空，空则模板用纯色背景）
    - shots：分镜列表 [{"index","duration","scene","narration"}, ...]
    - narration_audio：旁白音频列表 [{"index","file":"<绝对路径>","provider"}, ...]
    - output_abs_path：成品 mp4 输出绝对路径（render 容器写入共享卷）
    - composition_id：指定 render 项目里的 Remotion 组件（空则用默认 PromoVideo）
    - variables：本条视频的模板变量组 {"promo_code":...}，整体透传给模板
    - assets：模板素材绝对路径列表 [{"key","file":"<绝对路径>"}]

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

    # 素材列表转成 {key: 绝对路径} 映射，供模板按 key 取用。
    asset_map = {a.get("key"): a.get("file") for a in (assets or []) if a.get("key")}
    # 素材真实时长映射 {key: 秒}，供模板算「视频素材播完冻结在最后一帧」的冻结点。
    asset_durations = {
        a.get("key"): a.get("duration")
        for a in (assets or [])
        if a.get("key") and a.get("duration")
    }

    input_props = {
        "title": title or "",
        "keyword": keyword or "",
        "promoCode": promo_code or "",
        "coverSrc": cover_abs_path or "",
        "totalDuration": total_duration or 16,
        "shots": prop_shots,
        "variables": variables or {},
        "assets": asset_map,
        "assetDurations": asset_durations,
    }

    body = {"inputProps": input_props, "outPath": output_abs_path}
    if composition_id:
        body["compositionId"] = composition_id
    resp = requests.post(
        render_url,
        json=body,
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


# ---------------------------------------------------------------------------
# 视频模板库：用 Gemini 分析参考视频，产出模板规格（布局/文字/配色/转场/分镜时间戳）。
# 关键：必须用 Gemini 的 key + Gemini 模型；视频以 image_url 的 data uri 塞进 chat 接口。
# （每个 key 只能用一家厂商模型，用 GPT key 喂视频会报 unsupported format。）
# ---------------------------------------------------------------------------
DEFAULT_VIDEO_ANALYSIS_PROMPT = """你是一位专业的视频模板分析师。你要分析这段推广视频，目标是让开发能「像素级复刻」成一个可批量套数据的 Remotion 视频模板。
分析要极其精细：不要只写「左边是绿色品牌区」这种笼统描述，而要具体到每个区域的位置、每段文字的内容/字号/颜色/对齐、每个动画的方式。

【坐标系约定】所有位置和尺寸都用「相对百分比」表示（不要用像素）：
  - x/y 是元素左上角相对画面左上角的百分比（0~100）；w/h 是元素宽高占画面的百分比（0~100）。
  - 例：一个占左侧 40% 宽、满高的面板 = {"x":0,"y":0,"w":40,"h":100}。
颜色一律用十六进制（如 #0B4F37）；你只需给出「接近的估计值」，不必绝对精确。

【关键帧时间点 keyframes】请列出这段视频里「画面发生明显变化」的时间点（秒，可含小数），
例如：开场、每次文字/画面切换、转场、结尾定格。这些时间点稍后会被用来自动截图，供开发对照复刻。
控制在 4~8 个最有代表性的时间点，均匀覆盖全片，别漏掉任何一次大的画面切换。

【变量 vs 固定】指出哪些元素是「每条视频会变的变量」（如优惠码 promo_code、金额、国家、关键词），
哪些是固定不变的（如品牌名、slogan、按钮文案）。变量要具体到「它出现在画面什么位置」。

请严格只输出一个 JSON 对象（不要输出任何解释文字或 markdown 代码块标记），结构如下：
{
  "analysis": "整体分析（中文）：画面风格、分屏结构、节奏、转场、整体观感的文字总结",
  "canvas": {"aspect": "16:9 或 9:16", "bg_color": "整体背景色 #RRGGBB"},
  "regions": [
    {
      "name": "区域名（如 品牌面板/录屏面板/优惠码框）",
      "box": {"x":0,"y":0,"w":40,"h":100},
      "bg_color": "#RRGGBB",
      "texts": [
        {"content": "文字内容（若是变量写占位符如 {promo_code}）", "box": {"x":5,"y":40,"w":30,"h":10},
         "font_size_pct": 文字高度占画面高的百分比(数字), "color": "#RRGGBB",
         "align": "left/center/right", "weight": "normal/bold", "is_variable": true 或 false}
      ],
      "animation": "该区域的入场/强调动画描述（如 从左滑入、弹性放大、无）"
    }
  ],
  "shots": [
    {"index":1, "start": 起始秒(数字), "end": 结束秒(数字), "scene": "该分镜画面在做什么"}
  ],
  "keyframes": [关键帧时间点秒数的数组, 如 [0, 3.5, 7, 11, 15]],
  "shot_count": 建议旁白段数(整数),
  "shot_duration": 每段建议秒数(整数),
  "suggested_variables": [{"key":"变量名(英文,如 promo_code)", "label":"中文显示名", "position":"它在画面什么位置", "ai_editable": false}]
}
其中 suggested_variables 里优惠码/金额这类必须由人工提供、AI 不得编造的，填 ai_editable=false。"""

# 兼容旧引用名。
VIDEO_ANALYSIS_PROMPT = DEFAULT_VIDEO_ANALYSIS_PROMPT

# 补挂视频分析 Agent 的默认提示词到映射表（常量在此处才定义完，故延后补挂）。
DEFAULT_AGENT_PROMPTS[ContentAgent.AGENT_VIDEO_ANALYSIS] = DEFAULT_VIDEO_ANALYSIS_PROMPT


def probe_video_duration(video_abs_path):
    """
    用 ffprobe 读视频真实时长（秒，float）。读不到返回 None。
    用于：上传录屏素材后按其时长自动设定模板总时长；渲染前校验模板时长 > 素材时长。
    """
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_abs_path],
            capture_output=True, text=True, timeout=60,
        )
        val = (out.stdout or "").strip()
        return float(val) if val else None
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


def detect_scene_changes(video_abs_path, threshold=0.3, timeout=120):
    """
    用 ffmpeg 场景检测，找出画面「明显切换」的时间点（秒，float 列表，升序）。
    原理：select='gt(scene,阈值)' 逐帧算与前一帧的差异，超过阈值即视为一次切换。
    threshold 越小越敏感（0.3 是经验值）。检测不到或出错返回空列表。
    这是 Gemini 报的关键帧时间点的「客观兜底」，防止漏掉真正换画面的地方。
    """
    try:
        # -vf ... showinfo 会把命中帧的时间戳(pts_time) 打到 stderr，用正则捞出来。
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", video_abs_path,
             "-vf", f"select='gt(scene,{threshold})',showinfo",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=timeout,
        )
        times = []
        for m in re.finditer(r"pts_time:([0-9.]+)", out.stderr or ""):
            try:
                times.append(round(float(m.group(1)), 2))
            except ValueError:
                continue
        return sorted(set(times))
    except (subprocess.SubprocessError, OSError):
        return []


def extract_keyframes(video_abs_path, timestamps, out_dir, width=960, max_frames=10):
    """
    用 ffmpeg 在指定时间点各截一张图，存到 out_dir，返回帧信息列表。
    - timestamps：时间点列表（秒）。会先排序去重，超过 max_frames 则均匀下采样，避免太多帧撑爆上下文。
    - width：缩放宽度（高按比例），960 足够看清布局和颜色，又不至于太大。
    返回 [{"time": 秒, "file": 绝对路径, "name": 文件名}, ...]；单帧失败跳过不报错。
    抽帧放在 backend 容器做（有 ffmpeg），render 容器没有 ffmpeg。
    """
    # 规整时间点：去重排序 + 超量则均匀采样。
    clean = sorted({round(float(t), 2) for t in (timestamps or []) if _is_number(t) and float(t) >= 0})
    if not clean:
        return []
    if len(clean) > max_frames:
        step = len(clean) / max_frames
        clean = [clean[int(i * step)] for i in range(max_frames)]

    # 末尾夹取：seek 到视频最末尾（>=时长）ffmpeg 取不到帧，会漏掉「结尾定格帧」
    # （结尾 CTA 画面对复刻很重要）。把越界时间点回退到 时长-0.1s，确保能截到最后一帧。
    dur = probe_video_duration(video_abs_path)
    if dur:
        clean = sorted({(t if t < dur - 0.1 else round(dur - 0.1, 2)) for t in clean})

    os.makedirs(out_dir, exist_ok=True)
    frames = []
    for i, t in enumerate(clean):
        name = f"kf_{i:02d}_{t:.2f}s.jpg"
        abs_path = os.path.join(out_dir, name)
        try:
            # -ss 放在 -i 前=快速定位到该时间点；-frames:v 1 只取一帧；scale 缩放宽度、高自适应。
            r = subprocess.run(
                ["ffmpeg", "-hide_banner", "-y", "-ss", str(t), "-i", video_abs_path,
                 "-frames:v", "1", "-vf", f"scale={width}:-1", abs_path],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0 and os.path.exists(abs_path):
                frames.append({"time": t, "file": abs_path, "name": name})
        except (subprocess.SubprocessError, OSError):
            continue
    return frames


def _is_number(x):
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def analyze_reference_video(video_abs_path, prompt=None, timeout=600):
    """
    调 Gemini 分析参考视频，返回结构化分析规格。
    - video_abs_path：视频文件绝对路径
    - prompt：分析提示词。传 None 时从「视频分析 Agent」表读（留空则回退内置默认），
      这样运营可以在后台自行配置分析的精细程度。
    - 用 GEMINI_VIDEO_API_KEY（没配则用 GEMINI_IMAGE_API_KEY）+ Gemini 模型
    返回 dict：{model, text, spec, keyframes, shot_count?, shot_duration?, suggested_variables?}
      - text：整体分析文本（analysis 字段）
      - spec：完整结构化规格（canvas/regions/shots 等），供开发对照复刻
      - keyframes：关键帧时间点列表（秒），供上层用 ffmpeg 抽帧
    """
    # 提示词优先级：显式传入 > 后台 Agent 配置 > 内置默认。
    if prompt is None:
        prompt, _agent = _get_prompt(ContentAgent.AGENT_VIDEO_ANALYSIS, DEFAULT_VIDEO_ANALYSIS_PROMPT)
        if prompt is None:  # Agent 被停用，仍回退内置默认，保证分析可用
            prompt = DEFAULT_VIDEO_ANALYSIS_PROMPT
    base_url = get_setting("AI_BASE_URL", "https://moretokens.ai/v1").rstrip("/")
    api_key = (
        get_setting("GEMINI_VIDEO_API_KEY")
        or get_setting("GEMINI_IMAGE_API_KEY")
        or get_setting("AI_API_KEY")
    )
    model = get_setting("GEMINI_VIDEO_MODEL") or get_setting("GEMINI_IMAGE_MODEL", "gemini-3.6-flash-medium")
    if not api_key:
        raise RuntimeError("未配置 GEMINI_VIDEO_API_KEY / GEMINI_IMAGE_API_KEY，无法分析视频")

    with open(video_abs_path, "rb") as f:
        raw = f.read()
    data_uri = "data:video/mp4;base64," + base64.b64encode(raw).decode()
    messages = [{"role": "user", "content": [
        {"type": "text", "text": prompt or VIDEO_ANALYSIS_PROMPT},
        {"type": "image_url", "image_url": {"url": data_uri}},
    ]}]

    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "stream": True, "messages": messages},
        timeout=timeout, stream=True,
    )
    if response.status_code != 200:
        raise RuntimeError(f"视频分析失败（HTTP {response.status_code}）：{response.text[:400]}")

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

    if not content.strip():
        raise RuntimeError("视频分析返回为空")

    # 尝试解析结构化 JSON（分析文本 + 结构规格 + 关键帧 + 建议段数/时长 + 建议变量）。
    # 解析失败则回退：整段当分析文本，其余字段留空由上层用默认。
    parsed = _extract_json(content) or {}
    text = (parsed.get("analysis") or "").strip() or content
    result = {"model": model, "text": text}

    # spec：完整结构化规格（canvas/regions/shots 等），原样透传给上层存档，供开发复刻对照。
    spec = {}
    for field in ("canvas", "regions", "shots"):
        if parsed.get(field) is not None:
            spec[field] = parsed[field]
    if spec:
        result["spec"] = spec

    # keyframes：关键帧时间点（秒）。规整成升序去重的数字列表，供 ffmpeg 抽帧。
    result["keyframes"] = _normalize_keyframes(parsed.get("keyframes"))

    try:
        if parsed.get("shot_count"):
            result["shot_count"] = int(parsed["shot_count"])
        if parsed.get("shot_duration"):
            result["shot_duration"] = int(parsed["shot_duration"])
    except (TypeError, ValueError):
        pass
    sv = parsed.get("suggested_variables")
    if isinstance(sv, list):
        result["suggested_variables"] = sv
    return result


def _normalize_keyframes(raw):
    """把 AI 返回的关键帧时间点规整成升序去重的浮点秒列表；非法值忽略。"""
    if not isinstance(raw, list):
        return []
    seen = []
    for x in raw:
        try:
            t = round(float(x), 2)
        except (TypeError, ValueError):
            continue
        if t >= 0 and t not in seen:
            seen.append(t)
    return sorted(seen)
