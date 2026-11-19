"""Read-only acceptance checks for the V2.1 40-dish home-basics migration."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.db import SessionLocal
from app.services.rule_engine import SqlDataSource
from app.services.rule_engine.meal_templates import CATALOG, profile


SOURCE_ID = "home-basics-v2.1-20261119"
EXPECTED_INGREDIENTS = {
    "CN-882": ("鸡腿", 180.0, "未核查", ()),
    "CN-338": ("豆浆", 15.5, "已确认含", ("大豆",)),
    "CN-453": ("白菜薹", 28.4, "未核查", ()),
    "CN-483": ("生菜", 14.6, "未核查", ()),
}


with SessionLocal() as db:
    counts = db.execute(text("""
        SELECT
          (SELECT count(*) FROM core.dish WHERE NOT is_deleted) AS dishes,
          (SELECT count(*) FROM core.dish WHERE source_id=:source AND NOT is_deleted) AS added_dishes,
          (SELECT count(*) FROM core.dish WHERE dish_id BETWEEN 'DISH-001' AND 'DISH-060' AND NOT is_deleted) AS originals,
          (SELECT count(*) FROM core.ingredient WHERE food_id = ANY(:food_ids) AND NOT is_deleted) AS added_ingredients,
          (SELECT count(*) FROM core.dish_ingredient WHERE generated_from='v21_home_basics_20261119') AS added_relations
    """), {"source": SOURCE_ID, "food_ids": list(EXPECTED_INGREDIENTS)}).mappings().one()
    assert counts["dishes"] == 110, counts
    assert counts["added_dishes"] == 40, counts
    assert counts["originals"] == 60, counts
    assert counts["added_ingredients"] == 4, counts
    assert counts["added_relations"] == 75, counts
    print("COUNTS", dict(counts), flush=True)

    rows = db.execute(text("""
        SELECT food_id,name,energy_kcal,allergen_status,allergens,source_url,data_quality
        FROM core.ingredient WHERE food_id = ANY(:food_ids) ORDER BY food_id
    """), {"food_ids": list(EXPECTED_INGREDIENTS)}).mappings().all()
    for row in rows:
        expected = EXPECTED_INGREDIENTS[row["food_id"]]
        assert row["name"] == expected[0], row
        assert float(row["energy_kcal"]) == expected[1], row
        assert row["allergen_status"] == expected[2], row
        assert tuple(row["allergens"] or ()) == expected[3], row
        assert row["source_url"].startswith("https://nlc.chinanutri.cn/fq/foodinfo/"), row
        assert row["data_quality"] == "official", row
        print("INGREDIENT", row["food_id"], row["name"], row["allergen_status"], row["source_url"])

    dishes = db.execute(text("""
        SELECT d.dish_id,d.name,d.category,d.default_oil_g,d.default_salt_g,
               d.nutrition_snapshot,d.avoid_snapshot,
               string_agg(i.name||'='||di.amount_g||'g','；' ORDER BY di.dish_ingredient_id) AS ingredients
        FROM core.dish d
        JOIN core.dish_ingredient di USING (dish_id)
        JOIN core.ingredient i USING (ingredient_id)
        WHERE d.source_id=:source AND NOT d.is_deleted
        GROUP BY d.dish_id ORDER BY d.dish_id
    """), {"source": SOURCE_ID}).mappings().all()
    assert [d["dish_id"] for d in dishes] == [f"DISH-{i:03}" for i in range(61, 101)]
    for d in dishes:
        assert d["nutrition_snapshot"], d
        assert d["avoid_snapshot"], d
        assert d["dish_id"] in CATALOG, d
        assert CATALOG[d["dish_id"]].name == d["name"], d
        print("DISH", d["dish_id"], d["name"], "|", d["ingredients"],
              "| kcal", d["nutrition_snapshot"].get("energy_kcal"),
              "allergens", d["avoid_snapshot"].get("strict_allergens"),
              "unverified", d["avoid_snapshot"].get("unverified_food_ids"))

    variants = db.execute(text("""
        SELECT d.dish_id,d.name,
               string_agg(i.name||'='||di.amount_g||'g','；' ORDER BY di.dish_ingredient_id) AS ingredients
        FROM core.dish d JOIN core.dish_ingredient di USING(dish_id)
        JOIN core.ingredient i USING(ingredient_id)
        WHERE d.source_id='home-variants-v2.1-20261119' AND NOT d.is_deleted
        GROUP BY d.dish_id ORDER BY d.dish_id
    """)).mappings().all()
    assert [d["dish_id"] for d in variants] == [f"DISH-{i:03}" for i in range(101,111)]
    assert db.execute(text("SELECT count(*) FROM core.dish_ingredient WHERE generated_from='v21_home_variants_20261119'")).scalar_one() == 31
    for d in variants:
        print("VARIANT", d["dish_id"], d["name"], "|", d["ingredients"])

    facts = SqlDataSource(db).get_dish_facts()
    assert len(facts) == 110
    pending = [(d.dish_id, d.name) for d in facts if not profile(d).reviewed]
    assert not pending, pending
    by_id = {d.dish_id: d for d in facts}
    assert by_id["DISH-068"].strict_allergens == ["大豆"]
    assert by_id["DISH-069"].strict_allergens == ["牛奶"]
    assert "CN-882" in by_id["DISH-080"].unverified_food_ids
    assert "CN-453" in by_id["DISH-086"].unverified_food_ids
    assert "CN-483" in by_id["DISH-087"].unverified_food_ids
    db.rollback()

print("PASS V2.1 home-basics catalogue, provenance, nutrition snapshots and allergen status checks")
