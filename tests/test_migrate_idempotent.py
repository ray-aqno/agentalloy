"""AC-5: running migrate twice against existing stores preserves data and raises nothing."""

from __future__ import annotations

from pathlib import Path

from skillsmith.storage.ladybug import LadybugStore


def test_ladybug_migrate_twice(tmp_path: Path) -> None:
    path = str(tmp_path / "ladybug")
    with LadybugStore(path) as store:
        store.migrate()
        store.execute(
            """
            CREATE (:Skill {
                skill_id: 's1', canonical_name: 'keep me', category: 'design',
                skill_class: 'domain', domain_tags: [], deprecated: false,
                always_apply: false, phase_scope: [], category_scope: []
            })
            """
        )

    # Reopen and migrate again — data must survive.
    with LadybugStore(path) as store:
        store.migrate()
        rows = store.execute("MATCH (s:Skill {skill_id: 's1'}) RETURN s.canonical_name")
        assert rows == [["keep me"]]
