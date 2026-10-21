<script setup>
// 内容生成系统（流程3）。由 App.vue 的二级菜单通过 view 控制显示哪个页面：
//   flow3-tasks=任务管理 / flow3-agents=Agent 管理 / flow3-materials=素材库
// 任务管理采用「列表 + 独立新增界面」结构：顶部新增/搜索/批量删除，列表行右侧操作列。
import { onMounted, onUnmounted, ref, watch } from "vue";
import axios from "axios";
import { ElMessage, ElMessageBox } from "element-plus";

const props = defineProps({
  view: { type: String, default: "flow3-tasks" },
});

// 任务页子模式：list=任务列表，create=新增任务界面
const taskMode = ref("list");

// —— 任务 ——
const runs = ref([]);
const runTotal = ref(0);
const runPage = ref(1);
const runSearch = ref("");
const selectedIds = ref([]);
const creating = ref(false);
const form = ref({
  name: "", keyword: "", total_duration: 240, promo_code: "",
  country: "IN", language: "en-IN",
  hook_material: null, screen_material: null, hook_group: null, count: 1,
});
let pollTimer = null;

// —— Agent ——
const agents = ref([]);
const agentLoading = ref(false);
// Agent 试运行：每个 agent 独立的临时输入与结果（按 agent.id 存）
const agentRunInput = ref({});   // { [agentId]: {keyword, promo_code, country, repeat} }
const agentRunResult = ref({});  // { [agentId]: 产出 }
const agentRunning = ref({});    // { [agentId]: bool }

// —— 素材库 ——
const screenMaterials = ref([]);
const bgmMaterials = ref([]);
const hookMaterials = ref([]);
const selectedHookIds = ref([]);
const selectedScreenIds = ref([]);
const materialLoading = ref(false);
const tagLabel = (t) => (t === "used" ? "已使用" : "未使用");

// —— Hook 分组 ——
const groups = ref([]);
const currentGroupFilter = ref(null);  // 素材库 Hook 区按分组筛选（null=全部）
const uploadGroup = ref(null);         // 批量上传时归属的分组
const groupDialog = ref(false);
const groupEditing = ref(null);        // 正在编辑的分组对象（null=新建）
const groupName = ref("");
const moveDialog = ref(false);         // 批量移动分组弹窗
const moveTargetGroup = ref(null);     // 批量移动的目标分组

// Agent 试运行结果抽屉
const agentDrawer = ref(false);
const agentDrawerTitle = ref("");
const agentDrawerResult = ref(null);

// 当前所选 hook 分组的可用（未使用）数量，供批量上限提示
function groupUnusedCount(groupId) {
  const g = groups.value.find((x) => x.id === groupId);
  return g ? (g.unused_count || 0) : hookMaterials.value.filter((h) => h.tag === "unused").length;
}

// —— 详情 / Hook 上传 / 日志 ——
const detailDialog = ref(false);
const detailRun = ref(null);
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
// 耗时（秒）→「X分Y秒」/「Y秒」
function formatDuration(sec) {
  if (sec == null) return "—";
  if (sec < 60) return `${sec}秒`;
  const m = Math.floor(sec / 60), s = sec % 60;
  return s ? `${m}分${s}秒` : `${m}分`;
}

// ================= 任务 =================
async function loadRuns(page = runPage.value) {
  runPage.value = page;
  const { data } = await axios.get("/api/flow3-runs/", { params: { page, search: runSearch.value } });
  runs.value = data.results;
  runTotal.value = data.count;
  if (runs.value.some((r) => ["running", "pending"].includes(r.status))) startPoll();
  else stopPoll();
}

async function openCreate() {
  await loadGroups();
  const def = groups.value.find((g) => g.is_default) || groups.value[0];
  form.value = { name: "", keyword: "", total_duration: 240, promo_code: "",
    country: "IN", language: "en-IN",
    hook_material: null, screen_material: null,
    hook_group: def ? def.id : null, count: 1 };
  loadHookOptions();   // hook 素材下拉
  loadScreenOptions(); // 录屏素材下拉
  taskMode.value = "create";
}

async function createRun() {
  if (!form.value.keyword.trim()) return ElMessage.warning("请填写关键词");
  if (!form.value.hook_group) return ElMessage.warning("请选择一个 Hook 使用分组");
  const batch = (form.value.count || 1) > 1;
  if (batch) {
    const avail = groupUnusedCount(form.value.hook_group);
    if (form.value.count > avail) {
      return ElMessage.error(`所选分组可用未使用 Hook 素材仅 ${avail} 个，无法批量生成 ${form.value.count} 个`);
    }
  }
  creating.value = true;
  try {
    const payload = { ...form.value };
    if (batch) payload.hook_material = null;  // 批量强制随机
    const { data } = await axios.post("/api/flow3-runs/", payload);
    const n = Array.isArray(data) ? data.length : 1;
    ElMessage.success(batch ? `已批量创建 ${n} 个任务，随机取用 Hook 素材直接出片…` : "任务已创建…");
    taskMode.value = "list";
    await loadRuns(1);
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || (e.response?.data ? JSON.stringify(e.response.data) : "创建失败"));
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

function onSelectionChange(rows) {
  selectedIds.value = rows.map((r) => r.id);
}

async function bulkDelete() {
  if (!selectedIds.value.length) return ElMessage.warning("请先勾选要删除的任务");
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.length} 个任务？此操作不可恢复。`, "确认删除", { type: "warning" });
    await axios.post("/api/flow3-runs/bulk_delete/", { ids: selectedIds.value });
    ElMessage.success("已删除");
    selectedIds.value = [];
    await loadRuns();
  } catch (e) {
    if (e !== "cancel") ElMessage.error(e.response?.data?.detail || "删除失败");
  }
}

async function deleteOne(run) {
  try {
    await ElMessageBox.confirm(`确定删除任务「${run.name || run.keyword}」？`, "确认删除", { type: "warning" });
    await axios.delete(`/api/flow3-runs/${run.id}/`);
    ElMessage.success("已删除");
    await loadRuns();
  } catch (e) {
    if (e !== "cancel") ElMessage.error("删除失败");
  }
}

function openDetail(run) {
  detailRun.value = run;
  detailDialog.value = true;
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
    ElMessage.success("Hook 视频已上传，可点「继续」");
    hookDialog.value = false;
    await loadRuns();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "上传失败");
  } finally {
    uploading.value = false;
  }
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
  pollTimer = setInterval(() => { if (props.view === "flow3-tasks" && taskMode.value === "list") loadRuns(); }, 4000);
}
function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

// ================= Agent =================
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

// ================= Hook 分组 =================
async function loadGroups() {
  try {
    const { data } = await axios.get("/api/flow3-material-groups/");
    groups.value = Array.isArray(data) ? data : data.results || [];
  } catch { /* 忽略 */ }
}
function openGroupNew() {
  groupEditing.value = null; groupName.value = ""; groupDialog.value = true;
}
function openGroupEdit(g) {
  groupEditing.value = g; groupName.value = g.name; groupDialog.value = true;
}
async function saveGroup() {
  const name = groupName.value.trim();
  if (!name) return ElMessage.warning("请输入分组名");
  try {
    if (groupEditing.value) await axios.patch(`/api/flow3-material-groups/${groupEditing.value.id}/`, { name });
    else await axios.post("/api/flow3-material-groups/", { name });
    ElMessage.success("已保存分组");
    groupDialog.value = false;
    await loadGroups();
  } catch (e) {
    ElMessage.error(e.response?.data ? JSON.stringify(e.response.data) : "保存分组失败");
  }
}
async function deleteGroup(g) {
  if (g.is_default) return ElMessage.warning("默认分组不可删除");
  try {
    await ElMessageBox.confirm(`删除分组「${g.name}」？组内素材将转入默认分组。`, "确认", { type: "warning" });
    await axios.delete(`/api/flow3-material-groups/${g.id}/`);
    ElMessage.success("已删除分组");
    if (currentGroupFilter.value === g.id) currentGroupFilter.value = null;
    await loadGroups(); await loadMaterials();
  } catch (e) {
    if (e !== "cancel") ElMessage.error(e.response?.data?.detail || "删除失败");
  }
}

// ================= 素材库 =================
async function loadMaterials() {
  materialLoading.value = true;
  try {
    const hookParams = { type: "hook", page_size: 500 };
    if (currentGroupFilter.value) hookParams.group = currentGroupFilter.value;
    const [s, b, h] = await Promise.all([
      axios.get("/api/flow3-materials/", { params: { type: "screen_record", page_size: 100 } }),
      axios.get("/api/flow3-materials/", { params: { type: "bgm", page_size: 100 } }),
      axios.get("/api/flow3-materials/", { params: hookParams }),
    ]);
    screenMaterials.value = s.data.results || s.data;
    bgmMaterials.value = b.data.results || b.data;
    hookMaterials.value = h.data.results || h.data;
  } catch {
    ElMessage.error("加载素材失败");
  } finally {
    materialLoading.value = false;
  }
}
// 单个上传（录屏/BGM 沿用）
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
// Hook 批量上传（多个 mp4），归属 uploadGroup（空则后端落默认分组）
async function batchUploadHook(uploadFile) {
  const fd = new FormData();
  fd.append("material_type", "hook");
  fd.append("files", uploadFile.raw);
  if (uploadGroup.value) fd.append("group", uploadGroup.value);
  try {
    await axios.post("/api/flow3-materials/batch_upload/", fd);
    ElMessage.success(`已上传 ${uploadFile.name}`);
    await loadGroups(); await loadMaterials();
  } catch (e) {
    ElMessage.error(e.response?.data ? JSON.stringify(e.response.data) : "上传失败");
  }
}
// 录屏批量上传
async function batchUploadScreen(uploadFile) {
  const fd = new FormData();
  fd.append("material_type", "screen_record");
  fd.append("files", uploadFile.raw);
  try {
    await axios.post("/api/flow3-materials/batch_upload/", fd);
    ElMessage.success(`已上传 ${uploadFile.name}`);
    await loadMaterials();
  } catch (e) {
    ElMessage.error(e.response?.data ? JSON.stringify(e.response.data) : "上传失败");
  }
}
function onScreenSelectionChange(rows) {
  selectedScreenIds.value = rows.map((r) => r.id);
}
async function bulkDeleteScreen() {
  if (!selectedScreenIds.value.length) return ElMessage.warning("请先勾选要删除的录屏素材");
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedScreenIds.value.length} 个录屏素材？`, "确认删除", { type: "warning" });
    await axios.post("/api/flow3-materials/bulk_delete/", { ids: selectedScreenIds.value });
    ElMessage.success("已删除");
    selectedScreenIds.value = [];
    await loadMaterials();
  } catch (e) {
    if (e !== "cancel") ElMessage.error(e.response?.data?.detail || "删除失败");
  }
}
function onHookSelectionChange(rows) {
  selectedHookIds.value = rows.map((r) => r.id);
}
async function bulkDeleteHook() {
  if (!selectedHookIds.value.length) return ElMessage.warning("请先勾选要删除的 Hook 素材");
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedHookIds.value.length} 个 Hook 素材？`, "确认删除", { type: "warning" });
    await axios.post("/api/flow3-materials/bulk_delete/", { ids: selectedHookIds.value });
    ElMessage.success("已删除");
    selectedHookIds.value = [];
    await loadMaterials();
  } catch (e) {
    if (e !== "cancel") ElMessage.error(e.response?.data?.detail || "删除失败");
  }
}
async function updateHookTag(m, tag) {
  try {
    await axios.patch(`/api/flow3-materials/${m.id}/`, { tag });
    ElMessage.success("标签已更新");
    await loadMaterials();
  } catch {
    ElMessage.error("更新标签失败");
  }
}
// 单个素材改分组
async function updateHookGroup(m, group) {
  try {
    await axios.patch(`/api/flow3-materials/${m.id}/`, { group });
    ElMessage.success("分组已更新");
    await loadGroups(); await loadMaterials();
  } catch {
    ElMessage.error("更新分组失败");
  }
}
// 批量移动分组
function openMoveDialog() {
  if (!selectedHookIds.value.length) return ElMessage.warning("请先勾选要移动的 Hook 素材");
  moveTargetGroup.value = null;
  moveDialog.value = true;
}
async function saveMove() {
  if (!moveTargetGroup.value) return ElMessage.warning("请选择目标分组");
  try {
    await Promise.all(selectedHookIds.value.map((id) =>
      axios.patch(`/api/flow3-materials/${id}/`, { group: moveTargetGroup.value })));
    ElMessage.success(`已移动 ${selectedHookIds.value.length} 个素材`);
    moveDialog.value = false;
    selectedHookIds.value = [];
    await loadGroups(); await loadMaterials();
  } catch {
    ElMessage.error("移动失败");
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
// 任务创建时加载 hook 素材供下拉选择
async function loadHookOptions() {
  try {
    const { data } = await axios.get("/api/flow3-materials/", { params: { type: "hook", page_size: 500 } });
    hookMaterials.value = data.results || data;
  } catch { /* 忽略 */ }
}
// 任务创建时加载录屏素材供下拉选择
async function loadScreenOptions() {
  try {
    const { data } = await axios.get("/api/flow3-materials/", { params: { type: "screen_record", page_size: 200 } });
    screenMaterials.value = data.results || data;
  } catch { /* 忽略 */ }
}
// 创建界面：按所选分组过滤可选 hook 素材（单选模式用）
function hookOptionsInGroup() {
  if (!form.value.hook_group) return hookMaterials.value;
  return hookMaterials.value.filter((h) => h.group === form.value.hook_group);
}

// ================= 重试 =================
async function retryRun(run) {
  try {
    await axios.post(`/api/flow3-runs/${run.id}/retry/`);
    ElMessage.success("已重试，从失败步骤继续");
    await loadRuns();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "重试失败");
  }
}
async function bulkRetry() {
  const ids = selectedIds.value;
  if (!ids.length) return ElMessage.warning("请先勾选要重试的失败任务");
  try {
    const { data } = await axios.post("/api/flow3-runs/bulk_retry/", { ids });
    ElMessage.success(data.detail || "已重试");
    selectedIds.value = [];
    await loadRuns();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "重试失败");
  }
}

// ================= Agent 试运行 =================
function agentInput(id) {
  if (!agentRunInput.value[id]) {
    agentRunInput.value[id] = { keyword: "", promo_code: "", country: "IN", repeat: 1 };
  }
  return agentRunInput.value[id];
}
async function runAgentOnce(agent) {
  const inp = agentInput(agent.id);
  if (!inp.keyword.trim()) return ElMessage.warning("请填写关键词");
  agentRunning.value = { ...agentRunning.value, [agent.id]: true };
  try {
    const { data } = await axios.post(`/api/flow3-agents/${agent.id}/run_once/`, inp);
    // 结果不塞进卡片，改用右侧抽屉展示，避免 Agent 列表被撑长。
    agentDrawerTitle.value = `${agent.name} · 试运行结果`;
    agentDrawerResult.value = data;
    agentDrawer.value = true;
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "运行失败");
  } finally {
    agentRunning.value = { ...agentRunning.value, [agent.id]: false };
  }
}
function copyText(t) {
  navigator.clipboard?.writeText(t).then(() => ElMessage.success("已复制"), () => {});
}

// 首次 + 切换 view 时按需加载
function loadForView(v) {
  if (v === "flow3-tasks") { taskMode.value = "list"; loadRuns(1); loadGroups(); }
  else if (v === "flow3-agents") loadAgents();
  else if (v === "flow3-materials") { loadGroups(); loadMaterials(); }
}
onMounted(() => loadForView(props.view));
watch(() => props.view, (v) => { stopPoll(); loadForView(v); });
onUnmounted(() => stopPoll());
</script>

<template>
  <!-- ============ 任务管理 ============ -->
  <div v-if="view === 'flow3-tasks'">
    <!-- 列表视图 -->
    <template v-if="taskMode === 'list'">
      <el-card shadow="never" class="toolbar-card">
        <div class="toolbar">
          <div class="toolbar-left">
            <el-button type="primary" @click="openCreate">新增任务</el-button>
            <el-button type="warning" plain :disabled="!selectedIds.length" @click="bulkRetry">
              重试{{ selectedIds.length ? `(${selectedIds.length})` : '' }}
            </el-button>
            <el-button type="danger" plain :disabled="!selectedIds.length" @click="bulkDelete">
              删除{{ selectedIds.length ? `(${selectedIds.length})` : '' }}
            </el-button>
          </div>
          <div class="toolbar-right">
            <el-input v-model="runSearch" clearable placeholder="按任务名 / 关键词搜索" style="width: 240px"
                      @keyup.enter="loadRuns(1)" @clear="loadRuns(1)" />
            <el-button @click="loadRuns(1)">查询</el-button>
            <el-button @click="loadRuns()">刷新</el-button>
          </div>
        </div>
      </el-card>

      <el-card shadow="never" class="table-card">
        <el-table :data="runs" size="small" empty-text="暂无任务，点「新增任务」创建" @selection-change="onSelectionChange">
          <el-table-column type="selection" width="44" />
          <el-table-column prop="name" label="任务名" min-width="120"><template #default="{ row }">{{ row.name || '—' }}</template></el-table-column>
          <el-table-column prop="keyword" label="关键词" min-width="160" />
          <el-table-column prop="promo_code" label="优惠码" width="100" />
          <el-table-column label="总时长" width="80"><template #default="{ row }">{{ row.total_duration }}s</template></el-table-column>
          <el-table-column label="状态" width="120"><template #default="{ row }"><el-tag :type="statusType(row.status)" size="small" effect="light">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
          <el-table-column label="开始时间" min-width="150"><template #default="{ row }">{{ datetime(row.started_at) }}</template></el-table-column>
          <el-table-column label="结束时间" min-width="150"><template #default="{ row }">{{ datetime(row.finished_at) }}</template></el-table-column>
          <el-table-column label="耗时" width="90"><template #default="{ row }">{{ formatDuration(row.duration_seconds) }}</template></el-table-column>
          <el-table-column label="操作" width="360" fixed="right"><template #default="{ row }">
            <el-button v-if="row.status === 'awaiting_hook'" size="small" type="warning" @click="openHookUpload(row)">上传Hook</el-button>
            <el-button v-if="row.status === 'awaiting_hook' && row.hook_video_url" size="small" type="primary" @click="controlRun(row, 'resume')">继续</el-button>
            <el-button v-if="row.status === 'failed'" size="small" type="warning" @click="retryRun(row)">重试</el-button>
            <el-button size="small" plain @click="openDetail(row)">详情</el-button>
            <el-button size="small" type="success" plain :disabled="row.status !== 'completed'" @click="downloadPackage(row)">下载</el-button>
            <el-button size="small" type="info" plain @click="openLog(row)">日志</el-button>
            <el-button size="small" type="danger" plain @click="deleteOne(row)">删除</el-button>
          </template></el-table-column>
        </el-table>
        <el-pagination v-model:current-page="runPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="runTotal" @current-change="loadRuns" />
      </el-card>
    </template>

    <!-- 新增任务界面 -->
    <template v-else>
      <el-page-header class="create-header" content="新增流程3 任务" @back="taskMode = 'list'">
        <template #title>返回列表</template>
      </el-page-header>
      <el-alert
        title="三段式长视频（16:9 1080P）"
        description="选用/随机到 Hook 素材库的素材时，任务直接出片。若库中无可用素材，则生成 Hook Prompt 并暂停等待人工上传 Hook 视频，上传后点「继续」自动完成后续。"
        type="info" :closable="false" show-icon class="flow3-intro" />
      <el-card shadow="never" class="create-card">
        <el-form label-width="96px" style="max-width: 680px">
          <el-form-item label="任务名"><el-input v-model="form.name" placeholder="选填备注" /></el-form-item>
          <el-form-item label="关键词" required><el-input v-model="form.keyword" placeholder="仅 1 个，如 1xbet promo code" /></el-form-item>
          <el-form-item label="优惠码"><el-input v-model="form.promo_code" placeholder="如 ZH567" /></el-form-item>
          <el-form-item label="总时长(秒)"><el-input-number v-model="form.total_duration" :min="30" :max="600" :step="10" /></el-form-item>
          <el-form-item label="国家"><el-input v-model="form.country" style="width: 160px" /></el-form-item>
          <el-form-item label="语言"><el-input v-model="form.language" style="width: 160px" placeholder="en-IN" /></el-form-item>
          <el-form-item label="录屏素材">
            <el-select v-model="form.screen_material" clearable filterable placeholder="不选=随机取一个启用的录屏" style="width: 360px">
              <el-option v-for="s in screenMaterials" :key="s.id" :label="s.name || ('录屏#'+s.id)" :value="s.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="Hook 分组" required>
            <el-select v-model="form.hook_group" placeholder="必选：随机/批量只在该分组内取素材" style="width: 360px">
              <el-option v-for="g in groups" :key="g.id"
                :label="`${g.name}（可用 ${g.unused_count||0}）`" :value="g.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="生成数量">
            <el-input-number v-model="form.count" :min="1" :max="Math.max(1, groupUnusedCount(form.hook_group))" />
            <span class="form-hint" style="margin-left:10px">
              当前分组可用未使用 Hook 素材 {{ groupUnusedCount(form.hook_group) }} 个；
              数量>1 为批量生成（强制随机，最多 {{ groupUnusedCount(form.hook_group) }} 个）。
            </span>
          </el-form-item>
          <el-form-item v-if="(form.count || 1) === 1" label="Hook 素材">
            <el-select v-model="form.hook_material" clearable filterable placeholder="不选=在所选分组内随机取未使用素材" style="width: 360px">
              <el-option v-for="h in hookOptionsInGroup()" :key="h.id"
                :label="`${h.name || ('素材#'+h.id)}（${h.tag_label || (h.tag === 'used' ? '已使用' : '未使用')}）`"
                :value="h.id" />
            </el-select>
            <div class="form-hint">
              从所选分组按文件名选择；不选则在该分组内随机取「未使用」素材。
              <strong>选中或随机到素材后直接出片，无需上传 Hook 视频</strong>；分组内无可用素材将无法创建任务。
            </div>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="creating" @click="createRun">创建任务</el-button>
            <el-button @click="taskMode = 'list'">取消</el-button>
          </el-form-item>
        </el-form>
      </el-card>
    </template>
  </div>

  <!-- ============ Agent 管理 ============ -->
  <div v-else-if="view === 'flow3-agents'">
    <el-alert title="流程3 Agent 管理" description="流程3 使用独立的一组 Agent。支持 {PROMO_CODE}/{COUNTRY}/{EVENT_NAME} 全局占位符，[input] 为关键词。" type="success" :closable="false" show-icon class="flow3-intro" />
    <div v-loading="agentLoading">
      <!-- 折叠式：默认收起，点击某个 Agent 才展开其提示词与试运行区 -->
      <el-collapse class="agent-collapse">
        <el-collapse-item v-for="agent in agents" :key="agent.id" :name="agent.id">
          <template #title>
            <div class="agent-title-row">
              <el-tag size="small" type="warning" effect="plain">{{ agent.agent_type_label }}</el-tag>
              <strong class="agent-card-name">{{ agent.name }}</strong>
              <span class="agent-card-desc">{{ agent.description }}</span>
              <el-switch v-model="agent.enabled" active-text="启用" inactive-text="停用" inline-prompt size="small" @click.stop @change="saveAgent(agent)" />
            </div>
          </template>
          <el-form label-position="top">
            <el-form-item label="提示词（Prompt）">
              <el-input v-model="agent.prompt" type="textarea" :autosize="{ minRows: 8, maxRows: 26 }" placeholder="留空则使用系统内置默认提示词" />
            </el-form-item>
            <el-button type="primary" @click="saveAgent(agent)">保存</el-button>
            <el-button plain @click="resetAgent(agent)">恢复系统默认</el-button>
          </el-form>

          <!-- 试运行输入（结果在右侧抽屉展示，不撑长列表） -->
          <div class="agent-run">
            <div class="agent-run-title">试运行（调试用，不创建任务、不消耗素材；结果在右侧抽屉查看）</div>
            <div class="agent-run-inputs">
              <el-input v-model="agentInput(agent.id).keyword" size="small" placeholder="关键词（必填）" style="width: 220px" />
              <el-input v-model="agentInput(agent.id).promo_code" size="small" placeholder="优惠码" style="width: 130px" />
              <el-input v-model="agentInput(agent.id).country" size="small" placeholder="国家" style="width: 90px" />
              <el-input-number v-if="agent.agent_type === 'hook'" v-model="agentInput(agent.id).repeat" :min="1" :max="20" size="small" />
              <el-button type="success" size="small" :loading="agentRunning[agent.id]" @click="runAgentOnce(agent)">运行</el-button>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
      <el-empty v-if="!agentLoading && agents.length === 0" description="暂无 Agent" />
    </div>
  </div>

  <!-- ============ 素材库 ============ -->
  <div v-else-if="view === 'flow3-materials'">
    <el-alert title="流程3 素材库" description="Hook 视频：可批量上传 mp4，带「未使用/已使用」标签；创建任务时可指定或随机取未使用素材。9:16 录屏：库内保留 1 个，所有任务自动取用。BGM：可批量上传，任务执行时随机抽 1 个。" type="success" :closable="false" show-icon class="flow3-intro" />
    <div v-loading="materialLoading">
      <!-- Hook 视频库 -->
      <el-card shadow="never" class="table-card">
        <template #header>
          <div class="card-title">
            <strong>Hook 视频</strong>
            <div class="toolbar-left">
              <span class="form-hint">分组筛选：</span>
              <el-select v-model="currentGroupFilter" clearable placeholder="全部分组" size="small" style="width: 160px" @change="loadMaterials">
                <el-option v-for="g in groups" :key="g.id" :label="`${g.name}(${g.material_count||0})`" :value="g.id" />
              </el-select>
              <el-button size="small" @click="openGroupNew">新建分组</el-button>
              <el-button size="small" :disabled="!selectedHookIds.length" @click="openMoveDialog">移动到分组{{ selectedHookIds.length ? `(${selectedHookIds.length})` : '' }}</el-button>
              <el-button type="danger" plain size="small" :disabled="!selectedHookIds.length" @click="bulkDeleteHook">删除{{ selectedHookIds.length ? `(${selectedHookIds.length})` : '' }}</el-button>
              <span class="form-hint" style="margin-left:8px">上传到：</span>
              <el-select v-model="uploadGroup" clearable placeholder="默认分组" size="small" style="width: 150px">
                <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
              </el-select>
              <el-upload :auto-upload="true" :show-file-list="false" accept="video/*" :multiple="true" :http-request="({ file }) => batchUploadHook({ raw: file, name: file.name })">
                <el-button type="primary" size="small">批量上传 Hook</el-button>
              </el-upload>
            </div>
          </div>
          <!-- 分组管理行 -->
          <div class="group-chips">
            <el-tag v-for="g in groups" :key="g.id" :type="g.is_default ? 'info' : 'primary'" effect="plain"
              :closable="!g.is_default" size="small" class="group-chip"
              @close="deleteGroup(g)" @click="!g.is_default && openGroupEdit(g)">
              {{ g.name }}（{{ g.material_count || 0 }}，可用 {{ g.unused_count || 0 }}）
            </el-tag>
          </div>
        </template>
        <el-table :data="hookMaterials" size="small" empty-text="暂无 Hook 素材" @selection-change="onHookSelectionChange">
          <el-table-column type="selection" width="44" />
          <el-table-column prop="name" label="名称" min-width="180" />
          <el-table-column label="分组" width="150"><template #default="{ row }">
            <el-select :model-value="row.group" size="small" style="width: 130px" placeholder="默认分组" @change="(v) => updateHookGroup(row, v)">
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
          </template></el-table-column>
          <el-table-column label="时长" width="90"><template #default="{ row }">{{ row.duration ? row.duration + 's' : '—' }}</template></el-table-column>
          <el-table-column label="标签" width="140"><template #default="{ row }">
            <el-select :model-value="row.tag" size="small" style="width: 100px" @change="(v) => updateHookTag(row, v)">
              <el-option label="未使用" value="unused" />
              <el-option label="已使用" value="used" />
            </el-select>
          </template></el-table-column>
          <el-table-column label="预览" width="80"><template #default="{ row }"><a v-if="row.file_url" :href="row.file_url" target="_blank">查看</a></template></el-table-column>
          <el-table-column label="操作" width="90"><template #default="{ row }"><el-button size="small" type="danger" plain @click="deleteMaterial(row)">删除</el-button></template></el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never" class="table-card">
        <template #header><div class="card-title"><strong>9:16 手机录屏</strong>
          <div class="toolbar-left">
            <el-button type="danger" plain size="small" :disabled="!selectedScreenIds.length" @click="bulkDeleteScreen">删除{{ selectedScreenIds.length ? `(${selectedScreenIds.length})` : '' }}</el-button>
            <el-upload :auto-upload="true" :show-file-list="false" accept="video/*" :multiple="true" :http-request="({ file }) => batchUploadScreen({ raw: file, name: file.name })">
              <el-button type="primary" size="small">批量上传录屏</el-button>
            </el-upload>
          </div>
        </div></template>
        <el-table :data="screenMaterials" size="small" empty-text="暂无录屏素材" @selection-change="onScreenSelectionChange">
          <el-table-column type="selection" width="44" />
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
  </div>

  <!-- 详情弹窗 -->
  <el-dialog v-model="detailDialog" title="任务详情" width="720px" :destroy-on-close="true">
    <template v-if="detailRun">
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="任务名">{{ detailRun.name || '—' }}</el-descriptions-item>
        <el-descriptions-item label="状态"><el-tag :type="statusType(detailRun.status)" size="small">{{ statusLabel(detailRun.status) }}</el-tag></el-descriptions-item>
        <el-descriptions-item label="关键词">{{ detailRun.keyword }}</el-descriptions-item>
        <el-descriptions-item label="优惠码">{{ detailRun.promo_code }}</el-descriptions-item>
        <el-descriptions-item label="总时长">{{ detailRun.total_duration }}s</el-descriptions-item>
        <el-descriptions-item label="国家">{{ detailRun.country }}</el-descriptions-item>
        <el-descriptions-item label="标题" :span="2">{{ detailRun.title || '—' }}</el-descriptions-item>
        <el-descriptions-item label="描述" :span="2">{{ detailRun.description || '—' }}</el-descriptions-item>
        <el-descriptions-item v-if="detailRun.error_message" label="错误" :span="2"><span style="color:#f56c6c">{{ detailRun.error_message }}</span></el-descriptions-item>
      </el-descriptions>
      <div v-if="detailRun.hook_prompt" class="detail-block">
        <strong>Hook Prompt（复制去外部视频引擎生成）</strong>
        <pre class="log-pre">{{ detailRun.hook_prompt }}</pre>
      </div>
      <div v-if="detailRun.rendered_url" class="detail-block">
        <strong>成品视频</strong><br>
        <video :src="detailRun.rendered_url" controls style="max-width:100%; max-height:360px; margin-top:8px" />
      </div>
    </template>
  </el-dialog>

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
            :type="step.status === 'success' ? 'success' : (step.status === 'failed' ? 'danger' : (step.status === 'skipped' ? 'info' : 'primary'))"
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

  <!-- 分组 新建/重命名 弹窗 -->
  <el-dialog v-model="groupDialog" :title="groupEditing ? '重命名分组' : '新建分组'" width="400px">
    <el-input v-model="groupName" placeholder="分组名称" />
    <template #footer>
      <el-button @click="groupDialog = false">取消</el-button>
      <el-button type="primary" @click="saveGroup">保存</el-button>
    </template>
  </el-dialog>

  <!-- 批量移动分组弹窗 -->
  <el-dialog v-model="moveDialog" title="移动到分组" width="420px">
    <p class="hint">将选中的 {{ selectedHookIds.length }} 个 Hook 素材移动到：</p>
    <el-select v-model="moveTargetGroup" placeholder="选择目标分组" style="width: 100%">
      <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
    </el-select>
    <template #footer>
      <el-button @click="moveDialog = false">取消</el-button>
      <el-button type="primary" @click="saveMove">移动</el-button>
    </template>
  </el-dialog>

  <!-- Agent 试运行结果抽屉 -->
  <el-drawer v-model="agentDrawer" :title="agentDrawerTitle" size="640px" :destroy-on-close="true">
    <div v-if="agentDrawerResult">
      <!-- hook：多条 prompt -->
      <template v-if="agentDrawerResult.prompts">
        <p class="hint">共 {{ agentDrawerResult.prompts.length }} 条 Hook Prompt：</p>
        <div v-for="(p, i) in agentDrawerResult.prompts" :key="i" class="run-prompt">
          <div class="run-prompt-head">#{{ i + 1 }} <el-button link type="primary" size="small" @click="copyText(p)">复制</el-button></div>
          <pre class="log-pre">{{ p }}</pre>
        </div>
      </template>
      <template v-else-if="agentDrawerResult.narration">
        <p class="hint">旁白分段：</p>
        <pre class="log-pre">{{ JSON.stringify(agentDrawerResult.narration.shots, null, 2) }}</pre>
      </template>
      <template v-else-if="agentDrawerResult.metadata">
        <p class="hint">元数据：</p>
        <pre class="log-pre">{{ JSON.stringify(agentDrawerResult.metadata, null, 2) }}</pre>
      </template>
      <template v-else-if="agentDrawerResult.image_prompt">
        <div class="run-prompt-head">生图 Prompt <el-button link type="primary" size="small" @click="copyText(agentDrawerResult.image_prompt)">复制</el-button></div>
        <pre class="log-pre">{{ agentDrawerResult.image_prompt }}</pre>
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.flow3-intro { margin-bottom: 16px; }
.toolbar-card, .create-card, .table-card { margin-bottom: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; }
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; }
.card-title { display: flex; justify-content: space-between; align-items: center; }
.pagination { margin-top: 12px; justify-content: flex-end; }
.create-header { margin-bottom: 16px; }
.agent-card { margin-bottom: 16px; }
.agent-card-head { display: flex; justify-content: space-between; align-items: center; }
.agent-card-meta { display: flex; align-items: center; gap: 10px; }
.agent-card-name { font-size: 15px; }
.agent-card-desc { color: #8a949c; font-size: 13px; }
.agent-collapse { background: transparent; }
.agent-title-row { display: flex; align-items: center; gap: 10px; width: 100%; }
.agent-title-row .agent-card-desc { flex: 1; }
.detail-block { margin-top: 14px; }
.log-pre { white-space: pre-wrap; word-break: break-word; background: #0f1621; color: #c8d3de; padding: 10px; border-radius: 6px; font-size: 12px; max-height: 300px; overflow: auto; }
.log-collapse { margin-top: 8px; }
.log-err { color: #f56c6c; font-size: 13px; margin-top: 4px; }
.hint { color: #8a949c; font-size: 13px; margin-bottom: 10px; }
.form-hint { color: #8a949c; font-size: 12px; line-height: 1.5; margin-top: 4px; }
.group-chips { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 8px; }
.group-chip { cursor: pointer; }
.agent-run { margin-top: 14px; padding-top: 14px; border-top: 1px dashed #d8dee6; }
.agent-run-title { font-size: 13px; color: #8a949c; margin-bottom: 8px; }
.agent-run-inputs { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.agent-run-result { margin-top: 10px; }
.run-prompt { margin-bottom: 8px; }
.run-prompt-head { font-size: 12px; color: #8a949c; display: flex; align-items: center; gap: 6px; }
</style>