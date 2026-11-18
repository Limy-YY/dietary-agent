import assert from 'node:assert/strict'
import { normalizeMealCard } from '../src/utils/schema.js'
const slot = {meal_slot_id: 1, slot_date: '2026-11-18', meal_type: '午', target_macro: {kcal: 954.8}, candidates: [{candidate_id: 2, macro_estimate: {kcal: 841.8}, dishes: []}], selected_candidate_id: 2}
const card = normalizeMealCard({plan_type: '餐', goal_energy_kcal: 2387, slots: [slot]})
assert.match(card.subtitle, /954.8/)
assert.doesNotMatch(card.subtitle, /2387/)
assert.equal(card.slots[0].kcal, 841.8)
const missing = normalizeMealCard({plan_type: '日', goal_energy_kcal: 2387, slots: [slot, {...slot, meal_slot_id: 3, meal_type: '晚', target_macro: {kcal: 716.1}, candidates: []}]})
assert.equal(missing.slots[1].kcal, null)
assert.equal(missing.days[0].kcal, null)
assert.equal(missing.days[0].target_kcal, 1670.9)
console.log('V2.1 card target regression passed')
