# journal_app/database.py - SQLite database layer

import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime
from config import DATABASE_PATH

logger = logging.getLogger(__name__)
DB_PATH = DATABASE_PATH


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_connection():
    """Context manager that commits on success, rolls back on error, always closes."""
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS journals (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                name_cn TEXT,
                publisher TEXT,
                type TEXT,
                code TEXT,
                list_url TEXT,
                enabled INTEGER DEFAULT 1,
                last_scraped TEXT,
                article_count INTEGER DEFAULT 0,
                latest_volume TEXT,
                latest_issue TEXT
            );
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                journal_id TEXT NOT NULL,
                title TEXT NOT NULL,
                title_cn TEXT,
                authors TEXT,
                abstract TEXT,
                abstract_cn TEXT,
                url TEXT UNIQUE NOT NULL,
                doi TEXT,
                pub_date TEXT,
                journal_ref TEXT,
                volume TEXT,
                issue TEXT,
                scraped_at TEXT,
                is_new INTEGER DEFAULT 1,
                FOREIGN KEY (journal_id) REFERENCES journals(id)
            );
            CREATE TABLE IF NOT EXISTS scrape_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                journal_id TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                status TEXT,
                articles_found INTEGER DEFAULT 0,
                articles_new INTEGER DEFAULT 0,
                error_message TEXT,
                FOREIGN KEY (journal_id) REFERENCES journals(id)
            );
            CREATE INDEX IF NOT EXISTS idx_articles_journal ON articles(journal_id);
            CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url);
            CREATE INDEX IF NOT EXISTS idx_articles_volume ON articles(journal_id, volume);
            CREATE INDEX IF NOT EXISTS idx_logs_journal ON scrape_logs(journal_id);
        """)

        # Migrations: add columns if missing (only catch column-already-exists error)
        migrations = [
            ("articles", "favorite", "INTEGER DEFAULT 0"),
            ("articles", "volume", "TEXT"),
            ("articles", "issue", "TEXT"),
            ("journals", "latest_volume", "TEXT"),
            ("journals", "latest_issue", "TEXT"),
            ("articles", "title_cn", "TEXT"),
            ("articles", "abstract_cn", "TEXT"),
        ]
        for col in migrations:
            try:
                conn.execute(f"ALTER TABLE {col[0]} ADD COLUMN {col[1]} {col[2]}")
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    logger.warning("Migration error %s.%s: %s", col[0], col[1], e)


def seed_journals(journals_config):
    with db_connection() as conn:
        for j in journals_config:
            conn.execute(
                """INSERT OR IGNORE INTO journals
                (id,name,name_cn,publisher,type,code,list_url,enabled)
                VALUES (?,?,?,?,?,?,?,?)""",
                (
                    j["id"], j["name"], j.get("name_cn", ""), j.get("publisher", ""),
                    j.get("type", ""), j.get("code", ""), j.get("list_url", ""),
                    1 if j.get("enabled", True) else 0,
                ),
            )
            conn.execute(
                "UPDATE journals SET type=?, publisher=?, name_cn=?, list_url=? WHERE id=?",
                (
                    j.get("type", ""), j.get("publisher", ""),
                    j.get("name_cn", ""), j.get("list_url", ""),
                    j["id"],
                ),
            )


def save_articles(journal_id, articles, volume=None, issue=None):
    """Save articles with URL-based dedup. Returns count of new articles."""
    with db_connection() as conn:
        # Reset is_new for all articles of this journal before this scrape
        conn.execute("UPDATE articles SET is_new=0 WHERE journal_id=?", (journal_id,))

        now = datetime.now().isoformat()
        new_count = 0
        for art in articles:
            try:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO articles
                    (journal_id,title,title_cn,authors,abstract,abstract_cn,url,doi,pub_date,journal_ref,volume,issue,scraped_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        journal_id,
                        art.get("title", ""),
                        art.get("title_cn", "") or None,
                        art.get("authors", ""),
                        art.get("abstract", ""),
                        art.get("abstract_cn", "") or None,
                        art.get("url", ""),
                        art.get("doi", ""),
                        art.get("pub_date", ""),
                        art.get("journal_ref", ""),
                        art.get("volume", str(volume) if volume else None),
                        art.get("issue", str(issue) if issue else None),
                        now,
                    ),
                )
                if cur.lastrowid:
                    new_count += 1
                else:
                    # Update existing article with new metadata
                    updates = []
                    params = []
                    if art.get("abstract") and len(art.get("abstract", "")) > 10:
                        updates.append("abstract=?")
                        params.append(art["abstract"])
                    if art.get("authors") and len(art.get("authors", "")) > 2:
                        updates.append("authors=?")
                        params.append(art["authors"])
                    if art.get("doi"):
                        updates.append("doi=?")
                        params.append(art["doi"])
                    if art.get("pub_date"):
                        updates.append("pub_date=?")
                        params.append(art["pub_date"])
                    if volume:
                        updates.append("volume=?")
                        params.append(str(volume))
                    if issue:
                        updates.append("issue=?")
                        params.append(str(issue))
                    if updates:
                        params.append(art.get("url", ""))
                        conn.execute(
                            f"UPDATE articles SET {','.join(updates)} WHERE url=?",
                            params,
                        )
            except Exception:
                logger.exception("Save article error: %s", art.get("url", "?"))

        # Update journal stats
        conn.execute(
            """UPDATE journals SET last_scraped=?,
            article_count=(SELECT COUNT(*) FROM articles WHERE journal_id=?),
            latest_volume=?, latest_issue=? WHERE id=?""",
            (
                now, journal_id,
                str(volume) if volume else None,
                str(issue) if issue else None,
                journal_id,
            ),
        )
        return new_count


def get_journal_stats():
    with db_connection() as conn:
        rows = conn.execute("""SELECT j.*,
            (SELECT COUNT(*) FROM articles WHERE journal_id=j.id) as total_articles,
            (SELECT COUNT(*) FROM articles WHERE journal_id=j.id AND is_new=1) as new_articles
            FROM journals j ORDER BY j.name""").fetchall()
        return [dict(r) for r in rows]


def get_journal_volumes(journal_id):
    with db_connection() as conn:
        rows = conn.execute("""SELECT DISTINCT volume FROM articles
            WHERE journal_id=? AND volume IS NOT NULL AND volume != ''
            ORDER BY CAST(volume AS INTEGER) DESC""", (journal_id,)).fetchall()
        return [r["volume"] for r in rows]


def get_articles(journal_id=None, limit=50, offset=0, volume=None, with_journal_name=False):
    with db_connection() as conn:
        conditions = []
        params = []

        if journal_id:
            conditions.append("a.journal_id=?")
            params.append(journal_id)
        if volume:
            conditions.append("a.volume=?")
            params.append(volume)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        join = "JOIN journals j ON a.journal_id=j.id" if with_journal_name else ""

        arts = conn.execute(f"""SELECT a.* {', j.name as journal_name' if with_journal_name else ''}
            FROM articles a {join}
            {where}
            ORDER BY COALESCE(a.pub_date, a.scraped_at) DESC
            LIMIT ? OFFSET ?""",
            params + [limit, offset]).fetchall()

        total = conn.execute(f"""SELECT COUNT(*) FROM articles a {where}""",
            params).fetchone()[0]

        return [dict(r) for r in arts], total


def get_articles_by_volume(journal_id):
    """Get articles grouped by volume then issue for a journal.

    Returns: {volume: {"issues": {issue: [articles]}}}
    Articles without an issue go under the "__none__" key.
    """
    with db_connection() as conn:
        arts = conn.execute("""SELECT * FROM articles WHERE journal_id=?
            ORDER BY COALESCE(pub_date, scraped_at) DESC""", (journal_id,)).fetchall()

    grouped = {}
    for art in arts:
        a = dict(art)
        v = a.get("volume") or "Unknown"
        iss = a.get("issue") or "__none__"

        if v not in grouped:
            grouped[v] = {"issues": {}}
        if iss not in grouped[v]["issues"]:
            grouped[v]["issues"][iss] = []
        grouped[v]["issues"][iss].append(a)

    # Sort issues within each volume (newest first)
    for v in grouped:
        grouped[v]["issues"] = dict(
            sorted(
                grouped[v]["issues"].items(),
                key=lambda x: int(x[0]) if x[0].isdigit() else 0,
                reverse=True,
            )
        )

    return grouped


def get_all_articles(limit=500, offset=0):
    with db_connection() as conn:
        arts = conn.execute("""SELECT a.*, j.name as journal_name FROM articles a
            JOIN journals j ON a.journal_id=j.id
            ORDER BY COALESCE(a.pub_date,a.scraped_at) DESC LIMIT ? OFFSET ?""",
            (limit, offset)).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        return [dict(r) for r in arts], total


def get_urls_having_abstract(journal_id):
    """Return set of article URLs that already have a non-empty abstract."""
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT url FROM articles WHERE journal_id=? AND abstract IS NOT NULL AND abstract != '' AND length(abstract) > 50",
            (journal_id,),
        ).fetchall()
        return {r["url"] for r in rows}


def mark_articles_read(journal_id):
    """Mark all articles of a journal as read (is_new=0)."""
    with db_connection() as conn:
        conn.execute("UPDATE articles SET is_new=0 WHERE journal_id=?", (journal_id,))
    logger.info("Marked all articles read for %s", journal_id)


def get_articles_needing_translation(journal_id, limit=50):
    with db_connection() as conn:
        arts = conn.execute("""SELECT * FROM articles WHERE journal_id=?
            AND (title_cn IS NULL OR title_cn='' OR abstract_cn IS NULL OR abstract_cn='')
            LIMIT ?""", (journal_id, limit)).fetchall()
        return [dict(r) for r in arts]


def update_translation(article_id, title_cn=None, abstract_cn=None):
    with db_connection() as conn:
        if title_cn:
            conn.execute("UPDATE articles SET title_cn=? WHERE id=?", (title_cn, article_id))
        if abstract_cn:
            conn.execute("UPDATE articles SET abstract_cn=? WHERE id=?", (abstract_cn, article_id))


def get_article_by_id(article_id):
    with db_connection() as conn:
        art = conn.execute("""SELECT a.*, j.name as journal_name FROM articles a
            JOIN journals j ON a.journal_id=j.id WHERE a.id=?""", (article_id,)).fetchone()
        return dict(art) if art else None


def delete_articles(article_ids):
    """Delete articles by ID list. Returns count of deleted rows."""
    if not article_ids:
        return 0
    with db_connection() as conn:
        placeholders = ",".join("?" * len(article_ids))
        cur = conn.execute(
            f"DELETE FROM articles WHERE id IN ({placeholders})",
            article_ids,
        )
        return cur.rowcount


def set_favorite(article_ids, fav):
    """Set favorite status (1 or 0) for given article IDs. Returns count."""
    if not article_ids:
        return 0
    with db_connection() as conn:
        placeholders = ",".join("?" * len(article_ids))
        cur = conn.execute(
            f"UPDATE articles SET favorite=? WHERE id IN ({placeholders})",
            [fav] + list(article_ids),
        )
        return cur.rowcount


def get_favorite_articles(limit=500, offset=0):
    """Get all favorited articles."""
    with db_connection() as conn:
        arts = conn.execute("""SELECT a.*, j.name as journal_name FROM articles a
            JOIN journals j ON a.journal_id=j.id
            WHERE a.favorite=1
            ORDER BY COALESCE(a.pub_date, a.scraped_at) DESC
            LIMIT ? OFFSET ?""", (limit, offset)).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE favorite=1"
        ).fetchone()[0]
        return [dict(r) for r in arts], total
