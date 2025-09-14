#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
详细测试上下文压缩功能，显示原内容和压缩后的内容对比
"""

import sys
import os

# 将项目根目录添加到Python路径中
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.append(project_root)

from baseService.agent_class import Agent, ChatMessage
from Services.context_length_control_service import ContextLengthController


def print_content_comparison(title, original_content, compressed_content, original_tokens, compressed_tokens):
    """打印内容对比"""
    print(f"\n{'='*80}")
    print(f"📋 {title}")
    print('='*80)
    
    print(f"📊 Token统计: {original_tokens} → {compressed_tokens} ({compressed_tokens/original_tokens*100:.1f}%)")
    print(f"📊 压缩率: {(1-compressed_tokens/original_tokens)*100:.1f}%")
    
    print(f"\n🔸 原始内容 ({len(original_content)} 字符):")
    print("-" * 40)
    print(original_content)
    
    print(f"\n🔹 压缩后内容 ({len(compressed_content)} 字符):")
    print("-" * 40)
    print(compressed_content)
    print("="*80)


def test_compression_examples():
    """测试不同类型的内容压缩"""
    
    # 创建Agent用于获取LLM客户端
    test_agent = Agent(
        agent_name="CompressionTestAgent",
        system_prompt="你是一个内容压缩测试助手。",
        available_tools=["final_output"],
        max_turns=3,
        max_history_turns=1,
        max_history_tokens=400,  # 较小的限制，确保触发压缩
        model_type="gpt-4o-mini"
    )
    
    if not test_agent.context_controller:
        print("❌ 上下文控制器未初始化")
        return
    
    controller = test_agent.context_controller
    
    print("🚀 开始详细压缩测试")
    
    # 测试例子1：技术文档
    print("\n" + "="*80)
    print("🧪 测试例子1：技术文档内容")
    print("="*80)
    
    tech_content = """
    这是一个关于微服务架构的详细技术文档。在现代软件开发中，微服务架构已经成为了构建大型、复杂应用程序的主流方法。
    
    微服务架构的核心思想是将一个大型的单体应用拆分成多个小的、独立的服务，每个服务负责特定的业务功能。这些服务通过轻量级的通信机制（通常是HTTP RESTful API）进行交互。
    
    主要优势包括：
    1. 技术栈的多样性：不同的服务可以使用不同的编程语言和技术栈
    2. 独立部署：每个服务可以独立部署和扩展
    3. 故障隔离：一个服务的故障不会影响整个系统
    4. 团队自治：不同的团队可以独立开发和维护不同的服务
    
    然而，微服务架构也带来了一些挑战：
    1. 分布式系统的复杂性：网络延迟、数据一致性、服务发现等问题
    2. 运维复杂度增加：需要管理更多的服务实例
    3. 数据管理：如何在服务之间共享和管理数据
    4. 测试复杂性：集成测试变得更加困难
    
    在实施微服务架构时，需要考虑以下关键技术：
    - 容器化技术（Docker、Kubernetes）
    - 服务网格（Service Mesh）
    - API网关
    - 配置管理
    - 监控和日志系统
    - 持续集成和持续部署（CI/CD）
    
    总的来说，微服务架构是一个强大的架构模式，但需要团队具备相应的技术能力和组织结构来支持。
    """ * 3  # 重复3次增加长度
    
    original_tokens = controller.estimate_tokens(tech_content, "gpt-4o-mini")
    print(f"📊 原始内容token数: {original_tokens}")
    
    if original_tokens > 100:  # 确保会触发压缩
        compressed_content = controller._summarize_message(tech_content, 100, "gpt-4o-mini", test_agent.client)
        compressed_tokens = controller.estimate_tokens(compressed_content, "gpt-4o-mini")
        
        print_content_comparison(
            "技术文档压缩测试", 
            tech_content, 
            compressed_content, 
            original_tokens, 
            compressed_tokens
        )
    else:
        print("⚠️ 内容太短，未触发压缩")
    
    # 测试例子2：对话记录
    print("\n" + "="*80)
    print("🧪 测试例子2：对话记录内容")
    print("="*80)
    
    conversation_content = """
    用户: 你好，我想了解一下人工智能的发展历史。
    助手: 很高兴为您介绍人工智能的发展历史。人工智能（AI）的发展可以追溯到20世纪50年代。
    
    用户: 能详细说说每个阶段吗？
    助手: 当然可以。人工智能的发展大致可以分为以下几个阶段：
    
    1. 起源阶段（1950s-1960s）：
    - 1950年，阿兰·图灵提出了著名的"图灵测试"
    - 1956年，达特茅斯会议正式提出"人工智能"这个概念
    - 早期的AI程序如Logic Theorist和General Problem Solver
    
    2. 第一次繁荣期（1960s-1970s）：
    - 专家系统的兴起
    - LISP编程语言的发展
    - 机器学习的早期探索
    
    3. 第一次AI寒冬（1970s-1980s）：
    - 计算能力限制
    - 资金削减
    - 过度乐观的预期没有实现
    
    4. 专家系统时代（1980s）：
    - 商业化的专家系统
    - 知识工程的发展
    - 日本的第五代计算机项目
    
    5. 第二次AI寒冬（1980s末-1990s初）：
    - 专家系统的局限性暴露
    - 硬件成本高昂
    
    6. 机器学习复兴（1990s-2000s）：
    - 统计学习方法的兴起
    - 支持向量机、随机森林等算法
    - 互联网提供了大量数据
    
    7. 深度学习革命（2010s至今）：
    - GPU计算能力的提升
    - 大数据的可用性
    - 深度神经网络的突破
    - AlphaGo、GPT等里程碑式成果
    
    用户: 现在AI发展到什么程度了？
    助手: 目前AI已经在很多领域取得了显著进展，包括自然语言处理、计算机视觉、语音识别、推荐系统等。特别是大语言模型如GPT系列的出现，标志着AI在理解和生成人类语言方面达到了新的高度。
    
    用户: 未来AI会如何发展？
    助手: 未来AI的发展方向可能包括：
    - 更强的通用人工智能（AGI）
    - 更好的可解释性和透明度
    - 更高效的学习算法
    - 与人类更自然的交互方式
    - 在更多垂直领域的应用
    - 更好的安全性和可控性
    
    当然，AI的发展也面临着伦理、安全、就业等方面的挑战，需要社会各界共同努力来应对。
    """ * 2  # 重复2次增加长度
    
    original_tokens = controller.estimate_tokens(conversation_content, "gpt-4o-mini")
    print(f"📊 原始内容token数: {original_tokens}")
    
    if original_tokens > 100:
        compressed_content = controller._summarize_message(conversation_content, 100, "gpt-4o-mini", test_agent.client)
        compressed_tokens = controller.estimate_tokens(compressed_content, "gpt-4o-mini")
        
        print_content_comparison(
            "对话记录压缩测试", 
            conversation_content, 
            compressed_content, 
            original_tokens, 
            compressed_tokens
        )
    else:
        print("⚠️ 内容太短，未触发压缩")
    
    # 测试例子3：代码文档
    print("\n" + "="*80)
    print("🧪 测试例子3：代码文档内容")
    print("="*80)
    
    code_content = """
    # Python 数据处理示例代码
    
    import pandas as pd
    import numpy as np
    from sklearn.model_selection import train_test_split
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, classification_report
    
    def load_and_preprocess_data(file_path):
        \"\"\"
        加载和预处理数据的函数
        
        参数:
        file_path (str): 数据文件路径
        
        返回:
        DataFrame: 预处理后的数据
        \"\"\"
        # 读取数据
        df = pd.read_csv(file_path)
        
        # 处理缺失值
        df = df.dropna()
        
        # 特征工程
        df['feature_1_squared'] = df['feature_1'] ** 2
        df['feature_interaction'] = df['feature_1'] * df['feature_2']
        
        # 标准化数值特征
        numeric_columns = df.select_dtypes(include=[np.number]).columns
        df[numeric_columns] = (df[numeric_columns] - df[numeric_columns].mean()) / df[numeric_columns].std()
        
        return df
    
    def train_model(X, y):
        \"\"\"
        训练机器学习模型
        
        参数:
        X (DataFrame): 特征数据
        y (Series): 目标变量
        
        返回:
        model: 训练好的模型
        \"\"\"
        # 分割训练集和测试集
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # 创建和训练模型
        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        
        # 评估模型
        y_pred = model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        
        print(f"模型准确率: {accuracy:.4f}")
        print("分类报告:")
        print(classification_report(y_test, y_pred))
        
        return model
    
    def main():
        \"\"\"主函数\"\"\"
        # 数据处理流程
        data_file = "dataset.csv"
        
        # 加载和预处理数据
        df = load_and_preprocess_data(data_file)
        
        # 准备特征和目标变量
        feature_columns = [col for col in df.columns if col != 'target']
        X = df[feature_columns]
        y = df['target']
        
        # 训练模型
        model = train_model(X, y)
        
        # 保存模型
        import joblib
        joblib.dump(model, 'trained_model.pkl')
        print("模型已保存")
    
    if __name__ == "__main__":
        main()
    
    # 这是一个完整的机器学习项目示例，包括：
    # 1. 数据加载和预处理
    # 2. 特征工程
    # 3. 模型训练
    # 4. 模型评估
    # 5. 模型保存
    
    # 使用说明：
    # 1. 确保安装了所需的Python包：pandas, numpy, scikit-learn
    # 2. 准备CSV格式的数据文件，包含特征列和目标列
    # 3. 运行脚本即可完成整个机器学习流程
    
    # 注意事项：
    # - 根据实际数据调整特征工程步骤
    # - 可以尝试不同的机器学习算法
    # - 需要根据问题类型选择合适的评估指标
    """ * 2  # 重复2次增加长度
    
    original_tokens = controller.estimate_tokens(code_content, "gpt-4o-mini")
    print(f"📊 原始内容token数: {original_tokens}")
    
    if original_tokens > 100:
        compressed_content = controller._summarize_message(code_content, 100, "gpt-4o-mini", test_agent.client)
        compressed_tokens = controller.estimate_tokens(compressed_content, "gpt-4o-mini")
        
        print_content_comparison(
            "代码文档压缩测试", 
            code_content, 
            compressed_content, 
            original_tokens, 
            compressed_tokens
        )
    else:
        print("⚠️ 内容太短，未触发压缩")


def test_agent_integration():
    """测试Agent集成的压缩功能"""
    print("\n" + "="*80)
    print("🧪 测试Agent集成压缩功能")
    print("="*80)
    
    # 创建Agent，使用很小的token限制
    test_agent = Agent(
        agent_name="IntegrationTestAgent",
        system_prompt="你是一个测试助手。",
        available_tools=["final_output"],
        max_turns=3,
        max_history_turns=2,
        max_history_tokens=200,  # 小限制，确保压缩
        model_type="gpt-4o-mini"
    )
    
    # 创建包含长消息的对话历史
    long_user_message = """
    我需要你帮我分析一下这个复杂的业务场景。我们公司是一家电商平台，最近遇到了一些技术和业务上的挑战。
    
    首先，我们的用户增长非常快，日活跃用户已经超过了100万，但是我们的系统架构还是早期的单体架构，开始出现性能瓶颈。
    
    其次，我们的数据量也在快速增长，每天产生的交易数据、用户行为数据、商品数据等等，总量已经达到了TB级别，传统的关系型数据库开始力不从心。
    
    另外，我们的业务复杂度也在增加，从最初的简单商品销售，现在已经扩展到了多商户平台、供应链管理、金融服务、物流配送等多个领域。
    
    我们的技术团队也在快速扩张，从最初的10几个人，现在已经有了200多人，跨多个城市办公，协作和管理变得越来越困难。
    
    现在我们面临的主要问题包括：
    1. 系统性能问题：响应时间变慢，高峰期经常出现超时
    2. 开发效率问题：新功能开发周期越来越长，部署风险越来越大
    3. 数据管理问题：数据孤岛严重，数据一致性难以保证
    4. 团队协作问题：不同团队之间的依赖关系复杂，经常出现阻塞
    5. 运维复杂度：系统监控、故障排查、容量规划等都变得非常复杂
    
    我们正在考虑进行技术架构升级，主要的方向包括微服务化、云原生、数据中台等。
    但是这个转型过程非常复杂，涉及到技术、组织、流程等多个方面的变化。
    
    请你帮我分析一下这个情况，并给出一些建议。
    """ * 2  # 重复增加长度
    
    history = [
        ChatMessage(role="user", content="你好，我需要你的帮助"),
        ChatMessage(role="assistant", content="你好！我很乐意帮助你。请告诉我你遇到了什么问题？"),
        ChatMessage(role="user", content=long_user_message),
    ]
    
    print(f"📊 原始历史消息数量: {len(history)}")
    
    # 计算原始内容
    if test_agent.context_controller:
        original_tokens = sum(test_agent.context_controller.estimate_tokens(msg.content, "gpt-4o-mini") for msg in history)
        print(f"📊 原始总token数: {original_tokens}")
        
        # 找到最长的消息
        longest_msg = max(history, key=lambda x: len(x.content))
        longest_tokens = test_agent.context_controller.estimate_tokens(longest_msg.content, "gpt-4o-mini")
        
        print(f"📊 最长消息token数: {longest_tokens}")
        print(f"📊 最长消息字符数: {len(longest_msg.content)}")
        
        # 测试截断功能
        truncated, modified = test_agent._truncate_history(
            history=history,
            initial_user_input="你好，我需要你的帮助",
            current_turn=0
        )
        
        print(f"\n✂️ 截断后消息数量: {len(truncated)}")
        print(f"✂️ 是否有消息被修改: {modified}")
        
        # 显示处理后的消息
        for i, msg in enumerate(truncated):
            msg_tokens = test_agent.context_controller.estimate_tokens(msg.content, "gpt-4o-mini")
            print(f"\n📝 消息 {i+1} [{msg.role}] ({msg_tokens} tokens):")
            print("-" * 40)
            if len(msg.content) > 200:
                print(msg.content[:200] + "...")
            else:
                print(msg.content)
        
        # 如果有压缩，显示对比
        if modified:
            compressed_msg = None
            original_long_content = longest_msg.content
            
            for msg in truncated:
                if msg.content.startswith("[🤖 AI总结消息"):
                    compressed_msg = msg
                    break
            
            if compressed_msg:
                compressed_tokens = test_agent.context_controller.estimate_tokens(compressed_msg.content, "gpt-4o-mini")
                print_content_comparison(
                    "Agent集成压缩测试",
                    original_long_content,
                    compressed_msg.content,
                    longest_tokens,
                    compressed_tokens
                )


def main():
    """主测试函数"""
    print("🚀 开始详细压缩内容对比测试")
    
    try:
        # 测试不同类型内容的压缩
        test_compression_examples()
        
        # 测试Agent集成
        test_agent_integration()
        
        print("\n" + "="*80)
        print("✅ 所有压缩测试完成！")
        print("🎯 可以看到原内容和压缩后内容的详细对比")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
