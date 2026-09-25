from django.core.management import call_command


def test_openapi_schema_generates_without_errors(tmp_path):
    # drf-spectacular drops a view it cannot describe from the schema and only
    # logs it, so a missing endpoint would otherwise go unnoticed until deploy.
    call_command("spectacular", "--fail-on-warn", "--validate", "--file", tmp_path / "schema.yml")
