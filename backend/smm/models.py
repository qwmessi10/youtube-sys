"""SMM 面板系统数据模型（对接第三方 AutoLak Cloud Bot 面板）。

一个 Telegram 账号对应一个面板账号（靠 tg_user_id 唯一）；
一个面板账号下可创建多个刷量任务。
"""
from django.db import models


class SMMAccount(models.Model):
    """面板账号（个人中心）。token 由 publishTelegramAuth 接口自动提取。"""

    STATUS_ACTIVE = "active"
    STATUS_TOKEN_INVALID = "token_invalid"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "有效"),
        (STATUS_TOKEN_INVALID, "token 失效"),
    ]

    tg_user_id = models.CharField(max_length=32, unique=True, verbose_name="Telegram 数字 ID")
    username = models.CharField(max_length=100, blank=True, default="", verbose_name="@用户名(展示用)")
    first_name = models.CharField(max_length=100, blank=True, default="")
    last_name = models.CharField(max_length=100, blank=True, default="")
    panel_user_name = models.CharField(max_length=100, blank=True, default="", verbose_name="面板昵称")
    token = models.CharField(max_length=200, blank=True, default="")
    user_identifier = models.CharField(max_length=100, blank=True, default="")
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="余额(₹)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    remark = models.CharField(max_length=255, blank=True, default="", verbose_name="备注")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "面板账号"
        verbose_name_plural = "面板账号"

    def __str__(self):
        return self.panel_user_name or self.username or self.tg_user_id


class SMMTask(models.Model):
    """刷量任务（提交到面板后，状态/进度定期从面板同步）。"""

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "进行中"),
        (STATUS_RUNNING, "进行中"),
        (STATUS_COMPLETED, "已完成"),
        (STATUS_FAILED, "失败"),
    ]

    account = models.ForeignKey(SMMAccount, on_delete=models.CASCADE, related_name="tasks")
    panel_task_id = models.CharField(max_length=64, blank=True, default="", verbose_name="面板任务ID")
    show_id = models.CharField(max_length=100, blank=True, default="", verbose_name="任务号")
    youtube_link = models.CharField(max_length=500)
    key_words = models.CharField(max_length=500, blank=True, default="", verbose_name="关键词")
    total_user = models.IntegerField(default=0, verbose_name="人数")
    per_user = models.DecimalField(max_digits=10, decimal_places=2, default=2, verbose_name="每人奖励(₹)")
    task_type = models.IntegerField(default=42, verbose_name="服务类型")
    plant_form = models.IntegerField(default=1, verbose_name="平台")
    comment_num = models.IntegerField(default=1, verbose_name="评论数")
    end_time = models.CharField(max_length=32, blank=True, default="", verbose_name="结束时间")
    cost = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="成本(₹)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, verbose_name="状态")
    panel_status = models.CharField(max_length=50, blank=True, default="", verbose_name="面板原始状态")
    progress = models.JSONField(default=dict, blank=True, verbose_name="进度")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "刷量任务"
        verbose_name_plural = "刷量任务"

    def __str__(self):
        return self.show_id or self.panel_task_id or str(self.id)
