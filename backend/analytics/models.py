"""数据分析系统数据模型。

三大板块：
  1. 视频库（我的视频看板）：VideoLibraryItem + VideoMetricSnapshot（指标历史快照，趋势图）
  2. 竞品 SEO 分析：CompetitorAnalysis（关键词 → top N 拆解 + 汇总洞察）
  3. 关键词排名追踪：KeywordRankTracking + KeywordRankSnapshot（排名快照，趋势图）

数据源复用关键词系统的 SerpApi 搜索 + YouTube V3 补数（keywords.services）。
"""
from django.db import models


class VideoLibraryItem(models.Model):
    """视频库条目（我的视频）。来源：auto(AdsPower 上传自动关联) / manual(手动添加)。"""

    SOURCE_AUTO = "auto"
    SOURCE_MANUAL = "manual"
    SOURCE_CHOICES = [
        (SOURCE_AUTO, "自动关联"),
        (SOURCE_MANUAL, "手动添加"),
    ]

    video_id = models.CharField(max_length=32, unique=True, verbose_name="YouTube 视频 ID")
    video_url = models.CharField(max_length=500, verbose_name="视频链接")
    title = models.CharField(max_length=500, blank=True, default="", verbose_name="标题")
    channel_name = models.CharField(max_length=255, blank=True, default="", verbose_name="频道")
    channel_id = models.CharField(max_length=100, blank=True, default="", verbose_name="频道 ID")
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=SOURCE_MANUAL, verbose_name="来源")
    # 自动关联来源（可空）
    upload_task = models.ForeignKey(
        "uploader.UploadTask", on_delete=models.SET_NULL, null=True, blank=True, related_name="video_library_items"
    )
    flow3_run = models.ForeignKey(
        "flow3.Flow3Run", on_delete=models.SET_NULL, null=True, blank=True, related_name="video_library_items"
    )
    remark = models.CharField(max_length=255, blank=True, default="", verbose_name="备注")

    # —— 指标快照（最新一次抓取）——
    view_count = models.BigIntegerField(null=True, blank=True, verbose_name="播放量")
    like_count = models.BigIntegerField(null=True, blank=True, verbose_name="点赞")
    comment_count = models.BigIntegerField(null=True, blank=True, verbose_name="评论")
    published_at = models.DateTimeField(null=True, blank=True, verbose_name="发布时间")
    duration = models.CharField(max_length=32, blank=True, default="", verbose_name="时长(ISO8601)")
    snapshot_at = models.DateTimeField(null=True, blank=True, verbose_name="数据更新时间")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "视频库条目"
        verbose_name_plural = "视频库条目"

    def __str__(self):
        return self.title or self.video_id


class VideoMetricSnapshot(models.Model):
    """视频指标历史快照（用于播放/点赞/评论趋势图）。"""

    video = models.ForeignKey(VideoLibraryItem, on_delete=models.CASCADE, related_name="snapshots")
    view_count = models.BigIntegerField(null=True, blank=True)
    like_count = models.BigIntegerField(null=True, blank=True)
    comment_count = models.BigIntegerField(null=True, blank=True)
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["captured_at"]
        verbose_name = "视频指标快照"
        verbose_name_plural = "视频指标快照"


class CompetitorAnalysis(models.Model):
    """竞品 SEO 分析记录（一次查询 = 关键词 + 国家/语言 + top N 拆解结果）。"""

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "待处理"),
        (STATUS_RUNNING, "分析中"),
        (STATUS_COMPLETED, "已完成"),
        (STATUS_FAILED, "失败"),
    ]

    keyword = models.CharField(max_length=255, verbose_name="关键词")
    country = models.CharField(max_length=8, default="US", verbose_name="国家")
    language = models.CharField(max_length=16, default="en", verbose_name="语言")
    top_n = models.PositiveSmallIntegerField(default=10, verbose_name="取前 N")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, verbose_name="状态")
    result = models.JSONField(default=dict, blank=True, verbose_name="分析结果")
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "竞品 SEO 分析"
        verbose_name_plural = "竞品 SEO 分析"

    def __str__(self):
        return f"{self.keyword} ({self.top_n})"


class KeywordRankTracking(models.Model):
    """关键词排名追踪配置（定时抓 top N 排名，存快照，画趋势图）。"""

    keyword = models.CharField(max_length=255, verbose_name="关键词")
    country = models.CharField(max_length=8, default="US", verbose_name="国家")
    language = models.CharField(max_length=16, default="en", verbose_name="语言")
    top_n = models.PositiveSmallIntegerField(default=10, verbose_name="取前 N")
    enabled = models.BooleanField(default=True, verbose_name="启用")
    last_captured_at = models.DateTimeField(null=True, blank=True, verbose_name="最近抓取时间")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "排名追踪配置"
        verbose_name_plural = "排名追踪配置"

    def __str__(self):
        return self.keyword


class KeywordRankSnapshot(models.Model):
    """排名快照（某次抓取时该关键词下 top N 视频的排名数据）。"""

    tracking = models.ForeignKey(KeywordRankTracking, on_delete=models.CASCADE, related_name="snapshots")
    captured_at = models.DateTimeField(auto_now_add=True)
    videos = models.JSONField(default=list, blank=True, verbose_name="排名数据")

    class Meta:
        ordering = ["captured_at"]
        verbose_name = "排名快照"
        verbose_name_plural = "排名快照"

    def __str__(self):
        return f"{self.tracking.keyword} @ {self.captured_at}"
