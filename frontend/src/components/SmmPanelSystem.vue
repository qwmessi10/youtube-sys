<script setup>
// SMM 面板系统（对接 AutoLak Cloud Bot）。由 App.vue 二级菜单通过 view 控制：
//   smm-accounts=个人中心 / smm-tasks=任务管理
import { computed, onMounted, ref, watch } from "vue";
import axios from "axios";
import { ElMessage, ElMessageBox } from "element-plus";

const props = defineProps({ view: { type: String, default: "smm-accounts" } });

// —— 个人中心（账号）——
const accounts = ref([]);
const accountTotal = ref(0);
const accountPage = ref(1);
const accountLoading = ref(false);
const accountDialog = ref(false);
const accountSaving = ref(false);
const accountEditMode = ref(false);
const accountForm = ref({ id: null, tg_user_id: "", username: "", remark: "" });
const refreshingId = ref(null);

// —— 任务管理 ——
const tasks = ref([]);
const taskTotal = ref(0);
const taskPage = ref(1);
const taskSearch = ref("");
const taskLoading = ref(false);
const taskDialog = ref(false);
const taskSaving = ref(false);
const taskForm = ref({ account: "", youtube_link: "", key_words: "", total_user: 300, per_user: 2, end_hours: 48 });
const syncingId = ref(null);

const statusMeta = {
  pending: { label: "进行中", type: "warning" },
  running: { label: "进行中", type: "warning" },
  completed: { label: "已完成", type: "success" },
  failed: { label: "失败", type: "danger" },
};
const statusLabel = (s) => statusMeta[s]?.label || s;
const statusType = (s) => statusMeta[s]?.type || "info";

const accountStatusMeta = {
  active: { label: "有效", type: "success" },
  token_invalid: { label: "token 失效", type: "danger" },
};

const accountOptions = computed(() => accounts.value.map((a) => ({ id: a.id, label: a.panel_user_name || a.username || a.tg_user_id })));

function progressText(row) {
  const p = row.progress || {};
  if (p.complete_size == null) return "—";
  const done = p.complete_size ?? 0;
  const total = p.total_users ?? row.total_user ?? 0;
  return `${done}/${total}（${p.success_rate || "—"}）`;
}

const YT_LINK_RE = /^(https?:\/\/)?(www\.|m\.)?(youtube\.com|youtu\.be)\//i;

function isYoutubeLink(link) {
  return YT_LINK_RE.test((link || "").trim());
}

// 关键词按 ; 分隔，校验非空与空项，返回错误文案（空串表示通过）
function validateKeywords(kw) {
  const parts = (kw || "").split(";").map((s) => s.trim());
  const cleaned = parts.filter(Boolean);
  if (!cleaned.length) return "请填写关键词";
  if (cleaned.length !== parts.length) return "关键词格式有误：存在空项（多个用 ; 分隔）";
  return "";
}

// ============ 账号 ============
async function loadAccounts(page = accountPage.value) {
  accountPage.value = page;
  accountLoading.value = true;
  try {
    const { data } = await axios.get("/api/smm-accounts/", { params: { page } });
    accounts.value = data.results;
    accountTotal.value = data.count;
  } catch {
    ElMessage.error("加载账号列表失败");
  } finally {
    accountLoading.value = false;
  }
}

function openCreateAccount() {
  accountEditMode.value = false;
  accountForm.value = { id: null, tg_user_id: "", username: "", remark: "" };
  accountDialog.value = true;
}

function openEditAccount(row) {
  accountEditMode.value = true;
  accountForm.value = { id: row.id, tg_user_id: row.tg_user_id, username: row.username, remark: row.remark };
  accountDialog.value = true;
}

async function saveAccount() {
  if (!accountForm.value.tg_user_id.trim()) return ElMessage.warning("请填写 Telegram 数字 ID");
  accountSaving.value = true;
  try {
    if (accountEditMode.value) {
      await axios.patch(`/api/smm-accounts/${accountForm.value.id}/`, {
        username: accountForm.value.username,
        remark: accountForm.value.remark,
      });
      ElMessage.success("已保存");
    } else {
      await axios.post("/api/smm-accounts/", {
        tg_user_id: accountForm.value.tg_user_id,
        username: accountForm.value.username,
        remark: accountForm.value.remark,
      });
      ElMessage.success("新增成功，已自动提取 token 与余额");
    }
    accountDialog.value = false;
    await loadAccounts();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "保存失败");
  } finally {
    accountSaving.value = false;
  }
}

async function refreshAccount(row) {
  refreshingId.value = row.id;
  try {
    await axios.post(`/api/smm-accounts/${row.id}/refresh/`);
    ElMessage.success("已刷新 token 与余额");
    await loadAccounts();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "刷新失败");
  } finally {
    refreshingId.value = null;
  }
}

async function deleteAccount(row) {
  try {
    await ElMessageBox.confirm(`确定删除账号「${row.panel_user_name || row.tg_user_id}」？其下任务记录也会一并删除。`, "确认删除", { type: "warning" });
    await axios.delete(`/api/smm-accounts/${row.id}/`);
    ElMessage.success("已删除");
    await loadAccounts();
  } catch (e) {
    if (e !== "cancel") ElMessage.error("删除失败");
  }
}

// ============ 任务 ============
async function loadTasks(page = taskPage.value) {
  taskPage.value = page;
  taskLoading.value = true;
  try {
    const params = { page };
    if (taskSearch.value) params.search = taskSearch.value;
    const { data } = await axios.get("/api/smm-tasks/", { params });
    tasks.value = data.results;
    taskTotal.value = data.count;
  } catch {
    ElMessage.error("加载任务列表失败");
  } finally {
    taskLoading.value = false;
  }
}

function openCreateTask() {
  taskForm.value = { account: "", youtube_link: "", key_words: "", total_user: 300, per_user: 2, end_hours: 48 };
  taskDialog.value = true;
}

async function saveTask() {
  if (!taskForm.value.account) return ElMessage.warning("请选择所属账号");
  if (!taskForm.value.youtube_link.trim()) return ElMessage.warning("请填写 YouTube 链接");
  if (!isYoutubeLink(taskForm.value.youtube_link)) return ElMessage.warning("YouTube 链接格式不正确（需 youtube.com 或 youtu.be）");
  const kwErr = validateKeywords(taskForm.value.key_words);
  if (kwErr) return ElMessage.warning(kwErr);
  if (!taskForm.value.total_user) return ElMessage.warning("请填写刷量人数");
  if (taskForm.value.end_hours < 2) return ElMessage.warning("结束时间必须至少 2 小时后（面板按印度时区，需留足时差）");
  const cost = Number(taskForm.value.total_user) * Number(taskForm.value.per_user);
  const acc = findAccount(taskForm.value.account);
  if (acc && cost > Number(acc.locked_remaining)) {
    try {
      await ElMessageBox.confirm(`本次成本约 ₹${cost}，超过锁定后剩余余额 ₹${acc.locked_remaining}，是否仍要继续下单？`, "余额不足警告", { type: "warning" });
    } catch (e) { return; }
  }
  taskSaving.value = true;
  try {
    await axios.post("/api/smm-tasks/", taskForm.value);
    ElMessage.success("任务已提交");
    taskDialog.value = false;
    await loadTasks();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "保存失败");
  } finally {
    taskSaving.value = false;
  }
}

async function syncTask(row) {
  syncingId.value = row.id;
  try {
    await axios.post(`/api/smm-tasks/${row.id}/sync_status/`);
    await loadTasks();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "同步失败");
  } finally {
    syncingId.value = null;
  }
}

async function deleteTask(row) {
  try {
    await ElMessageBox.confirm(`确定删除任务「${row.show_id || row.id}」？仅删除本地记录，不影响面板。`, "确认删除", { type: "warning" });
    await axios.delete(`/api/smm-tasks/${row.id}/`);
    ElMessage.success("已删除");
    await loadTasks();
  } catch (e) {
    if (e !== "cancel") ElMessage.error("删除失败");
  }
}

// —— 轮询任务 ——
const taskTab = ref("normal"); // normal=普通任务 / poll=轮询任务
const pollTasks = ref([]);
const pollTotal = ref(0);
const pollPage = ref(1);
const pollSearch = ref("");
const pollLoading = ref(false);
const pollDialog = ref(false);
const pollSaving = ref(false);
const pollForm = ref({
  account: "", youtube_link: "", key_words: "", per_user: 2,
  initial_count: null, poll_total: 9, batch_min: 1, batch_max: 5,
  window_start_hour: 12, window_end_hour: 21,
});
const pollExpanded = ref(null); // 当前展开查看子下单的轮询任务 id

const pollStatusMeta = {
  running: { label: "运行中", type: "warning" },
  completed: { label: "已完成", type: "success" },
  stopped: { label: "已停止", type: "info" },
  failed: { label: "失败", type: "danger" },
};

// 执行计划预览（北京时间，具体到小时，纯前端计算，仅用于运营确认）
const pollSchedule = computed(() => {
  const slots = [];
  const start = pollForm.value.window_start_hour;
  const end = pollForm.value.window_end_hour;
  const n = pollForm.value.poll_total;
  if (!n || !(start >= 0 && end > start && end <= 24)) return slots;
  const d = new Date();
  d.setMinutes(0, 0, 0);
  d.setHours(d.getHours() + 1);
  let guard = 0;
  while (slots.length < n && guard < 24 * 400) {
    const h = d.getHours();
    if (h >= start && h < end) slots.push(new Date(d));
    d.setHours(d.getHours() + 1);
    guard++;
  }
  return slots;
});

// 预估成本区间（最低=每批下限，最高=每批上限；首次刷量也按每人奖励 per_user 计）
const pollCostRange = computed(() => {
  const per = Number(pollForm.value.per_user) || 0;
  const initial = Number(pollForm.value.initial_count) || 0;
  const total = Number(pollForm.value.poll_total) || 0;
  const min = initial * per + total * pollForm.value.batch_min * per;
  const max = initial * per + total * pollForm.value.batch_max * per;
  return { min: Math.ceil(min), max: Math.ceil(max) };
});

function findAccount(id) {
  return accounts.value.find((a) => Number(a.id) === Number(id));
}

function fmtSlot(d) {
  const p = (x) => String(x).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:00`;
}

async function loadPollTasks(page = pollPage.value) {
  pollPage.value = page;
  pollLoading.value = true;
  try {
    const params = { page };
    if (pollSearch.value) params.search = pollSearch.value;
    const { data } = await axios.get("/api/smm-poll-tasks/", { params });
    pollTasks.value = data.results;
    pollTotal.value = data.count;
  } catch {
    ElMessage.error("加载轮询任务失败");
  } finally {
    pollLoading.value = false;
  }
}

function openCreatePollTask() {
  pollForm.value = {
    account: "", youtube_link: "", key_words: "", per_user: 2,
    initial_count: null, poll_total: 9, batch_min: 1, batch_max: 5,
    window_start_hour: 12, window_end_hour: 21,
  };
  pollDialog.value = true;
}

async function savePollTask() {
  if (!pollForm.value.account) return ElMessage.warning("请选择所属账号");
  if (!pollForm.value.youtube_link.trim()) return ElMessage.warning("请填写 YouTube 链接");
  if (!isYoutubeLink(pollForm.value.youtube_link)) return ElMessage.warning("YouTube 链接格式不正确（需 youtube.com 或 youtu.be）");
  const kwErr = validateKeywords(pollForm.value.key_words);
  if (kwErr) return ElMessage.warning(kwErr);
  if (!pollForm.value.poll_total || pollForm.value.poll_total < 1) return ElMessage.warning("请填写轮询次数");
  const acc = findAccount(pollForm.value.account);
  if (acc && pollCostRange.value.max > Number(acc.locked_remaining)) {
    try {
      await ElMessageBox.confirm(`预估最大成本 ₹${pollCostRange.value.max}，超过锁定后剩余余额 ₹${acc.locked_remaining}，是否仍要继续创建？`, "余额不足警告", { type: "warning" });
    } catch (e) { return; }
  }
  pollSaving.value = true;
  try {
    await axios.post("/api/smm-poll-tasks/", pollForm.value);
    ElMessage.success("轮询任务已创建");
    pollDialog.value = false;
    await loadPollTasks();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "创建失败");
  } finally {
    pollSaving.value = false;
  }
}

async function stopPollTask(row) {
  try {
    await ElMessageBox.confirm("确定停止该轮询任务？不撤回已下单，之后不再自动刷。", "确认停止", { type: "warning" });
    await axios.post(`/api/smm-poll-tasks/${row.id}/stop/`);
    ElMessage.success("已停止");
    await loadPollTasks();
  } catch (e) {
    if (e !== "cancel") ElMessage.error("停止失败");
  }
}

async function restartPollTask(row) {
  try {
    await axios.post(`/api/smm-poll-tasks/${row.id}/restart/`);
    ElMessage.success("已重启（停掉的时间跳过不补）");
    await loadPollTasks();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "重启失败");
  }
}

async function deletePollTask(row) {
  try {
    await ElMessageBox.confirm("确定删除该轮询任务？仅删本地记录，不影响面板已下单。", "确认删除", { type: "warning" });
    await axios.delete(`/api/smm-poll-tasks/${row.id}/`);
    ElMessage.success("已删除");
    await loadPollTasks();
  } catch (e) {
    if (e !== "cancel") ElMessage.error("删除失败");
  }
}

function togglePollChildren(row) {
  pollExpanded.value = pollExpanded.value === row.id ? null : row.id;
}

watch(() => props.view, (v) => {
  loadAccounts();  // 账号列表个人中心/任务管理都要用，始终加载
  if (v === "smm-tasks") { loadTasks(); loadPollTasks(); }
});

onMounted(() => {
  loadAccounts();
  if (props.view === "smm-tasks") { loadTasks(); loadPollTasks(); }
});
</script>

<template>
  <!-- 个人中心 -->
  <div v-if="view === 'smm-accounts'">
    <el-alert
      title="SMM 面板 - 个人中心"
      description="管理面板账号。新增时只需填 Telegram 数字 ID（获取方式：给 @userinfobot 发消息，或网页版点「Saved Messages」看地址栏 # 后的数字），系统会自动提取 token 并拉取余额。"
      type="success" :closable="false" show-icon class="agent-intro"
    />
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <el-button type="primary" @click="openCreateAccount">新增账号</el-button>
        </div>
        <div class="toolbar-right">
          <el-button @click="loadAccounts()">刷新</el-button>
        </div>
      </div>
    </el-card>
    <el-card shadow="never" class="table-card">
      <el-table :data="accounts" size="small" v-loading="accountLoading" empty-text="暂无账号，点「新增账号」添加">
        <el-table-column prop="panel_user_name" label="面板昵称" min-width="130" />
        <el-table-column prop="tg_user_id" label="Telegram ID" width="140" />
        <el-table-column prop="username" label="@用户名" width="140" />
        <el-table-column label="实际余额" width="100"><template #default="{ row }">₹{{ row.balance }}</template></el-table-column>
        <el-table-column label="锁定中" width="90"><template #default="{ row }">₹{{ row.locked_total }}</template></el-table-column>
        <el-table-column label="剩余可用" width="100"><template #default="{ row }"><span :style="Number(row.locked_remaining) < 0 ? 'color:#f56c6c' : ''">₹{{ row.locked_remaining }}</span></template></el-table-column>
        <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag size="small" :type="accountStatusMeta[row.status]?.type || 'info'" effect="light">{{ accountStatusMeta[row.status]?.label || row.status }}</el-tag></template></el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
        <el-table-column label="操作" width="280" fixed="right"><template #default="{ row }">
          <el-button size="small" type="primary" plain :loading="refreshingId === row.id" @click="refreshAccount(row)">刷新余额</el-button>
          <el-button size="small" plain @click="openEditAccount(row)">编辑</el-button>
          <el-button size="small" type="danger" plain @click="deleteAccount(row)">删除</el-button>
        </template></el-table-column>
      </el-table>
      <el-pagination v-model:current-page="accountPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="accountTotal" @current-change="loadAccounts" />
    </el-card>

    <el-dialog v-model="accountDialog" :title="accountEditMode ? '编辑账号' : '新增账号'" width="460px">
      <el-form label-width="110px">
        <el-form-item label="Telegram ID" required>
          <el-input v-model="accountForm.tg_user_id" :disabled="accountEditMode" placeholder="数字 ID，如 8196195827" />
        </el-form-item>
        <el-form-item label="@用户名"><el-input v-model="accountForm.username" placeholder="仅作展示，选填" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="accountForm.remark" placeholder="选填" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="accountDialog = false">取消</el-button>
        <el-button type="primary" :loading="accountSaving" @click="saveAccount">保存并提取 token</el-button>
      </template>
    </el-dialog>
  </div>

  <!-- 任务管理 -->
  <div v-else>
    <el-alert
      title="SMM 面板 - 任务管理"
      description="创建刷量任务并跟踪进度。任务提交到面板后，系统会自动定时同步状态（有进行中任务时每 30s 同步一次），完成后自动标记为「已完成」。"
      type="success" :closable="false" show-icon class="agent-intro"
    />
    <el-tabs v-model="taskTab">
      <el-tab-pane label="普通任务" name="normal">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <el-button type="primary" @click="openCreateTask">新增任务</el-button>
        </div>
        <div class="toolbar-right">
          <el-input v-model="taskSearch" clearable placeholder="搜任务号/关键词/链接" style="width: 220px" @keyup.enter="loadTasks(1)" @clear="loadTasks(1)" />
          <el-button @click="loadTasks(1)">查询</el-button>
          <el-button @click="loadTasks()">刷新</el-button>
        </div>
      </div>
    </el-card>
    <el-card shadow="never" class="table-card">
      <el-table :data="tasks" size="small" v-loading="taskLoading" empty-text="暂无任务，点「新增任务」创建">
        <el-table-column prop="show_id" label="任务号" min-width="150" />
        <el-table-column prop="account_name" label="账号" width="130" />
        <el-table-column prop="key_words" label="关键词" min-width="140" show-overflow-tooltip />
        <el-table-column prop="total_user" label="人数" width="80" />
        <el-table-column label="成本" width="90"><template #default="{ row }">₹{{ row.cost }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag size="small" :type="statusType(row.status)" effect="light">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
        <el-table-column label="进度" width="140"><template #default="{ row }">{{ progressText(row) }}</template></el-table-column>
        <el-table-column label="操作" width="200" fixed="right"><template #default="{ row }">
          <el-button size="small" type="primary" plain :loading="syncingId === row.id" @click="syncTask(row)">同步</el-button>
          <el-button size="small" type="danger" plain @click="deleteTask(row)">删除</el-button>
        </template></el-table-column>
      </el-table>
      <el-pagination v-model:current-page="taskPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="taskTotal" @current-change="loadTasks" />
    </el-card>

    <el-dialog v-model="taskDialog" title="新增刷量任务" width="560px">
      <el-form label-width="110px">
        <el-form-item label="所属账号" required>
          <el-select v-model="taskForm.account" placeholder="选择账号" style="width: 100%">
            <el-option v-for="a in accountOptions" :key="a.id" :label="a.label" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="YouTube 链接" required><el-input v-model="taskForm.youtube_link" placeholder="https://youtu.be/..." /></el-form-item>
        <el-form-item label="关键词" required><el-input v-model="taskForm.key_words" placeholder="多个用 ; 分隔" /></el-form-item>
        <el-form-item label="刷量人数" required><el-input-number v-model="taskForm.total_user" :min="1" :max="10000" :step="100" style="width: 100%" /></el-form-item>
        <el-form-item label="每人奖励(₹)"><el-input-number v-model="taskForm.per_user" :min="2" :step="0.1" style="width: 100%" /></el-form-item>
        <el-form-item label="结束时间(小时后)">
          <el-input-number v-model="taskForm.end_hours" :min="2" :max="720" style="width: 100%" />
          <small class="agent-hint">面板按印度时区（比北京晚 2.5 小时），结束时间需至少 2 小时后，留足时差与运行缓冲。</small>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taskDialog = false">取消</el-button>
        <el-button type="primary" :loading="taskSaving" @click="saveTask">提交任务</el-button>
      </template>
    </el-dialog>
      </el-tab-pane>

      <el-tab-pane label="轮询任务" name="poll">
        <el-card shadow="never" class="toolbar-card">
          <div class="toolbar">
            <div class="toolbar-left">
              <el-button type="primary" @click="openCreatePollTask">新增轮询任务</el-button>
            </div>
            <div class="toolbar-right">
              <el-input v-model="pollSearch" clearable placeholder="搜关键词/链接" style="width: 220px" @keyup.enter="loadPollTasks(1)" @clear="loadPollTasks(1)" />
              <el-button @click="loadPollTasks(1)">查询</el-button>
              <el-button @click="loadPollTasks()">刷新</el-button>
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="table-card">
          <el-table :data="pollTasks" size="small" v-loading="pollLoading" empty-text="暂无轮询任务" row-key="id">
            <el-table-column type="expand" width="40">
              <template #default="{ row }">
                <el-table :data="row.children || []" size="small" border style="margin: 8px 20px" empty-text="暂无子下单">
                  <el-table-column prop="show_id" label="任务号" min-width="140" />
                  <el-table-column prop="total_user" label="人数" width="80" />
                  <el-table-column label="成本" width="90"><template #default="{ row: c }">₹{{ c.cost }}</template></el-table-column>
                  <el-table-column label="状态" width="100"><template #default="{ row: c }"><el-tag size="small" :type="statusType(c.status)" effect="light">{{ statusLabel(c.status) }}</el-tag></template></el-table-column>
                  <el-table-column label="进度" width="140"><template #default="{ row: c }">{{ progressText(c) }}</template></el-table-column>
                </el-table>
              </template>
            </el-table-column>
            <el-table-column prop="key_words" label="关键词" min-width="140" show-overflow-tooltip />
            <el-table-column prop="account_name" label="账号" width="120" />
            <el-table-column label="首次刷量" width="90"><template #default="{ row }">{{ row.initial_count ?? "—" }}</template></el-table-column>
            <el-table-column label="进度" width="100"><template #default="{ row }">{{ row.poll_done }}/{{ row.poll_total }}</template></el-table-column>
            <el-table-column label="每批人数" width="90"><template #default="{ row }">{{ row.batch_min }}-{{ row.batch_max }}</template></el-table-column>
            <el-table-column label="窗口(北京)" width="110"><template #default="{ row }">{{ row.window_start_hour }}:00-{{ row.window_end_hour }}:00</template></el-table-column>
            <el-table-column label="下次执行" width="140"><template #default="{ row }">{{ row.next_poll_at ? fmtSlot(new Date(row.next_poll_at)) : "—" }}</template></el-table-column>
            <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag size="small" :type="pollStatusMeta[row.status]?.type || 'info'" effect="light">{{ pollStatusMeta[row.status]?.label || row.status }}</el-tag></template></el-table-column>
            <el-table-column label="操作" width="220" fixed="right"><template #default="{ row }">
              <el-button v-if="row.status === 'running'" size="small" type="warning" plain @click="stopPollTask(row)">停止</el-button>
              <el-button v-else size="small" type="success" plain @click="restartPollTask(row)">重启</el-button>
              <el-button size="small" type="danger" plain @click="deletePollTask(row)">删除</el-button>
            </template></el-table-column>
          </el-table>
          <el-pagination v-model:current-page="pollPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="pollTotal" @current-change="loadPollTasks" />
        </el-card>

        <el-dialog v-model="pollDialog" title="新增轮询刷量任务" width="620px">
          <el-form label-width="120px">
            <el-form-item label="所属账号" required>
              <el-select v-model="pollForm.account" placeholder="选择账号" style="width: 100%">
                <el-option v-for="a in accountOptions" :key="a.id" :label="a.label" :value="a.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="YouTube 链接" required><el-input v-model="pollForm.youtube_link" placeholder="https://youtu.be/..." /></el-form-item>
            <el-form-item label="关键词" required><el-input v-model="pollForm.key_words" placeholder="多个用 ; 分隔" /></el-form-item>
            <el-form-item label="每人奖励(₹)"><el-input-number v-model="pollForm.per_user" :min="2" :step="0.1" style="width: 100%" /></el-form-item>
            <el-form-item label="首次刷量人数"><el-input-number v-model="pollForm.initial_count" :min="1" :max="10000" :step="50" style="width: 100%" placeholder="选填，创建时立即下单" /></el-form-item>
            <el-form-item label="轮询次数" required><el-input-number v-model="pollForm.poll_total" :min="1" style="width: 100%" /></el-form-item>
            <el-form-item label="每批人数区间">
              <div style="display:flex;gap:8px;align-items:center;width:100%">
                <el-input-number v-model="pollForm.batch_min" :min="1" :max="10000" style="flex:1" />
                <span>~</span>
                <el-input-number v-model="pollForm.batch_max" :min="1" :max="10000" style="flex:1" />
              </div>
            </el-form-item>
            <el-form-item label="执行时间窗口(北京)">
              <div style="display:flex;gap:8px;align-items:center;width:100%">
                <el-input-number v-model="pollForm.window_start_hour" :min="0" :max="23" style="flex:1" />
                <span>时 ~</span>
                <el-input-number v-model="pollForm.window_end_hour" :min="1" :max="24" style="flex:1" />
                <span>时</span>
              </div>
              <small class="agent-hint">窗口内每小时刷一次，跨天直到刷满轮询次数。</small>
            </el-form-item>
            <el-form-item v-if="pollSchedule.length" label="执行计划">
              <div class="poll-schedule">
                <div class="poll-schedule-summary">共 {{ pollSchedule.length }} 次，预计 {{ Math.ceil(pollSchedule.length / Math.max(1, pollForm.window_end_hour - pollForm.window_start_hour)) }} 天完成</div>
                <div class="poll-schedule-list">
                  <el-tag v-for="(s, i) in pollSchedule" :key="i" size="small" class="poll-slot" :type="i === 0 ? 'warning' : 'info'">{{ fmtSlot(s) }}</el-tag>
                </div>
              </div>
            </el-form-item>
            <el-form-item v-if="pollSchedule.length" label="预估成本">
              <span>最低 ₹{{ pollCostRange.min }} ~ 最高 ₹{{ pollCostRange.max }}（首次刷量 + 轮询均按每人奖励 ₹{{ pollForm.per_user }} 计算）</span>
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="pollDialog = false">取消</el-button>
            <el-button type="primary" :loading="pollSaving" @click="savePollTask">创建轮询任务</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
