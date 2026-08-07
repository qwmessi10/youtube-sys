import uuid

from django.db import models


class ContentAgent(models.Model):
    """
    内容生成系统的 Agent 提示词配置（仿 keywords.AgentPrompt）：
      - metadata：元数据生成 Agent（出标题/描述/封面提示词），流程一/流程二共用
      - storyboard：脚本分镜生成 Agent（出分镜 JSON），流程二用（人工按分镜拍视频）
      - narration：音频脚本生成 Agent（只出旁白文案），流程一用（画面由 Remotion 模板定）
    名称/用途/类型固定，只允许改 prompt 和 enabled。
    """
    AGENT_METADATA = "metadata"
    AGENT_STORYBOARD = "storyboard"
    AGENT_NARRATION = "narration"
    AGENT_TYPE_CHOICES = [
        (AGENT_METADATA, "元数据生成 Agent"),
        (AGENT_STORYBOARD, "脚本分镜生成 Agent"),
        (AGENT_NARRATION, "音频脚本生成 Agent"),
    ]

    agent_type = models.CharField(max_length=32, choices=AGENT_TYPE_CHOICES, unique=True)
    name = models.CharField(max_length=100)          # 展示名
    description = models.CharField(max_length=255, blank=True)
    prompt = models.TextField(blank=True)            # 留空则运行时回退到代码内默认提示词
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["agent_type"]

    def __str__(self):
        return self.name


class VideoTemplate(models.Model):
    """
    视频模板（流程一批量出片用）。
    一个模板 = 数据库这条元信息（尺寸/变量声明/默认素材/AI分析规格）
             + render 项目里对应的一段 Remotion 组件代码（用 composition_id 关联）。
    上传参考视频后由 Gemini 分析出规格（analysis），据此人工把组件调到位再复用批量出片。
    """
    # 模板接入状态：pending=运营提了需求、等开发写 Remotion 组件；ready=组件已接入、可出片。
    # 只有 ready 的模板才出现在流程一的可选列表里。
    STATUS_PENDING = "pending"
    STATUS_READY = "ready"
    STATUS_CHOICES = [(STATUS_PENDING, "待接入（开发制作组件中）"), (STATUS_READY, "已就绪（可出片）")]

    name = models.CharField(max_length=200)                       # 模板名
    description = models.CharField(max_length=500, blank=True)    # 模板说明
    # 画面尺寸，默认横屏 1080p（前端只让运营选 16:9 / 9:16，映射到具体像素）
    width = models.PositiveIntegerField(default=1920)
    height = models.PositiveIntegerField(default=1080)
    fps = models.PositiveSmallIntegerField(default=30)
    # 流程一段数/每段时长挪到模板上：analyze 时由 AI 给建议，运营可在模板编辑里微调。
    # 创建任务时不再让运营填，直接读模板的值。
    shot_count = models.PositiveSmallIntegerField(default=2)
    shot_duration = models.PositiveSmallIntegerField(default=8)
    # 接入状态（见上）。运营新建/提需求的模板默认 pending，开发接好组件后置 ready。
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    # 运营的「调整需求」：画面要怎么改（优惠码更大、换配色、挪位置等），作为开发改组件的需求单。
    # 画面模板=Remotion 组件代码，只能开发改，运营填文字无法自动改画面。
    adjust_notes = models.TextField(blank=True)
    # 关联 render 项目里 Root.tsx 注册的 Composition id；运营侧隐藏，由开发在后台填。
    composition_id = models.CharField(max_length=100, blank=True)
    # 变量声明：创建任务时据此动态渲染输入框。
    # 形如 [{"key":"promo_code","label":"优惠码","required":true,"ai_editable":false}]
    # ai_editable=false 表示该值必须由用户提供、AI 不得生成（如 promo code）。
    variables_schema = models.JSONField(default=list, blank=True)
    # 默认素材：做模板要用的录屏/logo 等，形如 [{"key":"screen_record","file":"content/templates/.../x.mp4","name":"注册录屏"}]
    assets = models.JSONField(default=list, blank=True)
    # Gemini 对参考视频的分析规格（布局/文字/配色/转场/分镜时间戳等），供调模板参考。
    analysis = models.JSONField(default=dict, blank=True)
    # 上传的参考视频（供分析）。用 FileField 避免额外依赖。
    source_video = models.FileField(upload_to="content/templates/source/", blank=True, null=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class ContentRun(models.Model):
    """
    一次内容生成任务批次。
    流程二：一个批次含多个关键词，每个关键词一条 ContentItem（人工上传视频合并）。
    流程一：一个关键词 + 一个模板 + N 组变量 → N 条 ContentItem（每条一个视频，AI 内容独立生成）。
    沿用关键词系统的 task_token 暂停/停止机制与 run_log 工作日志。
    """
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_PAUSED = "paused"
    STATUS_STOPPED = "stopped"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "待处理"), (STATUS_RUNNING, "处理中"), (STATUS_PAUSED, "已暂停"),
        (STATUS_STOPPED, "已停止"), (STATUS_COMPLETED, "已完成"), (STATUS_FAILED, "失败"),
    ]

    # 流程区分：flow2=半自动（人工上传视频合并），flow1=全自动（TTS + Remotion 渲染）。
    # 默认 flow2 兼容存量任务。
    FLOW_SEMI = "flow2"
    FLOW_AUTO = "flow1"
    FLOW_CHOICES = [(FLOW_SEMI, "流程二·半自动"), (FLOW_AUTO, "流程一·全自动")]

    # TTS 引擎（仅流程一用）：edge=微软免费无 key，elevenlabs=付费需 key。
    TTS_EDGE = "edge"
    TTS_ELEVENLABS = "elevenlabs"
    TTS_CHOICES = [(TTS_EDGE, "Edge TTS（免费）"), (TTS_ELEVENLABS, "ElevenLabs（付费）")]

    name = models.CharField(max_length=255, blank=True)   # 任务备注名，便于识别
    flow = models.CharField(max_length=8, choices=FLOW_CHOICES, default=FLOW_SEMI)
    country = models.CharField(max_length=8, default="US")
    language = models.CharField(max_length=16, default="en")
    # 分镜段数与每段时长：可变参数，默认 8+8（两段各 8s）。现阶段用默认。
    shot_count = models.PositiveSmallIntegerField(default=2)
    shot_duration = models.PositiveSmallIntegerField(default=8)
    # 流程一专用：选用的视频模板（必选）。流程二为空。
    template = models.ForeignKey(
        VideoTemplate, on_delete=models.PROTECT, null=True, blank=True, related_name="runs"
    )
    # 流程一专用：本次要生成的视频数量（方案a：数字框直接指定）。
    # 若上传了变量文件（方案b），实际条数以文件行数为准，此值仅作参考。
    video_count = models.PositiveSmallIntegerField(default=1)
    # 流程一专用：创建任务时手填的共享优惠码（整批共用一组变量时用），渲染时注入模板。
    # 每视频不同变量时改由 ContentItem.variables 承载。
    promo_code = models.CharField(max_length=64, blank=True)
    # 流程一专用：旁白 TTS 引擎，默认 edge。
    tts_provider = models.CharField(max_length=16, choices=TTS_CHOICES, default=TTS_EDGE)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    task_token = models.UUIDField(default=uuid.uuid4, editable=False)
    error_message = models.TextField(blank=True)
    run_log = models.JSONField(default=dict, blank=True)  # 任务级工作日志（AI 输入/输出等）
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name or f"内容任务 #{self.pk}"


class ContentItem(models.Model):
    """
    批次内单个关键词的内容生成记录：元数据 + 封面 + 分镜脚本 + 人工上传的分镜视频 + 合并成品。
    """
    STATUS_PENDING = "pending"          # 待生成
    STATUS_GENERATING = "generating"    # AI 生成中（元数据/分镜/封面）
    STATUS_GENERATED = "generated"      # AI 内容已生成，等待人工上传视频（流程二）
    STATUS_MERGING = "merging"          # 合并中（流程二）
    STATUS_MERGED = "merged"            # 已合并出成品（流程二）
    STATUS_RENDERING = "rendering"      # 渲染中（流程一：TTS + Remotion）
    STATUS_RENDERED = "rendered"        # 已渲染出成品（流程一）
    STATUS_FAILED = "failed"            # 生成失败
    STATUS_CHOICES = [
        (STATUS_PENDING, "待生成"), (STATUS_GENERATING, "AI 生成中"),
        (STATUS_GENERATED, "内容已生成，待上传视频"), (STATUS_MERGING, "合并中"),
        (STATUS_MERGED, "已合并成品"),
        (STATUS_RENDERING, "渲染中"), (STATUS_RENDERED, "已渲染成品"),
        (STATUS_FAILED, "生成失败"),
    ]

    run = models.ForeignKey(ContentRun, on_delete=models.CASCADE, related_name="items")
    keyword = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    # 流程一专用：该视频这一组变量的值，形如 {"promo_code":"75EPL","bonus":"100%"}。
    # 渲染时注入模板画面；文案里的 {promo_code} 占位符也用它替换。流程二为空。
    variables = models.JSONField(default=dict, blank=True)

    # 元数据 Agent 产出
    title = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    thumbnail_prompt = models.TextField(blank=True)     # 封面提示词
    # 用 FileField 而非 ImageField，避免引入 Pillow 依赖（封面是生成好的 jpeg，无需图像校验）
    thumbnail_file = models.FileField(upload_to="content/thumbnails/", blank=True, null=True)

    # 分镜 Agent 产出（固定 JSON，段数可变默认 8+8）
    storyboard = models.JSONField(default=dict, blank=True)

    # 人工上传的分镜视频（按段存列表：每段一个文件路径）；合并成品（流程二）
    clip_files = models.JSONField(default=list, blank=True)   # [{"index":1,"file":"content/.../x.mp4"}, ...]
    merged_file = models.FileField(upload_to="content/merged/", blank=True, null=True)

    # 流程一专用：按段旁白音频（TTS 产出）与 Remotion 渲染成品。
    narration_audio = models.JSONField(default=list, blank=True)  # [{"index":1,"file":"content/.../x.mp3","provider":"edge"}, ...]
    rendered_file = models.FileField(upload_to="content/rendered/", blank=True, null=True)

    # 生成工作日志：两个 Agent 的完整输入提示词/原始输出/解析结果，封面出图提示词与结果，各步骤进度。
    # 供前端「查看日志」抽屉展示，方便调试提示词、看封面提示词到底长啥样。
    gen_log = models.JSONField(default=dict, blank=True)

    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # 流程一同一关键词会产出多条（每条一个视频），故不再约束 run+keyword 唯一。
        # 流程二在创建接口内已对关键词去重，去掉约束不影响其行为。
        ordering = ["created_at"]

    def __str__(self):
        return self.keyword
