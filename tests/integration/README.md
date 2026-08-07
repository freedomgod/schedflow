# SchedFlow 集成测试

## 什么是集成测试？

集成测试用于验证SchedFlow不同组件之间的交互是否正常。与单元测试（测试单个组件）不同，集成测试关注：

1. **端到端工作流执行** - 完整工作流从创建到执行的全过程
2. **组件交互** - 调度器、执行器、作业存储之间的协同工作
3. **真实场景** - 模拟实际使用场景的复杂配置
4. **错误恢复** - 系统级错误处理和恢复机制
5. **性能特征** - 多任务并行执行、资源使用等

## 为什么需要集成测试？

1. **发现组件间的不兼容问题** - 单个组件测试通过，但组合使用时可能失败
2. **验证配置正确性** - 确保配置参数在不同组件间正确传递
3. **测试并发和并行执行** - 验证多线程/多进程环境下的正确性
4. **确保数据一致性** - 跨组件的状态管理和数据流正确性
5. **模拟真实负载** - 接近生产环境的使用模式

## 集成测试目录结构

```
tests/integration/
├── README.md                    # 本说明文档
├── __init__.py                  # 集成测试包初始化
├── test_e2e_workflows.py        # 端到端工作流测试
└── test_component_interaction.py # 组件交互测试
```

## 测试类别

### 1. 端到端工作流测试 (End-to-End)
- 测试完整的工作流生命周期：创建 → 配置 → 执行 → 结果收集
- 验证任务依赖关系、条件执行、重试机制等
- 示例：多层依赖的数据处理管道

### 2. 组件交互测试
- 测试调度器与执行器的协同
- 测试作业存储与调度器的数据同步
- 测试触发器与调度器的集成

### 3. (计划中) 更多测试类别
- 真实场景测试、错误恢复测试、性能测试等将在后续版本中添加

## 如何运行集成测试

### 基本运行
```bash
# 运行所有集成测试
pytest tests/integration/

# 运行特定测试文件
pytest tests/integration/test_e2e_workflows.py

# 运行带标记的测试
pytest tests/integration/ -m "not slow"
```

### 标记系统
集成测试可以使用以下标记：

- `@pytest.mark.integration` - 标记为集成测试
- `@pytest.mark.slow` - 运行缓慢的测试
- `@pytest.mark.external` - 需要外部服务的测试
- `@pytest.mark.e2e` - 端到端测试

### 跳过条件
某些集成测试可能需要特定条件：
- Redis服务可用性
- MongoDB服务可用性
- 足够的系统资源
- 网络连接

## 编写集成测试指南

### 1. 测试结构
```python
@pytest.mark.integration
class TestE2EWorkflow:
    """端到端工作流测试"""
    
    def test_complex_workflow_execution(self):
        """测试复杂工作流的完整执行"""
        # 1. 创建工作流
        workflow = create_complex_workflow()
        
        # 2. 配置执行器
        workflow.configure_executor("thread", max_workers=4)
        
        # 3. 执行工作流
        execution_log = workflow.execute()
        
        # 4. 验证结果
        assert execution_log.successful
        assert len(execution_log.completed_tasks) == expected_count
```

### 2. 使用夹具
```python
@pytest.fixture
def production_workflow():
    """生产级工作流夹具"""
    workflow = create_production_workflow()
    yield workflow
    workflow.cleanup()  # 测试后清理
```

### 3. 异步支持
```python
@pytest.mark.asyncio
async def test_async_workflow():
    """测试异步工作流执行"""
    workflow = create_async_workflow()
    result = await workflow.execute_async()
    assert result.status == "completed"
```

### 4. 错误测试
```python
def test_workflow_with_failures():
    """测试包含失败任务的工作流"""
    workflow = create_workflow_with_failures()
    execution_log = workflow.execute()
    
    # 验证错误处理
    assert execution_log.has_failures
    assert execution_log.failed_tasks_handled_correctly
```

## 最佳实践

1. **保持测试独立** - 每个测试应该独立运行，不依赖其他测试状态
2. **合理使用标记** - 使用适当的标记分类测试
3. **清理资源** - 测试后清理创建的文件、数据库连接等
4. **模拟外部依赖** - 当外部服务不可用时使用模拟
5. **添加详细断言** - 提供清晰的错误信息
6. **记录测试假设** - 在文档中说明测试的前提条件

## 与单元测试的区别

| 方面 | 单元测试 | 集成测试 |
|------|----------|----------|
| 范围 | 单个函数/类 | 多个组件/系统 |
| 速度 | 快速 | 较慢 |
| 依赖性 | 模拟外部依赖 | 使用真实依赖 |
| 目的 | 验证逻辑正确性 | 验证组件交互 |
| 运行频率 | 每次提交 | 每次构建/部署 |

## 贡献指南

1. 为新功能添加相应的集成测试
2. 确保测试覆盖关键的业务场景
3. 维护测试文档的更新
4. 遵循项目的代码风格和测试约定