"""PDAM device codes: 0 headquarters, 1 completed, 2 franchise."""
import re

DEFAULT_PDAM_SALES_QUERY = """
SELECT d.id AS source_id,
 COALESCE(NULLIF(c.location, ''), NULLIF(g.groupName, ''), NULLIF(c.name, ''), CONCAT('현장-', d.id)) AS project_name,
 COALESCE(g.groupName, '') AS contractor, COALESCE(c.name, '') AS partner,
 COALESCE(NULLIF(d.machineNumber, ''), d.lavelNo) AS elevator,
 d.startDate AS start_date, d.createdDate AS record_date, d.endDate AS end_date,
 CASE WHEN d.conduct = 1 THEN '종료' ELSE '진행' END AS status,
 CASE WHEN d.conduct = 2 THEN '가맹' WHEN d.conduct = 0 THEN '본사' ELSE '' END AS category,
 COALESCE(d.isDel, 0) AS is_deleted
FROM TB_DEVICE d
LEFT JOIN TB_CONSTRUCTION c ON c.id = d.constructionIdx
LEFT JOIN TB_GROUP g ON g.idx = c.groupIdx
""".strip()


def sales_query(configured):
    # Upgrade the shipped legacy query even when it remains in a deployed .env.
    # Arbitrary custom queries keep their explicitly configured aliases.
    if not configured:
        return DEFAULT_PDAM_SALES_QUERY
    legacy_category = re.search(
        r"CASE\s+WHEN\s+COALESCE\(c\.fcIdx,\s*0\)\s*<>\s*0\s+THEN\s+'가맹'\s+ELSE\s+'본사'\s+END\s+AS\s+category",
        configured, re.I,
    )
    if legacy_category:
        return DEFAULT_PDAM_SALES_QUERY
    return configured
