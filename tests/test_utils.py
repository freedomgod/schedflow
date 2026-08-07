"""
Test utility functions for schedflow
"""
import pytest
import inspect
from schedflow.utils import obj_to_ref, ref_to_obj


def simple_function():
    """A simple function for testing"""
    return "test"


def nested_function():
    """A function defined at module level"""
    def inner():
        return "inner"
    return inner


class _TestClassForRef:
    """Module-level class for obj_to_ref testing"""
    def method(self):
        return "method"

    @classmethod
    def class_method(cls):
        return "class_method"

    @staticmethod
    def static_method():
        return "static_method"


_test_obj = _TestClassForRef()


class TestObjToRef:
    """Test obj_to_ref function"""
    
    def test_simple_function(self):
        """Test converting a simple function to ref"""
        ref = obj_to_ref(simple_function)
        assert ref == "tests.test_utils:simple_function"
    
    def test_lambda_function(self):
        """Test converting lambda function"""
        lambda_func = lambda x: x * 2
        # Lambda 函数无法序列化，应抛出 ValueError
        with pytest.raises(ValueError, match="Cannot create a reference to a lambda"):
            obj_to_ref(lambda_func)
    
    def test_nested_function(self):
        """Test converting nested function (defined inside another function)"""
        def inner_func():
            return "inner"

        # 嵌套函数无法序列化，应抛出 ValueError
        with pytest.raises(ValueError, match="Cannot create a reference to a nested function"):
            obj_to_ref(inner_func)
    
    def test_method(self):
        """Test converting method"""
        ref = obj_to_ref(_test_obj.method)
        assert "method" in ref
    
    def test_class_method(self):
        """Test converting classmethod"""
        ref = obj_to_ref(_TestClassForRef.class_method)
        assert "class_method" in ref
    
    def test_static_method(self):
        """Test converting staticmethod"""
        ref = obj_to_ref(_TestClassForRef.static_method)
        assert "static_method" in ref


class TestRefToObj:
    """Test ref_to_obj function"""
    
    def test_valid_ref(self):
        """Test converting valid ref back to object"""
        ref = "tests.test_utils:simple_function"
        obj = ref_to_obj(ref)
        assert obj == simple_function
    
    def test_invalid_ref_format(self):
        """Test invalid ref format"""
        with pytest.raises(LookupError):
            ref_to_obj("invalid:format:extra")
    
    def test_nonexistent_module(self):
        """Test ref with non-existent module"""
        with pytest.raises(LookupError):
            ref_to_obj("nonexistent.module:function")
    
    def test_nonexistent_attribute(self):
        """Test ref with non-existent attribute"""
        with pytest.raises(LookupError):
            ref_to_obj("tests.test_utils:nonexistent_function")