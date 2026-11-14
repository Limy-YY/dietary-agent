import http from './http.js'

/** GET /profile：data 直接是档案对象；1004 → null（尚未建档） */
export async function fetchProfile() {
  return (await http.get('/profile')) || null
}

/** PUT /profile：只提交 11 个可写字段，target_calories 由后端算 */
export async function updateProfile(payload) {
  return (await http.put('/profile', payload)) || null
}
