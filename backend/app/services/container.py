"""集装箱档案业务规则：状态流转、字段校验、箱况视图汇总口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "container"
REQUIRED_FIELDS = ["箱号", "箱型", "箱况等级"]
STATUS_ORDER = ["待检", "可周转", "待修", "已报废"]
ACTION_RULES = {"登记检验": "可周转", "标记可周转": "待修", "报废箱体": "已报废"}
NEGATIVE_ACTIONS = []

# 箱况等级允许取的值；空字符串表示未填写。
GRADE_ORDER = ["一级", "二级", "三级"]
EMPTY_GRADE_LABEL = "未填写"

# 箱况等级与检验有效期的对应口径（以“今天”为基准看剩余有效天数）：
# 一级箱检验有效期充裕；二级箱临近到期；三级箱已到须安排复检的窗口。
GRADE_VALID_DAYS: dict[str, tuple[int, int | None]] = {
    "一级": (180, None),   # 剩余有效期不少于 180 天
    "二级": (30, 179),     # 剩余有效期 30~179 天
    "三级": (None, 29),    # 剩余有效期不足 30 天（含已到期）
}
GRADE_RULE_TEXT = (
    "一级箱剩余检验有效期不少于 180 天；二级箱为 30~179 天；三级箱不足 30 天（含已到期）。"
    "箱况等级为空、检验到期日缺失或无法识别、或剩余有效期落在等级区间之外的，均按对不上标出。"
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _grade_mismatch(grade: str, expiry: date | None, today: date) -> str | None:
    """返回箱况等级与检验到期日对不上的原因；对得上时返回 None。"""
    if not grade:
        return "箱况等级未填写"
    if grade not in GRADE_VALID_DAYS:
        return f"箱况等级「{grade}」不在一级/二级/三级口径内"
    if expiry is None:
        return "检验到期日缺失或无法识别，无法核对箱况等级"
    remaining = (expiry - today).days
    lower, upper = GRADE_VALID_DAYS[grade]
    if lower is not None and remaining < lower:
        return f"{grade}箱要求剩余有效期不少于 {lower} 天，实际剩余 {remaining} 天"
    if upper is not None and remaining > upper:
        return f"{grade}箱要求剩余有效期不超过 {upper} 天，实际剩余 {remaining} 天"
    return None


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

    def condition_snapshot(self, *, today: date | None = None) -> dict[str, Any]:
        """箱况视图：与清单同源，一次遍历同时产出矩阵、占比与异常箱号。

        口径：集装箱档案内全部在港箱体（含待修与待报废处置的已报废箱）。
        箱型×箱况等级矩阵与四种箱况占比都基于同一份 rows，保证与清单总数一致。
        """
        today = today or date.today()

        grade_columns: list[str] = []
        type_totals: dict[str, int] = {}
        matrix: dict[str, dict[str, int]] = {}
        status_counts = {status: 0 for status in STATUS_ORDER}
        other_status: dict[str, int] = {}
        abnormal_rows: list[dict[str, Any]] = []
        total = 0

        def column_for(grade: str) -> str:
            label = grade if grade in GRADE_ORDER else (EMPTY_GRADE_LABEL if not grade else grade)
            if label not in grade_columns:
                grade_columns.append(label)
            return label

        for row in store.rows(MODULE):
            total += 1
            box_type = _clean(row.get("箱型")) or "未知箱型"
            grade_raw = _clean(row.get("箱况等级"))
            expiry_text = _clean(row.get("检验到期日"))

            try:
                expiry = date.fromisoformat(expiry_text) if expiry_text else None
            except ValueError:
                expiry = None

            column = column_for(grade_raw)
            matrix.setdefault(box_type, {})
            matrix[box_type][column] = matrix[box_type].get(column, 0) + 1
            type_totals[box_type] = type_totals.get(box_type, 0) + 1

            status = _clean(row.get("status"))
            if status in status_counts:
                status_counts[status] += 1
            elif status:
                other_status[status] = other_status.get(status, 0) + 1

            reason = _grade_mismatch(grade_raw, expiry, today)
            if reason is not None:
                abnormal_rows.append({
                    "箱号": _clean(row.get("箱号")) or f"id:{row.get('id')}",
                    "箱型": box_type,
                    "箱况等级": grade_raw or EMPTY_GRADE_LABEL,
                    "检验到期日": expiry_text or "缺失",
                    "箱况": status or "未知",
                    "异常原因": reason,
                })

        # 列顺序：一级/二级/三级优先，未填写放最后，其余识别不出的等级按出现次序排在中间。
        ordered_columns = [grade for grade in GRADE_ORDER if grade in grade_columns]
        ordered_columns += [
            column for column in grade_columns
            if column not in GRADE_ORDER and column != EMPTY_GRADE_LABEL
        ]
        if EMPTY_GRADE_LABEL in grade_columns:
            ordered_columns.append(EMPTY_GRADE_LABEL)

        matrix_rows = [
            {
                "箱型": box_type,
                "cells": [matrix[box_type].get(column, 0) for column in ordered_columns],
                "合计": type_totals[box_type],
            }
            for box_type in sorted(type_totals)
        ]
        matrix_totals = [
            sum(matrix_rows[index]["cells"][column_idx] for index in range(len(matrix_rows)))
            for column_idx in range(len(ordered_columns))
        ]

        share_rows = [
            {
                "箱况": status,
                "数量": status_counts[status],
                "占比": round(status_counts[status] * 100 / total, 1) if total else 0.0,
            }
            for status in STATUS_ORDER
        ]
        other_rows = [
            {"箱况": status, "数量": count,
             "占比": round(count * 100 / total, 1) if total else 0.0}
            for status, count in sorted(other_status.items())
        ]

        abnormal_rows.sort(key=lambda item: item["箱号"])
        return {
            "口径": "集装箱档案内在港箱体（含已报废待处置），与箱况清单同源同总数",
            "统计日期": today.isoformat(),
            "在港箱数": total,
            "等级口径": GRADE_RULE_TEXT,
            "matrix": {
                "columns": ordered_columns,
                "rows": matrix_rows,
                "totals": matrix_totals,
            },
            "shares": share_rows + other_rows,
            "abnormal": abnormal_rows,
        }
