import sys
import os
import json
from typing import List, Dict, Any
import yaml

# 将项目根目录添加到Python路径中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from baseService.agent_class import Agent
from baseService.llm_client import ModelType

global agent_name
agent_name = "experment_material_data_agent"

def _get_available_tools(level:int) -> List[str]:
    """从 tools_level.yaml 文件中加载所有级别为 level 的工具。"""
    tools_level_path = os.path.join(project_root, 'baseService', 'tools_level.yaml')
    available_tools = []
    try:
        with open(tools_level_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            for tool_name, details in config.get("tools", {}).items():
                if details.get("level") == level:
                    available_tools.append(tool_name)
        return available_tools
    except FileNotFoundError:
        print(f"警告: 工具级别配置文件 'tools_level.yaml' 未找到。")
        return []
    except Exception as e:
        print(f"读取 'tools_level.yaml' 时出错: {e}")
        return []

'''修改'''
def create_agent(max_turns: int = 100,task_id:str = "default_agent_task") -> Agent:

    """
    创建一个 修改 Agent实例。
    
    Args:
        max_turns (int): 最大轮次
        
    Returns:
        Agent: 配置好的 修改 Agent实例
    """
    
    agent_responsibility="你的职责是根据一个实验计划，将其实现，运行并得到实验数据。"
    agent_workflow=f'''
    **你的流程:**
    重要：不要在根目录运行递归的文件展开！！！
    创建文件前应该使用dir_list工具检查创建文件的地址下有无其他同名文件，不要覆盖不是自己的文件！文件命名尽量独特，根据相关信息进行命名！！！不要创建已经存在的目录！
    0. 你这次任务的 taskid 是{task_id}，你每次调用工具时，都应该将 taskid 作为参数传递给工具。如果你调用的工具返回结果提供了 judge agent 的报告，你应该基于 judge 结果和当前产出，重新使用对应工具，并调整任务，直到其可以完成剩下任务。这个重试最多重试三次。
    1. 你将会得到之前的 agent或者用户给你提供的详细的实验计划的文件地址，你首先应该确保文件存在。否则进行最终输出并给出错误信息。你应该严格查看注意事项，并严格遵守。
    2. 第二部分分析实验计划中所有的数据集相关的信息，首先尝试使用get_data_set_from_github_agent工具找到相关数据集，然后根据数据集收集结果改动实验计划。如果无法找到，你应该舍弃部分实验计划。
    2. 你的总体流程应该是先调用 experment_plan_to_coding_task_agent 工具，将实验计划转化为一个一个的编码任务。
    3.然后分析编码任务，将编码任务按照coding_task_agent指定的要求传递给它，注意coding_task_agent只允许在code_run目录下工作。重要！：你提供的编码任务一定要考虑到最后整体实验的成功，
    如果下一个模块可能使用之前默写已经写好的编码代码的功能，你应该告诉coding_task_agent相关代码说明文档地址（注意不是提供代码地址而是说明文档），要求其测试是否可以完美配合各模块一起工作。特别是最后主实验的入口。每一步都应该要求当前的
    coding_task_agent测试所有功能的协同。
    4. 每次完成工作后你应该检查其代码的文件夹所在位置是否复合预期，不是的话，重新提示和运行任务。这里你必须注意所有注意事项，不要有危险操作。
    5. 重复上面过程直到任务完成。
    6. 最后运行实验，并得到实验数据,注意你还是应该将运行任务交给coding_task_agent而不是自己尝试运行。
    6. 当你认为完成所有任务前，你应该给 judge_agent你的实验结果的文件地址，你的任务是什么，你的完成结果是什么，请 judge进行判断。。
    7. 当你觉得可以最终输出，使用 final_output 工具输出你的结果，你必须详细说明每个文件对应什么实验，实验数据的表格中所有的列代表什么含义。
    ** 注意事项 **
    **你每次输出给coding_task_agent任务的内容中请包含experment_plan_to_coding_task_agent的输出的整体代码计划的地址，以便于其理解上下文，你需要明白每个 agent 都是独立的和你上下文环境不同！！**
    **你要强调experment_plan_to_coding_task_agent的输出的整体代码计划的地址是用于其理解上下文的并不是需要整体实现！！！！只需专注于自己的任务即可**
    0. 在 judge 结束后诚实的输出你的进度，成果，和所有有价值的产出的文件地址和文字产物。并附上 judge agent 的报告作为 output的一部分。并说明这是来自于judge agent 的报告。
    1. 创建文件前应该检查创建文件的地址下有无其他同名文件，不要覆盖不是自己的文件（除非初始目标任务脚本名称和存在的重合），作为任务计划任务，你应该都在 upload 目录下创建所有文件,注意每次创建自己的文件前检查是否存在别人的文件，不要覆盖，有些别人已经写过的可以复用的功能文件你可以复用。
    2. 在最终输出时，使用 final_output 工具输出你的结果。文件命名尽量独特，根据相关信息进行命名！！！不要创建已经存在的目录！
    6. 重要：不要在根目录运行递归的文件展开！！！！
    7. 重要：创建文件前应该使用dir_list工具检查创建文件的地址下有无其他同名文件，不要覆盖不是自己的文件！文件命名尽量独特，根据相关信息进行命名！！！不要创建已经存在的目录！
    8. 重要：你不是！你不是编程 ai，你只需要确保利用已有的工具完成并运行实验，得到结果即可，实验结果尽量使用 csv 文件保存。
    9. 重要：实验的预计规模请不要太大，但是可以设置更多的实验组，例如一个参数从超小规模到小规模。
    10.重要：在你输出时候一定要减少废话！提供完整的相关结果的表格，生成结果表格代码说明等等！！但是忽略 readme 等文件。
    

    '''


    agent_output_format='''
         **JSON对象**: 当你准备输出思考过程或做出最终裁决时，必须输出一个严格符合以下格式的JSON字符串,只返回 json 字符串，不要添加任何额外内容：
        ```
        {{
          "status": "thinking" | "success" | "error",
          "output": "你的思考过程(我的初始任务是什么，现在完成到哪一步了，接下去应该做什么）、计划或最终的裁决摘要，如果你的生成物包括文件，必须给出文件的相对地址和说明！！",
          "error_information": "仅在最终裁决为 'error' 时填写失败原因。"
        }}
        ```
        **Status说明**:
        - `thinking`: 表示你还未完成审查，`output` 字段应包含你的思考、分析和下一步计划。对话将继续。
        - `success`: 表示你已完成审查，并确认任务 **完全符合** 原始指令。`output` 字段必须详细说明原始任务是什么，相关产物（如文件）在哪里，它们的内容和作用是什么。对话将终止。
        - `error`: 未通过。`output` 字段必须解释失败的原因，哪些部分不符合要求，哪些产物可以保留，哪些应该被删除。`error_information` 字段应包含核心的错误信息。对话将终止。
    '''
    # Judge Agent专用的系统提示
    judge_system_prompt = f"""
    你是一个名为 "{agent_name}" 的AI自动化工具，你高效，善于一步步思考并行动但是思考没有废话。你的职责是{agent_responsibility}
    你和工具还有其他 agent 在相同的工作环境中，因此对方提供的相对路径你也可以使用。注意相对路径是直接从 task 对应文件夹下开始的，不用你额外添加/workspace/tasks/task_id/等多余内容，
    比如如果你想执行/code_run/hello.py，你直接写 /code_run/hello.py 即可，不用写/workspace/tasks/task_id/code_run/hello.py 等多余内容，执行工具的默认执行位置为/workspace/tasks/task_id/code_run/下但提供相对/workspace/tasks/task_id的相对路径。

    {agent_workflow}
    **严格的输出格式:**
    你的每一次输出都 **必须** 是：
    
    {agent_output_format}
    
    """
    
    # 「修改这里」下面是例子 原则上下面的工具列表控制在 5 个左右，不要超过十个，除了通用 agent 之外
    available_tools = ['judge_agent','final_output','file_read','file_write',
                       'dir_list','dir_create','experment_plan_to_coding_task_agent','coding_task_agent','execute_shell','get_data_set_from_github_agent' ]
    
    # 创建Judge Agent实例
    agent = Agent(
        agent_name=agent_name,
        system_prompt=judge_system_prompt,
        available_tools=available_tools,
        max_turns=max_turns,
        model_type=ModelType.CLAUDE_3_7_SONNET
    )
    
    return agent


def run(
    task_id: str,
    task_input: str,
    max_turns: int = 100
) -> Dict:
    print(f"⚖️  启动{agent_name}，审查任务: {task_id} ⚖️")
    # 创建Agent实例
    agent = create_agent(max_turns,task_id)
    # 将输入转换为字符串格式
    
    # 构建用户输入
    # 运行Judge Agent
    return agent.run(task_id, task_input)


if __name__ == '__main__':
    # --- 使用示例 ---
    # 模拟一个场景：一个Agent被要求创建一个文件，并声称它成功了。
    
    # 1. 原始指令
    mock_instruction = '''
    我想要研究当前主流大模型幻觉问题，我已经在工作空间的 code_run 文件夹下写好一个主流大模型调用的 python 文件，不过先请你专注于自己的职责，不要执行这个文件！
{
  "status": "success",
  "output": "我已完成\"研究主流大模型幻觉问题\"的任务，成功提出了一个具体的研究方向和实验方案。\n\n## 研究方向与实验方案概述\n\n我提出了一个名为\"MedHallCheck\"的创新框架，该框架结合了SelfCheckGPT的幻觉检测能力和自反思方法的幻觉缓解策略，旨在提升医学领域大语言模型问答的可靠性。该研究以零资源黑盒幻觉检测和自反思迭代改进为基础，创建了一个两阶段检测-缓解闭环系统。\n\n## 完成的工作\n\n1. **文献分析**：分析了11篇关于LLM幻觉问题的高质量研究论文，涵盖定义、检测、缓解和评估四个关键方面。\n\n2. **关键方法详细研究**：深入研究了两种最有前景的方法：\n   - SelfCheckGPT：零资源黑盒幻觉检测方法\n   - Self-Reflection：基于三轮反思循环的幻觉缓解策略\n\n3. **研究思路构建**：提出将两种方法优势互补，形成一个完整的检测-缓解框架。\n\n4. **实验方案设计**：设计了详细的实验方案，包括数据集选择、评估指标、基线方法和实现细节。\n\n## 主要产出文件\n\n1. **研究方案文件**：`research_idea_and_plan.json`\n   - 包含研究背景、创新思路、框架设计和详细实验计划\n   - 覆盖了从理论基础到具体实现的各个方面\n\n2. **论文分析文件**：\n   - `papers/summaries/llm_hallucination_summary.json`：幻觉定义与分类研究总结\n   - `summary_output/selfcheckgpt_analysis.json`：SelfCheckGPT方法详细分析\n   - `summary_output/self_reflection_hallucination_analysis.json`：自反思方法详细分析\n   - `summary_output/halueval_benchmark_summary.json`：幻觉评估基准分析\n\n## 研究价值与可行性评估\n\nJudge Agent的评估结果表明，该研究提案具有显著的创新性和可行性：\n\n\"这个研究提案具有明显的创新性，将两种现有方法的优势结合起来形成完整的检测-缓解闭环。实验设计合理，选择了适当的数据集和评估指标。方案切实可行，特别是通过'自适应激活机制'平衡计算效率和答案质量的设计非常实用。总体而言，这是一个有价值的研究方向，有望为医学领域的大语言模型应用提供更可靠的解决方案。\"\n\n## 框架核心创新点\n\n1. **自适应两阶段架构**：先检测后缓解，避免对所有内容应用计算密集型自反思流程\n2. **医学领域优化**：针对医学术语和知识特点优化提示词和评估指标\n3. **动态反思深度**：根据幻觉类型和严重程度动态决定反思循环深度\n4. **计算效率与准确性平衡**：预期在保持高质量输出的同时减少50%的计算成本\n\n## 实验实施计划摘要\n\n1. **数据集**：PubMedQA和MedQuAD，涵盖医学事实判断和复杂问答\n2. **测试模型**：gpt-4o-mini和claude-3-5-haiku\n3. **评估指标**：幻觉检测准确率、事实一致性、计算效率和人工评估\n4. **实现组件**：包含幻觉检测器、反思模块和集成框架\n\n此研究方案充分利用了提供的模型调用代码（code_run/llm_client.py），可以实际实施并产生有价值的结果。研究聚焦于医学领域这一高风险、高价值的应用场景，具有重要的实际意义。",
  "error_information": ""
}
'''

   

    # 3. 启动 Judge Agent 进行审查
    final_judgement = run(
        task_id="agent_test_2",
        task_input=mock_instruction,
        max_turns=100
    )

    print("\n" + "="*20 + " 最终审查结果 " + "="*20)
    print(json.dumps(final_judgement, indent=2, ensure_ascii=False))
    print("="*55) 