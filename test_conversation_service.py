#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试对话服务
"""

import sys
import os
import tempfile

# 将项目根目录添加到Python路径中
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.append(project_root)

from Services.conversation_service import ConversationManager, ConversationState, ChatMessage


def test_conversation_service():
    """测试对话服务的基本功能"""
    print("🧪 测试对话服务...")
    
    # 使用临时目录进行测试
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建对话管理器
        conv_manager = ConversationManager(temp_dir)
        
        # 创建测试数据
        history = [
            ChatMessage(role="user", content="你好，请帮我创建一个文件"),
            ChatMessage(role="assistant", content="好的，我来帮你创建文件。我需要使用file_write工具。"),
        ]
        
        # 创建对话状态
        conversation_state = conv_manager.create_conversation_state(
            agent_name="TestAgent",
            agent_id="test_agent_123",
            system_prompt="你是一个文件操作助手",
            available_tools=["file_write", "file_read"],
            model_type="gpt-4o-mini",
            task_id="test_task",
            user_input="你好，请帮我创建一个文件",
            current_turn=1,
            history=history
        )
        
        print(f"📋 创建对话状态: Agent={conversation_state.agent_name}, 历史消息={len(conversation_state.history)}条")
        
        # 添加工具调用
        tool_call_id = conv_manager.add_tool_call_to_log(
            conversation_state, "file_write", {"filename": "test.txt", "content": "Hello World"}, 1
        )
        
        print(f"📝 添加工具调用: {tool_call_id}")
        print(f"📝 工具调用日志数量: {len(conversation_state.tool_calls_log)}")
        
        # 测试保存
        save_success = conv_manager.save_conversation(conversation_state)
        print(f"💾 保存对话: {'成功' if save_success else '失败'}")
        
        # 测试加载
        loaded_state = conv_manager.load_conversation("test_task", "你好，请帮我创建一个文件", "TestAgent")
        
        if loaded_state:
            print(f"📂 加载对话: 成功")
            print(f"📂 加载的历史消息数: {len(loaded_state.history)}")
            print(f"📂 加载的工具调用数: {len(loaded_state.tool_calls_log)}")
            print(f"📂 Agent名称: {loaded_state.agent_name}")
            print(f"📂 当前轮次: {loaded_state.current_turn}")
            
            # 测试工具调用状态管理
            pending_tools = conv_manager.get_pending_tool_calls(loaded_state)
            print(f"🔄 Pending工具调用数: {len(pending_tools)}")
            
            if pending_tools:
                # 更新工具状态
                conv_manager.update_tool_call_status(
                    loaded_state, 
                    pending_tools[0].id, 
                    "completed", 
                    {"status": "success", "output": "文件创建成功"}
                )
                print(f"✅ 更新工具状态为completed")
                
                # 检查final_output状态
                final_completed = conv_manager.check_final_output_completed(loaded_state)
                print(f"🎯 Final output完成状态: {final_completed}")
        else:
            print("❌ 加载对话失败")
        
        # 列出对话文件
        files = conv_manager.list_conversation_files()
        print(f"📁 对话文件列表: {files}")
        
        return conv_manager, conversation_state


def test_agent_integration():
    """测试Agent集成"""
    print("\n" + "="*60)
    print("🤖 测试Agent与对话服务的集成...")
    
    try:
        from baseService.agent_class import Agent
        
        # 创建测试Agent
        test_agent = Agent(
            agent_name="ConversationTestAgent",
            system_prompt="你是一个测试助手",
            available_tools=["final_output"],
            max_turns=3,
            model_type="gpt-4o-mini"
        )
        
        print(f"📋 Agent初始化完成")
        print(f"📋 对话管理器: {'✅ 可用' if test_agent.conversation_manager else '❌ 不可用'}")
        print(f"📋 上下文控制器: {'✅ 可用' if test_agent.context_controller else '❌ 不可用'}")
        
        # 测试对话文件列表功能
        if hasattr(test_agent, 'list_conversation_files'):
            files = test_agent.list_conversation_files()
            print(f"📁 现有对话文件数量: {len(files)}")
        
        return test_agent
        
    except Exception as e:
        print(f"❌ Agent集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """主测试函数"""
    print("🚀 开始测试对话服务")
    print("="*60)
    
    try:
        # 测试1: 对话服务基本功能
        conv_manager, conv_state = test_conversation_service()
        
        # 测试2: Agent集成
        test_agent = test_agent_integration()
        
        print("\n" + "="*60)
        print("✅ 对话服务测试完成！")
        print("🎯 对话服务工作正常，可以进行Agent集成")
        
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
