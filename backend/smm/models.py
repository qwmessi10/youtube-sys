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
    # 轮询任务产生的子下单指向父任务；普通任务该字段为空。
    poll_task = models.ForeignKey("SMMPollTask", on_delete=models.CASCADE, related_name="children", null=True, blank=True)
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


class SMMPollTask(models.Model):
    """轮询刷量任务（父任务）：维持 VPH，窗口内每小时自动下一单，跨天直到刷满轮询次数。

    首次刷量（initial_count）在创建时立即下单，不计入 poll_total。
    每次轮询产生一个 SMMTask 子下单（poll_task 指向本记录）。
    """

    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_STOPPED = "stopped"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "运行中"),
        (STATUS_COMPLETED, "已完成"),
        (STATUS_STOPPED, "已停止"),
        (STATUS_FAILED, "失败"),
    ]

    account = models.ForeignKey(SMMAccount, on_delete=models.CASCADE, related_name="poll_tasks")
    youtube_link = models.CharField(max_length=500)
    key_words = models.CharField(max_length=500, blank=True, default="", verbose_name="关键词")
    per_user = models.DecimalField(max_digits=10, decimal_places=2, default=2, verbose_name="每人奖励(₹)")
    task_type = models.IntegerField(default=42, verbose_name="服务类型")
    plant_form = models.IntegerField(default=1, verbose_name="平台")
    comment_num = models.IntegerField(default=1, verbose_name="评论数")

    initial_count = models.IntegerField(null=True, blank=True, verbose_name="首次刷量人数")

    poll_total = models.IntegerField(verbose_name="轮询次数")
    poll_done = models.IntegerField(default=0, verbose_name="已刷次数")
    batch_min = models.IntegerField(default=1, verbose_name="每批人数下限")
    batch_max = models.IntegerField(default=5, verbose_name="每批人数上限")
    window_start_hour = models.IntegerField(default=12, verbose_name="窗口开始小时(北京)")
    window_end_hour = models.IntegerField(default=21, verbose_name="窗口结束小时(北京)")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING, verbose_name="状态")
    next_poll_at = models.DateTimeField(null=True, blank=True, verbose_name="下次执行时间")
    fail_count = models.IntegerField(default=0, verbose_name="连续失败次数")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "轮询刷量任务"
        verbose_name_plural = "轮询刷量任务"

    def __str__(self):
        return f"{self.account} - {self.key_words or self.youtube_link}"

    @property
    def locked_amount(self):
        """锁定金额（按最大估算）：首次刷量 + 轮询次数×每批上限，均按每人奖励 per_user 计。"""
        initial = float(self.initial_count or 0)
        return float(self.per_user) * (initial + self.poll_total * self.batch_max)
