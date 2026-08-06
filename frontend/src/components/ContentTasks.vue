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

const form = ref({ name: "", country: "US", language: "en", shot_count: 2, shot_duration: 8, keywordsText: "" });
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

async function createRun() {
  const keywords = parsedKeywords.value;
  if (keywords.length === 0) return ElMessage.warning("请至少输入一个关键词");
  creating.value = true;
  try {
    await axios.post("/api/content-runs/", {
      name: form.value.name,
      country: form.value.country,
      language: form.value.language,
      shot_count: form.value.shot_count,
      shot_duration: form.value.shot_duration,
      keywords,
    });
    ElMessage.success(`任务已创建，正在为 ${keywords.length} 个关键词生成内容`);
    form.value.keywordsText = "";
    form.value.name = "";
    await loadRuns(1);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "创建任务失败，请检查输入");
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
          <el-form-item label=" "><el-button type="primary" :loading="creating" @click="createRun">开始生成</el-button></el-form-item>
        </el-form>
      </el-form>
    </el-card>

    <el-card shadow="never" class="table-card">
      <template #header><div class="card-title"><strong>任务记录</strong><div><el-input v-model="runSearch" clearable placeholder="搜索任务名/关键词" class="search-input" @keyup.enter="loadRuns(1)" @clear="loadRuns(1)" /><el-button @click="loadRuns(1)">搜索</el-button></div></div></template>
      <el-table :data="runs" size="small" empty-text="暂无任务" class="clickable-table" @row-click="selectRun">
        <el-table-column label="任务" min-width="160"><template #default="{ row }">{{ row.name || `任务 #${row.id}` }}</template></el-table-column>
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
      <el-alert title="每条记录先由 AI 生成标题/描述/封面/分镜脚本；再人工上传分镜视频，点合并出成品，最后一键打包下载。" type="info" :closable="false" class="process-note" />
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
                <el-table-column prop="scene" label="画面描述" min-width="200" />
                <el-table-column prop="prompt" label="生成提示词（复制到 AI 视频工具）" min-width="260" />
                <el-table-column label="上传该段视频" width="150"><template #default="{ row: s }">
                  <el-upload :show-file-list="false" :auto-upload="false" accept="video/*" :on-change="(f) => onClipChange(row, s.index, f)">
                    <el-button size="small" plain>上传分镜 {{ s.index }}</el-button>
                  </el-upload>
                </template></el-table-column>
              </el-table>
            </div>

            <div class="clip-status">
              <span>已上传分镜：{{ uploadedCount(row) }} / {{ row.storyboard?.shots?.length || 0 }} 段</span>
              <el-tag v-for="c in (row.clip_files || [])" :key="c.index" size="small" type="success" effect="plain">分镜{{ c.index }}：{{ c.name }}</el-tag>
              <el-button size="small" type="primary" :disabled="uploadedCount(row) === 0 || row.status === 'merging'" @click="mergeItem(row)">合并成品</el-button>
              <el-button v-if="row.merged_url" size="small" type="success" plain @click="downloadPackage(row)">下载成品包</el-button>
            </div>
            <video v-if="row.merged_url" :src="row.merged_url" controls class="merged-preview" />
          </div>
        </template></el-table-column>
        <el-table-column prop="keyword" label="关键词" min-width="170" />
        <el-table-column label="状态" width="130"><template #default="{ row }"><el-tag :type="itemStatusType(row.status)" size="small" effect="light">{{ itemStatusLabel(row.status) }}</el-tag></template></el-table-column>
        <el-table-column label="标题" min-width="220" show-overflow-tooltip><template #default="{ row }">{{ row.title || "—" }}</template></el-table-column>
        <el-table-column label="封面" width="90"><template #default="{ row }"><el-image v-if="row.thumbnail_url" :src="row.thumbnail_url" :preview-src-list="[row.thumbnail_url]" fit="cover" style="width: 48px; height: 48px; border-radius: 4px" /><span v-else>—</span></template></el-table-column>
        <el-table-column label="成品" width="130"><template #default="{ row }">
          <el-button v-if="row.merged_url" size="small" type="success" plain @click="downloadPackage(row)">下载成品包</el-button>
          <span v-else>—</span>
        </template></el-table-column>
      </el-table>
      <el-pagination v-model:current-page="itemPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="itemTotal" @current-change="loadItems" />
    </el-card>
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
</style>

