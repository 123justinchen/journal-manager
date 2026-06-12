# journal_app/app.py - Flask Web Application

import sys
import os
import time
import threading
import logging
import functools
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, render_template, request, jsonify

sys.path.insert(0, os.path.dirname(__file__))

from config import (
    SECRET_KEY,
    DEBUG_MODE,
    BROWSER_ADDRESS,
)
from translator import translate as do_translate
from scrapers import get_all_scrapers, scrape_journal
from database import (
    init_db, seed_journals, save_articles, get_journal_stats,
    get_articles, get_articles_by_volume, get_all_articles,
    get_article_by_id, get_journal_volumes, get_articles_needing_translation,
    update_translation, get_db, get_urls_having_abstract, mark_articles_read,
    delete_articles, set_favorite, get_favorite_articles,
)

# ── Logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY

# Per-journal locks (allows parallel scraping of different journals)
_journal_locks = {}
_locks_lock = threading.Lock()
_scrape_status = {}
_status_lock = threading.Lock()

# Rate limiting for translate endpoint
_translate_timestamps = []
_translate_rate_lock = threading.Lock()
_TRANSLATE_MAX_PER_MINUTE = 20
_EXPORT_MAX_IDS = 500


def _get_journal_lock(journal_id):
    """Get or create a per-journal lock."""
    with _locks_lock:
        if journal_id not in _journal_locks:
            _journal_locks[journal_id] = threading.Lock()
        return _journal_locks[journal_id]


def _set_status(journal_id, status_dict):
    with _status_lock:
        _scrape_status[journal_id] = status_dict


def _get_status(journal_id=None):
    with _status_lock:
        if journal_id:
            return dict(_scrape_status.get(journal_id, {}))
        return dict(_scrape_status)


def _check_rate_limit():
    """Simple sliding-window rate limiter. Returns True if allowed."""
    now = time.time()
    window = 60  # 1 minute
    with _translate_rate_lock:
        # Purge old timestamps
        global _translate_timestamps
        _translate_timestamps = [t for t in _translate_timestamps if now - t < window]
        if len(_translate_timestamps) >= _TRANSLATE_MAX_PER_MINUTE:
            return False
        _translate_timestamps.append(now)
        return True


def csrf_protect(f):
    """CSRF check for API endpoints.

    Only accepts requests with Content-Type: application/json.
    Non-JSON POST requests are rejected.
    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            is_json = request.is_json
            site = request.headers.get("Sec-Fetch-Site", "")
            logger.debug("CSRF check: is_json=%s, content_type=%s, site=%s, data_len=%d",
                         is_json, request.content_type, site, len(request.get_data() or b""))
            if not is_json and site not in ("same-origin", "none"):
                logger.warning("CSRF blocked: non-JSON %s from %s (site=%s, ct=%s)",
                               request.method, request.remote_addr, site, request.content_type)
                return jsonify({"error": "CSRF validation failed — JSON required"}), 403
        return f(*args, **kwargs)
    return wrapper


def init():
    init_db()
    journal_configs = get_all_scrapers()
    seed_journals(journal_configs)


# ── Routes ─────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ═══════════════════════════════════════════════════════════════════
# API: Journals
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/journals")
def api_journals():
    journals = get_journal_stats()
    # Inject category from scraper config (not stored in DB)
    cat_map = {}
    for s in get_all_scrapers():
        cat_map[s["id"]] = s.get("category", "other")
    for j in journals:
        j["category"] = cat_map.get(j["id"], "other")
    return jsonify(journals)


@app.route("/api/journals/<journal_id>")
def api_journal_detail(journal_id):
    stats = get_journal_stats()
    journal = next((j for j in stats if j["id"] == journal_id), None)
    if not journal:
        return jsonify({"error": "期刊不存在"}), 404
    volumes = get_journal_volumes(journal_id)
    journal["volumes"] = volumes
    return jsonify(journal)


@app.route("/api/journals/<journal_id>/mark-read", methods=["POST"])
@csrf_protect
def api_journal_mark_read(journal_id):
    """Mark all articles of a journal as read."""
    mark_articles_read(journal_id)
    return jsonify({"success": True, "message": "已标记为已读"})


@app.route("/api/journals/<journal_id>/volumes")
def api_journal_volumes(journal_id):
    volumes = get_journal_volumes(journal_id)
    return jsonify({"volumes": volumes})


# ═══════════════════════════════════════════════════════════════════
# API: Scraping
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/scrape/<journal_id>", methods=["POST"])
@csrf_protect
def api_scrape_journal(journal_id):
    lock = _get_journal_lock(journal_id)
    if not lock.acquire(blocking=False):
        existing = _get_status(journal_id)
        return jsonify({"error": "该期刊正在爬取中", "status": existing}), 409

    try:
        journal_config = next((j for j in get_all_scrapers() if j["id"] == journal_id), None)
        if not journal_config:
            return jsonify({"error": "期刊不存在"}), 404

        _set_status(journal_id, {
            "status": "running",
            "step": "正在获取文章列表...",
            "journal": journal_config["name"],
            "started": datetime.now().isoformat(),
        })

        def _progress(info):
            if isinstance(info, dict):
                step = info.get("step", f"正在抓取...")
                count = info.get("count", 0)
                if count:
                    step = f"{step} ({count} 篇)"
            else:
                step = f"正在抓取文章 ({info} 篇)..."
            _set_status(journal_id, {
                "status": "running",
                "step": step,
                "journal": journal_config["name"],
            })

        skip_urls = get_urls_having_abstract(journal_id)
        articles, volume, issue = scrape_journal(journal_id, allow_browser=True, browser_address=BROWSER_ADDRESS, skip_urls=skip_urls, on_progress=_progress)

        _set_status(journal_id, {
            "status": "running",
            "step": "正在保存到数据库...",
            "found": len(articles),
        })
        new_count = save_articles(journal_id, articles, volume, issue)

        _set_status(journal_id, {
            "status": "completed",
            "step": "爬取完成",
            "articles_total": len(articles),
            "articles_new": new_count,
            "volume": str(volume) if volume else None,
            "issue": str(issue) if issue else None,
            "finished": datetime.now().isoformat(),
        })

        result = {
            "success": True,
            "total": len(articles),
            "new": new_count,
            "volume": str(volume) if volume else None,
            "issue": str(issue) if issue else None,
            "message": f"爬取完成: 共 {len(articles)} 篇, 新增 {new_count} 篇",
        }

        # Auto-translate in background thread (doesn't block the response)
        if articles:
            t = threading.Thread(
                target=auto_translate_articles,
                args=(journal_id,),
                daemon=True,
            )
            t.start()

        return jsonify(result)

    except Exception as e:
        _set_status(journal_id, {"status": "error", "step": str(e)[:100]})
        logger.exception("Scrape error for %s", journal_id)
        return jsonify({"error": str(e)}), 500
    finally:
        lock.release()


@app.route("/api/scrape-all", methods=["POST"])
@csrf_protect
def api_scrape_all():
    results = []
    to_translate = []

    for journal_config in get_all_scrapers():
        if not journal_config.get("enabled", True):
            continue
        jid = journal_config["id"]
        lock = _get_journal_lock(jid)
        if not lock.acquire(blocking=False):
            results.append({
                "id": jid, "name": journal_config["name"],
                "error": "该期刊正在爬取中", "success": False,
            })
            continue

        try:
            _set_status(jid, {
                "status": "running",
                "step": "正在抓取文章...",
                "journal": journal_config["name"],
                "started": datetime.now().isoformat(),
            })

            def _progress(info, jid=jid):
                if isinstance(info, dict):
                    step = info.get("step", "正在抓取...")
                    count = info.get("count", 0)
                    if count:
                        step = f"{step} ({count} 篇)"
                else:
                    step = f"正在抓取文章 ({info} 篇)..."
                _set_status(jid, {
                    "status": "running",
                    "step": step,
                })

            skip_set = get_urls_having_abstract(jid)
            articles, volume, issue = scrape_journal(jid, browser_address=BROWSER_ADDRESS, skip_urls=skip_set, on_progress=_progress)
            new_count = save_articles(jid, articles, volume, issue)
            if articles:
                to_translate.append(jid)
            results.append({
                "id": jid,
                "name": journal_config["name"],
                "total": len(articles),
                "new": new_count,
                "volume": str(volume) if volume else None,
                "issue": str(issue) if issue else None,
                "success": True,
            })
            _set_status(jid, {
                "status": "completed",
                "articles_total": len(articles),
                "articles_new": new_count,
            })
        except Exception as e:
            logger.exception("Scrape error for %s", jid)
            results.append({
                "id": jid, "name": journal_config["name"],
                "error": str(e), "success": False,
            })
            _set_status(jid, {"status": "error", "error": str(e)})
        finally:
            lock.release()

    # Auto-translate in background thread
    if to_translate:
        t = threading.Thread(
            target=_batch_translate,
            args=(to_translate,),
            daemon=True,
        )
        t.start()

    return jsonify({"results": results})


@app.route("/api/scrape-status")
def api_scrape_status():
    return jsonify(_get_status())


# ═══════════════════════════════════════════════════════════════════
# API: Articles
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/articles")
def api_articles():
    journal_id = request.args.get("journal_id")
    volume = request.args.get("volume")
    limit = min(int(request.args.get("limit", 500)), 1000)
    offset = int(request.args.get("offset", 0))

    if journal_id:
        articles, total = get_articles(
            journal_id=journal_id, volume=volume, limit=limit, offset=offset
        )
    else:
        articles, total = get_all_articles(limit=limit, offset=offset)

    return jsonify({"articles": articles, "total": total})


@app.route("/api/articles/by-volume")
def api_articles_by_volume():
    journal_id = request.args.get("journal_id")
    if not journal_id:
        return jsonify({"error": "journal_id is required"}), 400

    grouped = get_articles_by_volume(journal_id)
    # Sort volumes newest first
    sorted_grouped = {}
    for v in sorted(grouped.keys(), key=lambda x: int(x) if x.isdigit() else 0, reverse=True):
        sorted_grouped[v] = grouped[v]

    return jsonify({"volumes": sorted_grouped, "journal_id": journal_id})


@app.route("/api/articles/<int:article_id>")
def api_article_detail(article_id):
    art = get_article_by_id(article_id)
    if not art:
        return jsonify({"error": "文章不存在"}), 404
    return jsonify(art)


# ═══════════════════════════════════════════════════════════════════
# API: Export Markdown
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/articles/export-md", methods=["POST"])
@csrf_protect
def api_export_md():
    data = request.get_json()
    article_ids = data.get("ids", [])
    if not article_ids:
        return jsonify({"error": "请选择文章"}), 400
    if len(article_ids) > _EXPORT_MAX_IDS:
        return jsonify({"error": f"一次最多导出 {_EXPORT_MAX_IDS} 篇"}), 400

    conn = get_db()
    placeholders = ",".join("?" * len(article_ids))
    articles = conn.execute(
        f"""SELECT a.*, j.name as journal_name FROM articles a
            JOIN journals j ON a.journal_id = j.id
            WHERE a.id IN ({placeholders})
            ORDER BY COALESCE(a.pub_date, a.scraped_at) ASC""",
        article_ids,
    ).fetchall()
    conn.close()

    if not articles:
        return jsonify({"error": "未找到文章"}), 404

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []

    for i, art in enumerate(articles, 1):
        art = dict(art)
        title = art.get("title", "无标题")
        title_cn = art.get("title_cn", "")
        authors = art.get("authors", "")
        pub_date = art.get("pub_date", "") or (
            art.get("scraped_at", "")[:10] if art.get("scraped_at") else ""
        )
        url = art.get("url", "")
        abstract = art.get("abstract", "")
        abstract_cn = art.get("abstract_cn", "")
        doi = art.get("doi", "")
        volume = art.get("volume", "")
        issue = art.get("issue", "")

        lines.append(f"## {i}. {title}")
        lines.append("")
        if title_cn:
            lines.append(title_cn)
            lines.append("")
        if authors:
            lines.append(f"**Authors:** {authors}")
            lines.append("")
        if volume:
            vol_info = f"Vol.{volume}"
            if issue:
                vol_info += f", Issue {issue}"
            lines.append(f"**Volume/Issue:** {vol_info}")
        if doi:
            lines.append(f"**DOI:** {doi}")
        lines.append(f"**Published:** {pub_date}")
        if url:
            lines.append(f"**Link:** [{url}]({url})")
        lines.append("")
        if abstract:
            lines.append("### Abstract")
            lines.append("")
            lines.append(abstract)
            lines.append("")
        if abstract_cn:
            lines.append("### 摘要")
            lines.append("")
            lines.append(abstract_cn)
            lines.append("")
        lines.append("---")
        lines.append("")

    md_content = "\n".join(lines)
    return jsonify({"markdown": md_content, "count": len(articles), "generated_at": now})


# ═══════════════════════════════════════════════════════════════════
# API: Delete & Favorite
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/articles/delete", methods=["POST"])
@csrf_protect
def api_delete_articles():
    """Delete articles by IDs."""
    data = request.get_json()
    article_ids = data.get("ids", [])
    if not article_ids:
        return jsonify({"error": "请选择文章"}), 400
    if len(article_ids) > _EXPORT_MAX_IDS:
        return jsonify({"error": f"一次最多删除 {_EXPORT_MAX_IDS} 篇"}), 400
    count = delete_articles(article_ids)
    logger.info("Deleted %d articles", count)
    return jsonify({"success": True, "deleted": count, "message": f"已删除 {count} 篇文章"})


@app.route("/api/articles/favorite", methods=["POST"])
@csrf_protect
def api_favorite_articles():
    """Toggle favorite status for articles by IDs."""
    data = request.get_json()
    article_ids = data.get("ids", [])
    fav = 1 if data.get("favorite", True) else 0
    if not article_ids:
        return jsonify({"error": "请选择文章"}), 400
    count = set_favorite(article_ids, fav)
    action = "收藏" if fav else "取消收藏"
    return jsonify({"success": True, "count": count, "message": f"已{action} {count} 篇文章"})


@app.route("/api/articles/favorites")
def api_get_favorites():
    """Get all favorited articles."""
    limit = min(int(request.args.get("limit", 500)), 1000)
    offset = int(request.args.get("offset", 0))
    articles, total = get_favorite_articles(limit=limit, offset=offset)
    return jsonify({"articles": articles, "total": total})


# ═══════════════════════════════════════════════════════════════════
# API: Translation
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/translate", methods=["POST"])
@csrf_protect
def api_translate():
    """Translate title or abstract on demand."""
    if not _check_rate_limit():
        return jsonify({"error": "请求频率过高，请稍后重试", "success": False}), 429

    data = request.get_json()
    text = data.get("text", "").strip()
    trans_type = data.get("type", "title")
    article_id = data.get("article_id")

    if not text:
        return jsonify({"error": "文本为空"}), 400

    translation = do_translate(text, trans_type)
    if not translation:
        return jsonify({"error": "Translation failed", "success": False}), 500

    if article_id:
        if trans_type == "title":
            update_translation(article_id, title_cn=translation)
        else:
            update_translation(article_id, abstract_cn=translation)

    return jsonify({"translation": translation, "success": True})


# ═══════════════════════════════════════════════════════════════════
# Auto-translate (runs in background thread)
# ═══════════════════════════════════════════════════════════════════

def auto_translate_articles(journal_id, limit=500):
    """Auto-translate untranslated articles using parallel HTTP requests."""
    articles = get_articles_needing_translation(journal_id, limit)
    if not articles:
        return 0

    total = len(articles)
    logger.info("[翻译] %s: translating %d articles (parallel, workers=5)...", journal_id, total)
    _set_status(journal_id, {
        "status": "translating",
        "step": f"正在翻译 (0/{total})...",
        "translated": 0,
        "translation_total": total,
    })

    def _translate_one(art):
        """Translate one article's title + abstract. Returns True if anything was translated."""
        art = dict(art)
        did = False
        try:
            if not art.get("title_cn") and art.get("title") and len(art["title"]) > 5:
                title_cn = do_translate(art["title"], "title")
                if title_cn:
                    update_translation(art["id"], title_cn=title_cn)
                    did = True
        except Exception:
            logger.exception("Title translation error for article %d", art["id"])

        try:
            if not art.get("abstract_cn") and art.get("abstract") and len(art["abstract"]) > 30:
                abstract_cn = do_translate(art["abstract"], "abstract")
                if abstract_cn:
                    update_translation(art["id"], abstract_cn=abstract_cn)
                    did = True
        except Exception:
            logger.exception("Abstract translation error for article %d", art["id"])

        if did:
            logger.debug("  Translated article %d", art["id"])
        return did

    translated = 0
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(_translate_one, a) for a in articles]
        for f in as_completed(futures):
            if f.result():
                translated += 1
            _set_status(journal_id, {
                "status": "translating",
                "step": f"正在翻译 ({translated}/{total})...",
                "translated": translated,
                "translation_total": total,
            })

    _set_status(journal_id, {
        "status": "completed",
        "step": f"翻译完成 ({translated}/{total})",
        "translated": translated,
    })
    logger.info("[翻译] %s: %d translated", journal_id, translated)
    return translated


def _batch_translate(journal_ids):
    """Translate articles for multiple journals (used by scrape-all)."""
    for jid in journal_ids:
        auto_translate_articles(jid)


# ── Main ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    init()
    logger.info("Journal Manager starting at http://127.0.0.1:5050")
    app.run(host="127.0.0.1", port=5050, debug=DEBUG_MODE)
