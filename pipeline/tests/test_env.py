import duckdb


def test_duckdb_version_is_pinned():
    assert duckdb.__version__ == "1.5.5"


def test_duckdb_runs_a_multi_statement_script():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE t(i INT); INSERT INTO t VALUES (1), (2);")
    assert con.execute("SELECT sum(i) FROM t").fetchall() == [(3,)]
