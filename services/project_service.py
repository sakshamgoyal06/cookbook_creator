from datetime import datetime, timezone
from models.database import get_connection


def create_project(user_id, title, **kwargs):
    conn = get_connection()
    conn.execute(
        """INSERT INTO projects
           (user_id, title, subtitle, description, theme, max_recipes, max_pages,
            acknowledgement, about_author, dedication, introduction, cover_note)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            title,
            kwargs.get("subtitle", ""),
            kwargs.get("description", ""),
            kwargs.get("theme", "classic"),
            kwargs.get("max_recipes", 50),
            kwargs.get("max_pages", 100),
            kwargs.get("acknowledgement", ""),
            kwargs.get("about_author", ""),
            kwargs.get("dedication", ""),
            kwargs.get("introduction", ""),
            kwargs.get("cover_note", ""),
        ),
    )
    conn.commit()
    project_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return project_id


def get_project(project_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_projects(user_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM projects WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_project(project_id, data):
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE projects SET
           title = ?, subtitle = ?, description = ?, theme = ?,
           max_recipes = ?, max_pages = ?,
           acknowledgement = ?, about_author = ?, dedication = ?,
           introduction = ?, cover_note = ?, status = ?, updated_at = ?
           WHERE id = ?""",
        (
            data.get("title", ""),
            data.get("subtitle", ""),
            data.get("description", ""),
            data.get("theme", "classic"),
            data.get("max_recipes", 50),
            data.get("max_pages", 100),
            data.get("acknowledgement", ""),
            data.get("about_author", ""),
            data.get("dedication", ""),
            data.get("introduction", ""),
            data.get("cover_note", ""),
            data.get("status", "draft"),
            now,
            project_id,
        ),
    )
    conn.commit()
    conn.close()


def delete_project(project_id):
    conn = get_connection()
    conn.execute("DELETE FROM recipes WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()


def get_project_recipe_count(project_id):
    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM recipes WHERE project_id = ?", (project_id,)
    ).fetchone()[0]
    conn.close()
    return count
