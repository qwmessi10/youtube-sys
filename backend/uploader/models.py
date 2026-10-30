"""
AdsPower 自动化上传系统数据模型（与 flow3 / keywords 隔离）。

两张表：
  - AdsPowerProfile：缓存 AdsPower 本地 API 拉回的浏览器环境列表，供前端展示、选择。
  - UploadTask：一次自动化上传任务（手动创建 或 从 flow3 成品任务创建）。

执行器（宿主独立进程）通过后端接口领任务、拿 payload、回调结果，后端只负责排任务 + 存结果。
"""
from django.db import models


class AdsPowerProfile(models.Model):
    """
    AdsPower 浏览器环境缓存（数据源：本地 API /api/v1/user/list）。
    后端定时 / 手动同步，前端"浏览器管理页"展示。user_id 为 AdsPower 环境唯一标识。
    注意：代理凭据（socks5 账号密码）不单独落库，仅在 raw 内保留原样并在序列化时脱敏。
    """
    user_id = models.CharField(max_length=64, unique=True)       # AdsPower 环境 ID（唯一）
    serial_number = models.CharField(max_length=32, blank=True)  # 环境编号（AdsPower 序号）
    name = models.CharField(max_length=255, blank=True)          # 环境名称
    group_id = models.CharField(max_length=64, blank=True)
    group_name = models.CharField(max_length=255, blank=True)    # 所属分组名
    domain_name = models.CharField(max_length=255, blank=True)   # 绑定平台（accounts.google.com 等）
    username = models.CharField(max_length=255, blank=True)      # 环境内账号（如有）
    remark = models.TextField(blank=True)
    ip = models.CharField(max_length=64, blank=True)             # 出口 IP
    ip_country = models.CharField(max_length=16, blank=True)     # IP 国家
    proxy_summary = models.CharField(max_length=255, blank=True)  # 代理摘要（类型 + IP:端口，不含账密）
    last_open_time = models.CharField(max_length=32, blank=True)  # AdsPower 返回的最近打开时间戳
    raw = models.JSONField(default=dict, blank=True)             # 原始返回（代理密码已脱敏）
    synced_at = models.DateTimeField(auto_now=True)              # 最近一次同步时间

    class Meta:
        ordering = ["group_name", "serial_number"]

    def __str__(self):
        return f"{self.name}({self.user_id})"


class UploadTask(models.Model):
    """
    一次自动化上传任务。状态机：
      queued → launching（起浏览器+接管）→ uploading（传视频+填元数据）
             → draft_saved（草稿已保存，开发阶段终态，等人工核对）
             → [后续] publishing → completed
             → failed（任一步失败）
    """
    STATUS_QUEUED = "queued"
    STATUS_LAUNCHING = "launching"
    STATUS_UPLOADING = "uploading"
    STATUS_DRAFT_SAVED = "draft_saved"
    STATUS_PUBLISHING = "publishing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "排队中"),
        (STATUS_LAUNCHING, "启动浏览器"),
        (STATUS_UPLOADING, "上传中"),
        (STATUS_DRAFT_SAVED, "草稿已保存"),
        (STATUS_PUBLISHING, "发布中"),
        (STATUS_COMPLETED, "已完成"),
        (STATUS_FAILED, "失败"),
    ]

    # 发布模式：开发阶段固定 draft，后续放开 public/unlisted/private
    MODE_DRAFT = "draft"
    MODE_PUBLIC = "public"
    MODE_UNLISTED = "unlisted"
    MODE_PRIVATE = "private"
    MODE_CHOICES = [
        (MODE_DRAFT, "仅存草稿（不发布）"),
        (MODE_PUBLIC, "公开"),
        (MODE_UNLISTED, "不公开（有链接可见）"),
        (MODE_PRIVATE, "私享"),
    ]

    name = models.CharField(max_length=255, blank=True)          # 任务备注名（空则取标题）
    # 关联的 flow3 成品任务（手动创建时可空）。flow3 删除不级联删上传任务，仅置空。
    source_run = models.ForeignKey(
        "flow3.Flow3Run", on_delete=models.SET_NULL, null=True, blank=True, related_name="upload_tasks"
    )
    profile = models.ForeignKey(
        AdsPowerProfile, on_delete=models.PROTECT, related_name="upload_tasks"
    )  # 目标浏览器环境

    # —— 上传内容（结构化字段，不走 zip）——
    video_file = models.FileField(upload_to="uploader/videos/", blank=True, null=True)  # 手动上传的视频
    video_path = models.CharField(max_length=500, blank=True)    # 来自 flow3 的成品相对路径（优先用它）
    title = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    cover_file = models.FileField(upload_to="uploader/covers/", blank=True, null=True)  # 手动上传封面
    cover_path = models.CharField(max_length=500, blank=True)    # 来自 flow3 的封面相对路径

    publish_mode = models.CharField(max_length=16, choices=MODE_CHOICES, default=MODE_DRAFT)

    # —— 执行 / 结果 ——
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    video_url = models.CharField(max_length=500, blank=True)     # 上传后回填的 YouTube 链接
    retry_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    upload_log = models.JSONField(default=dict, blank=True)      # 每步耗时 / 截图路径 / YT 返回
    locked_at = models.DateTimeField(null=True, blank=True)      # 执行器领取时间（防重复领取）

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name or self.title or f"上传任务 #{self.pk}"
