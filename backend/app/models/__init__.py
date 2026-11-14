"""ORM 模型导出。

导入本包即注册全部映射，供 `Base.metadata` 使用与后续 router 引用。
"""
from app.models.base import Base
from app.models.meal_plan import MealCandidate, MealCandidateDish, MealPlan, MealSlot
from app.models.profile import Profile

__all__ = [
    "Base",
    "Profile",
    "MealPlan",
    "MealSlot",
    "MealCandidate",
    "MealCandidateDish",
]
