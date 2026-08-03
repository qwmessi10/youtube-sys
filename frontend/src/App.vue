<script setup>
import { onMounted, ref } from "vue";
import axios from "axios";
import { ElMessage } from "element-plus";

const activeMenu = ref("keywords");
const loading = ref(false);
const settings = ref([]);
const runs = ref([]);
const results = ref([]);
const options = ref({ countries: [], languages: [] });
const selectedRun = ref();
const selectedRunLabel = ref("");
const runSearch = ref("");
const resultSearch = ref("");
const runPage = ref(1);
const resultPage = ref(1);
const runTotal = ref(0);
const resultTotal = ref(0);
const form = ref({ root_keyword: "", country: "US", language: "en", max_keywords: 15 });

const scoreLabels = {
  title_mismatch: "标题未完全匹配",
  low_subscriber: "低订阅频道",
  low_view: "低播放视频",
  published_over_24h: "发布超过 24 小时",
};

// 关键词结果状态 → 中文文案 + Element Plus 标签颜色
const statusMeta = {
  pending: { label: "待验证", type: "info" },
  rule_scored: { label: "规则打分完成", type: "success" },
  serpapi_error: { label: "SerpApi 查询失败", type: "danger" },
  needs_review: { label: "数据不全，需人工复核", type: "warning" },
};

function statusLabel(status) {
  return statusMeta[status]?.label || status;
}

function statusType(status) {
  return statusMeta[status]?.type || "info";
}

function number(value) {
  return value === null || value === undefined ? "未获取" : new Intl.NumberFormat("zh-CN").format(value);
}

function datetime(value) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "未获取";
}

async function loadRuns(page = runPage.value) {
  runPage.value = page;
  const { data } = await axios.get("/api/keyword-runs/", { params: { page, search: runSearch.value } });
  runs.value = data.results;
  runTotal.value = data.count;
}

async function loadResults(page = resultPage.value) {
  resultPage.value = page;
  const params = { page, search: resultSearch.value };
  if (selectedRun.value) params.run = selectedRun.value;
  const { data } = await axios.get("/api/keyword-results/", { params });
  results.value = data.results;
  resultTotal.value = data.count;
}

async function loadSettings() {
  const { data } = await axios.get("/api/settings/");
  settings.value = data;
}

async function loadOptions() {
  const { data } = await axios.get("/api/keyword-options/");
  options.value = data;
}

async function createRun() {
  if (!form.value.root_keyword.trim()) return ElMessage.warning("请输入基础关键词");
  loading.value = true;
  try {
    await axios.post("/api/keyword-runs/", form.value);
    ElMessage.success("任务已进入处理队列");
    form.value.root_keyword = "";
    await loadRuns(1);
  } catch (error) {
    ElMessage.error(error.response?.data ? "创建任务失败，请检查输入" : "无法连接后端");
  } finally {
    loading.value = false;
  }
}

async function saveSettings() {
  try {
    await Promise.all(settings.value.map((item) => axios.put(`/api/settings/${item.id}/`, item)));
    ElMessage.success("全局设置已保存");
  } catch {
    ElMessage.error("保存设置失败");
  }
}

async function controlRun(run, action) {
  const labels = { pause: "暂停", restart: "重启", stop: "停止" };
  try {
    await axios.post(`/api/keyword-runs/${run.id}/${action}/`);
    ElMessage.success(`任务已${labels[action]}`);
    await Promise.all([loadRuns(), loadResults()]);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "任务状态更新失败");
  }
}

function selectRun(run) {
  selectedRun.value = run.id;
  selectedRunLabel.value = run.root_keyword;
  loadResults(1);
}

function clearRunFilter() {
  selectedRun.value = undefined;
  selectedRunLabel.value = "";
  loadResults(1);
}

function exportCsv() {
  const params = new URLSearchParams();
  if (selectedRun.value) params.set("run", selectedRun.value);
  if (resultSearch.value) params.set("search", resultSearch.value);
  const query = params.toString();
  window.open(`/api/keyword-results/export/${query ? `?${query}` : ""}`, "_blank");
}

onMounted(async () => {
  await Promise.all([loadRuns(), loadResults(), loadSettings(), loadOptions()]);
});
</script>

<template>
  <el-container class="shell">
    <el-aside width="236px" class="sidebar">
      <div class="brand"><span>YT</span><div>YouTube Sys<small>内容自动化后台</small></div></div>
      <el-menu :default-active="activeMenu" @select="activeMenu = $event" class="menu">
        <el-menu-item index="keywords">关键词系统</el-menu-item>
        <el-menu-item index="settings">全局设置</el-menu-item>
        <el-menu-item disabled index="data">数据抓取系统（后续）</el-menu-item>
        <el-menu-item disabled index="content">内容生成系统（后续）</el-menu-item>
        <el-menu-item disabled index="adspower">AdsPower 自动化（隔离）</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header"><strong>{{ activeMenu === 'settings' ? '全局设置' : '关键词系统' }}</strong><span>第一期：关键词发现与规则评分</span></el-header>
      <el-main>
        <template v-if="activeMenu === 'keywords'">
          <el-card class="create-card" shadow="never">
            <template #header><strong>创建关键词任务</strong></template>
            <el-form :inline="true" @submit.prevent="createRun">
              <el-form-item label="基础关键词"><el-input v-model="form.root_keyword" placeholder="例如：youtube automation" /></el-form-item>
              <el-form-item label="目标国家"><el-select v-model="form.country" filterable><el-option v-for="item in options.countries" :key="item.value" :label="`${item.label} (${item.value})`" :value="item.value" /></el-select></el-form-item>
              <el-form-item label="结果语言"><el-select v-model="form.language" filterable><el-option v-for="item in options.languages" :key="item.value" :label="`${item.label} (${item.value})`" :value="item.value" /></el-select></el-form-item>
              <el-form-item label="最大长尾数"><el-input-number v-model="form.max_keywords" :min="1" :max="100" /></el-form-item>
              <el-button type="primary" :loading="loading" @click="createRun">开始分析</el-button>
            </el-form>
          </el-card>

          <el-card shadow="never" class="table-card">
            <template #header><div class="card-title"><strong>任务记录</strong><div><el-input v-model="runSearch" clearable placeholder="搜索基础关键词" class="search-input" @keyup.enter="loadRuns(1)" @clear="loadRuns(1)" /><el-button @click="loadRuns(1)">搜索</el-button></div></div></template>
            <el-table :data="runs" size="small" empty-text="暂无任务" @row-click="(row) => selectRun(row)">
              <el-table-column prop="root_keyword" label="基础关键词" min-width="180" />
              <el-table-column prop="country" label="国家" width="80" />
              <el-table-column prop="language" label="语言" width="90" />
              <el-table-column prop="status" label="状态" width="110" />
              <el-table-column prop="result_count" label="已处理" width="90" />
              <el-table-column label="更新时间" min-width="170"><template #default="{ row }">{{ datetime(row.updated_at) }}</template></el-table-column>
              <el-table-column label="控制" width="210"><template #default="{ row }">
                <el-button size="small" :disabled="!['pending', 'running'].includes(row.status)" @click.stop="controlRun(row, 'pause')">暂停</el-button>
                <el-button size="small" type="primary" plain :disabled="!['paused', 'stopped', 'failed'].includes(row.status)" @click.stop="controlRun(row, 'restart')">重启</el-button>
                <el-button size="small" type="danger" plain :disabled="!['pending', 'running', 'paused'].includes(row.status)" @click.stop="controlRun(row, 'stop')">停止</el-button>
              </template></el-table-column>
            </el-table>
            <el-pagination v-model:current-page="runPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="runTotal" @current-change="loadRuns" />
          </el-card>

          <el-card shadow="never" class="table-card">
            <template #header><div class="card-title"><div><strong>关键词评选结果</strong><el-tag v-if="selectedRun" class="run-filter-tag" closable type="primary" @close="clearRunFilter"> 当前任务：{{ selectedRunLabel }}</el-tag></div><div><el-input v-model="resultSearch" clearable placeholder="搜索基础词或长尾词" class="search-input" @keyup.enter="loadResults(1)" @clear="loadResults(1)" /><el-button @click="loadResults(1)">搜索</el-button><el-button @click="loadResults">刷新</el-button><el-button type="success" plain @click="exportCsv">导出完整 CSV</el-button></div></div></template>
            <el-alert title="点击左侧展开箭头可查看该关键词前 5 个视频的完整评选依据；评分越高，代表潜在内容空位越大。" type="info" :closable="false" class="process-note" />
            <el-table :data="results" stripe v-loading="loading" empty-text="创建关键词任务后在此查看结果">
              <el-table-column type="expand" width="48"><template #default="{ row }"><div class="video-details"><div class="score-summary"><strong>规则评分过程（总分 {{ row.rule_score ?? 0 }}）</strong><span v-for="(score, key) in row.score_breakdown" :key="key" class="score">{{ scoreLabels[key] || key }}：{{ score }} 分</span></div><el-table :data="row.top5_video_data" border size="small" empty-text="没有可展示的视频数据"><el-table-column type="index" label="#" width="48" /><el-table-column label="视频标题" min-width="260"><template #default="{ row: video }"><a v-if="video.video_url" :href="video.video_url" target="_blank" rel="noreferrer">{{ video.title }}</a><span v-else>{{ video.title }}</span></template></el-table-column><el-table-column prop="channel_name" label="频道" min-width="150" /><el-table-column label="订阅数" width="100"><template #default="{ row: video }">{{ number(video.subscriber_count) }}</template></el-table-column><el-table-column label="播放" width="100"><template #default="{ row: video }">{{ number(video.view_count) }}</template></el-table-column><el-table-column label="点赞" width="100"><template #default="{ row: video }">{{ number(video.like_count) }}</template></el-table-column><el-table-column label="评论" width="100"><template #default="{ row: video }">{{ number(video.comment_count) }}</template></el-table-column><el-table-column label="发布时间" min-width="170"><template #default="{ row: video }">{{ datetime(video.published_at) }}</template></el-table-column></el-table></div></template></el-table-column>
              <el-table-column prop="root_keyword" label="基础词" min-width="135" />
              <el-table-column prop="keyword" label="长尾关键词" min-width="190" />
              <el-table-column prop="rule_score" label="总分" width="78" sortable />
              <el-table-column label="状态" width="150"><template #default="{ row }"><el-tag :type="statusType(row.status)" size="small" effect="light">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
              <el-table-column label="评分过程" min-width="360"><template #default="{ row }"><span v-for="(score, key) in row.score_breakdown" :key="key" class="score">{{ scoreLabels[key] || key }}：{{ score }}</span></template></el-table-column>
              <el-table-column prop="elimination_reason" label="说明" min-width="210" show-overflow-tooltip />
            </el-table>
            <el-pagination v-model:current-page="resultPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="resultTotal" @current-change="loadResults" />
          </el-card>
        </template>
        <el-card v-else-if="activeMenu === 'settings'" shadow="never">
          <template #header><strong>第三方 API 与 AI 接入配置</strong></template>
          <p class="hint">保存后将优先使用这里的值；AI 配置已预留，第一期不会调用 AI。</p>
          <el-form label-position="top" class="settings-form">
            <el-form-item v-for="item in settings" :key="item.id" :label="item.key"><el-input v-model="item.value" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" /><small>{{ item.description }}</small></el-form-item>
            <el-button type="primary" @click="saveSettings">保存设置</el-button>
          </el-form>
        </el-card>
        <el-empty v-else description="该模块将在后续需求确认后开发" />
      </el-main>
    </el-container>
  </el-container>
</template>
