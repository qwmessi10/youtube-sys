<script setup>
// 视频模板库：创建/编辑模板、上传参考视频用 Gemini 分析、上传素材、声明变量。
import { onMounted, ref } from "vue";
import axios from "axios";
import { ElMessage } from "element-plus";

const templates = ref([]);
const loading = ref(false);

// 编辑抽屉
const drawer = ref(false);
const editing = ref(null);        // 当前编辑的模板对象
const analyzing = ref(false);
const saving = ref(false);

// 新建表单
const createForm = ref({ name: "", description: "", width: 1920, height: 1080, fps: 30, composition_id: "" });
const creating = ref(false);

async function loadTemplates() {
  loading.value = true;
  try {
    const { data } = await axios.get("/api/video-templates/", { params: { page: 1 } });
    templates.value = data.results || data || [];
  } catch {
    ElMessage.error("加载模板列表失败");
  } finally {
    loading.value = false;
  }
}

async function createTemplate() {
  if (!createForm.value.name.trim()) return ElMessage.warning("请填写模板名称");
  creating.value = true;
  try {
    await axios.post("/api/video-templates/", createForm.value);
    ElMessage.success("模板已创建，可上传参考视频分析、声明变量");
    createForm.value = { name: "", description: "", width: 1920, height: 1080, fps: 30, composition_id: "" };
    await loadTemplates();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "创建模板失败");
  } finally {
    creating.value = false;
  }
}

function openEdit(t) {
  // 深拷贝，避免直接改列表数据
  editing.value = JSON.parse(JSON.stringify(t));
  if (!Array.isArray(editing.value.variables_schema)) editing.value.variables_schema = [];
  drawer.value = true;
}

function addVariable() {
  editing.value.variables_schema.push({ key: "", label: "", required: true, ai_editable: false });
}
function removeVariable(i) {
  editing.value.variables_schema.splice(i, 1);
}

async function saveTemplate() {
  saving.value = true;
  try {
    const payload = {
      name: editing.value.name,
      description: editing.value.description,
      width: editing.value.width,
      height: editing.value.height,
      fps: editing.value.fps,
      composition_id: editing.value.composition_id,
      variables_schema: editing.value.variables_schema,
      enabled: editing.value.enabled,
    };
    const { data } = await axios.patch(`/api/video-templates/${editing.value.id}/`, payload);
    editing.value = data;
    ElMessage.success("模板已保存");
    await loadTemplates();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
}

// 上传参考视频并分析（同步，较慢）
async function analyzeVideo(uploadFile) {
  const file = uploadFile?.raw;
  if (!file) return;
  analyzing.value = true;
  try {
    const fd = new FormData();
    fd.append("file", file);
    const { data } = await axios.post(`/api/video-templates/${editing.value.id}/analyze/`, fd, { timeout: 600000 });
    editing.value = data;
    ElMessage.success("视频分析完成，见下方分析结果");
    await loadTemplates();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "视频分析失败");
  } finally {
    analyzing.value = false;
  }
}

// 上传素材
const assetKey = ref("");
async function uploadAsset(uploadFile) {
  const file = uploadFile?.raw;
  if (!file) return;
  if (!assetKey.value.trim()) return ElMessage.warning("请先填写素材标识（如 screen_record）");
  try {
    const fd = new FormData();
    fd.append("key", assetKey.value.trim());
    fd.append("file", file);
    const { data } = await axios.post(`/api/video-templates/${editing.value.id}/upload_asset/`, fd);
    editing.value = data;
    ElMessage.success(`素材「${assetKey.value}」已上传`);
    assetKey.value = "";
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "素材上传失败");
  }
}

function datetime(v) {
  return v ? new Date(v).toLocaleString("zh-CN", { hour12: false }) : "";
}

onMounted(loadTemplates);
</script>

<template>
  <div>
    <el-alert
      title="视频模板库"
      description="模板决定流程一批量生成视频的画面样式。流程：新建模板 → 上传参考视频让 AI 分析出规格 → 声明变量（如优惠码）→ 上传默认素材（如操作录屏）→ 交由开发把 Remotion 组件调到位并填入组件ID。之后创建流程一任务即可选用该模板批量出片。"
      type="success" :closable="false" show-icon class="intro"
    />

    <el-card class="create-card" shadow="never">
      <template #header><strong>新建模板</strong></template>
      <el-form :inline="true" @submit.prevent="createTemplate">
        <el-form-item label="模板名称"><el-input v-model="createForm.name" placeholder="如：1xBet 左右分屏" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="createForm.description" placeholder="选填" style="width: 220px" /></el-form-item>
        <el-form-item label="宽"><el-input-number v-model="createForm.width" :min="240" :max="3840" :step="10" /></el-form-item>
        <el-form-item label="高"><el-input-number v-model="createForm.height" :min="240" :max="3840" :step="10" /></el-form-item>
        <el-form-item label="组件ID"><el-input v-model="createForm.composition_id" placeholder="如 SplitScreenPromo" style="width: 180px" /></el-form-item>
        <el-button type="primary" :loading="creating" @click="createTemplate">创建</el-button>
      </el-form>
    </el-card>

    <el-card shadow="never" class="table-card">
      <template #header><div class="card-title"><strong>模板列表</strong><el-button size="small" @click="loadTemplates">刷新</el-button></div></template>
      <el-table :data="templates" v-loading="loading" size="small" empty-text="暂无模板">
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column label="尺寸" width="120"><template #default="{ row }">{{ row.width }}×{{ row.height }}</template></el-table-column>
        <el-table-column prop="composition_id" label="组件ID" min-width="150"><template #default="{ row }">{{ row.composition_id || '（未接入）' }}</template></el-table-column>
        <el-table-column label="变量" width="90"><template #default="{ row }">{{ (row.variables_schema || []).length }} 个</template></el-table-column>
        <el-table-column label="素材" width="90"><template #default="{ row }">{{ (row.assets || []).length }} 个</template></el-table-column>
        <el-table-column label="已分析" width="90"><template #default="{ row }"><el-tag size="small" :type="row.analysis && row.analysis.text ? 'success' : 'info'" effect="plain">{{ row.analysis && row.analysis.text ? '是' : '否' }}</el-tag></template></el-table-column>
        <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag size="small" :type="row.enabled ? 'success' : 'info'" effect="light">{{ row.enabled ? '启用' : '停用' }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="120"><template #default="{ row }"><el-button size="small" type="primary" plain @click="openEdit(row)">编辑</el-button></template></el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="drawer" title="编辑视频模板" size="820px" :destroy-on-close="true">
      <div v-if="editing" class="edit-body">
        <el-form label-position="top">
          <el-form :inline="true">
            <el-form-item label="模板名称"><el-input v-model="editing.name" /></el-form-item>
            <el-form-item label="组件ID（Remotion Composition）"><el-input v-model="editing.composition_id" placeholder="如 SplitScreenPromo" style="width: 200px" /></el-form-item>
            <el-form-item label="宽"><el-input-number v-model="editing.width" :min="240" :max="3840" :step="10" /></el-form-item>
            <el-form-item label="高"><el-input-number v-model="editing.height" :min="240" :max="3840" :step="10" /></el-form-item>
            <el-form-item label="启用"><el-switch v-model="editing.enabled" /></el-form-item>
          </el-form>
          <el-form-item label="说明"><el-input v-model="editing.description" type="textarea" :autosize="{ minRows: 2 }" /></el-form-item>
        </el-form>

        <el-divider content-position="left">变量声明</el-divider>
        <small class="hint">创建任务时会按这里的变量动态生成输入框。ai_editable=否 表示该值必须由用户提供、AI 不得生成（如优惠码）。</small>
        <div v-for="(v, i) in editing.variables_schema" :key="i" class="var-row">
          <el-input v-model="v.key" placeholder="变量名（如 promo_code）" style="width: 180px" />
          <el-input v-model="v.label" placeholder="显示名（如 优惠码）" style="width: 160px" />
          <el-checkbox v-model="v.required">必填</el-checkbox>
          <el-checkbox v-model="v.ai_editable">允许AI生成</el-checkbox>
          <el-button size="small" type="danger" plain @click="removeVariable(i)">删除</el-button>
        </div>
        <el-button size="small" plain @click="addVariable">+ 添加变量</el-button>

        <el-divider content-position="left">参考视频分析（Gemini）</el-divider>
        <el-upload :show-file-list="false" :auto-upload="false" accept="video/*" :on-change="analyzeVideo">
          <el-button type="primary" plain :loading="analyzing">{{ analyzing ? '分析中（可能需要几十秒到几分钟）…' : '上传参考视频并分析' }}</el-button>
        </el-upload>
        <div v-if="editing.analysis && editing.analysis.text" class="analysis">
          <p class="hint">模型：{{ editing.analysis.model }}，分析于 {{ datetime(editing.analysis.analyzed_at) }}</p>
          <pre class="analysis-pre">{{ editing.analysis.text }}</pre>
        </div>

        <el-divider content-position="left">默认素材</el-divider>
        <div class="asset-upload">
          <el-input v-model="assetKey" placeholder="素材标识，如 screen_record" style="width: 220px" />
          <el-upload :show-file-list="false" :auto-upload="false" :on-change="uploadAsset">
            <el-button plain>上传素材文件</el-button>
          </el-upload>
        </div>
        <div class="asset-list">
          <el-tag v-for="a in (editing.assets || [])" :key="a.key" type="success" effect="plain" class="asset-tag">{{ a.key }}：{{ a.name }}</el-tag>
        </div>

        <div class="save-bar">
          <el-button type="primary" :loading="saving" @click="saveTemplate">保存模板</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.intro { margin-bottom: 12px; }
.create-card { margin-bottom: 12px; }
.table-card { margin-bottom: 12px; }
.card-title { display: flex; justify-content: space-between; align-items: center; }
.edit-body { padding-bottom: 40px; }
.hint { color: #909399; font-size: 12px; display: block; margin-bottom: 8px; }
.var-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.analysis { margin-top: 10px; }
.analysis-pre { white-space: pre-wrap; word-break: break-word; background: #f5f7fa; border-radius: 6px; padding: 10px 12px; font-size: 12px; line-height: 1.6; max-height: 400px; overflow: auto; }
.asset-upload { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.asset-list { display: flex; flex-wrap: wrap; gap: 8px; }
.asset-tag { margin-right: 4px; }
.save-bar { margin-top: 24px; }
</style>
