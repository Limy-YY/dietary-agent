import http from './http.js'

export async function fetchProfile() {
  const data = await http.get('/profile')
  return data ? data.profile || null : null
}

export async function updateProfile(payload) {
  const data = await http.put('/profile', payload)
  return data ? data.profile || null : null
}
