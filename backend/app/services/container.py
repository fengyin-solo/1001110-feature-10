"""集装箱档案业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date, datetime

from typing import Any

from app.store import store

MODULE = "container"
REQUIRED_FIELDS = ["箱号", "箱型", "箱况等级"]
STATUS_ORDER = ["待检", "可周转", "待修", "已报废"]
ACTION_RULES = {"登记检验": "可周转", "标记可周转": "待修", "报废箱体": "已报废"}
NEGATIVE_ACTIONS = []


class ContainerService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("箱号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def condition_view(self) -> dict[str, Any]:
        """箱况视图：与箱况清单共用同一份在港档案数据，保证两边数字始终对得上。

        - 按箱型 × 箱况等级汇总箱量（空箱型/空等级归入「未填写」，仍计入合计）；
        - 给出待检、可周转、待修、已报废四种箱况的数量与占比；
        - 箱况等级为空，或检验到期日缺失、无法识别、已过期仍标记可周转的箱号
          单独列入 issues，供值班时核对。
        """
        rows = store.rows(MODULE)
        total = len(rows)

        grades: list[str] = []
        matrix: dict[str, dict[str, int]] = {}
        for row in rows:
            box_type = str(row.get("箱型") or "").strip() or "未填写"
            grade = str(row.get("箱况等级") or "").strip() or "未填写"
            if grade not in grades:
                grades.append(grade)
            type_row = matrix.setdefault(box_type, {})
            type_row[grade] = type_row.get(grade, 0) + 1

        # 已知等级按字序排，「未填写」固定在最后。
        grades.sort(key=lambda item: (item == "未填写", item))

        status_count = {status: 0 for status in STATUS_ORDER}
        for row in rows:
            status = str(row.get("status") or "").strip()
            if status in status_count:
                status_count[status] += 1
        status_share = [
            {
                "status": status,
                "count": count,
                "ratio": round(count * 100 / total, 1) if total else 0.0,
            }
            for status, count in status_count.items()
        ]

        today = date.today()
        issues: list[dict[str, str]] = []
        for row in rows:
            box_no = str(row.get("箱号") or "").strip() or f"档案 {row.get('id')}"
            reasons: list[str] = []
            if not str(row.get("箱况等级") or "").strip():
                reasons.append("箱况等级为空")

            raw_due = str(row.get("检验到期日") or "").strip()
            due_day = self._parse_due_date(raw_due)
            if not raw_due:
                reasons.append("检验到期日缺失，无法核对箱况等级")
            elif due_day is None:
                reasons.append(f"检验到期日「{raw_due}」格式无法识别")
            elif str(row.get("status") or "").strip() == "可周转" and due_day < today:
                reasons.append(f"检验到期日 {raw_due} 已过，仍标记为可周转")

            if reasons:
                issues.append({"箱号": box_no, "原因": "；".join(reasons)})

        matrix_rows = [
            {
                "箱型": box_type,
                "counts": {grade: matrix[box_type].get(grade, 0) for grade in grades},
                "subtotal": sum(matrix[box_type].values()),
            }
            for box_type in sorted(matrix)
        ]
        grade_totals = {
            grade: sum(row["counts"][grade] for row in matrix_rows) for grade in grades
        }
        return {
            "module": MODULE,
            "total": total,
            "grades": grades,
            "rows": matrix_rows,
            "grade_totals": grade_totals,
            "status_share": status_share,
            "issues": issues,
        }

    @staticmethod
    def _parse_due_date(raw: str) -> date | None:
        for parser in (
            lambda value: date.fromisoformat(value),
            lambda value: datetime.strptime(value, "%Y/%m/%d").date(),
        ):
            try:
                return parser(raw)
            except ValueError:
                continue
        return None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"集装箱 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于集装箱档案可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"集装箱已{action}"
