from src.tools.sql_validator import SQLValidationError, SQLValidator


def test_rejects_destructive_keyword():
    validator = SQLValidator(
        allowed_dataset="bigquery-public-data.thelook_ecommerce",
        allowed_tables={"orders", "order_items", "products", "users"},
    )

    try:
        validator.validate_and_rewrite("DELETE FROM orders")
        assert False, "Expected SQLValidationError"
    except SQLValidationError as exc:
        assert "Blocked SQL operation" in str(exc)


def test_rejects_unapproved_table():
    validator = SQLValidator(
        allowed_dataset="bigquery-public-data.thelook_ecommerce",
        allowed_tables={"orders", "order_items", "products", "users"},
    )

    try:
        validator.validate_and_rewrite("SELECT * FROM payments")
        assert False, "Expected SQLValidationError"
    except SQLValidationError as exc:
        assert "approved allowlist" in str(exc)


def test_qualifies_table_and_appends_limit():
    validator = SQLValidator(
        allowed_dataset="bigquery-public-data.thelook_ecommerce",
        allowed_tables={"orders", "order_items", "products", "users"},
    )

    sql = validator.validate_and_rewrite("SELECT order_id FROM orders")
    assert "`bigquery-public-data.thelook_ecommerce.orders`" in sql
    assert sql.lower().endswith("limit 200")


def test_accepts_fully_qualified_table_reference():
    validator = SQLValidator(
        allowed_dataset="bigquery-public-data.thelook_ecommerce",
        allowed_tables={"orders", "order_items", "products", "users"},
    )

    sql = validator.validate_and_rewrite(
        "SELECT p.id FROM bigquery-public-data.thelook_ecommerce.products p"
    )
    assert "`bigquery-public-data.thelook_ecommerce.products`" in sql


def test_allows_cte_reference():
    validator = SQLValidator(
        allowed_dataset="bigquery-public-data.thelook_ecommerce",
        allowed_tables={"orders", "order_items", "products", "users"},
    )

    sql = validator.validate_and_rewrite(
        "WITH monthly AS (SELECT order_id FROM orders) SELECT * FROM monthly"
    )
    assert "FROM monthly" in sql
