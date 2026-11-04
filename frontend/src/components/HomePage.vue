<script setup>
// 首页总览驾驶舱：纯查看、不跳转、不做操作。进入时拉一次聚合接口渲染。
import { onMounted, ref } from "vue";
import axios from "axios";

const summary = ref(null);
const loading = ref(false);

const statusMeta = {
  pending: { label: "进行中", type: "warning" },
  running: { label: "进行中", type: "warning" },
  completed: { label: "已完成", type: "success" },
  failed: { label: "失败", type: "danger" },
  awaiting_hook: { label: "等上传", type: "info" },
  paused: { label: "已暂停", type: "info" },
  stopped: { label: "已停止", type: "info" },
  queued: { label: "排队中", type: "info" },
  launching: { label: "启动中", type: "info" },
  uploading: { label: "上传中", type: "warning" },
  draft_saved: { label: "待核对", type: "info" },
  publishing: { label: "发布中", type: "warning" },
};
const statusLabel = (s) => statusMeta[s]?.label || s;
const statusType = (s) => statusMeta[s]?.type || "info";

function number(value) {
  return value === null || value === undefined ? "—" : new Intl.NumberFormat("zh-CN").format(value);
}

function datetime(value) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}

const systemMeta = {
  keywords: { label: "关键词系统", tag: "primary" },
  flow3: { label: "内容生成", tag: "success" },
  uploader: { label: "AdsPower", tag: "warning" },
  smm: { label: "SMM 面板", tag: "danger" },
  suggest: { label: "实用工具", tag: "info" },
};

async function loadSummary() {
  loading.value = true;
  try {
    const { data } = await axios.get("/api/dashboard/summary/");
    summary.value = data;
  } catch {
    summary.value = null;
  } finally {
    loading.value = false;
  }
}

onMounted(loadSummary);
</script>

<template>
  <div v-loading="loading">
    <el-alert
      title="总览驾驶舱"
      description="这里汇总各系统的关键指标与最近动态，仅供查看；具体操作请进入对应功能模块。"
      type="success"
      :closable="false"
      class="agent-intro"
      show-icon
    />

    <!-- 顶部指标卡（4 个） -->
    <div class="metric-grid">
      <el-card shadow="never" class="metric-card">
        <div class="metric-label">SMM 余额（剩余可用）</div>
        <div class="metric-value">₹{{ number(summary?.metrics.smm_remaining) }}</div>
      </el-card>
      <el-card shadow="never" class="metric-card">
        <div class="metric-label">今日出片</div>
        <div class="metric-value">{{ number(summary?.metrics.today_videos) }}</div>
      </el-card>
      <el-card shadow="never" class="metric-card">
        <div class="metric-label">待核对草稿</div>
        <div class="metric-value">{{ number(summary?.metrics.draft_count) }}</div>
      </el-card>
      <el-card shadow="never" class="metric-card">
        <div class="metric-label">进行中任务</div>
        <div class="metric-value">{{ number(summary?.metrics.running_count) }}</div>
      </el-card>
    </div>

    <!-- 系统概况（5 张卡） -->
    <div class="system-grid">
      <el-card v-for="sys in (summary?.systems || [])" :key="sys.key" shadow="never" class="system-card">
        <template #header>
          <div class="system-card-head">
            <el-tag size="small" :type="systemMeta[sys.key]?.tag || 'primary'" effect="dark">{{ sys.name }}</el-tag>
          </div>
        </template>
        <div class="system-stats">
          <div v-if="sys.total !== undefined" class="stat-item"><span class="stat-label">任务总数</span><span class="stat-value">{{ number(sys.total) }}</span></div>
          <div v-if="sys.running !== undefined" class="stat-item"><span class="stat-label">进行中</span><span class="stat-value">{{ number(sys.running) }}</span></div>
          <div v-if="sys.awaiting_hook !== undefined" class="stat-item"><span class="stat-label">等上传 Hook</span><span class="stat-value">{{ number(sys.awaiting_hook) }}</span></div>
          <div v-if="sys.draft !== undefined" class="stat-item"><span class="stat-label">待核对草稿</span><span class="stat-value">{{ number(sys.draft) }}</span></div>
          <div v-if="sys.accounts !== undefined" class="stat-item"><span class="stat-label">账号数</span><span class="stat-value">{{ number(sys.accounts) }}</span></div>
          <div v-if="sys.tasks_running !== undefined" class="stat-item"><span class="stat-label">刷量进行中</span><span class="stat-value">{{ number(sys.tasks_running) }}</span></div>
          <div v-if="sys.polls_running !== undefined" class="stat-item"><span class="stat-label">轮询运行中</span><span class="stat-value">{{ number(sys.polls_running) }}</span></div>
          <div v-if="sys.completed !== undefined" class="stat-item"><span class="stat-label">已完成</span><span class="stat-value">{{ number(sys.completed) }}</span></div>
          <div v-if="sys.failed !== undefined" class="stat-item"><span class="stat-label">失败</span><span class="stat-value">{{ number(sys.failed) }}</span></div>
        </div>
      </el-card>
    </div>

    <!-- 最近动态（时间线，10 条） -->
    <el-card shadow="never" class="table-card">
      <template #header><strong>最近动态（10 条）</strong></template>
      <el-timeline v-if="summary?.recent?.length">
        <el-timeline-item
          v-for="(item, idx) in summary.recent"
          :key="idx"
          :timestamp="datetime(item.time)"
          placement="top"
        >
          <div class="recent-item">
            <el-tag size="small" :type="systemMeta[item.system]?.tag || 'primary'" effect="plain">{{ systemMeta[item.system]?.label || item.system }}</el-tag>
            <span class="recent-type">{{ item.type }}</span>
            <span class="recent-title">{{ item.title }}</span>
            <el-tag size="small" :type="statusType(item.status)" effect="light">{{ statusLabel(item.status) }}</el-tag>
          </div>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="暂无动态" :image-size="80" />
    </el-card>
  </div>
</template>

<style scoped>
/* —— 顶部指标卡（4 个）—— */
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
.metric-card { text-align: center; }
.metric-card :deep(.el-card__body) { padding: 26px 16px; }
.metric-label { color: #718096; font-size: 13px; margin-bottom: 10px; }
.metric-value { font-size: 30px; font-weight: 700; color: #18202a; line-height: 1.1; }

/* —— 系统概况卡（5 张）—— */
.system-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin-bottom: 20px; }
.system-card { border: 1px solid #ebeef5; }
.system-card-head { display: flex; align-items: center; }
.system-stats { display: flex; flex-direction: column; gap: 10px; }
.stat-item { display: flex; align-items: center; justify-content: space-between; }
.stat-label { color: #718096; font-size: 13px; }
.stat-value { color: #18202a; font-size: 16px; font-weight: 600; }

/* —— 最近动态 —— */
.recent-item { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.recent-type { color: #52606d; font-size: 13px; }
.recent-title { color: #18202a; font-size: 14px; font-weight: 500; }

/* 窄屏自适应：指标卡和系统卡自动换行 */
@media (max-width: 1400px) {
  .system-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 1100px) {
  .metric-grid { grid-template-columns: repeat(2, 1fr); }
  .system-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
