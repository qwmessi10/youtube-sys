<script setup>
// AdsPower 自动化上传系统。由 App.vue 二级菜单通过 view 控制：
//   adspower-browsers=浏览器管理 / adspower-tasks=任务管理
import { onMounted, ref, watch } from "vue";
import axios from "axios";
import { ElMessage, ElMessageBox } from "element-plus";

const props = defineProps({ view: { type: String, default: "adspower-browsers" } });

// —— 浏览器管理 ——
const profiles = ref([]);
const profileTotal = ref(0);
const profilePage = ref(1);
const profileSearch = ref("");
const groupFilter = ref("");
const groups = ref([]);
const profileLoading = ref(false);
const syncing = ref(false);
const detailDialog = ref(false);
const detailData = ref(null);

// —— 任务管理 ——
const tasks = ref([]);
const taskTotal = ref(0);
const taskPage = ref(1);
const statusFilter = ref("");
const taskLoading = ref(false);
const taskMode = ref("list");       // list | create
const creating = ref(false);
const form = ref({ title: "", description: "", profile: "", video_path: "", publish_mode: "draft" });
const videoFile = ref(null);
const coverFile = ref(null);
const logDrawer = ref(false);
const logTask = ref(null);

const statusMeta = {
  queued: { label: "排队中", type: "info" },
  launching: { label: "启动浏览器", type: "warning" },
  uploading: { label: "上传中", type: "warning" },
  draft_saved: { label: "草稿已保存", type: "success" },
  publishing: { label: "发布中", type: "warning" },
  completed: { label: "已完成", type: "success" },
  failed: { label: "失败", type: "danger" },
};
const statusLabel = (s) => statusMeta[s]?.label || s;
const statusType = (s) => statusMeta[s]?.type || "info";

function datetime(v) {
  return v ? new Date(v).toLocaleString("zh-CN", { hour12: false }) : "—";
}
function tsToDate(ts) {
  if (!ts) return "—";
  const n = Number(ts);
  return n ? new Date(n * 1000).toLocaleString("zh-CN", { hour12: false }) : "—";
}

// ========================= 浏览器管理 =========================
async function loadProfiles(page = profilePage.value) {
  profilePage.value = page;
  profileLoading.value = true;
  try {
    const { data } = await axios.get("/api/adspower-profiles/", {
      params: { page, search: profileSearch.value, group_id: groupFilter.value },
    });
    profiles.value = data.results;
    profileTotal.value = data.count;
  } catch {
    ElMessage.error("加载浏览器列表失败");
  } finally {
    profileLoading.value = false;
  }
}

async function loadGroups() {
  try {
    const { data } = await axios.get("/api/adspower-profiles/groups/");
    groups.value = Array.isArray(data) ? data : [];
  } catch { /* 限频或离线时静默，不影响列表 */ }
}

async function syncProfiles() {
  syncing.value = true;
  try {
    const { data } = await axios.post("/api/adspower-profiles/sync/");
    ElMessage.success(`已同步 ${data.synced} 个浏览器环境`);
    await loadProfiles(1);
    setTimeout(loadGroups, 1200);   // 错开 AdsPower 每秒限频
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "同步失败，请确认 AdsPower 客户端已开启本地 API");
  } finally {
    syncing.value = false;
  }
}

function openDetail(row) {
  detailData.value = row;
  detailDialog.value = true;
}

async function openBrowser(row) {
  try {
    await axios.post(`/api/adspower-profiles/${row.user_id}/open/`);
    ElMessage.success(`已启动浏览器「${row.name}」`);
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "启动失败");
  }
}

async function closeBrowser(row) {
  try {
    await axios.post(`/api/adspower-profiles/${row.user_id}/close/`);
    ElMessage.success("已关闭浏览器");
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "关闭失败");
  }
}

// ========================= 任务管理 =========================
async function loadTasks(page = taskPage.value) {
  taskPage.value = page;
  taskLoading.value = true;
  try {
    const { data } = await axios.get("/api/upload-tasks/", {
      params: { page, status: statusFilter.value },
    });
    tasks.value = data.results;
    taskTotal.value = data.count;
  } catch {
    ElMessage.error("加载任务列表失败");
  } finally {
    taskLoading.value = false;
  }
}

function openCreate() {
  form.value = { title: "", description: "", profile: "", video_path: "", publish_mode: "draft" };
  videoFile.value = null;
  coverFile.value = null;
  // 新建任务需要浏览器下拉，确保已加载
  if (!profiles.value.length) loadProfiles(1);
  taskMode.value = "create";
}

async function createTask() {
  if (!form.value.title.trim()) return ElMessage.warning("请输入标题");
  if (!form.value.profile) return ElMessage.warning("请选择目标浏览器");
  if (!videoFile.value && !form.value.video_path.trim()) return ElMessage.warning("请上传视频或填写视频路径");
  creating.value = true;
  try {
    const fd = new FormData();
    fd.append("title", form.value.title);
    fd.append("description", form.value.description);
    fd.append("profile", form.value.profile);
    fd.append("publish_mode", form.value.publish_mode);
    if (form.value.video_path.trim()) fd.append("video_path", form.value.video_path);
    if (videoFile.value) fd.append("video_file", videoFile.value);
    if (coverFile.value) fd.append("cover_file", coverFile.value);
    await axios.post("/api/upload-tasks/", fd);
    ElMessage.success("任务已创建，进入排队");
    taskMode.value = "list";
    await loadTasks(1);
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "创建任务失败");
  } finally {
    creating.value = false;
  }
}

async function retryTask(row) {
  try {
    await axios.post(`/api/upload-tasks/${row.id}/retry/`);
    ElMessage.success("已重新排队");
    await loadTasks();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "重试失败");
  }
}

async function deleteTask(row) {
  try {
    await ElMessageBox.confirm(`确定删除任务「${row.name || row.title}」？`, "确认删除", { type: "warning" });
    await axios.delete(`/api/upload-tasks/${row.id}/`);
    ElMessage.success("已删除");
    await loadTasks();
  } catch (e) {
    if (e !== "cancel") ElMessage.error("删除失败");
  }
}

function openLog(row) {
  logTask.value = row;
  logDrawer.value = true;
}

function onVideoChange(file) { videoFile.value = file.raw; }
function onCoverChange(file) { coverFile.value = file.raw; }

onMounted(() => {
  if (props.view === "adspower-tasks") loadTasks(1);
  else { loadProfiles(1); loadGroups(); }
});

watch(() => props.view, (v) => {
  if (v === "adspower-tasks") loadTasks(1);
  else { loadProfiles(1); loadGroups(); }
});
</script>
<template>
  <!-- ==================== 浏览器管理 ==================== -->
  <template v-if="view === 'adspower-browsers'">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <el-button type="primary" :loading="syncing" @click="syncProfiles">同步 AdsPower 环境</el-button>
          <el-select v-model="groupFilter" placeholder="全部分组" clearable style="width: 180px" @change="loadProfiles(1)">
            <el-option v-for="g in groups" :key="g.group_id" :label="g.group_name" :value="g.group_id" />
          </el-select>
        </div>
        <div class="toolbar-right">
          <el-input v-model="profileSearch" clearable placeholder="按名称搜索" style="width: 200px" @keyup.enter="loadProfiles(1)" @clear="loadProfiles(1)" />
          <el-button @click="loadProfiles(1)">查询</el-button>
          <el-button @click="loadProfiles()">刷新</el-button>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-alert title="环境数据来自 AdsPower 本地 API，点「同步」拉取最新列表。代理账号密码已脱敏。" type="info" :closable="false" class="note" />
      <el-table :data="profiles" v-loading="profileLoading" size="small" empty-text="暂无环境，点「同步 AdsPower 环境」拉取">
        <el-table-column prop="serial_number" label="编号" width="70" />
        <el-table-column prop="name" label="名称" min-width="120" />
        <el-table-column prop="group_name" label="分组" min-width="110" />
        <el-table-column prop="domain_name" label="绑定平台" min-width="150" show-overflow-tooltip />
        <el-table-column label="IP / 国家" min-width="150"><template #default="{ row }">{{ row.ip || "—" }} <el-tag v-if="row.ip_country" size="small" effect="plain">{{ row.ip_country.toUpperCase() }}</el-tag></template></el-table-column>
        <el-table-column prop="proxy_summary" label="代理" min-width="170" show-overflow-tooltip />
        <el-table-column label="最近打开" min-width="160"><template #default="{ row }">{{ tsToDate(row.last_open_time) }}</template></el-table-column>
        <el-table-column label="操作" width="260" fixed="right"><template #default="{ row }">
          <el-button size="small" type="primary" plain @click="openDetail(row)">详情</el-button>
          <el-button size="small" type="success" plain @click="openBrowser(row)">打开浏览器</el-button>
          <el-button size="small" plain @click="closeBrowser(row)">关闭</el-button>
        </template></el-table-column>
      </el-table>
      <el-pagination v-model:current-page="profilePage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="profileTotal" @current-change="loadProfiles" />
    </el-card>

    <el-dialog v-model="detailDialog" title="浏览器环境详情" width="640px">
      <template v-if="detailData">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="名称">{{ detailData.name }}</el-descriptions-item>
          <el-descriptions-item label="编号">{{ detailData.serial_number }}</el-descriptions-item>
          <el-descriptions-item label="环境 ID">{{ detailData.user_id }}</el-descriptions-item>
          <el-descriptions-item label="分组">{{ detailData.group_name }}</el-descriptions-item>
          <el-descriptions-item label="绑定平台">{{ detailData.domain_name || "—" }}</el-descriptions-item>
          <el-descriptions-item label="账号">{{ detailData.username || "—" }}</el-descriptions-item>
          <el-descriptions-item label="IP">{{ detailData.ip || "—" }}</el-descriptions-item>
          <el-descriptions-item label="国家">{{ (detailData.ip_country || "—").toUpperCase() }}</el-descriptions-item>
          <el-descriptions-item label="代理" :span="2">{{ detailData.proxy_summary }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ detailData.remark || "—" }}</el-descriptions-item>
        </el-descriptions>
        <el-collapse class="detail-collapse">
          <el-collapse-item title="原始环境数据（raw，代理密码已脱敏）" name="raw">
            <pre class="log-pre">{{ JSON.stringify(detailData.raw, null, 2) }}</pre>
          </el-collapse-item>
        </el-collapse>
      </template>
    </el-dialog>
  </template>

  <!-- ==================== 任务管理 ==================== -->
  <template v-else>
    <template v-if="taskMode === 'create'">
      <el-page-header class="create-header" content="新建上传任务" @back="taskMode = 'list'"><template #title>返回列表</template></el-page-header>
      <el-card class="create-card" shadow="never">
        <el-form label-width="110px" style="max-width: 720px">
          <el-form-item label="标题" required><el-input v-model="form.title" placeholder="YouTube 视频标题" /></el-form-item>
          <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="视频描述" /></el-form-item>
          <el-form-item label="目标浏览器" required>
            <el-select v-model="form.profile" filterable placeholder="选择 AdsPower 环境" style="width: 360px">
              <el-option v-for="p in profiles" :key="p.user_id" :label="`${p.serial_number} · ${p.name}（${p.proxy_summary}）`" :value="p.user_id" />
            </el-select>
          </el-form-item>
          <el-form-item label="视频文件"><el-upload :auto-upload="false" :limit="1" :on-change="onVideoChange" accept="video/mp4"><el-button>选择 mp4</el-button><template #tip><span class="up-tip">或在下方填写已有成品路径</span></template></el-upload></el-form-item>
          <el-form-item label="视频路径"><el-input v-model="form.video_path" placeholder="如 flow3/rendered/1_final.mp4（与上传二选一）" /></el-form-item>
          <el-form-item label="封面图"><el-upload :auto-upload="false" :limit="1" :on-change="onCoverChange" accept="image/*"><el-button>选择封面</el-button></el-upload></el-form-item>
          <el-form-item label="发布模式">
            <el-select v-model="form.publish_mode" style="width: 260px">
              <el-option label="仅存草稿（不发布）" value="draft" />
              <el-option label="公开" value="public" disabled />
              <el-option label="不公开" value="unlisted" disabled />
              <el-option label="私享" value="private" disabled />
            </el-select>
            <small class="up-tip">开发阶段仅支持存草稿，人工核对后再发布</small>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="creating" @click="createTask">创建任务</el-button>
            <el-button @click="taskMode = 'list'">取消</el-button>
          </el-form-item>
        </el-form>
      </el-card>
    </template>

    <template v-else>
      <el-card shadow="never" class="toolbar-card">
        <div class="toolbar">
          <div class="toolbar-left">
            <el-button type="primary" @click="openCreate">新建任务</el-button>
            <el-select v-model="statusFilter" placeholder="全部状态" clearable style="width: 150px" @change="loadTasks(1)">
              <el-option v-for="(m, k) in statusMeta" :key="k" :label="m.label" :value="k" />
            </el-select>
          </div>
          <div class="toolbar-right"><el-button @click="loadTasks()">刷新</el-button></div>
        </div>
      </el-card>

      <el-card shadow="never" class="table-card">
        <el-alert title="开发阶段任务执行到「草稿已保存」为止，请到对应浏览器的 YouTube Studio 核对后手动发布。" type="warning" :closable="false" class="note" />
        <el-table :data="tasks" v-loading="taskLoading" size="small" empty-text="暂无任务">
          <el-table-column label="任务 / 标题" min-width="200"><template #default="{ row }"><div>{{ row.name || row.title }}</div><small class="sub">{{ row.source_run_keyword ? `来自内容任务：${row.source_run_keyword}` : "手动创建" }}</small></template></el-table-column>
          <el-table-column label="目标浏览器" min-width="140"><template #default="{ row }">{{ row.profile_serial }} · {{ row.profile_name }}</template></el-table-column>
          <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="statusType(row.status)" size="small" effect="light">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
          <el-table-column label="视频链接" min-width="180"><template #default="{ row }"><a v-if="row.video_url" :href="row.video_url" target="_blank" rel="noreferrer">打开</a><span v-else>—</span></template></el-table-column>
          <el-table-column label="创建时间" min-width="160"><template #default="{ row }">{{ datetime(row.created_at) }}</template></el-table-column>
          <el-table-column label="操作" width="230" fixed="right"><template #default="{ row }">
            <el-button size="small" type="info" plain @click="openLog(row)">日志</el-button>
            <el-button size="small" type="primary" plain :disabled="row.status !== 'failed'" @click="retryTask(row)">重试</el-button>
            <el-button size="small" type="danger" plain @click="deleteTask(row)">删除</el-button>
          </template></el-table-column>
        </el-table>
        <el-pagination v-model:current-page="taskPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="taskTotal" @current-change="loadTasks" />
      </el-card>
    </template>

    <el-drawer v-model="logDrawer" title="上传日志" size="600px" :destroy-on-close="true">
      <template v-if="logTask">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="任务">{{ logTask.name || logTask.title }}</el-descriptions-item>
          <el-descriptions-item label="状态"><el-tag :type="statusType(logTask.status)" size="small">{{ statusLabel(logTask.status) }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="视频链接"><a v-if="logTask.video_url" :href="logTask.video_url" target="_blank">{{ logTask.video_url }}</a><span v-else>—</span></el-descriptions-item>
          <el-descriptions-item v-if="logTask.error_message" label="错误">{{ logTask.error_message }}</el-descriptions-item>
        </el-descriptions>
        <el-divider content-position="left">执行步骤</el-divider>
        <el-timeline v-if="logTask.upload_log && logTask.upload_log.steps && logTask.upload_log.steps.length">
          <el-timeline-item v-for="(s, i) in logTask.upload_log.steps" :key="i" :timestamp="datetime(s.ts)">
            <strong>{{ s.step }}</strong> {{ s.note }}
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无步骤日志" :image-size="60" />
      </template>
    </el-drawer>
  </template>
</template>

<style scoped>
.toolbar-card { margin-bottom: 12px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; }
.table-card { margin-bottom: 12px; }
.note { margin-bottom: 12px; }
.pagination { margin-top: 12px; justify-content: flex-end; }
.create-header { margin-bottom: 12px; }
.sub { color: #8a98a8; }
.up-tip { color: #8a98a8; margin-left: 8px; }
.detail-collapse { margin-top: 12px; }
.log-pre { white-space: pre-wrap; word-break: break-all; font-size: 12px; max-height: 360px; overflow: auto; background: #0d1620; color: #b6c5d4; padding: 10px; border-radius: 6px; }
</style>

