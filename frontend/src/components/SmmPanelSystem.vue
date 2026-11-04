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
const taskEditMode = ref(false);
const taskForm = ref({ id: null, account: "", youtube_link: "", key_words: "", total_user: 300, per_user: 2, end_hours: 48 });
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
  taskEditMode.value = false;
  taskForm.value = { id: null, account: "", youtube_link: "", key_words: "", total_user: 300, per_user: 2, end_hours: 48 };
  taskDialog.value = true;
}

function openEditTask(row) {
  taskEditMode.value = true;
  taskForm.value = {
    id: row.id,
    account: row.account,
    youtube_link: row.youtube_link,
    key_words: row.key_words,
    total_user: row.total_user,
    per_user: Number(row.per_user),
    end_hours: 48,
  };
  taskDialog.value = true;
}

async function saveTask() {
  if (!taskForm.value.account) return ElMessage.warning("请选择所属账号");
  if (!taskForm.value.youtube_link.trim()) return ElMessage.warning("请填写 YouTube 链接");
  if (!taskForm.value.key_words.trim()) return ElMessage.warning("请填写关键词");
  if (!taskForm.value.total_user) return ElMessage.warning("请填写刷量人数");
  if (!taskEditMode.value && taskForm.value.end_hours < 2) return ElMessage.warning("结束时间必须至少 2 小时后（面板按印度时区，需留足时差）");
  taskSaving.value = true;
  try {
    if (taskEditMode.value) {
      await axios.patch(`/api/smm-tasks/${taskForm.value.id}/`, {
        account: taskForm.value.account,
        youtube_link: taskForm.value.youtube_link,
        key_words: taskForm.value.key_words,
        total_user: taskForm.value.total_user,
        per_user: taskForm.value.per_user,
      });
      ElMessage.success("已保存");
    } else {
      await axios.post("/api/smm-tasks/", taskForm.value);
      ElMessage.success("任务已提交");
    }
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

watch(() => props.view, (v) => {
  if (v === "smm-accounts") loadAccounts();
  else if (v === "smm-tasks") loadTasks();
});

onMounted(() => {
  if (props.view === "smm-accounts") loadAccounts();
  else loadTasks();
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
        <el-table-column label="余额" width="120"><template #default="{ row }">₹{{ row.balance }}</template></el-table-column>
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
        <el-table-column label="操作" width="260" fixed="right"><template #default="{ row }">
          <el-button size="small" plain @click="openEditTask(row)">编辑</el-button>
          <el-button size="small" type="primary" plain :loading="syncingId === row.id" @click="syncTask(row)">同步</el-button>
          <el-button size="small" type="danger" plain @click="deleteTask(row)">删除</el-button>
        </template></el-table-column>
      </el-table>
      <el-pagination v-model:current-page="taskPage" class="pagination" layout="total, prev, pager, next" :page-size="10" :total="taskTotal" @current-change="loadTasks" />
    </el-card>

    <el-dialog v-model="taskDialog" :title="taskEditMode ? '编辑刷量任务' : '新增刷量任务'" width="560px">
      <el-form label-width="110px">
        <el-form-item label="所属账号" required>
          <el-select v-model="taskForm.account" placeholder="选择账号" style="width: 100%">
            <el-option v-for="a in accountOptions" :key="a.id" :label="a.label" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="YouTube 链接" required><el-input v-model="taskForm.youtube_link" placeholder="https://youtu.be/..." /></el-form-item>
        <el-form-item label="关键词" required><el-input v-model="taskForm.key_words" placeholder="多个用 ; 分隔" /></el-form-item>
        <el-form-item label="刷量人数" required><el-input-number v-model="taskForm.total_user" :min="1" :step="100" style="width: 100%" /></el-form-item>
        <el-form-item label="每人奖励(₹)"><el-input-number v-model="taskForm.per_user" :min="2" :step="0.1" style="width: 100%" /></el-form-item>
        <el-form-item v-if="!taskEditMode" label="结束时间(小时后)">
          <el-input-number v-model="taskForm.end_hours" :min="2" :max="720" style="width: 100%" />
          <small class="agent-hint">面板按印度时区（比北京晚 2.5 小时），结束时间需至少 2 小时后，留足时差与运行缓冲。</small>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taskDialog = false">取消</el-button>
        <el-button type="primary" :loading="taskSaving" @click="saveTask">{{ taskEditMode ? '保存' : '提交任务' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>
