"""
流程3 数据模型（与流程1/2 的 content_gen 完全隔离）。
三段式长视频：SegA Hook(人工上传) + SegB 画中画(Remotion) + SegC 尾图微动(ffmpeg)。
单视频模式：一个任务 = 一个关键词 = 一个成品视频，无批量。
"""
import uuid

from django.db import models


class Flow3Agent(models.Model):
    """
    流程3 专属 Agent 提示词配置（与 content_gen.ContentAgent 隔离）。
    5 个 Agent：hook / narration / blur_bg / tail_image / metadata。
    名称/用途/类型固定，只允许改 prompt 和 enabled。
    """
    AGENT_HOOK = "hook"
    AGENT_NARRATION = "narration"
    AGENT_BLUR_BG = "blur_bg"
    AGENT_TAIL_IMAGE = "tail_image"
    AGENT_METADATA = "metadata"
    AGENT_TYPE_CHOICES = [
        (AGENT_HOOK, "Hook 视频文案 Agent"),
        (AGENT_NARRATION, "语音文案 Agent（7s-30s）"),
        (AGENT_BLUR_BG, "模糊底图 Agent"),
        (AGENT_TAIL_IMAGE, "尾图 Agent"),
        (AGENT_METADATA, "元数据生成 Agent"),
    ]

    agent_type = models.CharField(max_length=32, choices=AGENT_TYPE_CHOICES, unique=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    prompt = models.TextField(blank=True)  # 留空则运行时回退到代码内默认提示词
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["agent_type"]

    def __str__(self):
        return self.name


class Flow3Material(models.Model):
    """
    流程3 专属素材库（与 content_gen 的模板 assets 完全不同、隔离）。
    三类：
      - screen_record：SegB 右侧 9:16 手机录屏，库内固定维护 1 个，所有任务自动取用。
      - bgm：背景音乐，可批量上传多个，任务执行时随机抽 1 个（种子记录到任务）。
      - hook：SegA 开场 Hook 视频，可批量上传。任务创建时可指定或随机取「未使用」的；
        用过标记为「已使用」，已使用的不再参与随机，除非用户显式选中。
    """
    TYPE_SCREEN = "screen_record"
    TYPE_BGM = "bgm"
    TYPE_HOOK = "hook"
    TYPE_CHOICES = [
        (TYPE_SCREEN, "9:16 手机录屏"),
        (TYPE_BGM, "背景音乐 BGM"),
        (TYPE_HOOK, "Hook 视频"),
    ]

    # 素材标签（主要用于 hook 素材的使用状态流转）。
    TAG_UNUSED = "unused"
    TAG_USED = "used"
    TAG_CHOICES = [
        (TAG_UNUSED, "未使用"),
        (TAG_USED, "已使用"),
    ]

    material_type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    name = models.CharField(max_length=200, blank=True)        # 展示名，留空取文件名
    file = models.FileField(upload_to="flow3/materials/")
    duration = models.FloatField(null=True, blank=True)        # 视频/音频时长（秒），ffprobe 探测
    tag = models.CharField(max_length=16, choices=TAG_CHOICES, default=TAG_UNUSED)  # 使用状态标签
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["material_type", "-created_at"]

    def __str__(self):
        return f"{self.get_material_type_display()}: {self.name or self.file.name}"


class Flow3Run(models.Model):
    """
    流程3 一次任务 = 一个关键词 = 一个成品视频（单视频，无批量）。
    状态机：pending → running(出Hook prompt) → awaiting_hook(暂停等上传)
            → [上传mp4+继续] → running(Step4~7) → completed / failed
    """
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_AWAITING_HOOK = "awaiting_hook"   # 新增中间态：已出 Hook prompt，暂停等人工上传 mp4
    STATUS_PAUSED = "paused"
    STATUS_STOPPED = "stopped"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "待处理"),
        (STATUS_RUNNING, "处理中"),
        (STATUS_AWAITING_HOOK, "等待 Hook 视频上传"),
        (STATUS_PAUSED, "已暂停"),
        (STATUS_STOPPED, "已停止"),
        (STATUS_COMPLETED, "已完成"),
        (STATUS_FAILED, "失败"),
    ]

    # —— 任务创建入参 ——
    name = models.CharField(max_length=255, blank=True)        # 任务备注名
    keyword = models.CharField(max_length=255)                 # 仅 1 个关键词
    total_duration = models.PositiveIntegerField(default=240)  # 总时长（秒），决定 SegC 结束点
    promo_code = models.CharField(max_length=64, blank=True)   # 手填，如 ZH567
    country = models.CharField(max_length=8, default="IN")     # 国家（注入 {COUNTRY}）
    event_name = models.CharField(max_length=255, blank=True)  # 赛事名（注入 {EVENT_NAME}）
    language = models.CharField(max_length=16, default="en-IN")  # 旁白语言，默认印式英语

    # —— 过程产出 ——
    hook_prompt = models.TextField(blank=True)                 # Step2 Hook Agent 产出的视频 prompt
    hook_video = models.FileField(upload_to="flow3/hook/", blank=True, null=True)  # Hook mp4（人工上传 或 从库复制）
    # 从 hook 素材库选用/随机到的素材（可空）。有值则跳过「出 prompt + 等待上传」直接出片。
    hook_material = models.ForeignKey(
        "Flow3Material", on_delete=models.SET_NULL, null=True, blank=True, related_name="used_by_runs"
    )
    narration = models.JSONField(default=dict, blank=True)     # 旁白脚本 {shots:[{index,duration,narration}]}
    narration_audio = models.JSONField(default=list, blank=True)  # TTS 产出 [{index,file,provider}]
    blur_bg_file = models.FileField(upload_to="flow3/blur_bg/", blank=True, null=True)   # SegB 高斯模糊底图
    tail_image_file = models.FileField(upload_to="flow3/tail/", blank=True, null=True)   # SegC 尾图
    segb_file = models.FileField(upload_to="flow3/segb/", blank=True, null=True)         # SegB 渲染中间产物
    segc_file = models.FileField(upload_to="flow3/segc/", blank=True, null=True)         # SegC 中间产物
    rendered_file = models.FileField(upload_to="flow3/rendered/", blank=True, null=True) # 最终成品

    # 元数据
    title = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    thumbnail_prompt = models.TextField(blank=True)
    thumbnail_file = models.FileField(upload_to="flow3/thumbnails/", blank=True, null=True)  # 封面图（按 thumbnail_prompt 生图）

    # —— 随机/防封参数 ——
    layout_seed = models.PositiveIntegerField(default=0)       # 左右布局随机种子（录屏左/右）
    bgm_seed = models.PositiveIntegerField(default=0)          # BGM 随机抽取种子
    bgm_file = models.CharField(max_length=500, blank=True)    # 实际选中的 BGM 相对路径（便于复现）

    # —— 控制/日志 ——
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    task_token = models.UUIDField(default=uuid.uuid4, editable=False)
    error_message = models.TextField(blank=True)
    run_log = models.JSONField(default=dict, blank=True)       # 全流程详细日志（每步输入/输出/耗时/状态）
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name or f"流程3任务 #{self.pk}"
