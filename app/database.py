"""PostgreSQL storage for every job returned by the search provider."""

import hashlib
import json
import os

import psycopg
from psycopg.types.json import Jsonb
from psycopg.rows import dict_row

from app.config import init_config


class JobStorageError(RuntimeError):
    """Job persistence failed; do not return a successful search."""


def connect():
    # 加载 .env 后读取连接配置；限制连接等待时间，避免数据库不可用时请求长时间挂起。
    init_config()
    url = os.getenv("DATABASE_URL")
    if not url:
        raise JobStorageError("DATABASE_URL is required")
    return psycopg.connect(url, connect_timeout=5)


def init_database():
    # 启动时按需建表；连接上下文正常退出会提交事务，异常退出会回滚并关闭连接。
    # source 区分数据来源，source_key 标识来源中的岗位，两者共同约束唯一性。
    # raw_data 保留完整供应商数据；first_seen_at 记录首次入库，last_seen_at 记录最近收录。
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                source TEXT NOT NULL,
                source_key TEXT NOT NULL,
                title TEXT,
                company TEXT,
                apply_url TEXT,
                raw_data JSONB NOT NULL,
                first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (source, source_key)
            )
        """)


def job_key(job: dict) -> str:
    # 按优先级选取供应商标识；键中保留字段名，避免不同字段的相同值互相碰撞。
    for field in ("id", "guid", "slug", "applicationLink"):
        value = job.get(field)
        if value is not None and str(value).strip():
            return f"{field}:{value}"
    # 没有可用标识时，对完整数据取哈希，避免仅凭标题和公司误合并不同岗位。
    # 排序键使字段顺序不影响哈希；此兜底策略下，数据内容改变会产生新记录。
    payload = json.dumps(job, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def list_jobs(query: str = "", page: int = 1, page_size: int = 20) -> dict:
    # 转义 LIKE 的特殊字符，使用户输入的 %、_ 和反斜杠按字面匹配。
    # 外层 % 实现包含搜索；ILIKE 忽略大小写，COALESCE 将空字段视为空字符串。
    pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    where = "WHERE COALESCE(title, '') ILIKE %s OR COALESCE(company, '') ILIKE %s"
    try:
        with connect() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                # 总数和分页查询使用同一数据库快照，避免并发写入使两次查询结果不一致。
                # dict_row 将每行转为字典，便于 API 按字段名返回 JSON。
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                cursor.execute("SELECT COUNT(*) AS total FROM jobs " + where,
                               (pattern, pattern))
                total = cursor.fetchone()["total"]
                # 更新时间相同时按唯一 id 排序，保证同一快照内分页顺序稳定。
                # 页码从 1 开始；查询值、条数和偏移量都通过参数绑定传入 SQL。
                cursor.execute(
                    "SELECT id, title, company, apply_url, source, raw_data, last_seen_at "
                    "FROM jobs " + where +
                    " ORDER BY last_seen_at DESC, id DESC LIMIT %s OFFSET %s",
                    (pattern, pattern, page_size, (page - 1) * page_size),
                )
                return {"items": cursor.fetchall(), "total": total,
                        "page": page, "page_size": page_size}
    except Exception as exc:
        # 统一数据库异常类型，供 API 映射为 503；保留原始异常链用于定位问题。
        raise JobStorageError("Unable to read jobs") from exc


def save_jobs(jobs: list[dict]):
    # 空结果无需建立数据库连接。
    if not jobs:
        return
    try:
        with connect() as conn:
            with conn.cursor() as cursor:
                # 整批岗位在同一事务中保存：全部成功才提交，任意一条失败就回滚整批。
                # 唯一键冲突时更新岗位内容和最近收录时间，保留首次入库时间。
                # EXCLUDED 代表本次尝试插入的数据；Jsonb 将原始字典适配为 JSONB。
                cursor.executemany("""
                    INSERT INTO jobs
                        (source, source_key, title, company, apply_url, raw_data)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source, source_key) DO UPDATE SET
                        title = EXCLUDED.title,
                        company = EXCLUDED.company,
                        apply_url = EXCLUDED.apply_url,
                        raw_data = EXCLUDED.raw_data,
                        last_seen_at = CURRENT_TIMESTAMP
                """, [
                    ("himalayas", job_key(job), job.get("title"),
                     job.get("companyName"), job.get("applicationLink"), Jsonb(job))
                    for job in jobs
                ])
    except Exception as exc:
        # 将存储失败传递给 Agent/API，避免返回成功却没有保存岗位的结果。
        raise JobStorageError("Unable to save jobs") from exc
