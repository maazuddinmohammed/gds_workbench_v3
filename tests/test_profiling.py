"""Tests for profiling (core/profiling.py): the queries it writes and how their numbers become profiles. Databricks
cannot be reached locally, so the queries are checked as text and the numbers as a result row would give them."""

import pytest
from psycopg.rows import dict_row

from core import blocks, profiling
from core.problems import Refused
from core.tenant_lock import take_lock

TABLE = {"object_schema": "sales", "object_name": "orders", "batch_attribute_name": "batch_id"}
COLUMNS = [{"attribute_name": "order_id", "attribute_data_type": "STRING"},
           {"attribute_name": "amount", "attribute_data_type": "DECIMAL(16,2)"},
           {"attribute_name": "tags", "attribute_data_type": "ARRAY<STRING>"}]


def test_one_aggregate_query_per_fifty_columns_measured_on_the_batches():
    many = [{"attribute_name": f"c{i}", "attribute_data_type": "INT"} for i in range(120)]
    queries = list(profiling.aggregate_queries("acme", TABLE, many, ["7", "8"]))
    assert [len(chunk) for chunk, _, _ in queries] == [50, 50, 20]
    chunk, sql, params = queries[0]
    assert sql.endswith("FROM `acme`.`sales`.`orders` WHERE `batch_id` IN (:b0, :b1)") and params == {"b0": "7", "b1": "8"}


def test_lengths_and_blanks_only_for_text_and_no_distinct_for_lists():
    [(chunk, sql, params)] = profiling.aggregate_queries("acme", TABLE | {"batch_attribute_name": None}, COLUMNS, [])
    assert "LENGTH(`order_id`)" in sql and "TRIM(`order_id`)" in sql and "LENGTH(`amount`)" not in sql
    assert "COUNT(DISTINCT `tags`)" not in sql and "COUNT(DISTINCT `amount`)" in sql
    assert params == {} and "WHERE" not in sql


def test_a_result_row_becomes_counts_and_percentages():
    row = {"row_count": 200, "c0_non_null": 200, "c0_distinct": 200, "c0_blank": 0, "c0_min_length": 8,
           "c0_max_length": 8, "c0_avg_length": 8.0, "c1_non_null": 150, "c1_distinct": 30, "c2_non_null": 0}
    records = profiling.profile_records(TABLE, COLUMNS, [(COLUMNS, row)], {"order_id": ["A-1", "A-2"]})
    order, amount, tags = records
    assert (order["null_count"], order["percent_distinct"], order["sample_values"]) == (0, 100.0, ["A-1", "A-2"])
    assert (amount["null_count"], amount["percent_null"], amount["percent_duplicates"]) == (50, 25.0, 80.0)
    assert (tags["distinct_count"], tags["percent_distinct"], tags["sample_values"]) == (None, None, [])


def test_a_batched_table_needs_batch_ids(demo_data):
    d = demo_data
    take_lock(d.conn, d.ben, d.acme)
    d.conn.execute("""INSERT INTO project.project_input_scope (project_id, object_id)
                      SELECT %s, object_id FROM core.object WHERE object_name = 'KNA1'""", (d.sales,))
    d.conn.execute("UPDATE core.object SET batch_attribute_name = 'batch_id' WHERE object_name = 'KNA1'")
    with pytest.raises(Refused) as info:
        profiling.start_run(d.conn, d.ben, d.sales, {})
    assert info.value.rule_id == "RUN-005" and "batch IDs" in info.value.message
    run_id = profiling.start_run(d.conn, d.ben, d.sales, {"batch_ids": ["1"]})
    cur = d.conn.cursor(row_factory=dict_row)
    cur.execute("SELECT project_workflow, run_request_document FROM application.run WHERE run_id = %s", (run_id,))
    assert cur.fetchone() == {"project_workflow": "profiling",
                              "run_request_document": {"environment_code": "dev", "batch_ids": ["1"]}}
    assert blocks.scope_tables(cur, d.sales)[0]["batch_attribute_name"] == "batch_id"
