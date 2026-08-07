"""Tests for the shared API schemas (job schemas live in api.rest.schemas)."""


class TestAPIResponse:
    def test_api_response_success(self):
        from schedflow.api.schemas import APIResponse

        resp = APIResponse(code=0, data=[1, 2], message="ok")
        assert resp.code == 0
        assert resp.data == [1, 2]
        assert resp.message == "ok"

    def test_api_response_error(self):
        from schedflow.api.schemas import APIResponse

        resp = APIResponse(code=-1, message="boom")
        assert resp.code == -1
        assert resp.message == "boom"

    def test_api_response_default_message(self):
        from schedflow.api.schemas import APIResponse

        resp = APIResponse()
        assert resp.code == 0
        assert resp.message == "ok"
