import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { fetchProfile, updateProfile } from '@/api/profile.js'

export const useProfileStore = defineStore('profile', () => {
  const profile = ref(null)
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')

  const name = computed(() => profile.value?.name || '小膳')
  const avatar = computed(() => profile.value?.avatar || '🍃')
  const goalText = computed(() => profile.value?.goal_name || '')
  const targetKcal = computed(() => {
    const n = Number(profile.value?.target_calories)
    return Number.isFinite(n) ? n : null
  })
  const bmi = computed(() => {
    if (!profile.value?.height_cm || !profile.value?.weight_kg) return ''
    const h = Number(profile.value.height_cm) / 100
    return (Number(profile.value.weight_kg) / (h * h)).toFixed(1)
  })
  const hasProfile = computed(() => Boolean(profile.value))

  async function load() {
    if (loading.value) return profile.value
    loading.value = true
    error.value = ''
    try {
      profile.value = await fetchProfile()
      return profile.value
    } catch (e) {
      error.value = e.message || '档案加载失败'
      return profile.value
    } finally {
      loading.value = false
    }
  }

  async function save(payload) {
    saving.value = true
    try {
      const next = await updateProfile(payload)
      if (next) profile.value = next
      return next
    } finally {
      saving.value = false
    }
  }

  return { profile, loading, saving, error, name, avatar, goalText, targetKcal, bmi, hasProfile, load, save }
})
