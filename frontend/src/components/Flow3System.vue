<script setup>
// 流程3 · 全新内容生成系统（独立组件，与流程1/2 完全隔离）。
// 含三个子页：任务管理 / Agent 管理 / 素材库。删除流程1/2 不影响本组件。
import { computed, onMounted, onUnmounted, ref } from "vue";
import axios from "axios";
import { ElMessage, ElMessageBox } from "element-plus";

const tab = ref("tasks");

// —— 任务 ——
const runs = ref([]);
const runTotal = ref(0);
const runPage = ref(1);
const runSearch = ref("");
const creating = ref(false);
const form = ref({
  name: "", keyword: "", total_duration: 240, promo_code: "",
  country: "IN", event_name: "", language: "en-IN",
});
let pollTimer = null;

// —— Agent ——
const agents = ref([]);
const agentLoading = ref(false);

// —— 素材库 ——
const screenMaterials = ref([]);
const bgmMaterials = ref([]);
const materialLoading = ref(false);

// —— Hook 上传 / 日志 ——
const hookDialog = ref(false);
const hookRun = ref(null);
const hookFile = ref(null);
const uploading = ref(false);
const logDrawer = ref(false);
const logData = ref(null);
const logLoading = ref(false);

const statusMeta = {
  pending: { label: "待处理", type: "info" },
  running: { label: "处理中", type: "warning" },
  awaiting_hook: { label: "等待 Hook 上传", type: "danger" },
  paused: { label: "已暂停", type: "info" },
  stopped: { label: "已停止", type: "info" },
  completed: { label: "已完成", type: "success" },
  failed: { label: "失败", type: "danger" },
};
const statusLabel = (s) => statusMeta[s]?.label || s;
const statusType = (s) => statusMeta[s]?.type || "info";
const datetime = (v) => (v ? new Date(v).toLocaleString("zh-CN", { hour12: false }) : "—");

async function loadRuns(page = runPage.value) {
  runPage.value = page;
  const { data } = await axios.get("/api/flow3-runs/", { params: { page, search: runSearch.value } });
  runs.value = data.results;
  runTotal.value = data.count;
  if (runs.value.some((r) => ["running", "pending"].includes(r.status))) startPoll();
  else stopPoll();
}

async function createRun() {
  if (!form.value.keyword.trim()) return ElMessage.warning("请填写关键词");
  creating.value = true;
  try {
    await axios.post("/api/flow3-runs/", form.value);
    ElMessage.success("任务已创建，正在生成 Hook Prompt…");
    form.value.keyword = "";
    form.value.promo_code = "";
    form.value.name = "";
    await loadRuns(1);
  } catch (e) {
    ElMessage.error(e.response?.data ? JSON.stringify(e.response.data) : "创建失败");
  } finally {
    creating.value = false;
  }
}

async function controlRun(run, action) {
  const labels = { pause: "暂停", stop: "停止", restart: "重启", resume: "继续" };
  try {
    await axios.post(`/api/flow3-runs/${run.id}/${action}/`);
    ElMessage.success(`已${labels[action]}`);
    await loadRuns();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "操作失败");
  }
}

function openHookUpload(run) {
  hookRun.value = run;
  hookFile.value = null;
  hookDialog.value = true;
}

async function submitHook() {
  if (!hookFile.value) return ElMessage.warning("请选择 Hook 视频文件");
  uploading.value = true;
  try {
    const fd = new FormData();
    fd.append("file", hookFile.value.raw);
    await axios.post(`/api/flow3-runs/${hookRun.value.id}/upload_hook/`, fd);
    ElMessage.success("Hook 视频已上传");
    hookDialog.value = false;
    await loadRuns();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "上传失败");
  } finally {
    uploading.value = false;
  }
}

async function resumeRun(run) {
  await controlRun(run, "resume");
}

function downloadPackage(run) {
  window.open(`/api/flow3-runs/${run.id}/package/`, "_blank");
}

async function openLog(run) {
  logDrawer.value = true;
  logLoading.value = true;
  logData.value = null;
  try {
    const { data } = await axios.get(`/api/flow3-runs/${run.id}/log/`);
    logData.value = data;
  } catch {
    ElMessage.error("加载日志失败");
  } finally {
    logLoading.value = false;
  }
}

function startPoll() {
  if (pollTimer) return;
  pollTimer = setInterval(() => { if (tab.value === "tasks") loadRuns(); }, 4000);
}
function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

// —— Agent ——
async function loadAgents() {
  agentLoading.value = true;
  try {
    const { data } = await axios.get("/api/flow3-agents/");
    agents.value = Array.isArray(data) ? data : data.results || [];
  } catch {
    ElMessage.error("加载 Agent 失败");
  } finally {
    agentLoading.value = false;
  }
}
async function saveAgent(agent) {
  try {
    await axios.patch(`/api/flow3-agents/${agent.id}/`, { prompt: agent.prompt, enabled: agent.enabled });
    ElMessage.success(`已保存「${agent.name}」`);
  } catch {
    ElMessage.error("保存失败");
  }
}
async function resetAgent(agent) {
  try {
    const { data } = await axios.get(`/api/flow3-agents/${agent.id}/default_prompt/`);
    if (!data.prompt) return ElMessage.warning("无默认提示词");
    agent.prompt = data.prompt;
    ElMessage.success("已载入默认提示词，请点保存");
  } catch {
    ElMessage.error("获取默认提示词失败");
  }
}

// —— 素材库 ——
async function loadMaterials() {
  materialLoading.value = true;
  try {
    const [s, b] = await Promise.all([
      axios.get("/api/flow3-materials/", { params: { type: "screen_record", page_size: 100 } }),
      axios.get("/api/flow3-materials/", { params: { type: "bgm", page_size: 100 } }),
    ]);
    screenMaterials.value = s.data.results || s.data;
    bgmMaterials.value = b.data.results || b.data;
  } catch {
    ElMessage.error("加载素材失败");
  } finally {
    materialLoading.value = false;
  }
}

async function uploadMaterial(type, uploadFile) {
  const fd = new FormData();
  fd.append("material_type", type);
  fd.append("file", uploadFile.raw);
  fd.append("name", uploadFile.name);
  try {
    await axios.post("/api/flow3-materials/", fd);
    ElMessage.success("上传成功");
    await loadMaterials();
  } catch (e) {
    ElMessage.error(e.response?.data ? JSON.stringify(e.response.data) : "上传失败");
  }
}

async function deleteMaterial(m) {
  try {
    await ElMessageBox.confirm(`确定删除素材「${m.name || m.id}」？`, "确认", { type: "warning" });
    await axios.delete(`/api/flow3-materials/${m.id}/`);
    ElMessage.success("已删除");
    await loadMaterials();
  } catch (e) {
    if (e !== "cancel") ElMessage.error("删除失败");
  }
}

onMounted(() => { loadRuns(); loadAgents(); loadMaterials(); });
onUnmounted(() => stopPoll());
</script>

<template>
  <el-tabs v-model="tab" class="flow3-tabs">
    <!-- ============ 任务管理 ============ -->
    <el-tab-pane label="任务管理" name="tasks">
      <el-alert
        title="流程3 · 三段式长视频（16:9 1080P）"
        description="单视频模式：一个任务 = 一个关键词 = 一个成品。创建后系统先生成 Hook Prompt，任务暂停等你上传 Hook 视频（mp4），上传后点「继续」自动完成旁白/TTS/模糊底图/尾图/组装/混音去重。"
        type="success" :closable="false" show-icon class="flow3-intro"
      />
      <el-card class="create-card" shadow="never">
        <template #header><strong>创建流程3 任务</strong></template>
        <el-form :inline="true" @submit.prevent="createRun">
          <el-form-item label="任务名"><el-input v-model="form.name" placeholder="选填备注" style="width: 160px" /></el-form-item>
          <el-form-item label="关键词"><el-input v-model="form.keyword" placeholder="仅 1 个，如 1xbet promo code" style="width: 220px" /></el-form-item>
          <el-form-item label="优惠码"><el-input v-model="form.promo_code" placeholder="如 ZH567" style="width: 130px" /></el-form-item>
          <el-form-item label="总时长(秒)"><el-input-number v-model="form.total_duration" :min="30" :max="600" :step="10" /></el-form-item>
          <el-form-item label="国家"><el-input v-model="form.country" style="width: 90px" /></el-form-item>
          <el-form-item label="赛事"><el-input v-model="form.event_name" placeholder="选填" style="width: 150px" /></el-form-item>
          <el-form-item label="语言"><el-input v-model="form.language" style="width: 100px" /></el-form-item>
          <el-button type="primary" :loading="creating" @click="createRun">创建任务</el-button>
        </el-form>
      </el-card>

      <el-card shadow="never" class="table-card">
        <template #header><div class="card-title"><strong>任务记录</strong>
          <div><el-input v-model="runSearch" clearable placeholder="搜索任务名/关键词" style="width: 200px" @keyup.enter="loadRuns(1)" @clear="loadRuns(1)" /><el-button @click="loadRuns(1)">搜索</el-button><el-button @click="loadRuns()">刷新</el-button></div>
        </div></template>
        <el-table :data="runs" size="small" empty-text="暂无任务">
          <el-table-column prop="keyword" label="关键词" min-width="160" />
          <el-table-column prop="promo_code" label="优惠码" width="100" />
          <el-table-column label="总时长" width="80"><template #default="{ row }">{{ row.total_duration }}s</template></el-table-column>
          <el-table-column label="状态" width="130"><template #default="{ row }"><el-tag :type="statusType(row.status)" size="small" effect="light">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
          <el-table-column label="成品" width="90"><template #default="{ row }"><a v-if="row.rendered_url" :href="row.rendered_url" target="_blank">预览</a><span v-else>—</span></template></el-table-column>
          <el-table-column label="更新时间" min-width="160"><template #default="{ row }">{{ datetime(row.updated_at) }}</template></el-table-column>
          <el-table-column label="操作" width="360"><template #default="{ row }">
            <el-button v-if="row.status === 'awaiting_hook'" size="small" type="warning" @click="openHookUpload(row)">上传Hook</el-button>
            <el-button v-if="row.status === 'awaiting_hook' && row.hook_video_url" size="small" type="primary" @click="resumeRun(row)">继续</el-button>
            <el-button size="small" :disabled="!['pending','running'].includes(row.status)" @click="controlRun(row, 'pause')">暂停</el-button>
            <el-button size="small" type="primary" plain :disabled="!['paused','stopped','failed','completed'].includes(row.status)" @click="controlRun(row, 'restart')">重启</el-button>
            <el-button size="small" type="danger" plain :disabled="['completed','stopped'].includes(row.status)" @click="controlRun(row, 'stop')">停止</el-button>
            <el-button size="small" type="info" plain @click="openLog(row)">日志</el-button>
            <el-button size="small" type="success" plain :disabled="row.status !== 'completed'" @click="downloadPackage(row)">下载</el-button>
          </template></el-table-column>
        </el-table>
        <el-pagination v-model:current-page="runPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="runTotal" @current-change="loadRuns" />
      </el-card>

      <!-- 展开查看 Hook Prompt（awaiting_hook 态很有用） -->
      <el-card v-if="runs.some(r => r.hook_prompt)" shadow="never" class="table-card">
        <template #header><strong>各任务 Hook Prompt（供复制去外部视频引擎生成）</strong></template>
        <div v-for="r in runs.filter(x => x.hook_prompt)" :key="r.id" class="hook-prompt-block">
          <div class="hook-prompt-head"><el-tag size="small">{{ r.keyword }}</el-tag><el-tag size="small" :type="statusType(r.status)" effect="plain">{{ statusLabel(r.status) }}</el-tag></div>
          <pre class="log-pre">{{ r.hook_prompt }}</pre>
        </div>
      </el-card>
    </el-tab-pane>

    <!-- ============ Agent 管理 ============ -->
    <el-tab-pane label="Agent 管理" name="agents">
      <el-alert title="流程3 Agent 管理" description="流程3 使用独立的一组 Agent（与流程1/2 隔离）。支持 {PROMO_CODE}/{COUNTRY}/{EVENT_NAME} 全局占位符，[input] 为关键词。" type="success" :closable="false" show-icon class="flow3-intro" />
      <div v-loading="agentLoading">
        <el-card v-for="agent in agents" :key="agent.id" shadow="never" class="agent-card">
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
              <el-input v-model="agent.prompt" type="textarea" :autosize="{ minRows: 8, maxRows: 26 }" placeholder="留空则使用系统内置默认提示词" />
            </el-form-item>
            <el-button type="primary" @click="saveAgent(agent)">保存</el-button>
            <el-button plain @click="resetAgent(agent)">恢复系统默认</el-button>
          </el-form>
        </el-card>
        <el-empty v-if="!agentLoading && agents.length === 0" description="暂无 Agent" />
      </div>
    </el-tab-pane>

    <!-- ============ 素材库 ============ -->
    <el-tab-pane label="素材库" name="materials">
      <el-alert title="流程3 素材库（独立）" description="9:16 录屏：库内保留 1 个，所有任务自动取用（取最新启用的一个）。BGM：可批量上传多个，任务执行时随机抽 1 个。" type="success" :closable="false" show-icon class="flow3-intro" />
      <div v-loading="materialLoading">
        <el-card shadow="never" class="table-card">
          <template #header><div class="card-title"><strong>9:16 手机录屏</strong>
            <el-upload :auto-upload="true" :show-file-list="false" accept="video/*" :http-request="({ file }) => uploadMaterial('screen_record', { raw: file, name: file.name })">
              <el-button type="primary" size="small">上传录屏</el-button>
            </el-upload>
          </div></template>
          <el-table :data="screenMaterials" size="small" empty-text="暂无录屏素材">
            <el-table-column prop="name" label="名称" min-width="200" />
            <el-table-column label="时长" width="100"><template #default="{ row }">{{ row.duration ? row.duration + 's' : '—' }}</template></el-table-column>
            <el-table-column label="预览" width="90"><template #default="{ row }"><a v-if="row.file_url" :href="row.file_url" target="_blank">查看</a></template></el-table-column>
            <el-table-column label="启用" width="80"><template #default="{ row }"><el-tag size="small" :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag></template></el-table-column>
            <el-table-column label="操作" width="100"><template #default="{ row }"><el-button size="small" type="danger" plain @click="deleteMaterial(row)">删除</el-button></template></el-table-column>
          </el-table>
        </el-card>

        <el-card shadow="never" class="table-card">
          <template #header><div class="card-title"><strong>背景音乐 BGM</strong>
            <el-upload :auto-upload="true" :show-file-list="false" accept="audio/*" :multiple="true" :http-request="({ file }) => uploadMaterial('bgm', { raw: file, name: file.name })">
              <el-button type="primary" size="small">批量上传 BGM</el-button>
            </el-upload>
          </div></template>
          <el-table :data="bgmMaterials" size="small" empty-text="暂无 BGM 素材">
            <el-table-column prop="name" label="名称" min-width="200" />
            <el-table-column label="时长" width="100"><template #default="{ row }">{{ row.duration ? row.duration + 's' : '—' }}</template></el-table-column>
            <el-table-column label="试听" width="90"><template #default="{ row }"><a v-if="row.file_url" :href="row.file_url" target="_blank">播放</a></template></el-table-column>
            <el-table-column label="启用" width="80"><template #default="{ row }"><el-tag size="small" :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag></template></el-table-column>
            <el-table-column label="操作" width="100"><template #default="{ row }"><el-button size="small" type="danger" plain @click="deleteMaterial(row)">删除</el-button></template></el-table-column>
          </el-table>
        </el-card>
      </div>
    </el-tab-pane>
  </el-tabs>

  <!-- Hook 上传弹窗 -->
  <el-dialog v-model="hookDialog" title="上传 Hook 视频" width="480px">
    <p class="hint">请上传用 Hook Prompt 在外部视频引擎生成的 mp4（约 7 秒）。</p>
    <el-upload :auto-upload="false" :limit="1" accept="video/*" :on-change="(f) => hookFile = f" :show-file-list="true">
      <el-button type="primary">选择文件</el-button>
    </el-upload>
    <template #footer>
      <el-button @click="hookDialog = false">取消</el-button>
      <el-button type="primary" :loading="uploading" @click="submitHook">上传</el-button>
    </template>
  </el-dialog>

  <!-- 日志抽屉 -->
  <el-drawer v-model="logDrawer" title="流程3 工作日志" size="680px" :destroy-on-close="true">
    <div v-loading="logLoading">
      <template v-if="logData && logData.run_log && logData.run_log.steps">
        <el-timeline>
          <el-timeline-item
            v-for="(step, i) in logData.run_log.steps" :key="i"
            :type="step.status === 'success' ? 'success' : (step.status === 'failed' ? 'danger' : 'primary')"
            :timestamp="datetime(step.at)"
          >
            <strong>{{ step.step }}</strong> · {{ step.status }}
            <span v-if="step.elapsed_seconds"> （{{ step.elapsed_seconds }}s）</span>
            <div v-if="step.error" class="log-err">{{ step.error }}</div>
            <el-collapse v-if="step.prompt || step.raw_output || step.video_prompt || step.image_prompt" class="log-collapse">
              <el-collapse-item v-if="step.video_prompt" title="Hook 视频 Prompt"><pre class="log-pre">{{ step.video_prompt }}</pre></el-collapse-item>
              <el-collapse-item v-if="step.image_prompt" title="生图 Prompt"><pre class="log-pre">{{ step.image_prompt }}</pre></el-collapse-item>
              <el-collapse-item v-if="step.prompt" title="Agent 输入 Prompt"><pre class="log-pre">{{ step.prompt }}</pre></el-collapse-item>
              <el-collapse-item v-if="step.raw_output" title="AI 原始输出"><pre class="log-pre">{{ step.raw_output }}</pre></el-collapse-item>
            </el-collapse>
          </el-timeline-item>
        </el-timeline>
      </template>
      <el-empty v-else-if="!logLoading" description="暂无日志" />
    </div>
  </el-drawer>
</template>

<style scoped>
.flow3-intro { margin-bottom: 16px; }
.create-card, .table-card { margin-bottom: 16px; }
.card-title { display: flex; justify-content: space-between; align-items: center; }
.pagination { margin-top: 12px; justify-content: flex-end; }
.agent-card { margin-bottom: 16px; }
.agent-card-head { display: flex; justify-content: space-between; align-items: center; }
.agent-card-meta { display: flex; align-items: center; gap: 10px; }
.agent-card-name { font-size: 15px; }
.agent-card-desc { color: #8a949c; font-size: 13px; }
.hook-prompt-block { margin-bottom: 14px; }
.hook-prompt-head { display: flex; gap: 8px; margin-bottom: 6px; }
.log-pre { white-space: pre-wrap; word-break: break-word; background: #0f1621; color: #c8d3de; padding: 10px; border-radius: 6px; font-size: 12px; max-height: 300px; overflow: auto; }
.log-collapse { margin-top: 8px; }
.log-err { color: #f56c6c; font-size: 13px; margin-top: 4px; }
.hint { color: #8a949c; font-size: 13px; margin-bottom: 10px; }
</style>

