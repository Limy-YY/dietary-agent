<template>
  <el-dialog
    v-model="open"
    :title="mode === 'edit' ? '编辑档案' : '个人档案'"
    width="560px"
    top="8vh"
    append-to-body
    @open="onOpen"
  >
    <!-- 查看态 -->
    <div v-if="mode === 'view'">
      <div v-if="!profile.profile" class="sk-wrap">
        <div class="skeleton sk-line" style="width: 60%"></div>
        <div class="skeleton sk-line" style="width: 80%"></div>
        <div class="skeleton sk-line" style="width: 45%"></div>
      </div>

      <template v-else>
        <div class="profile-hero">
          <div class="ph-avatar">
            <img v-if="isImageAvatar" :src="p.avatar" alt="头像" />
            <span v-else>{{ p.avatar || '🍃' }}</span>
          </div>
          <div>
            <div class="ph-name">{{ p.name || '小膳' }}</div>
            <div class="ph-sub">目标：<span class="ph-goal">{{ goalLabel }}</span></div>
          </div>
        </div>

        <div class="pf-list">
          <div class="pf-li">
            <span class="pf-k">性别</span>
            <span class="pf-v">{{ p.gender || '—' }}</span>
          </div>
          <div class="pf-li">
            <span class="pf-k">年龄</span>
            <span class="pf-v">{{ fmtValue(p.age, '岁') }}</span>
          </div>
          <div class="pf-li">
            <span class="pf-k">身高</span>
            <span class="pf-v">{{ fmtValue(p.height_cm, 'cm') }}</span>
          </div>
          <div class="pf-li">
            <span class="pf-k">体重</span>
            <span class="pf-v">{{ fmtValue(p.weight_kg, 'kg') }}</span>
          </div>
          <div class="pf-li">
            <span class="pf-k">BMI</span>
            <span class="pf-v">{{ profile.bmi || '—' }}</span>
          </div>
          <div class="pf-li">
            <span class="pf-k">健康目标</span>
            <div class="pf-v pf-tags">
              <span class="pf-tag">{{ goalLabel }}</span>
            </div>
          </div>
          <div class="pf-li">
            <span class="pf-k">烹饪条件</span>
            <div class="pf-v pf-tags">
              <span v-for="c in p.cooking_equipment || []" :key="c" class="pf-tag">{{ c }}</span>
              <span v-if="!(p.cooking_equipment || []).length" class="pf-tag">未填写</span>
            </div>
          </div>
          <div class="pf-li">
            <span class="pf-k">疾病限制</span>
            <div class="pf-v pf-tags">
              <span v-for="item in conditionList" :key="item.id" class="pf-tag" :class="'cond-' + item.status">
                {{ item.label }} · {{ CONDITION_STATUS[item.status] }}
              </span>
              <span v-if="hasUnknownConditions" class="pf-tag pf-tag-muted">
                {{ conditionList.length ? '其余' : '' }}{{ CONDITION_STATUS.unknown }}
              </span>
            </div>
          </div>
          <div class="pf-li">
            <span class="pf-k">过敏原</span>
            <div class="pf-v pf-tags">
              <span v-for="a in p.allergies || []" :key="a" class="pf-tag">{{ a }}</span>
              <span v-if="!(p.allergies || []).length" class="pf-tag">无</span>
            </div>
          </div>
          <div class="pf-li">
            <span class="pf-k">宗教伦理</span>
            <div class="pf-v pf-tags">
              <span v-for="r in p.religious_ethical || []" :key="r" class="pf-tag">{{ r }}</span>
              <span v-if="!(p.religious_ethical || []).length" class="pf-tag">无</span>
            </div>
          </div>
          <div class="pf-li">
            <span class="pf-k">能量目标</span>
            <span class="pf-v">{{ targetKcalText }}</span>
          </div>
        </div>
      </template>
    </div>

    <!-- 编辑态 -->
    <div v-else>
      <el-form label-position="top" :model="form">
        <div class="pf-group">
          <div class="pf-avatar-name">
            <div class="avatar-big" title="点击上传图片" @click="pickAvatar">
              <img v-if="isFormImageAvatar" :src="form.avatar" alt="头像" />
              <span v-else>{{ form.avatar || '🍃' }}</span>
            </div>
            <div class="pf-avatar-name-field">
              <el-form-item label="昵称" style="margin-bottom: 4px">
                <el-input v-model="form.name" maxlength="10" placeholder="怎么称呼你" />
              </el-form-item>
              <div class="avatar-upload-tip">点击头像可上传图片，自动裁成圆形</div>
            </div>
          </div>
          <input ref="avatarFileInput" type="file" accept="image/*" class="pf-file" @change="onAvatarFile" />
        </div>

        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="性别" :class="{ 'pf-hl': isHl('gender') }">
              <el-select v-model="form.gender" style="width: 100%">
                <el-option label="女" value="女" />
                <el-option label="男" value="男" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="年龄" :class="{ 'pf-hl': isHl('age') }">
              <el-input-number v-model="form.age" :min="10" :max="100" :controls="false" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="健康目标" :class="{ 'pf-hl': isHl('goal_code') }">
              <el-select v-model="form.goal_code" style="width: 100%">
                <el-option v-for="g in GOAL_OPTIONS" :key="g.value" :label="g.label" :value="g.value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="身高（cm）" :class="{ 'pf-hl': isHl('height_cm') }">
              <el-input-number v-model="form.height_cm" :min="120" :max="220" :controls="false" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="体重（kg）" :class="{ 'pf-hl': isHl('weight_kg') }">
              <el-input-number v-model="form.weight_kg" :min="30" :max="200" :controls="false" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>

        <div class="pf-group" :class="{ 'pf-hl-group': isHl('cooking_equipment') }">
          <span class="field-label">烹饪设备</span>
          <PillGroup v-model="form.cooking_equipment" :options="COOKWARE_OPTIONS" allow-custom />
        </div>

        <div class="pf-group" :class="{ 'pf-hl-group': isHl('conditions') }">
          <span class="field-label">疾病情况</span>
          <div class="cond-grid">
            <div v-for="id in conditionIds" :key="id" class="cond-row">
              <span class="cond-name">{{ conditionLabels[id] }}</span>
              <el-select v-model="form.conditions[id]" size="small" style="width: 120px">
                <el-option v-for="(label, key) in CONDITION_STATUS" :key="key" :label="label" :value="key" />
              </el-select>
            </div>
          </div>
          <div v-if="!conditionIds.length" class="cond-empty">疾病项目录加载中或为空，暂无法编辑疾病限制</div>
        </div>

        <div class="pf-group" :class="{ 'pf-hl-group': isHl('allergies') }">
          <span class="field-label">过敏原 / 忌口</span>
          <PillGroup v-model="form.allergies" :options="ALLERGY_OPTIONS" allow-custom />
        </div>

        <div class="pf-group" :class="{ 'pf-hl-group': isHl('religious_ethical') }">
          <span class="field-label">宗教伦理限制</span>
          <PillGroup v-model="form.religious_ethical" :options="ETHICAL_OPTIONS" allow-custom />
        </div>
      </el-form>
      <div class="modal-note">
        能量目标会根据你的身高、体重、年龄、性别自动计算，无需手动填写。
      </div>
    </div>

    <template #footer>
      <div v-if="mode === 'view'" style="display: flex; justify-content: flex-end">
        <el-button type="primary" @click="mode = 'edit'">编辑档案</el-button>
      </div>
      <div v-else style="display: flex; justify-content: flex-end; gap: 10px">
        <el-button @click="cancelEdit">取消</el-button>
        <el-button type="primary" :loading="profile.saving" @click="save">保存</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import PillGroup from './PillGroup.vue'
import { useProfileStore } from '@/stores/profile.js'
import { useUi } from '@/composables/useUi.js'
import { fetchConditionCatalog } from '@/api/profile.js'

const ui = useUi()
const profile = useProfileStore()

const highlightFields = computed(() => new Set(ui.profileHighlight || []))
const isHl = (field) => highlightFields.value.has(field)

/** 展示层文案：中文名称不落业务映射表，仅用于表单选项与兜底展示 */
const GOAL_OPTIONS = [
  { value: 'maintain', label: '维持' },
  { value: 'fat_loss', label: '减脂' },
  { value: 'muscle_gain', label: '增肌' },
  { value: 'glucose_control', label: '控糖' },
  { value: 'digestive_health', label: '改善肠胃' }
]
// 病种字典从 GET /conditions/catalog 动态拉取，前端不写死
const conditionCatalog = ref([]) // [{ condition_id, name_zh }]
const conditionCatalogLoaded = ref(false)
const conditionIds = computed(() => conditionCatalog.value.map((c) => c.condition_id))
const conditionLabels = computed(() => {
  const m = {}
  conditionCatalog.value.forEach((c) => {
    m[c.condition_id] = c.name_zh || c.condition_id
  })
  return m
})
const CONDITION_STATUS = { confirmed: '已确诊', suspected: '疑似', unknown: '未填写' }
const ALLERGY_OPTIONS = ['花生', '牛奶', '海鲜', '鸡蛋', '麸质', '无']
const ETHICAL_OPTIONS = ['清真', '素食', '不吃牛肉', '不吃猪肉', '无']
const COOKWARE_OPTIONS = ['灶具', '电饭煲', '空气炸锅', '微波炉', '蒸锅', '烤箱']

const open = computed({
  get: () => ui.profileOpen,
  set: (v) => {
    ui.profileOpen = v
    if (!v) ui.profileHighlight = []
  }
})
const mode = computed({
  get: () => ui.profileMode,
  set: (v) => (ui.profileMode = v)
})

const p = computed(() => profile.profile || {})
const isImageAvatar = computed(() => String(p.value.avatar || '').startsWith('data:image'))
const goalLabel = computed(
  () => p.value.goal_name || GOAL_OPTIONS.find((g) => g.value === p.value.goal_code)?.label || '未设置'
)
/** 铁律 null≠0：只有 null/undefined 才判「未计算」，0 或非法值也如实呈现为数字，不做假兜底 */
const targetKcalText = computed(() => {
  const v = p.value.target_calories
  if (v == null) return '未计算'
  const n = Number(v)
  return Number.isFinite(n) ? `约 ${Math.round(n)} kcal` : '未计算'
})

const avatarFileInput = ref(null)
const isFormImageAvatar = computed(() => String(form.avatar || '').startsWith('data:image'))

const conditionList = computed(() => {
  const c = p.value.conditions || {}
  return conditionIds.value.filter((id) => c[id] && c[id].status && c[id].status !== 'unknown').map((id) => ({
    id,
    label: conditionLabels.value[id] || id,
    status: c[id].status
  }))
})

/** 三态下「未填写」≠「无」：只要还有未核查的疾病项就提示，避免把 unknown 误读成「无病」 */
const hasUnknownConditions = computed(() => {
  const c = p.value.conditions || {}
  if (!conditionIds.value.length) return true
  return conditionIds.value.some((id) => !c[id] || !c[id].status || c[id].status === 'unknown')
})

function fmtValue(v, unit) {
  if (v === null || v === undefined || v === '') return '—'
  return `${v} ${unit}`
}

const form = reactive({
  name: '',
  avatar: '',
  gender: '女',
  age: 26,
  height_cm: 158,
  weight_kg: 58,
  goal_code: 'fat_loss',
  cooking_equipment: [],
  conditions: {},
  allergies: [],
  religious_ethical: []
})
const backup = ref(null)

function emptyConditions() {
  const out = {}
  conditionIds.value.forEach((id) => {
    out[id] = 'unknown'
  })
  return out
}

/** 空列表或含「无」→ 回显为 ['无']，与后端「空数组=无限制」口径对齐，保证编辑态能看到选中态 */
function toNoneList(list) {
  const arr = list || []
  return arr.length && !arr.includes('无') ? [...arr] : ['无']
}

function fillForm() {
  const pr = profile.profile || {}
  form.name = pr.name || '小膳'
  form.avatar = pr.avatar || '🍃'
  form.gender = pr.gender === '男' ? '男' : '女'
  form.age = Number(pr.age) || 26
  form.height_cm = Number(pr.height_cm) || 158
  form.weight_kg = Number(pr.weight_kg) || 58
  form.goal_code = pr.goal_code || 'fat_loss'
  form.cooking_equipment = [...(pr.cooking_equipment || [])]
  form.allergies = toNoneList(pr.allergies)
  form.religious_ethical = toNoneList(pr.religious_ethical)
  const cond = emptyConditions()
  conditionIds.value.forEach((id) => {
    const st = pr.conditions && pr.conditions[id] && pr.conditions[id].status
    cond[id] = ['confirmed', 'suspected', 'unknown'].includes(st) ? st : 'unknown'
  })
  form.conditions = cond
  return {
    ...form,
    cooking_equipment: [...form.cooking_equipment],
    allergies: [...form.allergies],
    religious_ethical: [...form.religious_ethical],
    conditions: { ...cond }
  }
}

async function loadConditionCatalog() {
  if (conditionCatalogLoaded.value) return
  try {
    conditionCatalog.value = (await fetchConditionCatalog()) || []
  } catch (e) {
    conditionCatalog.value = []
  } finally {
    conditionCatalogLoaded.value = true
  }
}

async function onOpen() {
  // 必须 await：否则应用刚启动、profile.load() 未完成时，fillForm 会读空档案回填默认值，
  // 用户点保存就把默认 26 岁/158cm/58kg 写回真实档案（BUG-048）。
  if (!profile.profile) await profile.load()
  await loadConditionCatalog()
  backup.value = fillForm()
}

function pickAvatar() {
  avatarFileInput.value && avatarFileInput.value.click()
}

async function onAvatarFile(e) {
  const file = e.target.files && e.target.files[0]
  e.target.value = '' // 允许重复选择同一张图
  if (!file) return
  if (!/^image\//.test(file.type)) {
    ElMessage.warning('请选择图片文件')
    return
  }
  const dataUrl = await cropAvatar(file)
  if (dataUrl) form.avatar = dataUrl
}

/** 居中裁成方形、压到 160px 再存 dataURL，避免大图撑爆档案字段 */
function cropAvatar(file) {
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onload = () => {
      const img = new Image()
      img.onload = () => {
        const size = 160
        const canvas = document.createElement('canvas')
        canvas.width = size
        canvas.height = size
        const ctx = canvas.getContext('2d')
        ctx.fillStyle = '#fff'
        ctx.fillRect(0, 0, size, size)
        const s = Math.min(img.width, img.height)
        ctx.drawImage(img, (img.width - s) / 2, (img.height - s) / 2, s, s, 0, 0, size, size)
        resolve(canvas.toDataURL('image/jpeg', 0.88))
      }
      img.onerror = () => {
        ElMessage.error('这张图读不出来，换一张试试')
        resolve(null)
      }
      img.src = reader.result
    }
    reader.onerror = () => resolve(null)
    reader.readAsDataURL(file)
  })
}

function cancelEdit() {
  const b = backup.value
  if (b) {
    Object.assign(form, {
      ...b,
      cooking_equipment: [...b.cooking_equipment],
      allergies: [...b.allergies],
      religious_ethical: [...b.religious_ethical],
      conditions: { ...b.conditions }
    })
  }
  mode.value = 'view'
}

async function save() {
  const payload = {
    name: String(form.name || '').trim() || '小膳',
    avatar: String(form.avatar || '').trim() || '🍃',
    gender: form.gender,
    age: Number(form.age),
    height_cm: Number(form.height_cm),
    weight_kg: Number(form.weight_kg),
    goal_code: form.goal_code,
    cooking_equipment: [...form.cooking_equipment],
    conditions: conditionIds.value.reduce((acc, id) => {
      acc[id] = { status: form.conditions[id] || 'unknown' }
      return acc
    }, {}),
    allergies: form.allergies.filter((x) => x && x !== '无'),
    religious_ethical: form.religious_ethical.filter((x) => x && x !== '无')
  }
  try {
    await profile.save(payload)
    ElMessage.success('档案已保存')
    backup.value = fillForm()
    mode.value = 'view'
  } catch (e) {
    ElMessage.error(e.message || '保存失败，请稍后重试')
  }
}

onMounted(loadConditionCatalog)
</script>

<style scoped>
.sk-wrap {
  padding: 8px 0;
}

.pf-avatar-name {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.pf-avatar-name-field {
  flex: 1;
  min-width: 0;
}

.cond-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px 32px;
}

.cond-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 0;
}

.cond-name {
  font-size: 13px;
  color: var(--text-main, #333);
  /* 固定名称宽度，让「痛风/高血压」等字数不同的病种其输入框左缘对齐 */
  width: 3em;
  flex-shrink: 0;
}

/* clarify 补录引导：缺失字段高亮 */
.pf-hl :deep(.el-form-item__label) {
  color: #4a7c59;
  font-weight: 700;
}
.pf-hl :deep(.el-form-item__label)::before {
  content: '待补 · ';
  color: #e8942c;
  font-weight: 600;
}
.pf-hl-group .field-label {
  color: #4a7c59;
  font-weight: 700;
}
.pf-hl-group .field-label::before {
  content: '待补 · ';
  color: #e8942c;
  font-weight: 600;
}

.cond-empty {
  font-size: 12px;
  color: var(--text-sub, #999);
  padding: 4px 0;
}
</style>
