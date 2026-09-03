"""SQLite activity logging for Garena Bot Monitor."""

import os
import sqlite3

DB_FILE = os.path.join(os.path.dirname(__file__), "garena_monitor.db")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_FILE, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
                user_id     INTEGER NOT NULL,
                username    TEXT,
                first_name  TEXT,
                feature     TEXT NOT NULL,
                email       TEXT,
                token_hint  TEXT,
                result      TEXT NOT NULL DEFAULT 'pending',
                flagged     INTEGER NOT NULL DEFAULT 0
            )
        """)
        c.commit()


def log_entry(
    user_id: int,
    username: str | None,
    first_name: str | None,
    feature: str,
    email: str | None = None,
    access_token: str | None = None,
) -> int:
    hint = (access_token[:12] + "…") if (access_token and len(access_token) > 12) else access_token
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO activity_log(user_id,username,first_name,feature,email,token_hint) "
            "VALUES(?,?,?,?,?,?)",
            (user_id, username, first_name, feature, email, hint),
        )
        c.commit()
        return cur.lastrowid  # type: ignore[return-value]


def update_result(log_id: int, result: str) -> None:
    with _conn() as c:
        c.execute("UPDATE activity_log SET result=? WHERE id=?", (result, log_id))
        c.commit()


def toggle_flag(log_id: int) -> bool:
    with _conn() as c:
        row = c.execute("SELECT flagged FROM activity_log WHERE id=?", (log_id,)).fetchone()
        if not row:
            return False
        new_val = 0 if row["flagged"] else 1
        c.execute("UPDATE activity_log SET flagged=? WHERE id=?", (new_val, log_id))
        c.commit()
        return bool(new_val)


def get_activities(
    limit: int = 500,
    feature: str | None = None,
    result: str | None = None,
    search: str | None = None,
) -> list[dict]:
    conn = _conn()
    sql, p = "SELECT * FROM activity_log WHERE 1=1", []
    if feature:
        sql += " AND feature=?";  p.append(feature)
    if result:
        sql += " AND result=?";   p.append(result)
    if search:
        sql += " AND (email LIKE ? OR username LIKE ? OR CAST(user_id AS TEXT) LIKE ?)"
        p += [f"%{search}%"] * 3
    sql += " ORDER BY ts DESC LIMIT ?";  p.append(limit)
    rows = [dict(r) for r in conn.execute(sql, p).fetchall()]
    conn.close()
    return rows


def get_stats() -> dict:
    conn  = _conn()
    cur   = conn.cursor()
    def n(sql: str) -> int:
        return cur.execute(sql).fetchone()[0]

    total   = n("SELECT COUNT(*) FROM activity_log")
    success = n("SELECT COUNT(*) FROM activity_log WHERE result='success'")
    done    = success + n("SELECT COUNT(*) FROM activity_log WHERE result='failed'")

    stats: dict = {
        "total":         total,
        "unique_users":  n("SELECT COUNT(DISTINCT user_id) FROM activity_log"),
        "unique_emails": n("SELECT COUNT(DISTINCT email) FROM activity_log WHERE email IS NOT NULL"),
        "success":       success,
        "failed":        n("SELECT COUNT(*) FROM activity_log WHERE result='failed'"),
        "pending":       n("SELECT COUNT(*) FROM activity_log WHERE result='pending'"),
        "today":         n("SELECT COUNT(*) FROM activity_log WHERE date(ts)=date('now','localtime')"),
        "flagged":       n("SELECT COUNT(*) FROM activity_log WHERE flagged=1"),
        "success_rate":  round(success / done * 100) if done else 0,
    }

    rows = cur.execute(
        "SELECT feature, COUNT(*) cnt FROM activity_log GROUP BY feature"
    ).fetchall()
    stats["by_feature"] = {r[0]: r[1] for r in rows}

    rows = cur.execute("""
        SELECT date(ts,'localtime') d, COUNT(*) cnt
        FROM activity_log
        WHERE ts >= datetime('now','-7 days','localtime')
        GROUP BY d ORDER BY d
    """).fetchall()
    stats["last_7_days"] = [{"date": r[0], "count": r[1]} for r in rows]

    conn.close()
    return stats


def get_alerts() -> list[dict]:
    conn  = _conn()
    cur   = conn.cursor()
    alerts: list[dict] = []

    # Same token used by multiple users
    for r in cur.execute("""
        SELECT token_hint, COUNT(DISTINCT user_id) uc,
               GROUP_CONCAT(DISTINCT COALESCE('@'||username,'#'||user_id)) users
        FROM activity_log WHERE token_hint IS NOT NULL
        GROUP BY token_hint HAVING uc > 1
    """).fetchall():
        alerts.append({
            "level": "danger", "icon": "🔴",
            "msg": f"Token <code>{r[0]}</code> is being used by "
                   f"<b>{r[1]} different users</b>: {r[2]}",
        })

    # Email with many different tokens (>2)
    for r in cur.execute("""
        SELECT email, COUNT(DISTINCT token_hint) tc
        FROM activity_log
        WHERE email IS NOT NULL AND token_hint IS NOT NULL
        GROUP BY email HAVING tc > 2
    """).fetchall():
        alerts.append({
            "level": "warning", "icon": "🟡",
            "msg": f"Email <code>{r[0]}</code> used with "
                   f"<b>{r[1]} different tokens</b> — possible unauthorized access",
        })

    # Rapid activity: >15 ops in 30 min by same user
    for r in cur.execute("""
        SELECT user_id, COALESCE('@'||username, '#'||user_id), COUNT(*) cnt
        FROM activity_log
        WHERE ts > datetime('now','-30 minutes','localtime')
        GROUP BY user_id HAVING cnt > 15
    """).fetchall():
        alerts.append({
            "level": "warning", "icon": "🟡",
            "msg": f"User <b>{r[1]}</b> performed <b>{r[2]} operations</b> "
                   f"in the last 30 minutes",
        })

    # Multiple brute-force sessions in 1 hour
    for r in cur.execute("""
        SELECT user_id, COALESCE('@'||username, '#'||user_id), COUNT(*) cnt
        FROM activity_log
        WHERE feature='bf' AND ts > datetime('now','-1 hour','localtime')
        GROUP BY user_id HAVING cnt > 2
    """).fetchall():
        alerts.append({
            "level": "danger", "icon": "🔴",
            "msg": f"User <b>{r[1]}</b> started <b>{r[2]} brute-force sessions</b> "
                   f"in the last hour",
        })

    conn.close()
    return alerts
