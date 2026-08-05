import uuid

from django.db import models


class GlobalSetting(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField(blank=True)
    description = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return self.key


class AgentPrompt(models.Model):
    """
    打分模型里各个 AI Agent 的提示词。
    一个打分模型（scoring_model）下可以有多个 agent（agent_type 区分用途，如意图识别），
    每个 agent 一条记录，方便后续扩展（新模型、新 agent 只需插一行）。
    """
    AGENT_INTENT = "intent"
    AGENT_TYPE_CHOICES = [
        (AGENT_INTENT, "关键词意图识别"),
    ]

    scoring_model = models.CharField(max_length=8)  # 对应 KeywordRun.SCORING_MODEL_*
    agent_type = models.CharField(max_length=32, choices=AGENT_TYPE_CHOICES)
    name = models.CharField(max_length=100)  # 展示名，如「博彩意图识别」
    description = models.CharField(max_length=255, blank=True)
    prompt = models.TextField(blank=True)  # 留空则运行时回退到代码内默认提示词
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scoring_model", "agent_type"]
        constraints = [
            models.UniqueConstraint(fields=["scoring_model", "agent_type"], name="unique_agent_per_model"),
        ]

    def __str__(self):
        return f"{self.scoring_model} / {self.name}"


class KeywordRun(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_PAUSED = "paused"
    STATUS_STOPPED = "stopped"
    STATUS_CHOICES = [
        (STATUS_PENDING, "待处理"), (STATUS_RUNNING, "处理中"), (STATUS_PAUSED, "已暂停"),
        (STATUS_STOPPED, "已停止"), (STATUS_COMPLETED, "已完成"), (STATUS_FAILED, "失败"),
    ]

    SCORING_MODEL_V1 = "1.0"
    SCORING_MODEL_V2 = "2.0"
    SCORING_MODEL_CHOICES = [
        (SCORING_MODEL_V1, "打分模型 1.0（前 5 视频规则打分）"),
        (SCORING_MODEL_V2, "打分模型 2.0（AI 博彩意图筛选 + 全量视频打分）"),
    ]

    root_keyword = models.CharField(max_length=255)
    country = models.CharField(max_length=8, default="US")
    language = models.CharField(max_length=16, default="en")
    max_keywords = models.PositiveSmallIntegerField(default=15)
    # 新建任务默认用 2.0；历史迁移里已存在的旧任务在迁移中回填为 1.0。
    scoring_model = models.CharField(max_length=8, choices=SCORING_MODEL_CHOICES, default=SCORING_MODEL_V2)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    task_token = models.UUIDField(default=uuid.uuid4, editable=False)
    error_message = models.TextField(blank=True)
    # 任务级工作日志：Suggest 拓展的全部词、AI 输入/输出等，供前端「查看日志」抽屉展示。
    run_log = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class KeywordResult(models.Model):
    STATUS_PENDING = "pending"
    STATUS_SERP_ERROR = "serpapi_error"
    STATUS_RULE_SCORED = "rule_scored"
    STATUS_NEEDS_REVIEW = "needs_review"
    STATUS_ELIMINATED = "eliminated"
    STATUS_CHOICES = [
        (STATUS_PENDING, "待验证"),
        (STATUS_SERP_ERROR, "SerpApi 查询失败"),
        (STATUS_RULE_SCORED, "规则打分完成"),
        (STATUS_NEEDS_REVIEW, "数据不全，需人工复核"),
        (STATUS_ELIMINATED, "已淘汰"),
    ]

    run = models.ForeignKey(KeywordRun, on_delete=models.CASCADE, related_name="results")
    keyword = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING)
    elimination_stage = models.CharField(max_length=64, blank=True)
    elimination_reason = models.TextField(blank=True)
    serpapi_status = models.CharField(max_length=32, default="pending")
    top5_video_data = models.JSONField(default=list, blank=True)
    score_breakdown = models.JSONField(default=dict, blank=True)
    rule_score = models.PositiveSmallIntegerField(null=True, blank=True)
    # 2.0 用：存 AI 博彩意图判定结果（意向等级、理由等固定 JSON）；1.0 任务保持空 dict。
    agent_result = models.JSONField(default=dict, blank=True)
    final_decision = models.CharField(max_length=32, default="待人工复核")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-rule_score", "keyword"]
        constraints = [models.UniqueConstraint(fields=["run", "keyword"], name="unique_keyword_per_run")]


class SuggestExpansionRun(models.Model):
    """
    实用工具「获取 Suggest API 长尾词」的一次任务。
    对词根做 BFS 递归拓展：查「词根 + 空格 + a~z」，新词继续当种子拓展，
    直到没有新词或达到最大词数上限。结果词直接存 JSON 列表。
    """
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_STOPPED = "stopped"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "待处理"), (STATUS_RUNNING, "处理中"),
        (STATUS_COMPLETED, "已完成"), (STATUS_STOPPED, "已停止"), (STATUS_FAILED, "失败"),
    ]

    root_keyword = models.CharField(max_length=255)
    country = models.CharField(max_length=8, default="US")
    language = models.CharField(max_length=16, default="en")
    max_keywords = models.PositiveIntegerField(default=5000)  # 安全上限，防止热门词无限膨胀
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    task_token = models.UUIDField(default=uuid.uuid4, editable=False)
    error_message = models.TextField(blank=True)
    keywords = models.JSONField(default=list, blank=True)  # 拓展出的全部长尾词
    keyword_count = models.PositiveIntegerField(default=0)
    processed_seeds = models.PositiveIntegerField(default=0)  # 已拓展的种子数
    current_round = models.PositiveIntegerField(default=0)  # 当前 BFS 轮次（层数）
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
