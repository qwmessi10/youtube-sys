import uuid

from django.db import models


class ContentAgent(models.Model):
    """
    内容生成系统的两个 Agent 提示词配置（仿 keywords.AgentPrompt）：
      - metadata：元数据生成 Agent（出标题/描述/封面提示词）
      - storyboard：脚本分镜生成 Agent（出分镜 JSON）
    名称/用途/类型固定，只允许改 prompt 和 enabled。
    """
    AGENT_METADATA = "metadata"
    AGENT_STORYBOARD = "storyboard"
    AGENT_TYPE_CHOICES = [
        (AGENT_METADATA, "元数据生成 Agent"),
        (AGENT_STORYBOARD, "脚本分镜生成 Agent"),
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


class ContentRun(models.Model):
    """
    一次内容生成任务批次。一个批次可含多个关键词，每个关键词一条 ContentItem。
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
    # 流程一专用：创建任务时手填一个 promo code，整批关键词共用，渲染时注入模板。
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
        ordering = ["keyword"]
        constraints = [models.UniqueConstraint(fields=["run", "keyword"], name="unique_keyword_per_content_run")]

    def __str__(self):
        return self.keyword
