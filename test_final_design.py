#!/usr/bin/env python3
"""
最终简化版处理器协作测试 - 只使用context方式
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from json2graph.interfaces import IProcessor, EntityType, ProcessorResult


class FinalTestProcessor1(IProcessor):
    """最终测试处理器1：使用context传递数据"""
    
    def get_name(self) -> str:
        return "final_processor_1"
    
    def get_supported_entity_types(self) -> list:
        return [EntityType.BASE_ENTITY]
    
    def process(self, entity_type, data, context=None):
        # 使用context传递数据
        ctx = context or {}
        
        # 添加图操作
        result = ProcessorResult()
        result.add_property("processor_1_processed", True)
        
        # 通过context传递数据给后续处理器
        new_context = {
            "entity_name": data.get("名称", "unknown"),
            "entity_type": data.get("类型", "unknown"),
            "step1_completed": True,
            "sequence": ctx.get("sequence", 0) + 1
        }
        
        result.processor_context = new_context
        
        print(f"处理器1: 处理了 {data.get('名称', '未知实体')}，序列号: {new_context['sequence']}")
        return result
    
    def validate_config(self, config):
        return True


class FinalTestProcessor2(IProcessor):
    """最终测试处理器2：使用context中的数据"""
    
    def get_name(self) -> str:
        return "final_processor_2"
    
    def get_supported_entity_types(self) -> list:
        return [EntityType.BASE_ENTITY]
    
    def process(self, entity_type, data, context=None):
        ctx = context or {}
        
        result = ProcessorResult()
        
        if ctx.get("step1_completed"):
            # 使用前面处理器的数据
            entity_name = ctx.get("entity_name", "unknown")
            sequence = ctx.get("sequence", 0)
            
            result.add_property("processor_2_used_context", True)
            result.add_property("combined_info", f"{entity_name}_step{sequence}")
            
            # 继续传递上下文
            new_context = {
                "step2_completed": True,
                "final_combined": f"{entity_name}_{sequence}"
            }
            result.processor_context = new_context
            
            print(f"处理器2: 使用了context数据 - {entity_name} (步骤{sequence})")
        else:
            print("处理器2: 没有收到context数据")
            result.add_property("processor_2_no_context", True)
        
        return result
    
    def validate_config(self, config):
        return True


def test_final_design():
    """测试最终简化设计"""
    print("=== 测试最终简化设计（仅context方式） ===")
    
    # 创建测试数据
    test_data = {
        "唯一ID": "TEST-001",
        "类型": "测试类型",
        "名称": "测试实体"
    }
    
    # 模拟处理器链式执行
    processors = [FinalTestProcessor1(), FinalTestProcessor2()]
    
    context = {}
    all_operations = []
    
    print("开始处理器链式执行...")
    
    for i, processor in enumerate(processors, 1):
        print(f"\n执行处理器{i}: {processor.get_name()}")
        
        result = processor.process(EntityType.BASE_ENTITY, test_data, context)
        
        # 收集图操作
        if result.graph_operations:
            all_operations.extend(result.graph_operations)
        
        # 更新上下文
        if result.processor_context:
            context.update(result.processor_context)
            print(f"  更新context: {result.processor_context}")
        
        print(f"  当前context: {context}")
    
    print(f"\n执行完成!")
    print(f"总图操作数量: {len(all_operations)}")
    print(f"最终context: {context}")
    
    # 验证结果
    expected_context_keys = ["entity_name", "entity_type", "step1_completed", "sequence", "step2_completed", "final_combined"]
    
    missing_keys = [key for key in expected_context_keys if key not in context]
    
    if not missing_keys:
        print("[SUCCESS] 所有预期的context键都存在")
        print(f"最终组合结果: {context.get('final_combined')}")
    else:
        print(f"[FAIL] 缺少context键: {missing_keys}")
    
    # 显示图操作
    if all_operations:
        print("\n图操作列表:")
        for i, op in enumerate(all_operations, 1):
            print(f"  {i}. {op.operation_type.value}: {op.params}")


if __name__ == "__main__":
    test_final_design()