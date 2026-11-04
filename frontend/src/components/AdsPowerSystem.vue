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

// —— 环境增删改 + 分组 + IP 下拉 ——
const envDialog = ref(false);
const envSaving = ref(false);
const envEditMode = ref(false);     // true=编辑, false=新建
const envForm = ref({ user_id: "", name: "", group_id: "", domain_name: "", remark: "", proxy_id: null });
const proxyOptions = ref([]);        // IP 池下拉
const groupDialog = ref(false);
const groupSaving = ref(false);
const groupForm = ref({ group_id: "", group_name: "", remark: "", edit: false });
// 设置 IP 弹窗（下拉选 IP 池）
const setProxyDialog = ref(false);
const setProxySaving = ref(false);
const setProxyForm = ref({ user_id: "", name: "", proxy_id: null });

// —— IP 管理页 ——
const proxies = ref([]);
const proxyTotal = ref(0);
const proxyPage = ref(1);
const proxySearch = ref("");
const proxyLoading = ref(false);
const proxyImporting = ref(false);
const proxyAssignedFilter = ref("");
const proxyVerifying = ref(0);       // 正在验证的 IP id
const proxyDialog = ref(false);
const proxySaving = ref(false);
const proxyEditMode = ref(false);
const proxyForm = ref({ id: null, name: "", proxy_type: "socks5", proxy_host: "", proxy_port: "", proxy_user: "", proxy_password: "", remark: "" });

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

// —— 环境增删改 ——
async function loadProxyOptions() {
  try {
    const { data } = await axios.get("/api/adspower-proxies/", { params: { page_size: 200 } });
    proxyOptions.value = data.results || [];
  } catch { /* 静默 */ }
}

function openCreateEnv() {
  envEditMode.value = false;
  envForm.value = { user_id: "", name: "", group_id: "", domain_name: "youtube.com", remark: "", proxy_id: null };
  if (!groups.value.length) loadGroups();
  loadProxyOptions();
  envDialog.value = true;
}

function openEditEnv(row) {
  envEditMode.value = true;
  envForm.value = {
    user_id: row.user_id, name: row.name, group_id: row.group_id || "",
    domain_name: row.domain_name || "", remark: row.remark || "", proxy_id: null,
  };
  if (!groups.value.length) loadGroups();
  loadProxyOptions();
  envDialog.value = true;
}

async function saveEnv() {
  if (!envEditMode.value && !envForm.value.group_id) return ElMessage.warning("请选择分组");
  envSaving.value = true;
  try {
    const body = {
      name: envForm.value.name, group_id: envForm.value.group_id,
      domain_name: envForm.value.domain_name, remark: envForm.value.remark,
    };
    if (envForm.value.proxy_id) body.proxy_id = envForm.value.proxy_id;
    if (envEditMode.value) {
      await axios.patch(`/api/adspower-profiles/${envForm.value.user_id}/`, body);
      ElMessage.success("环境已更新");
    } else {
      await axios.post("/api/adspower-profiles/", body);
      ElMessage.success("环境已创建");
    }
    envDialog.value = false;
    await loadProfiles(1);
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "保存失败");
  } finally {
    envSaving.value = false;
  }
}

async function deleteEnv(row) {
  try {
    await ElMessageBox.confirm(`确定删除环境「${row.name}」？此操作会从 AdsPower 永久删除该环境。`, "确认删除", { type: "warning" });
    await axios.delete(`/api/adspower-profiles/${row.user_id}/`);
    ElMessage.success("已删除");
    await loadProfiles();
  } catch (e) {
    if (e !== "cancel") ElMessage.error(e.response?.data?.detail || "删除失败");
  }
}

async function setEnvProxy(row) {
  await loadProxyOptions();
  setProxyForm.value = { user_id: row.user_id, name: row.name, proxy_id: null };
  setProxyDialog.value = true;
}

async function saveEnvProxy() {
  setProxySaving.value = true;
  try {
    const body = setProxyForm.value.proxy_id ? { proxy_id: setProxyForm.value.proxy_id } : {};
    await axios.post(`/api/adspower-profiles/${setProxyForm.value.user_id}/set-proxy/`, body);
    ElMessage.success(setProxyForm.value.proxy_id ? "IP 已更新" : "已设为无代理");
    setProxyDialog.value = false;
    await loadProfiles();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "设置 IP 失败");
  } finally {
    setProxySaving.value = false;
  }
}

// —— 分组管理 ——
function openCreateGroup() {
  groupForm.value = { group_id: "", group_name: "", remark: "", edit: false };
  groupDialog.value = true;
}

function openEditGroup() {
  if (!groupFilter.value) return ElMessage.warning("请先在上方选择一个分组");
  const g = groups.value.find((x) => x.group_id === groupFilter.value);
  groupForm.value = { group_id: g.group_id, group_name: g.group_name, remark: g.remark || "", edit: true };
  groupDialog.value = true;
}

async function saveGroup() {
  if (!groupForm.value.group_name.trim()) return ElMessage.warning("请输入分组名称");
  groupSaving.value = true;
  try {
    if (groupForm.value.edit) {
      await axios.post("/api/adspower-profiles/update-group/", {
        group_id: groupForm.value.group_id, group_name: groupForm.value.group_name, remark: groupForm.value.remark,
      });
      ElMessage.success("分组已更新");
    } else {
      await axios.post("/api/adspower-profiles/create-group/", {
        group_name: groupForm.value.group_name, remark: groupForm.value.remark,
      });
      ElMessage.success("分组已创建");
    }
    groupDialog.value = false;
    await loadGroups();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "保存失败");
  } finally {
    groupSaving.value = false;
  }
}

// —— IP 管理页 ——
async function loadProxies(page = proxyPage.value) {
  proxyPage.value = page;
  proxyLoading.value = true;
  try {
    const params = { page, search: proxySearch.value };
    if (proxyAssignedFilter.value) params.assigned = proxyAssignedFilter.value;
    const { data } = await axios.get("/api/adspower-proxies/", { params });
    proxies.value = data.results;
    proxyTotal.value = data.count;
  } catch {
    ElMessage.error("加载 IP 列表失败");
  } finally {
    proxyLoading.value = false;
  }
}

async function importProxies() {
  proxyImporting.value = true;
  try {
    const { data } = await axios.post("/api/adspower-proxies/import-from-adspower/");
    ElMessage.success(`已从 AdsPower 同步：新增 ${data.imported} 条，跳过 ${data.skipped} 条`);
    await loadProxies(1);
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "同步失败");
  } finally {
    proxyImporting.value = false;
  }
}

async function verifyProxyGeo(row) {
  proxyVerifying.value = row.id;
  try {
    const { data } = await axios.post(`/api/adspower-proxies/${row.id}/verify-geo/`);
    row.geo_summary = data.geo_summary;
    row.verified_at = data.verified_at;
    ElMessage.success(data.geo_summary ? `归属地：${data.geo_summary}` : "已验证，但未返回地区");
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "验证失败");
  } finally {
    proxyVerifying.value = 0;
  }
}

function openCreateProxy() {
  proxyEditMode.value = false;
  proxyForm.value = { id: null, name: "", proxy_type: "socks5", proxy_host: "", proxy_port: "", proxy_user: "", proxy_password: "", remark: "" };
  proxyDialog.value = true;
}

function openEditProxy(row) {
  proxyEditMode.value = true;
  proxyForm.value = { id: row.id, name: row.name, proxy_type: row.proxy_type, proxy_host: row.proxy_host, proxy_port: row.proxy_port, proxy_user: row.proxy_user, proxy_password: row.proxy_password || "", remark: row.remark };
  proxyDialog.value = true;
}

async function saveProxy() {
  if (!proxyForm.value.proxy_host.trim() || !String(proxyForm.value.proxy_port).trim()) return ElMessage.warning("请填写主机和端口");
  proxySaving.value = true;
  try {
    const body = { ...proxyForm.value };
    if (proxyEditMode.value) {
      const { data } = await axios.patch(`/api/adspower-proxies/${proxyForm.value.id}/`, body);
      if (data.sync_warning) ElMessage.warning(data.sync_warning);
      else ElMessage.success(`IP 已更新${data.synced_profiles ? `，已同步到 ${data.synced_profiles} 个 AdsPower 环境` : ""}`);
    } else {
      await axios.post("/api/adspower-proxies/", body);
      ElMessage.success("IP 已添加");
    }
    proxyDialog.value = false;
    await loadProxies(1);
  } catch (e) {
    const err = e.response?.data;
    ElMessage.error(err?.detail || err?.non_field_errors?.[0] || "保存失败");
  } finally {
    proxySaving.value = false;
  }
}

async function deleteProxy(row) {
  try {
    await ElMessageBox.confirm(`确定删除 IP「${row.label}」？已套用到环境的代理不受影响。`, "确认删除", { type: "warning" });
    await axios.delete(`/api/adspower-proxies/${row.id}/`);
    ElMessage.success("已删除");
    await loadProxies();
  } catch (e) {
    if (e !== "cancel") ElMessage.error("删除失败");
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

async function runTaskNow() {
  ElMessage.info("任务已在自动上传队列中，系统会在约 10 秒内自动领取执行。请确认 Docker Desktop 与 AdsPower 客户端正在运行。");
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

function loadByView(v) {
  if (v === "adspower-tasks") loadTasks(1);
  else if (v === "adspower-ips") loadProxies(1);
  else { loadProfiles(1); loadGroups(); }
}

onMounted(() => loadByView(props.view));
watch(() => props.view, (v) => loadByView(v));
</script>
<template>
  <!-- ==================== 浏览器管理 ==================== -->
  <template v-if="view === 'adspower-browsers'">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <el-button type="primary" @click="openCreateEnv">新建环境</el-button>
          <el-button :loading="syncing" @click="syncProfiles">同步 AdsPower 环境</el-button>
          <el-select v-model="groupFilter" placeholder="全部分组" clearable style="width: 160px" @change="loadProfiles(1)">
            <el-option v-for="g in groups" :key="g.group_id" :label="g.group_name" :value="g.group_id" />
          </el-select>
          <el-button plain @click="openCreateGroup">新建分组</el-button>
          <el-button plain :disabled="!groupFilter" @click="openEditGroup">编辑分组</el-button>
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
        <el-table-column label="操作" width="420" fixed="right"><template #default="{ row }">
          <el-button size="small" type="primary" plain @click="openDetail(row)">详情</el-button>
          <el-button size="small" type="warning" plain @click="openEditEnv(row)">编辑</el-button>
          <el-button size="small" plain @click="setEnvProxy(row)">设置IP</el-button>
          <el-button size="small" type="success" plain @click="openBrowser(row)">打开</el-button>
          <el-button size="small" plain @click="closeBrowser(row)">关闭</el-button>
          <el-button size="small" type="danger" plain @click="deleteEnv(row)">删除</el-button>
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

    <!-- 新建 / 编辑环境 -->
    <el-dialog v-model="envDialog" :title="envEditMode ? '编辑环境' : '新建环境'" width="560px">
      <el-form label-width="90px">
        <el-form-item label="名称"><el-input v-model="envForm.name" placeholder="环境名称" /></el-form-item>
        <el-form-item label="分组" :required="!envEditMode">
          <el-select v-model="envForm.group_id" filterable placeholder="选择分组" style="width: 100%">
            <el-option v-for="g in groups" :key="g.group_id" :label="g.group_name" :value="g.group_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="绑定平台"><el-input v-model="envForm.domain_name" placeholder="如 youtube.com" /></el-form-item>
        <el-form-item label="IP / 代理">
          <el-select v-model="envForm.proxy_id" clearable filterable placeholder="从 IP 池选择（留空=无代理）" style="width: 100%">
            <el-option v-for="p in proxyOptions" :key="p.id" :label="p.label" :value="p.id" />
          </el-select>
          <small class="up-tip">IP 来自「IP 管理」页，没有可先去添加</small>
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="envForm.remark" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="envDialog = false">取消</el-button>
        <el-button type="primary" :loading="envSaving" @click="saveEnv">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新建 / 编辑分组 -->
    <el-dialog v-model="groupDialog" :title="groupForm.edit ? '编辑分组' : '新建分组'" width="440px">
      <el-form label-width="80px">
        <el-form-item label="分组名" required><el-input v-model="groupForm.group_name" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="groupForm.remark" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="groupDialog = false">取消</el-button>
        <el-button type="primary" :loading="groupSaving" @click="saveGroup">保存</el-button>
      </template>
    </el-dialog>

    <!-- 设置 IP（下拉选 IP 池） -->
    <el-dialog v-model="setProxyDialog" title="设置 IP" width="520px">
      <el-form label-width="90px">
        <el-form-item label="目标环境"><strong>{{ setProxyForm.name }}</strong></el-form-item>
        <el-form-item label="选择 IP">
          <el-select v-model="setProxyForm.proxy_id" clearable filterable placeholder="从 IP 池选择（留空=设为无代理）" style="width: 100%">
            <el-option v-for="p in proxyOptions" :key="p.id" :label="`${p.label}${p.geo_summary ? '（' + p.geo_summary + '）' : ''}`" :value="p.id" />
          </el-select>
          <small class="up-tip">IP 来自「IP 管理」页；留空则清除该环境的代理</small>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="setProxyDialog = false">取消</el-button>
        <el-button type="primary" :loading="setProxySaving" @click="saveEnvProxy">保存</el-button>
      </template>
    </el-dialog>
  </template>

  <!-- ==================== IP 管理 ==================== -->
  <template v-else-if="view === 'adspower-ips'">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <el-button type="primary" @click="openCreateProxy">新增 IP</el-button>
          <el-button :loading="proxyImporting" @click="importProxies">从 AdsPower 同步</el-button>
          <el-select v-model="proxyAssignedFilter" placeholder="全部分配状态" clearable style="width: 160px" @change="loadProxies(1)">
            <el-option label="已分配" value="assigned" />
            <el-option label="未分配" value="unassigned" />
          </el-select>
        </div>
        <div class="toolbar-right">
          <el-input v-model="proxySearch" clearable placeholder="按名称 / 主机搜索" style="width: 200px" @keyup.enter="loadProxies(1)" @clear="loadProxies(1)" />
          <el-button @click="loadProxies(1)">查询</el-button>
          <el-button @click="loadProxies()">刷新</el-button>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-alert title="IP 池用于在新建 / 编辑环境时快速套用代理。密码仅在保存时写入、列表不回显。「从 AdsPower 同步」会把现有环境里的代理导入（密码受脱敏限制不导入，需用时手动补）。「验证地区」用 IP2Location 查 IP 归属地，仅代表地理位置、不代表代理当前可连通。" type="info" :closable="false" class="note" />
      <el-table :data="proxies" v-loading="proxyLoading" size="small" empty-text="暂无 IP，点「新增 IP」添加">
        <el-table-column prop="name" label="名称" min-width="120" show-overflow-tooltip />
        <el-table-column prop="proxy_type" label="类型" width="80" />
        <el-table-column prop="proxy_host" label="主机" min-width="140" />
        <el-table-column prop="proxy_port" label="端口" width="75" />
        <el-table-column label="来源" width="90"><template #default="{ row }"><el-tag size="small" :type="row.source === 'adspower' ? 'warning' : 'info'" effect="plain">{{ row.source === 'adspower' ? '环境同步' : '手动' }}</el-tag></template></el-table-column>
        <el-table-column label="分配状态" min-width="130"><template #default="{ row }">
          <el-tag v-if="row.assigned_count" size="small" type="success" effect="light">已分配 {{ row.assigned_count }}</el-tag>
          <el-tag v-else size="small" type="info" effect="plain">未分配</el-tag>
          <el-tooltip v-if="row.assigned_count" :content="row.assigned_to.map(x => x.name).join('、')" placement="top"><el-icon class="assigned-info">ℹ</el-icon></el-tooltip>
        </template></el-table-column>
        <el-table-column label="归属地" min-width="170"><template #default="{ row }">
          <span v-if="row.geo_summary">{{ row.geo_summary }}</span>
          <span v-else class="muted">未验证</span>
        </template></el-table-column>
        <el-table-column label="密码" width="70"><template #default="{ row }"><el-tag size="small" :type="row.password_set ? 'success' : 'info'" effect="plain">{{ row.password_set ? "已设" : "无" }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="230" fixed="right"><template #default="{ row }">
          <el-button size="small" plain :loading="proxyVerifying === row.id" @click="verifyProxyGeo(row)">验证地区</el-button>
          <el-button size="small" type="warning" plain @click="openEditProxy(row)">编辑</el-button>
          <el-button size="small" type="danger" plain @click="deleteProxy(row)">删除</el-button>
        </template></el-table-column>
      </el-table>
      <el-pagination v-model:current-page="proxyPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="proxyTotal" @current-change="loadProxies" />
    </el-card>

    <el-dialog v-model="proxyDialog" :title="proxyEditMode ? '编辑 IP' : '新增 IP'" width="520px">
      <el-form label-width="90px">
        <el-form-item label="名称"><el-input v-model="proxyForm.name" placeholder="便于识别，如 印度-住宅IP" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="proxyForm.proxy_type" style="width: 160px">
            <el-option label="SOCKS5" value="socks5" />
            <el-option label="HTTP" value="http" />
            <el-option label="HTTPS" value="https" />
          </el-select>
        </el-form-item>
        <el-form-item label="主机" required><el-input v-model="proxyForm.proxy_host" placeholder="IP 或域名" /></el-form-item>
        <el-form-item label="端口" required><el-input v-model="proxyForm.proxy_port" /></el-form-item>
        <el-form-item label="账号"><el-input v-model="proxyForm.proxy_user" placeholder="如 g745998539" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="proxyForm.proxy_password" placeholder="明文显示，便于核对" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="proxyForm.remark" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="proxyDialog = false">取消</el-button>
        <el-button type="primary" :loading="proxySaving" @click="saveProxy">保存</el-button>
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
        <el-alert title="任务由系统内置执行器自动串行领取；「排队中」通常会在约 10 秒内开始执行。请保持 Docker Desktop 与 AdsPower 客户端运行。开发阶段执行到「草稿已保存」为止，请到对应浏览器的 YouTube Studio 核对后手动发布。" type="warning" :closable="false" class="note" />
        <el-table :data="tasks" v-loading="taskLoading" size="small" empty-text="暂无任务">
          <el-table-column label="任务 / 标题" min-width="200"><template #default="{ row }"><div>{{ row.name || row.title }}</div><small class="sub">{{ row.source_run_keyword ? `来自内容任务：${row.source_run_keyword}` : "手动创建" }}</small></template></el-table-column>
          <el-table-column label="目标浏览器" min-width="140"><template #default="{ row }">{{ row.profile_serial }} · {{ row.profile_name }}</template></el-table-column>
          <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="statusType(row.status)" size="small" effect="light">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
          <el-table-column label="视频链接" min-width="180"><template #default="{ row }"><a v-if="row.video_url" :href="row.video_url" target="_blank" rel="noreferrer">打开</a><span v-else>—</span></template></el-table-column>
          <el-table-column label="创建时间" min-width="160"><template #default="{ row }">{{ datetime(row.created_at) }}</template></el-table-column>
          <el-table-column label="操作" width="230" fixed="right"><template #default="{ row }">
            <el-button size="small" type="info" plain @click="openLog(row)">日志</el-button>
          <el-button size="small" type="success" plain :disabled="row.status !== 'queued'" @click="runTaskNow">查看执行条件</el-button>
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
.muted { color: #8a98a8; }
.assigned-info { margin-left: 4px; color: #8a98a8; cursor: help; vertical-align: middle; }
.detail-collapse { margin-top: 12px; }
.log-pre { white-space: pre-wrap; word-break: break-all; font-size: 12px; max-height: 360px; overflow: auto; background: #0d1620; color: #b6c5d4; padding: 10px; border-radius: 6px; }
</style>

