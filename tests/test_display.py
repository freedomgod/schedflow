"""Tests for the EasyDisplay utility class."""

from schedflow.display import EasyDisplay


class TestEasyDisplay:
    def test_init_with_content(self):
        ed = EasyDisplay("Hello, World!")
        assert ed.content == "Hello, World!"

    def test_init_with_none(self):
        ed = EasyDisplay()
        assert ed.content is None

    def test_str_with_content(self):
        ed = EasyDisplay("Hello")
        assert str(ed) == "Hello"

    def test_str_with_none(self):
        ed = EasyDisplay()
        assert str(ed) == ""

    def test_str_with_empty_string(self):
        ed = EasyDisplay("")
        assert str(ed) == ""
