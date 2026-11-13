<template>
  <el-dialog
    v-model="open"
    :title="mode === 'edit' ? '编辑档案' : '个人档案'"
    width="520px"
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
            <img v-if="isImageAvatar" :src="profile.avatar" alt="头像" />
            <span v-else>{{ profile.avatar }}</span>
          </div>
          <div>
            <div class="ph-name">{{ profile.name }}</div>
            <div class="ph-sub">目标：{{ profile.goals.join('、') || '未设置' }}</div>
          </div>
        </div>

        <div class="pf-list">
          <div class="pf-li">
            <span class="pf-k">性别</span>
            <span class="pf-v">{{ p.sex || '—' }}</span>
          </div>
          <div class="pf-li">
            <span class="pf-k">年龄</span>
            <span class="pf-v">{{ p.age ? p.age + ' 岁' : '—' }}</span>
          </div>
          <div class="pf-li">
            <span class="pf-k">身高</span>
            <span class="pf-v">{{ p.height_cm ? p.height_cm + ' cm' : '—' }}</span>
          </div>
          <div class="pf-li">
            <span class="pf-k">体重</span>
            <span class="pf-v">{{ p.weight_kg ? p.weight_kg + ' kg' : '—' }}</span>
          </div>
          <div class="pf-li">
            <span class="pf-k">健康目标</span>
            <div class="pf-v pf-tags">
              <span v-for="g in profile.goals" :key="g" class="pf-tag">{{ g }}</span>
              <span v-if="!profile.goals.length" class="pf-tag">无</span>
            </div>
          </div>
          <div class="pf-li">
            <span class="pf-k">烹饪条件</span>
            <div class="pf-v pf-tags">
              <span v-for="c in p.extras?.cookware || []" :key="c" class="pf-tag">{{ c }}</span>
              <span v-if="!(p.extras?.cookware || []).length" class="pf-tag">无</span>
            </div>
          </div>
          <div class="pf-li">
            <span class="pf-k">疾病限制</span>
            <div class="pf-v pf-tags">
              <span v-for="c in conditionList" :key="c" class="pf-tag">{{ c }}</span>
            </div>
          </div>
          <div class="pf-li">
            <span class="pf-k">过敏原</span>
            <div class="pf-v pf-tags">
              <span v-for="a in allAllergies" :key="a" class="pf-tag">{{ a }}</span>
              <span v-if="!allAllergies.length" class="pf-tag">无</span>
            </div>
          </div>
          <div class="pf-li">
            <span class="pf-k">宗教伦理</span>
            <div class="pf-v pf-tags">
              <span v-for="r in p.extras?.religion || []" :key="r" class="pf-tag">{{ r }}</span>
              <span v-if="!(p.extras?.religion || []).length" class="pf-tag">无</span>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 编辑态 -->
    <div v-else>
      <el-form label-position="top" :model="form">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="昵称">
              <el-input v-model="form.name" maxlength="10" placeholder="怎么称呼你" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="头像（emoji 也可以）">
              <el-input v-model="form.avatar" maxlength="2" placeholder="🍃" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="性别">
              <el-select v-model="form.sex" style="width: 100%">
                <el-option label="女" value="女" />
                <el-option label="男" value="男" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="年龄">
              <el-input-number v-model="form.age" :min="12" :max="100" :controls="false" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="活动量">
              <el-select v-model="form.activity_level" style="width: 100%">
                <el-option label="久坐少动" value="light" />
                <el-option label="每周 3 次" value="moderate" />
                <el-option label="经常运动" value="high" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="身高（cm）">
              <el-input-number v-model="form.height_cm" :min="100" :max="230" :controls="false" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="体重（kg）">
              <el-input-number v-model="form.weight_kg" :min="30" :max="200" :controls="false" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>

        <div class="pf-group">
          <span class="field-label">饮食目标（可多选）</span>
          <PillGroup v-model="form.goals" :options="GOAL_OPTIONS" />
        </div>

        <div class="pf-group">
          <span class="field-label">过敏 / 忌口</span>
          <PillGroup v-model="form.allergies" :options="ALLERGY_OPTIONS" allow-custom />
        </div>

        <div class="pf-group">
          <span class="field-label">常用厨具</span>
          <PillGroup v-model="form.cookware" :options="COOKWARE_OPTIONS" allow-custom />
        </div>
      </el-form>
      <div class="modal-note">保存后会用 PUT /api/profile 写回，能量目标随身高体重重新估算。</div>
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
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import PillGroup from './PillGroup.vue'
import { useProfileStore } from '@/stores/profile.js'
import { useUi } from '@/composables/useUi.js'

const ui = useUi()
const profile = useProfileStore()

const GOAL_OPTIONS = ['减脂', '增肌', '控糖', '控血压', '均衡饮食']
const ALLERGY_OPTIONS = ['花生', '牛奶', '海鲜', '鸡蛋', '麸质', '无']
const COOKWARE_OPTIONS = ['灶具', '电饭煲', '空气炸锅', '微波炉', '蒸锅']

const open = computed({
  get: () => ui.profileOpen,
  set: (v) => (ui.profileOpen = v)
})
const mode = computed({
  get: () => ui.profileMode,
  set: (v) => (ui.profileMode = v)
})

const p = computed(() => profile.profile || {})
const isImageAvatar = computed(() => String(profile.avatar || '').startsWith('data:image'))
const ACTIVITY_LABELS = { light: '久坐少动', moderate: '每周 3 次', high: '经常运动' }
const activityText = computed(() => ACTIVITY_LABELS[p.value.activity_level] || '未设置')

const conditionList = computed(() => {
  const c = p.value.conditions || {}
  const list = Object.keys(c).filter((k) => c[k])
  return list.length ? list : ['无']
})

const allAllergies = computed(() => [...(p.value.allergies || []), ...(p.value.taboos || [])])

const form = reactive({
  name: '',
  avatar: '',
  sex: '女',
  age: 26,
  height_cm: 158,
  weight_kg: 58,
  activity_level: 'light',
  goals: [],
  allergies: [],
  cookware: []
})
const backup = ref(null)

function fillForm() {
  const pr = profile.profile || {}
  form.name = pr.extras?.name || '小膳'
  form.avatar = pr.extras?.avatar || '🍃'
  form.sex = pr.sex || '女'
  form.age = Number(pr.age) || 26
  form.height_cm = Number(pr.height_cm) || 158
  form.weight_kg = Number(pr.weight_kg) || 58
  form.activity_level = pr.activity_level || 'light'
  form.goals = [...(pr.extras?.goals || (pr.goal ? [pr.goal] : []))]
  form.allergies = [...(pr.allergies || []), ...(pr.taboos || [])]
  form.cookware = [...(pr.extras?.cookware || [])]
  return { ...form, goals: [...form.goals], allergies: [...form.allergies], cookware: [...form.cookware] }
}

function onOpen() {
  if (!profile.profile) profile.load()
  backup.value = fillForm()
}

function cancelEdit() {
  const b = backup.value
  if (b) Object.assign(form, { ...b, goals: [...b.goals], allergies: [...b.allergies], cookware: [...b.cookware] })
  mode.value = 'view'
}

async function save() {
  if (!form.goals.length) {
    ElMessage.warning('至少选一个饮食目标')
    return
  }
  const payload = {
    sex: form.sex,
    age: Number(form.age),
    height_cm: Number(form.height_cm),
    weight_kg: Number(form.weight_kg),
    activity_level: form.activity_level,
    goal: form.goals[0],
    allergies: form.allergies.filter((x) => x !== '无'),
    taboos: [],
    extras: {
      name: form.name.trim() || '小膳',
      avatar: form.avatar.trim() || '🍃',
      goals: [...form.goals],
      cookware: [...form.cookware]
    }
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
</script>

<style scoped>
.sk-wrap {
  padding: 8px 0;
}
</style>
