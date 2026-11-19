"""Read-only real catalogue audit. Run from repo root with backend environment configured."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.rule_engine.repository import SqlDataSource
from app.services.rule_engine.quality import dish_roles
from app.db import get_db


def main():
    session_generator = get_db()
    db = next(session_generator)
    try:
        dishes = SqlDataSource(db).get_dish_facts()
        print("DISH TOTAL", len(dishes))
        for d in dishes:
            print(d.dish_id, d.name, "roles=", "/".join(sorted(dish_roles(d))),
                  "servings=", d.servings, "kcal=", d.energy_kcal,
                  "oil=", d.default_oil_g, "salt=", d.default_salt_g,
                  "allergens=", d.strict_allergens)
        print("NON-SINGLE-SERVING", [d.dish_id for d in dishes if d.servings != 1])
        print("MISSING ENERGY", [d.dish_id for d in dishes if d.energy_kcal is None])
    finally:
        db.rollback()
        session_generator.close()


if __name__ == "__main__":
    main()
