<script setup>
// 内容生成-任务管理：创建任务、任务列表（暂停/停止/重启）、结果记录
//（元数据 + 封面 + 分镜脚本 + 上传分镜视频 + 合并 + 成品打包下载）。
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import axios from "axios";
import { ElMessage } from "element-plus";

// 父组件（App.vue）传入国家/语言选项，以及从关键词结果页「送入内容生成」带过来的关键词。
const props = defineProps({
  options: { type: Object, default: () => ({ countries: [], languages: [] }) },
  injectedKeywords: { type: Array, default: () => [] },
});

const form = ref({
  name: "", flow: "flow2", country: "US", language: "en",
  shot_count: 2, shot_duration: 8, keywordsText: "",
  promo_code: "", tts_provider: "edge",   // 流程一专用
});
const creating = ref(false);
const runs = ref([]);
const runTotal = ref(0);
const runPage = ref(1);
const runSearch = ref("");
const loading = ref(false);

const items = ref([]);
const itemTotal = ref(0);
const itemPage = ref(1);
const itemSearch = ref("");
const selectedRun = ref();
const selectedRunLabel = ref("");
let pollTimer = null;

// 生成日志抽屉
const logDrawer = ref(false);
const logItem = ref(null);

const statusMeta = {
  pending: { label: "待处理", type: "info" },
  running: { label: "处理中", type: "warning" },
  paused: { label: "已暂停", type: "info" },
  stopped: { label: "已停止", type: "info" },
  completed: { label: "已完成", type: "success" },
  failed: { label: "失败", type: "danger" },
};
const itemStatusMeta = {
  pending: { label: "待生成", type: "info" },
  generating: { label: "AI 生成中", type: "warning" },
  generated: { label: "待上传视频", type: "primary" },
  merging: { label: "合并中", type: "warning" },
  merged: { label: "已合并成品", type: "success" },
  rendering: { label: "渲染中", type: "warning" },
  rendered: { label: "已渲染成品", type: "success" },
  failed: { label: "生成失败", type: "danger" },
};
const statusLabel = (s) => statusMeta[s]?.label || s;
const statusType = (s) => statusMeta[s]?.type || "info";
const itemStatusLabel = (s) => itemStatusMeta[s]?.label || s;
const itemStatusType = (s) => itemStatusMeta[s]?.type || "info";

function datetime(value) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "";
}

// 关键词文本框拆成数组（支持换行/逗号分隔）
const parsedKeywords = computed(() =>
  form.value.keywordsText.split(/[\n,，]/).map((s) => s.trim()).filter(Boolean),
);

async function loadRuns(page = runPage.value) {
  runPage.value = page;
  const { data } = await axios.get("/api/content-runs/", { params: { page, search: runSearch.value } });
  runs.value = data.results;
  runTotal.value = data.count;
  if (runs.value.some((r) => ["running", "pending"].includes(r.status))) startPoll();
  else stopPoll();
}

async function loadItems(page = itemPage.value) {
  itemPage.value = page;
  const params = { page, search: itemSearch.value };
  if (selectedRun.value) params.run = selectedRun.value;
  const { data } = await axios.get("/api/content-items/", { params });
  items.value = data.results;
  itemTotal.value = data.count;
}

const isFlow1 = computed(() => form.value.flow === "flow1");

async function createRun() {
  const keywords = parsedKeywords.value;
  if (keywords.length === 0) return ElMessage.warning("请至少输入一个关键词");
  // 流程一（全自动）必须填优惠码，渲染时注入视频模板。
  if (isFlow1.value && !form.value.promo_code.trim()) {
    return ElMessage.warning("流程一（全自动）需填写优惠码");
  }
  creating.value = true;
  try {
    const payload = {
      name: form.value.name,
      flow: form.value.flow,
      country: form.value.country,
      language: form.value.language,
      shot_count: form.value.shot_count,
      shot_duration: form.value.shot_duration,
      keywords,
    };
    // 流程一附带优惠码与 TTS 引擎
    if (isFlow1.value) {
      payload.promo_code = form.value.promo_code.trim();
      payload.tts_provider = form.value.tts_provider;
    }
    await axios.post("/api/content-runs/", payload);
    const tip = isFlow1.value ? "，将自动完成配音与视频渲染" : "";
    ElMessage.success(`任务已创建，正在为 ${keywords.length} 个关键词生成内容${tip}`);
    form.value.keywordsText = "";
    form.value.name = "";
    await loadRuns(1);
  } catch (error) {
    const data = error.response?.data;
    // 后端字段级校验（如 promo_code）也能提示出来
    const msg = data?.detail || (data?.promo_code && data.promo_code[0]) || "创建任务失败，请检查输入";
    ElMessage.error(msg);
  } finally {
    creating.value = false;
  }
}

async function controlRun(run, action) {
  const labels = { pause: "暂停", restart: "重启", stop: "停止" };
  try {
    await axios.post(`/api/content-runs/${run.id}/${action}/`);
    ElMessage.success(`任务已${labels[action]}`);
    await Promise.all([loadRuns(), loadItems()]);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "任务状态更新失败");
  }
}

function selectRun(run) {
  selectedRun.value = run.id;
  selectedRunLabel.value = run.name || `任务 #${run.id}`;
  loadItems(1);
}

function clearRunFilter() {
  selectedRun.value = undefined;
  selectedRunLabel.value = "";
  loadItems(1);
}

// 上传某条记录的第 index 段分镜视频
async function uploadClip(item, index, file) {
  const fd = new FormData();
  fd.append("index", index);
  fd.append("file", file);
  try {
    await axios.post(`/api/content-items/${item.id}/upload_clip/`, fd);
    ElMessage.success(`分镜 ${index} 已上传`);
    await loadItems();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "上传失败");
  }
}

function onClipChange(item, index, uploadFile) {
  if (uploadFile?.raw) uploadClip(item, index, uploadFile.raw);
}

async function regenerateItem(item) {
  try {
    const { data } = await axios.post(`/api/content-items/${item.id}/regenerate/`);
    ElMessage.success(data.detail || "已重新开始生成");
    await loadItems();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "重新生成失败");
  }
}

async function mergeItem(item) {
  try {
    const { data } = await axios.post(`/api/content-items/${item.id}/merge/`);
    ElMessage.success(data.detail || "已开始合并");
    await loadItems();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "合并失败");
  }
}

function downloadPackage(item) {
  window.open(`/api/content-items/${item.id}/package/`, "_blank");
}

// 成品视频地址：流程二取合并成品，流程一取 Remotion 渲染成品。
function finalUrl(item) {
  return item.merged_url || item.rendered_url || "";
}

// 打开某条记录的生成日志抽屉。运行中的记录 4 秒轮询也会刷新 items，抽屉内容跟着更新。
async function openLog(item) {
  logItem.value = item;
  logDrawer.value = true;
}

// 步骤名 → 中文 + 状态色
const stepMeta = {
  metadata: "元数据生成",
  thumbnail: "封面出图",
  storyboard: "分镜脚本生成",
  narration: "旁白配音（TTS）",
  render: "视频渲染（Remotion）",
};
const stepStatusMeta = {
  running: { label: "进行中", type: "warning" },
  success: { label: "成功", type: "success" },
  failed: { label: "失败", type: "danger" },
  skipped: { label: "跳过", type: "info" },
};
const stepLabel = (s) => stepMeta[s] || s;
const stepStatusLabel = (s) => stepStatusMeta[s]?.label || s;
const stepStatusType = (s) => stepStatusMeta[s]?.type || "info";

// 抽屉里始终展示 items 里最新的那条（轮询会更新 items），避免看到过期日志
const logItemLive = computed(() => {
  if (!logItem.value) return null;
  return items.value.find((it) => it.id === logItem.value.id) || logItem.value;
});

// 已上传的分镜数（用于判断能否合并）
function uploadedCount(item) {
  return (item.clip_files || []).length;
}

function startPoll() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    await loadRuns();
    await loadItems();
  }, 4000);
}
function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

// 关键词结果页「送入内容生成」：把带来的关键词填进创建表单
watch(() => props.injectedKeywords, (kws) => {
  if (kws && kws.length) {
    form.value.keywordsText = kws.join("\n");
    ElMessage.success(`已带入 ${kws.length} 个关键词，请确认后创建任务`);
  }
});

onMounted(async () => {
  await Promise.all([loadRuns(), loadItems()]);
  if (props.injectedKeywords?.length) form.value.keywordsText = props.injectedKeywords.join("\n");
});
onUnmounted(stopPoll);
</script>
<template>
  <div>
    <el-card class="create-card" shadow="never">
      <template #header><strong>创建内容生成任务</strong></template>
      <el-form label-position="top" @submit.prevent="createRun">
        <el-form-item label="生成流程">
          <el-radio-group v-model="form.flow">
            <el-radio-button label="flow2">流程二 · 半自动（AI 出内容，人工上传视频合并）</el-radio-button>
            <el-radio-button label="flow1">流程一 · 全自动（AI 配音 + 自动渲染视频）</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-alert
          v-if="isFlow1"
          title="流程一会在生成标题/描述/封面/分镜脚本后，自动为每段分镜配旁白语音，再用 Remotion 渲染出竖屏成品视频，无需人工上传。当前模板为纯文字动效版，后续可精细化。"
          type="warning" :closable="false" class="process-note" show-icon
        />
        <el-form-item label="关键词（每行一个，或用逗号分隔；可从关键词结果页一键送入）">
          <el-input v-model="form.keywordsText" type="textarea" :autosize="{ minRows: 3, maxRows: 10 }" placeholder="例如：&#10;1xbet promo code&#10;betwinner bonus" />
          <small class="agent-hint">当前解析出 {{ parsedKeywords.length }} 个关键词，每个关键词生成一条内容记录。</small>
        </el-form-item>
        <el-form :inline="true">
          <el-form-item label="任务备注名"><el-input v-model="form.name" placeholder="选填，便于识别" /></el-form-item>
          <el-form-item label="目标国家"><el-select v-model="form.country" filterable style="width: 150px"><el-option v-for="item in options.countries" :key="item.value" :label="`${item.label} (${item.value})`" :value="item.value" /></el-select></el-form-item>
          <el-form-item label="内容语言"><el-select v-model="form.language" filterable style="width: 150px"><el-option v-for="item in options.languages" :key="item.value" :label="`${item.label} (${item.value})`" :value="item.value" /></el-select></el-form-item>
          <el-form-item label="分镜段数"><el-input-number v-model="form.shot_count" :min="1" :max="10" /></el-form-item>
          <el-form-item label="每段时长(秒)"><el-input-number v-model="form.shot_duration" :min="1" :max="60" /></el-form-item>
          <!-- 流程一专属：优惠码 + 配音引擎 -->
          <el-form-item v-if="isFlow1" label="优惠码（注入视频）"><el-input v-model="form.promo_code" placeholder="必填，如 NEW100" style="width: 160px" /></el-form-item>
          <el-form-item v-if="isFlow1" label="配音引擎"><el-select v-model="form.tts_provider" style="width: 170px"><el-option label="Edge TTS（免费）" value="edge" /><el-option label="ElevenLabs（付费）" value="elevenlabs" /></el-select></el-form-item>
          <el-form-item label=" "><el-button type="primary" :loading="creating" @click="createRun">开始生成</el-button></el-form-item>
        </el-form>
      </el-form>
    </el-card>

    <el-card shadow="never" class="table-card">
      <template #header><div class="card-title"><strong>任务记录</strong><div><el-input v-model="runSearch" clearable placeholder="搜索任务名/关键词" class="search-input" @keyup.enter="loadRuns(1)" @clear="loadRuns(1)" /><el-button @click="loadRuns(1)">搜索</el-button></div></div></template>
      <el-table :data="runs" size="small" empty-text="暂无任务" class="clickable-table" @row-click="selectRun">
        <el-table-column label="任务" min-width="160"><template #default="{ row }">{{ row.name || `任务 #${row.id}` }}</template></el-table-column>
        <el-table-column label="流程" width="110"><template #default="{ row }"><el-tag size="small" :type="row.flow === 'flow1' ? 'warning' : 'info'" effect="plain">{{ row.flow === 'flow1' ? '全自动' : '半自动' }}</el-tag></template></el-table-column>
        <el-table-column prop="country" label="国家" width="70" />
        <el-table-column prop="language" label="语言" width="80" />
        <el-table-column label="分镜" width="90"><template #default="{ row }">{{ row.shot_count }}×{{ row.shot_duration }}s</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag size="small" :type="statusType(row.status)" effect="light">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
        <el-table-column prop="item_count" label="关键词数" width="90" />
        <el-table-column label="更新时间" min-width="160"><template #default="{ row }">{{ datetime(row.updated_at) }}</template></el-table-column>
        <el-table-column label="控制" width="270"><template #default="{ row }">
          <el-button size="small" :disabled="!['pending','running'].includes(row.status)" @click.stop="controlRun(row, 'pause')">暂停</el-button>
          <el-button size="small" type="primary" plain :disabled="!['paused','stopped','failed','completed'].includes(row.status)" @click.stop="controlRun(row, 'restart')">重启</el-button>
          <el-button size="small" type="danger" plain :disabled="!['pending','running','paused'].includes(row.status)" @click.stop="controlRun(row, 'stop')">停止</el-button>
        </template></el-table-column>
      </el-table>
      <el-pagination v-model:current-page="runPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="runTotal" @current-change="loadRuns" />
    </el-card>

    <el-card shadow="never" class="table-card">
      <template #header><div class="card-title"><div><strong>内容记录</strong><el-tag v-if="selectedRun" class="run-filter-tag" closable type="primary" @close="clearRunFilter"> 当前任务：{{ selectedRunLabel }}</el-tag></div><div><el-input v-model="itemSearch" clearable placeholder="搜索关键词" class="search-input" @keyup.enter="loadItems(1)" @clear="loadItems(1)" /><el-button @click="loadItems(1)">搜索</el-button><el-button @click="loadItems">刷新</el-button></div></div></template>
      <el-alert title="流程二（半自动）：AI 生成标题/描述/封面/分镜脚本 → 人工上传分镜视频 → 合并成品 → 打包下载。流程一（全自动）：AI 生成内容后自动配音 + Remotion 渲染出成品，直接打包下载。展开每行查看详情。" type="info" :closable="false" class="process-note" />
      <el-table :data="items" stripe v-loading="loading" empty-text="创建任务后在此查看内容记录">
        <el-table-column type="expand" width="40"><template #default="{ row }">
          <div class="item-detail">
            <el-alert v-if="row.error_message" :title="row.error_message" type="warning" :closable="false" class="process-note" />

            <div class="item-actions">
              <el-button size="small" type="warning" plain :disabled="row.status === 'generating'" @click="regenerateItem(row)">重新生成 AI 内容</el-button>
              <small class="agent-hint">元数据/封面/分镜若失败或不满意，可重新生成（不影响已上传的分镜视频）。</small>
            </div>
            <el-descriptions :column="1" border size="small" class="item-meta">
              <el-descriptions-item label="标题">{{ row.title || "未生成" }}</el-descriptions-item>
              <el-descriptions-item label="描述"><div class="item-desc">{{ row.description || "未生成" }}</div></el-descriptions-item>
              <el-descriptions-item label="封面提示词">{{ row.thumbnail_prompt || "未生成" }}</el-descriptions-item>
            </el-descriptions>

            <div v-if="row.storyboard && row.storyboard.shots && row.storyboard.shots.length" class="storyboard-block">
              <strong>分镜脚本（总时长 {{ row.storyboard.total_duration }}s）</strong>
              <el-table :data="row.storyboard.shots" border size="small">
                <el-table-column prop="index" label="#" width="48" />
                <el-table-column prop="duration" label="时长" width="70"><template #default="{ row: s }">{{ s.duration }}s</template></el-table-column>
                <el-table-column prop="scene" label="画面描述" min-width="180" />
                <!-- 流程一：展示旁白文案；流程二：展示生成提示词供复制到 AI 视频工具 -->
                <el-table-column v-if="row.run_flow === 'flow1'" label="旁白文案（自动配音）" min-width="260"><template #default="{ row: s }">{{ s.narration || "—" }}</template></el-table-column>
                <el-table-column v-else prop="prompt" label="生成提示词（复制到 AI 视频工具）" min-width="260" />
                <!-- 流程二才需要人工上传分镜视频 -->
                <el-table-column v-if="row.run_flow !== 'flow1'" label="上传该段视频" width="150"><template #default="{ row: s }">
                  <el-upload :show-file-list="false" :auto-upload="false" accept="video/*" :on-change="(f) => onClipChange(row, s.index, f)">
                    <el-button size="small" plain>上传分镜 {{ s.index }}</el-button>
                  </el-upload>
                </template></el-table-column>
              </el-table>
            </div>

            <!-- 流程二：人工上传分镜 + 合并 -->
            <div v-if="row.run_flow !== 'flow1'" class="clip-status">
              <span>已上传分镜：{{ uploadedCount(row) }} / {{ row.storyboard?.shots?.length || 0 }} 段</span>
              <el-tag v-for="c in (row.clip_files || [])" :key="c.index" size="small" type="success" effect="plain">分镜{{ c.index }}：{{ c.name }}</el-tag>
              <el-button size="small" type="primary" :disabled="uploadedCount(row) === 0 || row.status === 'merging'" @click="mergeItem(row)">合并成品</el-button>
              <el-button v-if="row.merged_url" size="small" type="success" plain @click="downloadPackage(row)">下载成品包</el-button>
            </div>
            <!-- 流程一：全自动渲染，展示成品状态 -->
            <div v-else class="clip-status">
              <el-tag v-if="row.status === 'rendering'" type="warning" effect="light">正在自动配音并渲染视频…</el-tag>
              <template v-if="row.rendered_url">
                <el-tag type="success" effect="plain">已渲染成品</el-tag>
                <el-button size="small" type="success" plain @click="downloadPackage(row)">下载成品包</el-button>
              </template>
            </div>
            <video v-if="finalUrl(row)" :src="finalUrl(row)" controls class="merged-preview" />
          </div>
        </template></el-table-column>
        <el-table-column prop="keyword" label="关键词" min-width="170" />
        <el-table-column label="状态" width="130"><template #default="{ row }"><el-tag :type="itemStatusType(row.status)" size="small" effect="light">{{ itemStatusLabel(row.status) }}</el-tag></template></el-table-column>
        <el-table-column label="标题" min-width="220" show-overflow-tooltip><template #default="{ row }">{{ row.title || "—" }}</template></el-table-column>
        <el-table-column label="封面" width="90"><template #default="{ row }"><el-image v-if="row.thumbnail_url" :src="row.thumbnail_url" :preview-src-list="[row.thumbnail_url]" :preview-teleported="true" fit="cover" style="width: 48px; height: 48px; border-radius: 4px" /><span v-else>—</span></template></el-table-column>
        <el-table-column label="成品" width="120"><template #default="{ row }">
          <el-button v-if="finalUrl(row)" size="small" type="success" plain @click="downloadPackage(row)">下载成品包</el-button>
          <span v-else>—</span>
        </template></el-table-column>
        <el-table-column label="日志" width="80"><template #default="{ row }">
          <el-button size="small" type="info" plain @click="openLog(row)">日志</el-button>
        </template></el-table-column>
      </el-table>
      <el-pagination v-model:current-page="itemPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="itemTotal" @current-change="loadItems" />
    </el-card>

    <el-drawer v-model="logDrawer" title="生成工作日志" size="720px" :destroy-on-close="true">
      <div v-if="logItemLive">
        <div class="log-head">
          <el-tag :type="itemStatusType(logItemLive.status)" effect="light">{{ itemStatusLabel(logItemLive.status) }}</el-tag>
          <span class="log-root">关键词：{{ logItemLive.keyword }}</span>
        </div>
        <el-alert v-if="logItemLive.error_message" :title="logItemLive.error_message" type="warning" :closable="false" class="process-note" />

        <template v-if="logItemLive.gen_log && logItemLive.gen_log.steps && logItemLive.gen_log.steps.length">
          <el-timeline class="log-timeline">
            <el-timeline-item
              v-for="(step, i) in logItemLive.gen_log.steps"
              :key="i"
              :type="stepStatusType(step.status)"
              :timestamp="step.elapsed_seconds !== undefined ? `耗时 ${step.elapsed_seconds}s` : ''"
            >
              <div class="log-step-head">
                <strong>{{ stepLabel(step.step) }}</strong>
                <el-tag size="small" :type="stepStatusType(step.status)" effect="plain">{{ stepStatusLabel(step.status) }}</el-tag>
                <span v-if="step.model" class="log-model">模型：{{ step.model }}</span>
              </div>
              <el-alert v-if="step.error" :title="step.error" type="error" :closable="false" class="process-note" />

              <!-- 封面出图：重点展示封面提示词 -->
              <template v-if="step.step === 'thumbnail' && step.thumbnail_prompt">
                <p class="log-line">封面提示词：</p>
                <pre class="log-pre">{{ step.thumbnail_prompt }}</pre>
              </template>

              <!-- 旁白配音（流程一）：展示每段配音结果 -->
              <template v-if="step.step === 'narration' && step.segments">
                <p class="log-line">配音引擎：{{ step.provider }}，成功 {{ step.audio_count }} 段</p>
                <div v-for="seg in step.segments" :key="seg.index" class="log-line">
                  分镜 {{ seg.index }}：
                  <el-tag size="small" :type="seg.status === 'skipped' ? 'danger' : 'success'" effect="plain">{{ seg.status }}</el-tag>
                  <span v-if="seg.provider" class="log-model">实际引擎 {{ seg.provider }}</span>
                  <span v-if="seg.error" class="log-model">{{ seg.error }}</span>
                </div>
              </template>

              <!-- 视频渲染（流程一）：展示渲染成品信息 -->
              <template v-if="step.step === 'render' && step.status === 'success'">
                <p class="log-line">成品：{{ step.output }}（{{ step.duration_in_frames }} 帧）</p>
              </template>

              <!-- 元数据 / 分镜：展示 AI 输入输出 -->
              <el-collapse v-if="step.prompt || step.raw_output || step.parsed" class="log-collapse">
                <el-collapse-item v-if="step.title" title="生成的标题 / 描述 / 封面提示词" name="meta">
                  <p class="log-line"><strong>标题：</strong>{{ step.title }}</p>
                  <p class="log-line"><strong>描述：</strong></p>
                  <pre class="log-pre">{{ step.description }}</pre>
                  <p class="log-line"><strong>封面提示词：</strong></p>
                  <pre class="log-pre">{{ step.thumbnail_prompt }}</pre>
                </el-collapse-item>
                <el-collapse-item v-if="step.shots" title="分镜内容" name="shots">
                  <div v-for="shot in step.shots" :key="shot.index" class="log-shot">
                    <strong>分镜 {{ shot.index }}（{{ shot.duration }}s）</strong>
                    <p class="log-line">画面：{{ shot.scene }}</p>
                    <p class="log-line">提示词：{{ shot.prompt }}</p>
                  </div>
                </el-collapse-item>
                <el-collapse-item v-if="step.prompt" title="Agent 输入 Prompt" name="prompt">
                  <pre class="log-pre">{{ step.prompt }}</pre>
                </el-collapse-item>
                <el-collapse-item v-if="step.raw_output" title="Agent 原始输出" name="raw">
                  <pre class="log-pre">{{ step.raw_output }}</pre>
                </el-collapse-item>
                <el-collapse-item v-if="step.parsed" title="解析后结构" name="parsed">
                  <pre class="log-pre">{{ JSON.stringify(step.parsed, null, 2) }}</pre>
                </el-collapse-item>
              </el-collapse>
            </el-timeline-item>
          </el-timeline>
        </template>
        <el-empty v-else description="暂无生成日志（任务可能尚未开始或为旧数据）" :image-size="60" />
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.item-detail { padding: 8px 12px; }
.item-actions { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.item-meta { margin-bottom: 12px; }
.item-desc { white-space: pre-wrap; line-height: 1.5; }
.storyboard-block { margin-bottom: 12px; }
.storyboard-block > strong { display: block; margin-bottom: 8px; }
.clip-status { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin: 8px 0; }
.merged-preview { max-width: 240px; max-height: 420px; margin-top: 8px; border-radius: 6px; display: block; }
.agent-hint { color: #909399; font-size: 12px; display: block; margin-top: 4px; }
.process-note { margin-bottom: 12px; }
.log-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.log-root { color: #606266; font-size: 13px; }
.log-timeline { padding-top: 4px; }
.log-step-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
.log-model { color: #909399; font-size: 12px; }
.log-line { margin: 4px 0; line-height: 1.5; word-break: break-word; }
.log-pre { white-space: pre-wrap; word-break: break-word; background: #f5f7fa; border-radius: 6px; padding: 8px 10px; margin: 4px 0; font-size: 12px; line-height: 1.5; max-height: 320px; overflow: auto; }
.log-collapse { margin-top: 6px; }
.log-shot { margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px dashed #ebeef5; }
.log-shot:last-child { border-bottom: none; }
</style>

