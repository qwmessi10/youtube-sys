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

// 画面比例预设：运营只选比例，前端映射成具体像素（运营不懂 1920/1080）。
const RATIO_PRESETS = {
  "16:9": { width: 1920, height: 1080, label: "横屏 16:9（YouTube 常规）" },
  "9:16": { width: 1080, height: 1920, label: "竖屏 9:16（Shorts/竖版）" },
};
// 从宽高反推比例 key，用于编辑时回显。
function ratioOf(w, h) {
  return w >= h ? "16:9" : "9:16";
}

// 新建表单：运营只填名称、说明、比例、调整需求（组件由开发接入，运营不填组件ID）。
const createForm = ref({ name: "", description: "", ratio: "16:9", adjust_notes: "" });
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
    const preset = RATIO_PRESETS[createForm.value.ratio];
    await axios.post("/api/video-templates/", {
      name: createForm.value.name,
      description: createForm.value.description,
      adjust_notes: createForm.value.adjust_notes,
      width: preset.width,
      height: preset.height,
      // 新模板默认待接入（status=pending），等开发写好组件后置为就绪。
    });
    ElMessage.success("模板已创建（待接入）。请上传参考视频分析、填写调整需求，开发接入组件后即可出片。");
    createForm.value = { name: "", description: "", ratio: "16:9", adjust_notes: "" };
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
  if (!Array.isArray(editing.value.assets_schema)) editing.value.assets_schema = [];
  // 根据宽高回显比例选择
  editing.value.ratio = ratioOf(editing.value.width, editing.value.height);
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
    const preset = RATIO_PRESETS[editing.value.ratio] || RATIO_PRESETS["16:9"];
    const payload = {
      name: editing.value.name,
      description: editing.value.description,
      adjust_notes: editing.value.adjust_notes,
      width: preset.width,
      height: preset.height,
      shot_count: editing.value.shot_count,
      shot_duration: editing.value.shot_duration,
      variables_schema: editing.value.variables_schema,
      assets_schema: editing.value.assets_schema,
      enabled: editing.value.enabled,
      // 组件ID / status 由开发在后台维护，运营侧不提交。
    };
    const { data } = await axios.patch(`/api/video-templates/${editing.value.id}/`, payload);
    editing.value = data;
    editing.value.ratio = ratioOf(data.width, data.height);
    ElMessage.success("模板已保存");
    await loadTemplates();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
}

// 模板状态 → 中文标签 + 颜色
function statusLabel(s) {
  return s === "ready" ? "已就绪（可出片）" : "待接入（开发制作中）";
}
function statusType(s) {
  return s === "ready" ? "success" : "warning";
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

// 上传素材：key 直接来自槽位声明（不再手打），uploadFile 由 el-upload 传入。
const uploadingKey = ref("");
async function uploadAsset(slotKey, uploadFile) {
  const file = uploadFile?.raw;
  if (!file) return;
  uploadingKey.value = slotKey;
  try {
    const fd = new FormData();
    fd.append("key", slotKey);
    fd.append("file", file);
    const { data } = await axios.post(`/api/video-templates/${editing.value.id}/upload_asset/`, fd);
    editing.value = data;
    editing.value.ratio = ratioOf(data.width, data.height);
    ElMessage.success(`素材「${slotKey}」已上传`);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "素材上传失败");
  } finally {
    uploadingKey.value = "";
  }
}

// 已上传素材：按槽位 key 取回文件记录（用于显示“已上传/未上传”与文件名）。
function uploadedAsset(key) {
  return (editing.value.assets || []).find((a) => a.key === key) || null;
}

// 素材槽位声明的增删（和变量声明对称，供开发/运营定义模板需要哪些素材）。
function addAssetSlot() {
  if (!Array.isArray(editing.value.assets_schema)) editing.value.assets_schema = [];
  editing.value.assets_schema.push({ key: "", name: "", desc: "", required: true, source: "upload" });
}
function removeAssetSlot(i) {
  editing.value.assets_schema.splice(i, 1);
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
      description="模板决定流程一批量生成视频的画面样式。新建模板 → 上传参考视频让 AI 分析（自动给出旁白段数/时长和建议变量）→ 声明变量（如优惠码）→ 在「调整需求」里写清楚画面要怎么做 → 上传默认素材（如操作录屏）。画面组件由开发接入，接入后模板变为「已就绪」，即可在流程一任务里选用批量出片。"
      type="success" :closable="false" show-icon class="intro"
    />

    <el-card class="create-card" shadow="never">
      <template #header><strong>新建模板</strong></template>
      <el-form label-position="top" @submit.prevent="createTemplate">
        <el-form :inline="true">
          <el-form-item label="模板名称"><el-input v-model="createForm.name" placeholder="如：1xBet 左右分屏" /></el-form-item>
          <el-form-item label="说明"><el-input v-model="createForm.description" placeholder="选填" style="width: 240px" /></el-form-item>
          <el-form-item label="画面比例">
            <el-select v-model="createForm.ratio" style="width: 240px">
              <el-option v-for="(p, k) in RATIO_PRESETS" :key="k" :label="p.label" :value="k" />
            </el-select>
          </el-form-item>
        </el-form>
        <el-form-item label="调整需求（告诉开发画面要怎么做/怎么改，越具体越好）">
          <el-input v-model="createForm.adjust_notes" type="textarea" :autosize="{ minRows: 2 }"
            placeholder="如：左侧放品牌名和优惠码，优惠码要大、红色；右侧放手机操作录屏；整体深绿配色。" />
        </el-form-item>
        <el-button type="primary" :loading="creating" @click="createTemplate">创建模板</el-button>
      </el-form>
    </el-card>

    <el-card shadow="never" class="table-card">
      <template #header><div class="card-title"><strong>模板列表</strong><el-button size="small" @click="loadTemplates">刷新</el-button></div></template>
      <el-table :data="templates" v-loading="loading" size="small" empty-text="暂无模板">
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column label="比例" width="90"><template #default="{ row }">{{ row.width >= row.height ? '16:9' : '9:16' }}</template></el-table-column>
        <el-table-column label="旁白" width="100"><template #default="{ row }">{{ row.shot_count }} 段 × {{ row.shot_duration }}s</template></el-table-column>
        <el-table-column label="变量" width="80"><template #default="{ row }">{{ (row.variables_schema || []).length }} 个</template></el-table-column>
        <el-table-column label="素材" width="80"><template #default="{ row }">{{ (row.assets || []).length }} 个</template></el-table-column>
        <el-table-column label="已分析" width="80"><template #default="{ row }"><el-tag size="small" :type="row.analysis && row.analysis.text ? 'success' : 'info'" effect="plain">{{ row.analysis && row.analysis.text ? '是' : '否' }}</el-tag></template></el-table-column>
        <el-table-column label="接入状态" width="150"><template #default="{ row }"><el-tag size="small" :type="statusType(row.status)" effect="light">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
        <el-table-column label="启用" width="80"><template #default="{ row }"><el-tag size="small" :type="row.enabled ? 'success' : 'info'" effect="plain">{{ row.enabled ? '启用' : '停用' }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="100"><template #default="{ row }"><el-button size="small" type="primary" plain @click="openEdit(row)">编辑</el-button></template></el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="drawer" title="编辑视频模板" size="820px" :destroy-on-close="true">
      <div v-if="editing" class="edit-body">
        <el-alert
          :title="editing.status === 'ready' ? '该模板已接入组件，可用于流程一出片。' : '该模板尚未接入画面组件，暂不能出片。请填好调整需求，等开发接入后自动变为「已就绪」。'"
          :type="editing.status === 'ready' ? 'success' : 'warning'" :closable="false" show-icon class="status-alert"
        />
        <el-form label-position="top">
          <el-form :inline="true">
            <el-form-item label="模板名称"><el-input v-model="editing.name" style="width: 240px" /></el-form-item>
            <el-form-item label="画面比例">
              <el-select v-model="editing.ratio" style="width: 220px">
                <el-option v-for="(p, k) in RATIO_PRESETS" :key="k" :label="p.label" :value="k" />
              </el-select>
            </el-form-item>
            <el-form-item label="旁白段数"><el-input-number v-model="editing.shot_count" :min="1" :max="10" /></el-form-item>
            <el-form-item label="每段时长(秒)"><el-input-number v-model="editing.shot_duration" :min="1" :max="60" /></el-form-item>
            <el-form-item label="启用"><el-switch v-model="editing.enabled" /></el-form-item>
          </el-form>
          <el-form-item label="说明"><el-input v-model="editing.description" type="textarea" :autosize="{ minRows: 2 }" /></el-form-item>
          <el-form-item label="调整需求（告诉开发画面要怎么改，越具体越好）">
            <el-input v-model="editing.adjust_notes" type="textarea" :autosize="{ minRows: 3 }"
              placeholder="如：优惠码字号再大一点、放到左上角；背景换成深蓝色；右侧录屏加圆角边框。" />
          </el-form-item>
        </el-form>

        <el-divider content-position="left">变量声明</el-divider>
        <small class="hint">创建任务时会按这里的变量动态生成输入框，并告知 AI 在文案里用 {变量名} 引用。允许AI生成=否 表示该值必须由用户提供、AI 不得编造（如优惠码）。</small>
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
          <p class="hint">模型：{{ editing.analysis.model }}，分析于 {{ datetime(editing.analysis.analyzed_at) }}。分析已自动回填旁白段数/时长和建议变量（可在上方微调）。</p>
          <div v-if="(editing.analysis.suggested_variables || []).length" class="suggest-vars">
            <span class="hint">AI 识别到的变量：</span>
            <el-tag v-for="sv in editing.analysis.suggested_variables" :key="sv.key" size="small"
              :type="sv.ai_editable ? 'info' : 'warning'" effect="plain">
              {{ sv.label || sv.key }}（{{ sv.key }}）{{ sv.ai_editable ? '' : '·人工提供' }}
            </el-tag>
          </div>

          <!-- 关键帧图：ffmpeg 按 Gemini 关键帧时间点 + 场景检测切换点抽出的真实画面帧，
               供开发/AI 对照复刻画面（比纯文字描述精确得多）。点图可放大。 -->
          <div v-if="(editing.keyframe_images || []).length" class="keyframes">
            <span class="hint">关键帧截图（共 {{ editing.keyframe_images.length }} 张，供对照原画面复刻）：</span>
            <div class="kf-grid">
              <div v-for="(kf, i) in editing.keyframe_images" :key="i" class="kf-item">
                <el-image
                  :src="kf.url" fit="cover" class="kf-img"
                  :preview-src-list="editing.keyframe_images.map(k => k.url)"
                  :initial-index="i" :preview-teleported="true"
                />
                <span class="kf-time">{{ Number(kf.time).toFixed(2) }}s</span>
              </div>
            </div>
          </div>

          <!-- 结构化规格：Gemini 给出的画面布局 JSON（区域坐标/文字/配色/分镜），
               目前以折叠 JSON 呈现，开发复刻时对照。 -->
          <el-collapse v-if="editing.analysis.spec && Object.keys(editing.analysis.spec).length" class="spec-collapse">
            <el-collapse-item title="结构化布局规格（区域坐标 / 文字 / 配色 / 分镜）">
              <pre class="analysis-pre">{{ JSON.stringify(editing.analysis.spec, null, 2) }}</pre>
            </el-collapse-item>
          </el-collapse>

          <el-collapse class="spec-collapse">
            <el-collapse-item title="完整文字分析">
              <pre class="analysis-pre">{{ editing.analysis.text }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>

        <el-divider content-position="left">素材槽位声明</el-divider>
        <small class="hint">
          声明这个模板需要哪些素材（每个槽位对应画面里一处，如“手机操作录屏”）。标识 key 必须和画面组件里访问的一致（由开发定义，运营勿改）。
          声明后，下方「素材上传」会按槽位列出上传按钮，无需手打标识。来源=AI 生成的素材出片时由系统自动生成，不用在这里上传。
        </small>
        <div v-for="(s, i) in editing.assets_schema" :key="i" class="asset-slot-row">
          <el-input v-model="s.key" placeholder="标识 key（如 screen_record）" style="width: 180px" />
          <el-input v-model="s.name" placeholder="显示名（如 手机操作录屏）" style="width: 160px" />
          <el-input v-model="s.desc" placeholder="说明（这个素材是什么/放哪）" style="width: 220px" />
          <el-select v-model="s.source" style="width: 120px">
            <el-option label="人工上传" value="upload" />
            <el-option label="AI 生成" value="ai" />
          </el-select>
          <el-checkbox v-model="s.required">必需</el-checkbox>
          <el-button size="small" type="danger" plain @click="removeAssetSlot(i)">删除</el-button>
        </div>
        <el-button size="small" plain @click="addAssetSlot">+ 添加素材槽位</el-button>

        <el-divider content-position="left">素材上传</el-divider>
        <small v-if="!(editing.assets_schema || []).length" class="hint">还没有素材槽位。请先在上方「素材槽位声明」添加槽位（或上传参考视频让 AI 分析后自动补全）。</small>
        <div v-for="(s, i) in (editing.assets_schema || [])" :key="'up' + i" class="asset-upload-row">
          <div class="asset-upload-info">
            <div class="asset-upload-name">
              {{ s.name || s.key }}
              <el-tag v-if="s.required" size="small" type="danger" effect="plain">必需</el-tag>
              <el-tag size="small" :type="s.source === 'ai' ? 'info' : 'warning'" effect="plain">{{ s.source === 'ai' ? 'AI 生成' : '人工上传' }}</el-tag>
            </div>
            <div class="asset-upload-desc">
              <span class="asset-key-code">{{ s.key }}</span>
              <span v-if="s.desc"> · {{ s.desc }}</span>
            </div>
            <div v-if="uploadedAsset(s.key)" class="asset-uploaded">
              ✓ 已上传：{{ uploadedAsset(s.key).filename || uploadedAsset(s.key).name }}
              <span v-if="uploadedAsset(s.key).duration">（{{ uploadedAsset(s.key).duration }}s）</span>
            </div>
            <div v-else class="asset-notyet">尚未上传</div>
          </div>
          <el-upload
            v-if="s.source !== 'ai'"
            :show-file-list="false" :auto-upload="false"
            :on-change="(f) => uploadAsset(s.key, f)"
          >
            <el-button plain :loading="uploadingKey === s.key">
              {{ uploadedAsset(s.key) ? '重新上传' : '上传素材文件' }}
            </el-button>
          </el-upload>
          <span v-else class="asset-ai-note">出片时自动生成</span>
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
.status-alert { margin-bottom: 12px; }
.suggest-vars { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 6px 0; }
.analysis { margin-top: 10px; }
.analysis-pre { white-space: pre-wrap; word-break: break-word; background: #f5f7fa; border-radius: 6px; padding: 10px 12px; font-size: 12px; line-height: 1.6; max-height: 400px; overflow: auto; }
.keyframes { margin: 10px 0; }
.kf-grid { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 4px; }
.kf-item { position: relative; width: 160px; }
.kf-img { width: 160px; height: 90px; border-radius: 6px; border: 1px solid #dcdfe6; cursor: pointer; }
.kf-time { position: absolute; left: 4px; bottom: 4px; background: rgba(0,0,0,0.6); color: #fff; font-size: 11px; padding: 1px 5px; border-radius: 3px; }
.spec-collapse { margin-top: 10px; }
.asset-slot-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.asset-upload-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; border: 1px solid #ebeef5; border-radius: 8px; margin-bottom: 8px; }
.asset-upload-info { flex: 1; }
.asset-upload-name { font-weight: 600; display: flex; align-items: center; gap: 6px; }
.asset-upload-desc { color: #909399; font-size: 12px; margin-top: 2px; }
.asset-key-code { font-family: monospace; background: #f0f2f5; padding: 1px 6px; border-radius: 4px; color: #606266; }
.asset-uploaded { color: #67c23a; font-size: 12px; margin-top: 4px; }
.asset-notyet { color: #e6a23c; font-size: 12px; margin-top: 4px; }
.asset-ai-note { color: #909399; font-size: 12px; }
.save-bar { margin-top: 24px; }
</style>
