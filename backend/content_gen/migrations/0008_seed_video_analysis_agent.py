from django.db import migrations

# 视频分析 Agent 内置默认提示词（与 services.DEFAULT_VIDEO_ANALYSIS_PROMPT 保持一致）。
# 作用：分析上传的参考视频，产出「像素级复刻」用的结构化规格 + 关键帧时间点。
# 运营可在「内容生成 Agent 管理」页微调此提示词，改变分析的精细程度。
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

AGENT = (
    "video_analysis",
    "视频分析 Agent",
    "上传参考视频时用它分析画面结构、产出复刻用的结构化规格与关键帧时间点",
    DEFAULT_VIDEO_ANALYSIS_PROMPT,
)


def seed_agent(apps, schema_editor):
    ContentAgent = apps.get_model("content_gen", "ContentAgent")
    agent_type, name, description, prompt = AGENT
    ContentAgent.objects.get_or_create(
        agent_type=agent_type,
        defaults={"name": name, "description": description, "prompt": prompt, "enabled": True},
    )


def remove_agent(apps, schema_editor):
    ContentAgent = apps.get_model("content_gen", "ContentAgent")
    ContentAgent.objects.filter(agent_type=AGENT[0]).delete()


class Migration(migrations.Migration):
    dependencies = [("content_gen", "0007_videotemplate_adjust_notes_videotemplate_shot_count_and_more")]

    operations = [
        migrations.RunPython(seed_agent, remove_agent),
    ]
