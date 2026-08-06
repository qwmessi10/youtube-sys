<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import axios from "axios";
import { ElMessage } from "element-plus";
import ContentTasks from "./components/ContentTasks.vue";
import ContentAgents from "./components/ContentAgents.vue";

// 当前菜单从 localStorage 恢复，刷新后停留在原页面而不是跳回默认。
const activeMenu = ref(localStorage.getItem("activeMenu") || "tasks");
// 从关键词结果页「送入内容生成」带过来的关键词，传给内容任务组件预填。
const injectedKeywords = ref([]);
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
const form = ref({ root_keyword: "", country: "US", language: "en", max_keywords: 15, scoring_model: "2.0" });
const logDrawer = ref(false);
const logLoading = ref(false);
const logData = ref(null);
const logRun = ref(null);
const agents = ref([]);
const agentLoading = ref(false);
// Suggest 长尾词拓展工具
const seForm = ref({ root_keyword: "", country: "US", language: "en", max_keywords: 5000 });
const seRuns = ref([]);
const seTotal = ref(0);
const sePage = ref(1);
const seLoading = ref(false);
const seDetail = ref(null);        // 当前查看的任务详情（含词列表）
const seDetailLoading = ref(false);
let sePollTimer = null;            // 运行中任务的进度轮询定时器

const menuTitles = {
  tasks: "任务管理", agents: "关键词 Agent 管理", "suggest-expand": "获取 Suggest API 长尾词",
  "content-tasks": "内容生成 - 任务管理", "content-agents": "内容生成 Agent 管理", settings: "全局设置",
};
const menuTitle = computed(() => menuTitles[activeMenu.value] || "关键词系统");

// 把选中的关键词送入内容生成：填充关键词并切到内容任务页。
function sendToContent(item) {
  injectedKeywords.value = [item.keyword];
  activeMenu.value = "content-tasks";
}

// Suggest 拓展任务状态 → 文案 + 标签色
const seStatusMeta = {
  pending: { label: "待处理", type: "info" },
  running: { label: "处理中", type: "warning" },
  completed: { label: "已完成", type: "success" },
  stopped: { label: "已停止", type: "info" },
  failed: { label: "失败", type: "danger" },
};
const seStatusLabel = (s) => seStatusMeta[s]?.label || s;
const seStatusType = (s) => seStatusMeta[s]?.type || "info";

// Agent 按打分模型分组，方便 UI 按模型分区展示
const agentsByModel = computed(() => {
  const groups = {};
  for (const a of agents.value) {
    (groups[a.scoring_model] ||= []).push(a);
  }
  return groups;
});

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
  eliminated: { label: "已淘汰", type: "info" },
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

async function loadAgents() {
  agentLoading.value = true;
  try {
    const { data } = await axios.get("/api/agent-prompts/");
    agents.value = Array.isArray(data) ? data : data.results || [];
  } catch {
    ElMessage.error("加载 Agent 列表失败");
  } finally {
    agentLoading.value = false;
  }
}

async function saveAgent(agent) {
  try {
    await axios.patch(`/api/agent-prompts/${agent.id}/`, {
      prompt: agent.prompt,
      enabled: agent.enabled,
    });
    ElMessage.success(`已保存「${agent.name}」`);
  } catch {
    ElMessage.error("保存 Agent 失败");
  }
}

async function resetAgentPrompt(agent) {
  try {
    const { data } = await axios.get(`/api/agent-prompts/${agent.id}/default_prompt/`);
    if (!data.prompt) return ElMessage.warning("该 Agent 没有系统默认提示词");
    agent.prompt = data.prompt;  // 只填回编辑框，需用户点「保存」才写库
    ElMessage.success("已载入系统默认提示词，确认后请点击保存");
  } catch {
    ElMessage.error("获取默认提示词失败");
  }
}

async function loadSeRuns(page = sePage.value) {
  sePage.value = page;
  const { data } = await axios.get("/api/suggest-expansions/", { params: { page } });
  seRuns.value = data.results;
  seTotal.value = data.count;
  // 有任务在跑就开启轮询，全部结束就停
  if (seRuns.value.some((r) => r.status === "running" || r.status === "pending")) {
    startSePoll();
  } else {
    stopSePoll();
  }
}

async function createSeRun() {
  if (!seForm.value.root_keyword.trim()) return ElMessage.warning("请输入词根");
  seLoading.value = true;
  try {
    await axios.post("/api/suggest-expansions/", seForm.value);
    ElMessage.success("拓展任务已开始，正在遍历 Suggest API");
    await loadSeRuns(1);
  } catch (error) {
    ElMessage.error(error.response?.data ? "创建失败，请检查输入" : "无法连接后端");
  } finally {
    seLoading.value = false;
  }
}

async function stopSeRun(run) {
  try {
    await axios.post(`/api/suggest-expansions/${run.id}/stop/`);
    ElMessage.success("已停止");
    await loadSeRuns();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "停止失败");
  }
}

async function openSeDetail(run) {
  seDetailLoading.value = true;
  seDetail.value = null;
  try {
    const { data } = await axios.get(`/api/suggest-expansions/${run.id}/`);
    seDetail.value = data;
  } catch {
    ElMessage.error("加载结果失败");
  } finally {
    seDetailLoading.value = false;
  }
}

function exportSeCsv(run) {
  window.open(`/api/suggest-expansions/${run.id}/export/`, "_blank");
}

async function refreshSeDetailSilently() {
  if (!seDetail.value) return;
  try {
    const { data } = await axios.get(`/api/suggest-expansions/${seDetail.value.id}/`);
    seDetail.value = data;
  } catch { /* 轮询静默失败，不打扰用户 */ }
}

function startSePoll() {
  if (sePollTimer) return;
  sePollTimer = setInterval(async () => {
    if (activeMenu.value !== "suggest-expand") return;
    await loadSeRuns();
    await refreshSeDetailSilently();  // 同步刷新当前详情词表，看实时增长
  }, 3000);
}

function stopSePoll() {
  if (sePollTimer) { clearInterval(sePollTimer); sePollTimer = null; }
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

// 给当前选中的任务行加高亮 class，让「正在查看哪个任务」一目了然
function runRowClass({ row }) {
  return row.id === selectedRun.value ? "row-selected" : "";
}

async function openLog(run) {
  logRun.value = run;
  logDrawer.value = true;
  logLoading.value = true;
  logData.value = null;
  try {
    const { data } = await axios.get(`/api/keyword-runs/${run.id}/log/`);
    logData.value = data;
  } catch {
    ElMessage.error("加载日志失败");
  } finally {
    logLoading.value = false;
  }
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
  await Promise.all([loadRuns(), loadResults(), loadSettings(), loadOptions(), loadAgents(), loadSeRuns()]);
});

onUnmounted(() => stopSePoll());

// 离开工具页时停止轮询，进入时刷新一次；同时记住当前菜单，刷新后不跳转。
watch(activeMenu, (menu) => {
  localStorage.setItem("activeMenu", menu);
  if (menu === "suggest-expand") loadSeRuns();
  else stopSePoll();
});
</script>

<template>
  <el-container class="shell">
    <el-aside width="236px" class="sidebar">
      <div class="brand"><span>YT</span><div>YouTube Sys<small>内容自动化后台</small></div></div>
      <el-menu
        :default-active="activeMenu"
        @select="activeMenu = $event"
        class="menu"
        :default-openeds="['keywords', 'content', 'tools']"
        background-color="#17212d"
        text-color="#b6c5d4"
        active-text-color="#ffffff"
      >
        <el-sub-menu index="keywords">
          <template #title>关键词系统</template>
          <el-menu-item index="tasks">任务管理</el-menu-item>
          <el-menu-item index="agents">关键词 Agent 管理</el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="content">
          <template #title>内容生成系统</template>
          <el-menu-item index="content-tasks">任务管理</el-menu-item>
          <el-menu-item index="content-agents">内容生成 Agent 管理</el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="tools">
          <template #title>实用工具</template>
          <el-menu-item index="suggest-expand">获取 Suggest API 长尾词</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="settings">全局设置</el-menu-item>
        <el-menu-item disabled index="data">数据抓取系统（后续）</el-menu-item>
        <el-menu-item disabled index="adspower">AdsPower 自动化（隔离）</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header"><strong>{{ menuTitle }}</strong><span>第一期：关键词发现与规则评分</span></el-header>
      <el-main>
        <template v-if="activeMenu === 'tasks'">
          <el-card class="create-card" shadow="never">
            <template #header><strong>创建关键词任务</strong></template>
            <el-form :inline="true" @submit.prevent="createRun">
              <el-form-item label="基础关键词"><el-input v-model="form.root_keyword" placeholder="例如：youtube automation" /></el-form-item>
              <el-form-item label="目标国家"><el-select v-model="form.country" filterable><el-option v-for="item in options.countries" :key="item.value" :label="`${item.label} (${item.value})`" :value="item.value" /></el-select></el-form-item>
              <el-form-item label="结果语言"><el-select v-model="form.language" filterable><el-option v-for="item in options.languages" :key="item.value" :label="`${item.label} (${item.value})`" :value="item.value" /></el-select></el-form-item>
              <el-form-item label="最大长尾数"><el-input-number v-model="form.max_keywords" :min="1" :max="100" /></el-form-item>
              <el-form-item label="打分模型"><el-select v-model="form.scoring_model" style="width: 260px"><el-option label="2.0（AI BC意图筛选 + 全量打分）" value="2.0" /><el-option label="1.0（前 5 视频规则打分）" value="1.0" /></el-select></el-form-item>
              <el-button type="primary" :loading="loading" @click="createRun">开始分析</el-button>
            </el-form>
          </el-card>

          <el-card shadow="never" class="table-card">
            <template #header><div class="card-title"><strong>任务记录</strong><div><el-input v-model="runSearch" clearable placeholder="搜索基础关键词" class="search-input" @keyup.enter="loadRuns(1)" @clear="loadRuns(1)" /><el-button @click="loadRuns(1)">搜索</el-button></div></div></template>
            <el-table :data="runs" size="small" empty-text="暂无任务" :row-class-name="runRowClass" class="clickable-table" @row-click="(row) => selectRun(row)">
              <el-table-column prop="root_keyword" label="基础关键词" min-width="180" />
              <el-table-column prop="country" label="国家" width="80" />
              <el-table-column prop="language" label="语言" width="90" />
              <el-table-column label="模型" width="70"><template #default="{ row }"><el-tag size="small" :type="row.scoring_model === '2.0' ? 'success' : 'info'" effect="plain">{{ row.scoring_model }}</el-tag></template></el-table-column>
              <el-table-column prop="status" label="状态" width="110" />
              <el-table-column prop="result_count" label="已处理" width="90" />
              <el-table-column label="更新时间" min-width="170"><template #default="{ row }">{{ datetime(row.updated_at) }}</template></el-table-column>
              <el-table-column label="控制" width="280"><template #default="{ row }">
                <el-button size="small" :disabled="!['pending', 'running'].includes(row.status)" @click.stop="controlRun(row, 'pause')">暂停</el-button>
                <el-button size="small" type="primary" plain :disabled="!['paused', 'stopped', 'failed'].includes(row.status)" @click.stop="controlRun(row, 'restart')">重启</el-button>
                <el-button size="small" type="danger" plain :disabled="!['pending', 'running', 'paused'].includes(row.status)" @click.stop="controlRun(row, 'stop')">停止</el-button>
                <el-button size="small" type="info" plain @click.stop="openLog(row)">日志</el-button>
              </template></el-table-column>
            </el-table>
            <el-pagination v-model:current-page="runPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="runTotal" @current-change="loadRuns" />
          </el-card>

          <el-card shadow="never" class="table-card">
            <template #header><div class="card-title"><div><strong>关键词评选结果</strong><el-tag v-if="selectedRun" class="run-filter-tag" closable type="primary" @close="clearRunFilter"> 当前任务：{{ selectedRunLabel }}</el-tag></div><div><el-input v-model="resultSearch" clearable placeholder="搜索基础词或长尾词" class="search-input" @keyup.enter="loadResults(1)" @clear="loadResults(1)" /><el-button @click="loadResults(1)">搜索</el-button><el-button @click="loadResults">刷新</el-button><el-button type="success" plain @click="exportCsv">导出完整 CSV</el-button></div></div></template>
            <el-alert title="点击左侧展开箭头可查看该关键词前 5 个视频的完整评选依据；评分越高，代表潜在内容空位越大。" type="info" :closable="false" class="process-note" />
            <el-table :data="results" stripe v-loading="loading" empty-text="创建关键词任务后在此查看结果">
              <el-table-column type="expand" width="48"><template #default="{ row }"><div class="video-details"><div v-if="row.agent_result && row.agent_result.intent" class="agent-summary"><strong>AI 博彩意图判定</strong><el-tag size="small" type="warning" effect="light">意向：{{ row.agent_result.intent }}</el-tag><span class="agent-reason">{{ row.agent_result.reason }}</span></div><div class="score-summary"><strong>规则评分过程（总分 {{ row.rule_score ?? 0 }}）</strong><span v-for="(score, key) in row.score_breakdown" :key="key" class="score">{{ scoreLabels[key] || key }}：{{ score }} 分</span></div><el-table :data="row.top5_video_data" border size="small" empty-text="没有可展示的视频数据"><el-table-column type="index" label="#" width="48" /><el-table-column label="视频标题" min-width="260"><template #default="{ row: video }"><a v-if="video.video_url" :href="video.video_url" target="_blank" rel="noreferrer">{{ video.title }}</a><span v-else>{{ video.title }}</span></template></el-table-column><el-table-column prop="channel_name" label="频道" min-width="150" /><el-table-column label="订阅数" width="100"><template #default="{ row: video }">{{ number(video.subscriber_count) }}</template></el-table-column><el-table-column label="播放" width="100"><template #default="{ row: video }">{{ number(video.view_count) }}</template></el-table-column><el-table-column label="点赞" width="100"><template #default="{ row: video }">{{ number(video.like_count) }}</template></el-table-column><el-table-column label="评论" width="100"><template #default="{ row: video }">{{ number(video.comment_count) }}</template></el-table-column><el-table-column label="发布时间" min-width="170"><template #default="{ row: video }">{{ datetime(video.published_at) }}</template></el-table-column></el-table></div></template></el-table-column>
              <el-table-column prop="root_keyword" label="基础词" min-width="135" />
              <el-table-column prop="keyword" label="长尾关键词" min-width="190" />
              <el-table-column prop="rule_score" label="总分" width="78" sortable />
              <el-table-column label="状态" width="150"><template #default="{ row }"><el-tag :type="statusType(row.status)" size="small" effect="light">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
              <el-table-column label="评分过程" min-width="360"><template #default="{ row }"><span v-for="(score, key) in row.score_breakdown" :key="key" class="score">{{ scoreLabels[key] || key }}：{{ score }}</span></template></el-table-column>
              <el-table-column prop="elimination_reason" label="说明" min-width="180" show-overflow-tooltip />
              <el-table-column label="操作" width="130"><template #default="{ row }"><el-button size="small" type="primary" plain @click="sendToContent(row)">送入内容生成</el-button></template></el-table-column>
            </el-table>
            <el-pagination v-model:current-page="resultPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="resultTotal" @current-change="loadResults" />
          </el-card>
        </template>
        <template v-else-if="activeMenu === 'agents'">
          <el-alert
            title="关键词 Agent 管理"
            description="每个 Agent 的名称和用途是固定的，这里只用来编辑它的提示词。若发现意图识别不准，可在提示词中补充「哪些词属于博彩意向」的说明，让判断更贴合你的需求。"
            type="success"
            :closable="false"
            class="agent-intro"
            show-icon
          />
          <div v-loading="agentLoading">
            <div v-for="(list, model) in agentsByModel" :key="model" class="agent-model-block">
              <div class="agent-model-head">
                <el-tag :type="model === '2.0' ? 'success' : 'info'" size="large" effect="dark">打分模型 {{ model }}</el-tag>
                <span class="agent-model-sub">{{ list.length }} 个 Agent</span>
              </div>
              <el-card v-for="agent in list" :key="agent.id" shadow="never" class="agent-card">
                <template #header>
                  <div class="agent-card-head">
                    <div class="agent-card-meta">
                      <el-tag size="small" type="warning" effect="plain">{{ agent.agent_type_label }}</el-tag>
                      <strong class="agent-card-name">{{ agent.name }}</strong>
                      <span class="agent-card-desc">{{ agent.description }}</span>
                    </div>
                    <el-switch v-model="agent.enabled" active-text="启用" inactive-text="停用" inline-prompt />
                  </div>
                </template>
                <el-form label-position="top">
                  <el-form-item label="提示词（Prompt）">
                    <el-input v-model="agent.prompt" type="textarea" :autosize="{ minRows: 10, maxRows: 30 }" placeholder="留空则使用系统内置默认提示词" />
                    <small class="agent-hint">占位符：[input] 自动替换为待判定的关键词列表，[output] 自动替换为固定的 JSON 输出格式说明（这两个请勿删除）。想让识别更准，可在「# 目标」附近补充具体规则，例如列出哪些词应判为高意向。</small>
                  </el-form-item>
                  <el-button type="primary" @click="saveAgent(agent)">保存提示词</el-button>
                  <el-button plain @click="resetAgentPrompt(agent)">恢复系统默认</el-button>
                </el-form>
              </el-card>
            </div>
            <el-empty v-if="!agentLoading && agents.length === 0" description="暂无 Agent 配置" />
          </div>
        </template>
        <template v-else-if="activeMenu === 'suggest-expand'">
          <el-alert
            title="获取 Suggest API 长尾词"
            description="输入词根后，工具会直接用词根查询 Suggest API 拿到长尾词，再把每个新词当作词根继续递归查询，直到再没有新词返回为止（默认最多 5000 个）。适合一次性挖掘某个主题下的全部真实搜索词。"
            type="success"
            :closable="false"
            class="agent-intro"
            show-icon
          />
          <el-card class="create-card" shadow="never">
            <template #header><strong>新建拓展任务</strong></template>
            <el-form :inline="true" @submit.prevent="createSeRun">
              <el-form-item label="词根"><el-input v-model="seForm.root_keyword" placeholder="例如：bitcoin" /></el-form-item>
              <el-form-item label="目标国家"><el-select v-model="seForm.country" filterable><el-option v-for="item in options.countries" :key="item.value" :label="`${item.label} (${item.value})`" :value="item.value" /></el-select></el-form-item>
              <el-form-item label="结果语言"><el-select v-model="seForm.language" filterable><el-option v-for="item in options.languages" :key="item.value" :label="`${item.label} (${item.value})`" :value="item.value" /></el-select></el-form-item>
              <el-form-item label="最大词数上限"><el-input-number v-model="seForm.max_keywords" :min="1" :max="20000" :step="500" /></el-form-item>
              <el-button type="primary" :loading="seLoading" @click="createSeRun">开始遍历</el-button>
            </el-form>
          </el-card>

          <el-card shadow="never" class="table-card">
            <template #header><strong>拓展任务列表</strong></template>
            <el-table :data="seRuns" size="small" empty-text="暂无任务">
              <el-table-column prop="root_keyword" label="词根" min-width="150" />
              <el-table-column prop="country" label="国家" width="70" />
              <el-table-column prop="language" label="语言" width="80" />
              <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag size="small" :type="seStatusType(row.status)" effect="light">{{ seStatusLabel(row.status) }}</el-tag></template></el-table-column>
              <el-table-column label="已拓展词数" width="110"><template #default="{ row }">{{ number(row.keyword_count) }}</template></el-table-column>
              <el-table-column label="已处理种子" width="110"><template #default="{ row }">{{ number(row.processed_seeds) }}</template></el-table-column>
              <el-table-column label="轮次" width="70"><template #default="{ row }">{{ row.current_round }}</template></el-table-column>
              <el-table-column label="更新时间" min-width="160"><template #default="{ row }">{{ datetime(row.updated_at) }}</template></el-table-column>
              <el-table-column label="操作" width="230"><template #default="{ row }">
                <el-button size="small" type="primary" plain @click="openSeDetail(row)">查看词</el-button>
                <el-button size="small" type="danger" plain :disabled="!['pending','running'].includes(row.status)" @click="stopSeRun(row)">停止</el-button>
                <el-button size="small" :disabled="!row.keyword_count" @click="exportSeCsv(row)">导出</el-button>
              </template></el-table-column>
            </el-table>
            <el-pagination v-model:current-page="sePage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="seTotal" @current-change="loadSeRuns" />
          </el-card>

          <el-card v-if="seDetail" shadow="never" class="table-card" v-loading="seDetailLoading">
            <template #header>
              <div class="card-title">
                <strong>「{{ seDetail.root_keyword }}」拓展结果（{{ seDetail.keyword_count }} 词）</strong>
                <el-button size="small" @click="seDetail = null">收起</el-button>
              </div>
            </template>
            <el-alert v-if="seDetail.status === 'running'" title="任务进行中，词表每 3 秒自动刷新…" type="info" :closable="false" class="process-note" />
            <div class="se-keywords">
              <el-tag v-for="kw in seDetail.keywords" :key="kw" size="small" class="log-tag" type="info">{{ kw }}</el-tag>
            </div>
            <el-empty v-if="!seDetail.keywords || seDetail.keywords.length === 0" description="暂无长尾词" :image-size="60" />
          </el-card>
        </template>
        <ContentTasks v-else-if="activeMenu === 'content-tasks'" :options="options" :injected-keywords="injectedKeywords" />
        <ContentAgents v-else-if="activeMenu === 'content-agents'" />
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

    <el-drawer v-model="logDrawer" title="工作日志" size="640px" :destroy-on-close="true">
      <div v-loading="logLoading">
        <template v-if="logData">
          <div class="log-head">
            <el-tag>{{ logData.scoring_model === '2.0' ? '打分模型 2.0' : '打分模型 1.0' }}</el-tag>
            <span class="log-root">根词：{{ logData.root_keyword }}</span>
          </div>

          <el-divider content-position="left">Suggest 拓展词</el-divider>
          <template v-if="logData.run_log && logData.run_log.suggest">
            <p class="log-line">保留拓展词（{{ logData.run_log.suggest.count }}）：</p>
            <div class="log-tags">
              <el-tag
                v-for="kw in (logData.run_log.suggest.all_keywords || [])"
                :key="kw"
                size="small"
                class="log-tag"
                type="info"
              >{{ kw }}</el-tag>
            </div>
            <template v-if="(logData.run_log.suggest.dropped_by_language || []).length">
              <p class="log-line">语言过滤剔除（目标语言 {{ logData.run_log.suggest.language }}，共 {{ logData.run_log.suggest.dropped_count }} 个非目标语言词）：</p>
              <div class="log-tags">
                <el-tag
                  v-for="kw in logData.run_log.suggest.dropped_by_language"
                  :key="kw"
                  size="small"
                  class="log-tag"
                  type="danger"
                  effect="plain"
                >{{ kw }}</el-tag>
              </div>
            </template>
          </template>
          <el-empty v-else description="无 Suggest 日志" :image-size="60" />

          <template v-if="logData.run_log && logData.run_log.agent">
            <el-divider content-position="left">Agent 博彩意图判定</el-divider>
            <p class="log-line">模型：{{ logData.run_log.agent.model }}</p>
            <p class="log-line">命中高意向词（{{ (logData.run_log.agent.hit_keywords || []).length }}）：</p>
            <div class="log-tags">
              <el-tag
                v-for="kw in (logData.run_log.agent.hit_keywords || [])"
                :key="kw"
                size="small"
                class="log-tag"
                type="success"
              >{{ kw }}</el-tag>
            </div>
            <p class="log-line">淘汰词（{{ (logData.run_log.agent.eliminated_keywords || []).length }}）：</p>
            <div class="log-tags">
              <el-tag
                v-for="kw in (logData.run_log.agent.eliminated_keywords || [])"
                :key="kw"
                size="small"
                class="log-tag"
                type="danger"
              >{{ kw }}</el-tag>
            </div>
            <el-collapse class="log-collapse">
              <el-collapse-item title="Agent 输入 Prompt" name="prompt">
                <pre class="log-pre">{{ logData.run_log.agent.prompt }}</pre>
              </el-collapse-item>
              <el-collapse-item title="Agent 原始输出" name="raw">
                <pre class="log-pre">{{ logData.run_log.agent.raw_output }}</pre>
              </el-collapse-item>
              <el-collapse-item title="解析后结构" name="parsed">
                <pre class="log-pre">{{ JSON.stringify(logData.run_log.agent.parsed, null, 2) }}</pre>
              </el-collapse-item>
            </el-collapse>
          </template>
        </template>
        <el-empty v-else-if="!logLoading" description="暂无日志数据" />
      </div>
    </el-drawer>
  </el-container>
</template>
