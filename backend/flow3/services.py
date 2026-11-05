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


def list_text_models():
    """
    返回「文案 Agent 可选模型清单」（去重、保序）。
    真相源：全局设置 AI_MODELS（逗号分隔）；并确保当前全局默认 AI_MODEL 一定在列表里。
    新增模型只需在全局设置 AI_MODELS 里加一项，Agent 管理下拉会自动出现，无需改代码。
    """
    raw = get_setting("AI_MODELS", "")
    models_list = [m.strip() for m in raw.split(",") if m.strip()]
    default_model = get_setting("AI_MODEL", "gemini-3.6-flash-medium").strip()
    if default_model and default_model not in models_list:
        models_list.insert(0, default_model)
    # 去重保序
    seen, result = set(), []
    for m in models_list:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


def _model_api_key(model):
    """
    按模型名解析应使用的 apikey。
    优先查全局设置 AI_MODEL_KEYS（JSON：{"模型名": "apikey"}）里该模型的专属 key，
    查不到则回退通用 AI_API_KEY。用于「不同模型走不同 key」（如 Claude 用独立 key）。
    """
    raw = get_setting("AI_MODEL_KEYS", "")
    if model and raw:
        try:
            mapping = json.loads(raw)
            key = (mapping.get(model) or "").strip() if isinstance(mapping, dict) else ""
            if key:
                return key
        except (json.JSONDecodeError, TypeError):
            pass
    return get_setting("AI_API_KEY")


def _call_ai_stream(messages, timeout=180, max_retries=3, model=None):
    """
    调用 moretokens（OpenAI 兼容）聊天接口，强制 stream:true，拼接返回完整文本。
    该平台模型响应较慢（10~30s）且偶发中途断连（SSL EOF / ChunkedEncoding），
    故对「连接类错误」或「拿到空内容」做指数退避重试，提升长链路任务的稳定性。
    model：本次调用使用的模型名；为空则用全局默认 AI_MODEL。apikey 按模型映射解析（_model_api_key）。
    """
    base_url = get_setting("AI_BASE_URL", "https://moretokens.ai/v1").rstrip("/")
    model = (model or "").strip() or get_setting("AI_MODEL", "gemini-3.6-flash-medium")
    api_key = _model_api_key(model)
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
你是一位深谙「前 3 秒抓注意力」的视频开场编导，专做面向南亚（印度）市场的博彩/优惠码推广视频 Hook。你的开场要让人一眼就停下来看，绝不官方、绝不平淡。

# 目标
根据关键词和优惠码，生成一段约 10 秒 Hook 视频的「文生视频」Prompt，用于外部 AI 视频引擎（Runway/Kling/Sora 类）渲染开场。
这 10 秒的核心信息是「引导用户下载 App」：告诉还没下载的人——加主页 Telegram 频道下载，或直接搜官网域名注册下载。

# 核心台词（务必在视频里自然传达，口播 + 醒目字幕都要有）
大意：「还没下载 App？赶紧加主页 Telegram 频道下载，或者直接搜官网注册下载，别错过！」
- 台词必须用 [language] 语言（任务配置什么语言就说什么语言）。
- 口播节奏要快、有紧迫感，10 秒内干净利落地讲完这句引导。
- 具体 App 名称 / 官网域名以关键词 [input] 为准（如「1win」则说 1win app、搜 1win.com）。

# 风格要求（强 hook）
- 开场 0-2 秒就用「问题 / 悬念 / 大额奖金数字 / 金钱利益」抓住眼球（如直接发问、甩出 +500% 奖金、或"还没下载？"的急迫感）。
- 强吸引力、高能量、口语化，像本地博主喊话，有煽动力。
- 画面配合台词：手机屏幕展示 App 下载/注册页、Telegram 频道图标、官网网址特写等，字幕大字清晰可读。
- 印度本地化：真实印度年轻人/手机操作场景，兴奋的表情和手势，自然但有活力。
- 若优惠码 {PROMO_CODE} 非空，自然带出（字幕或口播提一句），不喧宾夺主。

# 输入
关键词：[input]
语言：[language]
优惠码：{PROMO_CODE}

# 输出
[output]"""

HOOK_OUTPUT_SPEC = """严格只输出一个 JSON 对象，不要输出任何解释文字或 markdown 代码块标记，格式如下：
{"video_prompt": "用于外部 AI 视频引擎的提示词（一段连贯描述，含画面、运镜、口播台词、字幕、风格，时长约10秒）"}"""

DEFAULT_NARRATION_PROMPT = """# 角色
你是一位务实、可信的口播文案师，语气像正规教程/官方介绍，不浮夸。

# 目标
根据给定的关键词，撰写一段用于视频配音（TTS 朗读）的旁白，语言为 [language]，
目的是自然介绍并引导观众使用优惠码 {PROMO_CODE} 完成注册。
画面由固定模板呈现，你只需产出要被朗读的旁白文字。

# 要求
- 与关键词「[input]」强相关，围绕该平台/产品/操作讲清楚「怎么做、用什么码、有什么好处」。
- 语气务实、可信、口语自然，贴合目标语言地区观众；不要浮夸承诺和夸张煽动。
- 必须自然地把优惠码读出来：在要提到优惠码处原样写占位符 {{promo_code}}（不要自己编造、不要改写），
  系统会在渲染时替换成真实优惠码，TTS 会把真实码读出来。

# 输入
关键词：[input]
语言：[language]

# 输出
[output]"""

NARRATION_OUTPUT_SPEC = """严格只输出一个 JSON 对象，不要输出任何解释文字或 markdown 代码块标记。
需要把旁白拆成 {shot_count} 段，每段约 {shot_duration} 秒，总时长约 {total_duration} 秒。格式如下：
{{"shots": [{{"index": 1, "duration": {shot_duration}, "narration": "该段旁白文案（目标语言）"}}]}}
shots 数组恰好包含 {shot_count} 个元素，index 从 1 递增。
重要：每段 narration 必须简短，**每段不超过 {narration_word_limit} 个单词**，确保朗读时长不超过 {shot_duration} 秒。
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


# ===========================================================================
# 元数据 Agent 语言与关键词库支持（描述按任务 language 生成 + 堆砌关键词库）
# ===========================================================================
def detect_keyword_language(keyword):
    """按关键词的语言特征自动分类：西里尔→ru，天城文→hi，葡/西语特殊字符→pt，其余→en。"""
    if not keyword:
        return "en"
    if re.search(r"[\u0400-\u04FF]", keyword):     # 西里尔字母（俄语等）
        return "ru"
    if re.search(r"[\u0900-\u097F]", keyword):     # 天城文（印地语）
        return "hi"
    if re.search(r"[éáâãçõóíúêàü]", keyword, re.IGNORECASE):  # 葡/西语特殊字符
        return "pt"
    return "en"


# language 代码 → 人类可读语言名（传给元数据 Agent，让它按对应语言写标题/描述）
LANGUAGE_DISPLAY = {
    "en-IN": "印地英语（Hinglish：英语为主，自然带印度口语/常用词）",
    "en": "英语",
    "pt-BR": "巴西葡萄牙语",
    "pt": "葡萄牙语",
    "es": "西班牙语",
    "hi": "印地语",
    "ru": "俄语",
    "de": "德语",
    "fr": "法语",
    "it": "意大利语",
    "ja": "日语",
    "ko": "韩语",
    "ar": "阿拉伯语",
}

# language 代码 → 关键词库语言标签（决定堆砌哪类关键词）
LANGUAGE_KEY_MAP = {
    "en-IN": "en", "en": "en",
    "pt-BR": "pt", "pt": "pt",
    "es": "es", "hi": "hi", "ru": "ru",
}


def language_display(language):
    """返回 language 的人类可读名；未登记回退原始代码。"""
    return LANGUAGE_DISPLAY.get((language or "").strip(), (language or "").strip())


def keyword_lang_key(language):
    """返回 language 对应的关键词库语言标签。"""
    return LANGUAGE_KEY_MAP.get((language or "").strip(), "en")


def build_keyword_context(language):
    """
    按任务语言筛关键词库，生成注入元数据 Agent 的文本。
    主词库按搜索量降序（标注权重，要求尽量多写入）；长尾词随机打乱（字符有余量时补）。
    """
    from .models import KeywordLibrary
    key = keyword_lang_key(language)
    primary = list(KeywordLibrary.objects.filter(
        source=KeywordLibrary.SOURCE_PRIMARY, language=key, enabled=True,
    ).order_by("-search_volume", "id"))
    suggest = list(KeywordLibrary.objects.filter(
        source=KeywordLibrary.SOURCE_SUGGEST, language=key, enabled=True,
    ).order_by("?"))
    lines = []
    if primary:
        lines.append("主关键词库（按搜索量从大到小，务必尽可能多、自然地写入描述）：")
        lines.extend(f"- {k.keyword}（搜索量 {k.search_volume}）" for k in primary)
    if suggest:
        lines.append("补充长尾词（描述字符还有余量时随机取用，增强长尾覆盖）：")
        lines.extend(f"- {k.keyword}" for k in suggest)
    return "\n".join(lines)


DEFAULT_METADATA_PROMPT = """# 角色
你是一位深耕南亚（印度为主）市场的 YouTube 博彩/优惠码类视频营销专家，同时精通 SEO 文案与高点击封面设计。你针对一个博彩平台（如 1win）及其目标关键词，一次性产出可直接使用的视频元数据：高点击标题、SEO 拉满的视频描述、以及让人忍不住点击的封面图提示词。

# 输入信息
- 主关键词：[input]（标题和描述都必须围绕它）
- 优惠码：{PROMO_CODE}（CTA 和封面要体现）
- 输出语言：[language]（标题、描述必须用这种语言写，是当地语言而非国际简写）
- 关键词库：[keywords]（按搜索量从大到小排列，用于描述堆砌，增强 SEO）

# 标题（对应 JSON 的 title 字段）
- 只产出 1 个最终标题，长度 ≤ 70 字符。
- 主关键词 [input] 必须放在标题最开头。
- 再自然融入关键词库里另一个高搜索量词。
- 加入「点击钩子」：具体数字（奖金倍数/金额，如 +500%、₹50,000）、紧迫感、利益点，或 1 个 emoji。
- 用 [language] 语言写，口语化、有煽动力，像当地博主而非官方公告。

# 视频描述（对应 JSON 的 description 字段）
- 纯文本，用 \\n 换行，禁止 ``` 和表格。总长目标 3000~4000 字符，绝不能写短（SEO 需要足够内容量，短描述会丢失大量关键词覆盖）。
- 严格按下面 6 段结构输出：
  1. 首段（钩子，1-2 句）：必须含主关键词 [input] + 最核心利益点，抓眼球。
  2. 正文段（2-3 句）：自然介绍产品/玩法/优惠，自然融入 3-4 个高搜索量关键词（不要生硬）。
  3. 章节（5-6 个，带时间戳从 0:00 开始）：每个章节标题都要含至少一个关键词，如「0:00 1win Registration 教程」。
  4. 关键词堆砌区（占描述最大篇幅）：把关键词库里高搜索量的词逐个用自然叙述的方式铺进去，能写多少写多少（这是 SEO 关键）。搜索量大的词优先，其余按顺序尽量全部覆盖，组成连贯的长段落，不要偷懒只写几个。
  5. CTA 区：明确的行动号召，含优惠码 {PROMO_CODE} 和推广链接占位 AFFILIATE_LINK。
  6. 标签行：从关键词库里挑词转成 #Hashtag（无空格），至少 15 个。
- 关键词库里的高搜索量词必须全部出现；长尾词尽量覆盖。

# 封面图提示词（对应 JSON 的 thumbnail_prompt 字段）
- 一段连续英文提示词，核心目标只有一个：让人忍不住点进来。
- 风格：博彩推广的「高点击」风，绝不是官方商务冷谈风。
  - 超大醒目的奖金/金额数字（如 +500% BONUS、₹50,000），用最抢眼的字体色。
  - 鲜艳撞色（红金 / 黄黑 / 蓝金），高对比、高饱和。
  - 元素：手机屏幕 + 现金/金币/筹码/钞票 + 兴奋的人物表情或手势（可带人物）。
  - 主关键词大字 + 优惠码 {PROMO_CODE} 用金色高亮框，缩略图小尺寸也要一眼看清。
  - 氛围：兴奋、赚钱、发财、抓紧机会，符合印度博彩用户审美。
- 末尾加修饰词：bold vibrant, eye-catching, high contrast, realistic, 8k。

# 通用规则
- 标题和描述用 [language] 语言写；关键词堆砌区的关键词保留原词（关键词本身是什么语言就写什么）。
- 涉及年份时按 2027 年执行。
- 优先可读性和点击率，其次才是关键词覆盖。

# 输出
[output]"""

METADATA_OUTPUT_SPEC = """严格只输出一个 JSON 对象，不要输出任何解释文字，不要用 markdown 代码块包裹整个 JSON，格式如下：
{"title": "单个 YouTube 标题（≤70字符，不含编号、不含多个候选）", "description": "YouTube 描述纯文本（用 \\n 换行，不含 ``` 代码块标记）", "thumbnail_prompt": "单段英文封面提示词"}
注意：title 只能是一个标题字符串；description 内不得出现 ``` 三反引号。"""

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


def _agent_model(agent):
    """取 Agent 实际使用的文案模型：Agent 自身 model 非空则用之，否则回退全局 AI_MODEL。"""
    configured = (getattr(agent, "model", "") or "").strip()
    return configured or get_setting("AI_MODEL", "gemini-3.6-flash-medium")


# ===========================================================================
# 各 Agent 文案生成
# ===========================================================================
def generate_hook_prompt(run):
    """Hook 文案 Agent → 产出外部视频引擎用的 video_prompt。返回 (prompt_text, log)。"""
    prompt, agent = _get_prompt(Flow3Agent.AGENT_HOOK)
    if prompt is None:
        raise RuntimeError("Hook 视频文案 Agent 已停用")
    full = (_inject_globals(prompt, run)
            .replace("[input]", run.keyword)
            .replace("[language]", language_display(run.language))
            .replace("[output]", HOOK_OUTPUT_SPEC))
    model = _agent_model(agent)
    raw = _call_ai_stream([{"role": "user", "content": full}], model=model)
    data = _extract_json(raw)
    video_prompt = (data.get("video_prompt") or "").strip()
    log = {"model": model, "prompt": full, "raw_output": raw, "parsed": data}
    return video_prompt, log


def generate_narration_script(run, shot_count, shot_duration):
    """语音文案 Agent → 产出分段旁白（按任务语言）。返回 (data, log)。data={shots:[{index,duration,narration}]}。"""
    prompt, agent = _get_prompt(Flow3Agent.AGENT_NARRATION)
    if prompt is None:
        raise RuntimeError("语音文案 Agent 已停用")
    total = shot_count * shot_duration
    narration_word_limit = max(1, int(shot_duration * 2.5))
    output_spec = NARRATION_OUTPUT_SPEC.format(
        shot_count=shot_count, shot_duration=shot_duration,
        total_duration=total, narration_word_limit=narration_word_limit,
    )
    full = (_inject_globals(prompt, run)
            .replace("[input]", run.keyword)
            .replace("[language]", language_display(run.language))
            .replace("[output]", output_spec))
    model = _agent_model(agent)
    raw = _call_ai_stream([{"role": "user", "content": full}], model=model)
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
    log = {"model": model, "prompt": full, "raw_output": raw, "parsed": data}
    return result, log


def generate_metadata(run):
    """元数据 Agent → 标题/描述/封面提示词。返回 (data, log)。"""
    prompt, agent = _get_prompt(Flow3Agent.AGENT_METADATA)
    if prompt is None:
        raise RuntimeError("元数据生成 Agent 已停用")
    keywords_context = build_keyword_context(run.language)
    lang_name = language_display(run.language)
    full = _inject_globals(prompt, run)
    full = (full.replace("[input]", run.keyword)
                .replace("[keywords]", keywords_context)
                .replace("[language]", lang_name)
                .replace("[output]", METADATA_OUTPUT_SPEC))
    model = _agent_model(agent)
    raw = _call_ai_stream([{"role": "user", "content": full}], model=model)
    data = _extract_json(raw)
    result = {
        "title": (data.get("title") or "").strip(),
        "description": (data.get("description") or "").strip(),
        "thumbnail_prompt": (data.get("thumbnail_prompt") or "").strip(),
    }
    log = {"model": model, "prompt": full, "raw_output": raw, "parsed": data}
    return result, log


def _generate_image_prompt(run, agent_type):
    """模糊底图 / 尾图 Agent → 产出英文生图 prompt。返回 (image_prompt, log)。"""
    prompt, agent = _get_prompt(agent_type)
    if prompt is None:
        raise RuntimeError(f"{dict(Flow3Agent.AGENT_TYPE_CHOICES).get(agent_type, agent_type)} 已停用")
    full = _inject_globals(prompt, run).replace("[input]", run.keyword).replace("[output]", IMAGE_OUTPUT_SPEC)
    model = _agent_model(agent)
    raw = _call_ai_stream([{"role": "user", "content": full}], model=model)
    data = _extract_json(raw)
    image_prompt = (data.get("image_prompt") or "").strip()
    log = {"model": model, "prompt": full, "raw_output": raw, "parsed": data}
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
# 多语言 TTS（Edge TTS 免费）。失败降级 elevenlabs，再失败跳过该段。
# ===========================================================================
# language 代码 → edge-tts 默认音色（男声优先）。全局设置 FLOW3_TTS_VOICE 优先覆盖。
_EDGE_VOICE_MAP = {
    "en-IN": "en-IN-PrabhatNeural",   # 印度英语
    "en": "en-US-GuyNeural",          # 英语（美式）
    "pt-BR": "pt-BR-AntonioNeural",   # 巴西葡萄牙语
    "pt": "pt-BR-AntonioNeural",      # 葡萄牙语（复用巴西）
    "ru": "ru-RU-DmitryNeural",       # 俄语
    "es": "es-ES-AlvaroNeural",       # 西班牙语
    "hi": "hi-IN-MadhurNeural",       # 印地语
    "de": "de-DE-ConradNeural",       # 德语
    "fr": "fr-FR-HenriNeural",        # 法语
    "it": "it-IT-DiegoNeural",        # 意大利语
    "ja": "ja-JP-KeitaNeural",        # 日语
    "ko": "ko-KR-InJoonNeural",       # 韩语
    "ar": "ar-SA-HamedNeural",        # 阿拉伯语
}


def _edge_voice(language):
    """取 TTS 音色：全局设置 FLOW3_TTS_VOICE 优先，否则按 language 映射，未登记回退印度英语。"""
    configured = get_setting("FLOW3_TTS_VOICE")
    if configured:
        return configured
    lang = (language or "").strip()
    return _EDGE_VOICE_MAP.get(lang, "en-IN-PrabhatNeural")


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
                     output_abs_path, promo_variant=0, render_url=None, timeout=2400):
    """
    通过 HTTP 调 render 容器的 Remotion 服务渲染 SegB（compositionId=Flow3SegmentB）。
    所有路径用 render 容器可见的共享卷绝对路径（/app/media/...）。
    返回 render 响应 dict（含 durationInFrames）。失败抛异常。
    
    超时调整：从 1200s → 2400s（40min），给予充足时间处理图片加载延迟。
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

