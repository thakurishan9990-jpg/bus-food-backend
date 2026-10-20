from app.main import app

SPEC_ENDPOINTS = {
    "passenger": [
        ("get", "/routes"), ("get", "/routes/{code}/buses"), ("get", "/buses/{bus_number}"),
        ("get", "/buses/{bus_number}/stops"), ("get", "/stops/{stop_id}/dhabas"), ("get", "/dhabas/{dhaba_ref}/menu"),
        ("get", "/search"), ("get", "/ads"), ("post", "/ads/{campaign_id}/view"), ("post", "/ads/{campaign_id}/tap"),
        ("post", "/orders"),
    ],
    "kitchen": [("get", "/kitchen/orders"), ("patch", "/kitchen/orders/{order_id}")],
    "admin": [("get", "/admin/operations"), ("get", "/admin/business")],
}


def test_docs_group_every_spec_endpoint_by_role():
    paths = app.openapi()["paths"]

    for tag, endpoints in SPEC_ENDPOINTS.items():
        for method, path in endpoints:
            assert paths[path][method]["tags"] == [tag], (method, path)


def test_docs_offer_the_password_login_for_authorize():
    flow = app.openapi()["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"]["password"]
    assert flow["tokenUrl"] == "auth/login"
