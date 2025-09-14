#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import time
from datetime import datetime

# API基础URL
BASE_URL = "http://localhost:5000"

def test_api():
    """测试所有API接口"""
    
    print("🧪 开始测试Agent API接口...")
    
    # 测试任务ID
    test_task_id = f"api_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # 1. 测试健康检查
    print("\n1. 🏥 测试健康检查...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")
    
    # 2. 测试创建任务
    print("\n2. 🚀 测试创建任务...")
    create_data = {
        "task_id": test_task_id,
        "instruction": "你能完成什么任务？请简要介绍。",
        "tool_name": "writing_agent"
    }
    response = requests.post(f"{BASE_URL}/api/task/create", json=create_data)
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")
    
    # 等待任务启动
    time.sleep(2)
    
    # 3. 测试获取任务状态
    print("\n3. 📊 测试获取任务状态...")
    response = requests.get(f"{BASE_URL}/api/task/status", params={"task_id": test_task_id})
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    
    # 4. 测试获取任务日志
    print("\n4. 📋 测试获取任务日志...")
    response = requests.get(f"{BASE_URL}/api/task/logs", params={"task_id": test_task_id, "lines": 20})
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        log_data = response.json()
        print(f"日志文件: {log_data['log_file']}")
        print(f"日志内容（最后20行）:\n{log_data['log_content']}")
    else:
        print(f"响应: {response.json()}")
    
    # 等待任务完成
    print("\n⏳ 等待任务完成...")
    max_wait = 60  # 最多等待60秒
    wait_count = 0
    
    while wait_count < max_wait:
        response = requests.get(f"{BASE_URL}/api/task/status", params={"task_id": test_task_id})
        if response.status_code == 200:
            status_data = response.json()
            if not status_data["is_running"]:
                print("✅ 任务已完成")
                break
        
        time.sleep(2)
        wait_count += 2
        print(f"⏳ 等待中... ({wait_count}s)")
    
    # 5. 测试添加新指令
    print("\n5. ➕ 测试添加新指令...")
    add_instruction_data = {
        "task_id": test_task_id,
        "instruction": "另外，请告诉我你最擅长的任务类型是什么？"
    }
    response = requests.post(f"{BASE_URL}/api/task/add_instruction", json=add_instruction_data)
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")
    
    # 等待新任务完成
    time.sleep(10)
    
    # 6. 测试获取对话历史
    print("\n6. 💬 测试获取对话历史...")
    response = requests.get(f"{BASE_URL}/api/task/conversation_history", params={"task_id": test_task_id})
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        conv_data = response.json()
        print(f"对话总数: {conv_data['total_messages']}")
        print("对话历史:")
        for i, msg in enumerate(conv_data['conversation']):
            msg_type = "👤 用户" if msg['type'] == 'user' else f"🤖 {msg.get('agent_name', 'Assistant')}"
            content_preview = msg['content'][:100] + "..." if len(msg['content']) > 100 else msg['content']
            print(f"  {i+1}. [{msg['timestamp']}] {msg_type}: {content_preview}")
    else:
        print(f"响应: {response.json()}")
    
    # 7. 测试获取LLM配置
    print("\n7. ⚙️ 测试获取LLM配置...")
    response = requests.get(f"{BASE_URL}/api/config/llm")
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        config_data = response.json()
        print(f"配置文件: {config_data['config_file']}")
        print("配置内容（部分）:")
        print(f"  默认温度: {config_data['config'].get('default', {}).get('temperature')}")
        print(f"  OpenAI模型: {config_data['config'].get('openai', {}).get('official', {}).get('models', [])[:3]}")
    else:
        print(f"响应: {response.json()}")
    
    # 8. 测试获取Agent配置
    print("\n8. 🔧 测试获取Agent配置...")
    response = requests.get(f"{BASE_URL}/api/config/agent/general_prompts")
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        config_data = response.json()
        print(f"配置类型: {config_data['config_type']}")
        print(f"配置文件: {config_data['config_file']}")
        print("配置内容（部分）:")
        general_prompts = config_data['config'].get('general_prompts', {})
        if 'agent_system_prompt' in general_prompts:
            prompt_preview = general_prompts['agent_system_prompt'][:100] + "..."
            print(f"  系统提示词: {prompt_preview}")
    else:
        print(f"响应: {response.json()}")
    
    # 9. 测试获取任务列表
    print("\n9. 📝 测试获取任务列表...")
    response = requests.get(f"{BASE_URL}/api/tasks/list")
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        tasks_data = response.json()
        print(f"任务总数: {tasks_data['total_count']}")
        print("任务列表:")
        for task in tasks_data['tasks'][:5]:  # 只显示前5个
            print(f"  - {task['task_id']}: 运行中={task['is_running']}, 历史={task['history_count']}个")
    else:
        print(f"响应: {response.json()}")
    
    print(f"\n✅ API测试完成！测试任务ID: {test_task_id}")

if __name__ == '__main__':
    print("请确保API服务器已启动 (python api_server.py)")
    input("按Enter键开始测试...")
    
    try:
        test_api()
    except requests.exceptions.ConnectionError:
        print("❌ 连接失败！请确保API服务器正在运行在 http://localhost:5000")
    except Exception as e:
        print(f"❌ 测试过程中出错: {str(e)}") 