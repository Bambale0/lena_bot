"""The exported API schema must support deterministic client generation."""

from main import app


def test_openapi_operation_ids_are_unique() -> None:
    schema = app.openapi()
    operation_ids = [
        operation["operationId"]
        for path in schema["paths"].values()
        for method, operation in path.items()
        if method in {"get", "head", "post", "put", "patch", "delete"}
    ]
    assert len(operation_ids) == len(set(operation_ids))
    assert schema["paths"]["/health"]["get"]["operationId"] == "public_health_get"
    assert schema["paths"]["/health"]["head"]["operationId"] == "public_health_head"
    assert schema["paths"]["/api/v1/health"]["get"]["operationId"] == "miniapp_health_get"
    assert schema["paths"]["/api/v1/health"]["head"]["operationId"] == "miniapp_health_head"
