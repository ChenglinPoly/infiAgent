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
agent_name = "get_idea_and_experiment_plan"
global hardware_info
hardware_info = "运行环境:4核心 cpu 和 6gb 内存。"
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
    
    agent_responsibility="你的职责是根据现有资料和用户最开始的想法，得到一个十分具体的论文方向，并且获取一个本机环境下实际可行的具体实验方案，并输出一个 json 文件。"
    agent_workflow=f'''
    **你的流程:**
    重要：不要在根目录运行递归的文件展开！！！！
    在最终输出时，使用 final_output 工具输出你的结果!!!
    创建文件或目录前应该使用dir_list工具检查创建文件的地址下有无其他同名文件，不要覆盖不是自己的文件！文件命名尽量独特，根据相关信息进行命名！！！不要创建已经存在的目录！
    idea+研究计划哲学：应该聚焦于一篇文章或者最多两三篇文章的方向上！研究问题针对一个点进行研究和改进！不是每一篇文章都对研究方案有用！目标单一，明确，可实现（要考虑 llm 模型的局限性）是第一要务！
    0. 你这次任务的 taskid 是{task_id}，你每次调用工具时，都应该将 taskid 作为参数传递给工具。如果你调用的工具返回结果提供了 judge agent 的报告，而且 judge 结果不好，你应该基于 judge 结果和当前产出，重新使用对应工具，并调整任务和说明改进意见，指导其可以完成剩下任务。这个重试最多重试三次。
    1. 对于每篇论文，你应该使用 summary_from_one_paper 工具对齐总结，然后基于总结后的内容思考以下问题：是否让自己有了新的 idea，是否比之前的已有 idea 更好（实现率高是你首要考虑的目标）。是否需要针对这篇文章提出一个更详细的问题来获取更详细的知识和完成你的 idea 与实验计划？在执行时，杨哥遵守注意事项
    2. 如果需要针对文章提供更详细的问题答案（如果你重点参考某文章，你应该使用 answer_from_one_paper 工具，并提供具体的问题，文章地址和你预期想要获得的答案形式。
    3. 重复以上过程，直到你获得满意的 idea 和具体实验计划（包括实验方案，实验数据，实验结果，实验分析，产生的图表等）。对于有数值对比的实验，你应该基于文章设计一个简单的 baseline 实验。
    4. 当你认为完成所有任务前，你应该调用 judge_agent 来判断你是否完成任务。你应该给 judge_agent你的 idea的文件地址（注意不是内容），不需要提供文章，只需要说明你的思路是基于什么文章的什么内容产生的。
    无论 judge agent是否通过你都应该进行最终输出，基于 agent 的意见诚实的输出你的进度，成果，和所有有价值的产出的文件地址（一定要说明其相对地址！）和文字产物。并附上 judge agent 的报告作为 output。并说明这是来自于judge agent 的报告。
    5. 创建文件前应该检查创建文件的地址下有无其他同名文件，不要覆盖不是自己的文件！文件命名尽量独特，根据相关信息进行命名。
    你的硬件环境是{hardware_info}。你不是编程 Agent!绝对不要自己尝试去编程！！你最后的要求只有得到idea和实验计划，不要自己尝试去编程！！！
    **注意事项**
    1.你在要求工具总结论文前，应该自己先确认文章位置是否存在文章，找到文章真实存放的位置！
    2. 重要：如果实验计划涉及外部资源。例如数据集，你应该详细说明对应数据集如何找到（依据论文），否则不应该写入到实验计划中！
    '''


    agent_output_format='''
    
         **JSON对象**: 当你准备输出思考过程或做出最终裁决时，必须输出一个严格符合以下格式的JSON字符串,只返回 json 字符串，不要添加任何额外内容：
        ```
        {{
          "status": "thinking" | "success" | "error",
          "output": "你的思考过程、计划或最终的裁决摘要，如果你的生成物包括文件，必须给出文件的相对地址和说明，不用重复文件中已经有的内容",
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
    比如如果你想执行/code_run/hello.py，你直接写 /code_run/hello.py 即可，不用写/workspace/tasks/task_id/code_run/hello.py 等多余内容。

    {agent_workflow}
    **严格的输出格式:**
    你的每一次输出都 **必须** 是：
    
    {agent_output_format}
    
    """
    
    # 获取可用工具 change_here 「改」
    available_tools = ["summary_from_one_paper","judge_agent","file_read","dir_list","answer_from_one_paper","file_write","final_output"]
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
  "output": "我已完成关于大型语言模型(LLM)幻觉问题的文献收集任务。\n\n## 收集成果\n\n我成功收集了11篇高质量、近期(2020-2023年)的研究论文，全面覆盖LLM幻觉问题的四个关键方面：\n\n### 1. 幻觉的定义、分类和形成机制 (3篇)\n- \"The troubling emergence of hallucination in large language models\"\n- \"Insights into Classifying and Mitigating LLMs' Hallucinations\"\n- \"A survey of hallucination in large foundation models\"\n\n### 2. 幻觉的检测方法 (3篇)\n- \"Selfcheckgpt: Zero-resource black-box hallucination detection for generative large language models\"\n- \"Hallucination detection: Robustly discerning reliable answers in large language models\"\n- \"Weakly supervised detection of hallucinations in llm activations\"\n\n### 3. 幻觉的缓解策略 (3篇)\n- \"Cognitive mirage: A review of hallucinations in large language models\"\n- \"Self-contradictory hallucinations of large language models: Evaluation, detection and mitigation\"\n- \"Towards mitigating LLM hallucination via self reflection\"\n\n### 4. 评估大模型幻觉的基准和方法 (2篇)\n- \"Halueval: A large-scale hallucination evaluation benchmark for large language models\"\n- \"Amber: An llm-free multi-dimensional benchmark for mllms hallucination evaluation\"\n\n## 文献资源位置\n\n所有PDF文件已成功下载到系统的/uploads目录，文件列表如下:\n\n1. \"The troubling emergence of hallucination in large language models-an extensive definition, quantification, and prescriptive remediations.pdf\"\n2. \"Insights into Classifying and Mitigating LLMs' Hallucinations.pdf\"\n3. \"A survey of hallucination in large foundation models.pdf\"\n4. \"Selfcheckgpt_ Zero-resource black-box hallucination detection for generative large language models.pdf\"\n5. \"Hallucination detection_ Robustly discerning reliable answers in large language models.pdf\"\n6. \"Weakly supervised detection of hallucinations in llm activations.pdf\"\n7. \"Cognitive mirage_ A review of hallucinations in large language models.pdf\"\n8. \"Self-contradictory hallucinations of large language models_ Evaluation, detection and mitigation.pdf\"\n9. \"Towards mitigating LLM hallucination via self reflection.pdf\"\n10. \"Halueval_ A large-scale hallucination evaluation benchmark for large language models.pdf\"\n11. \"Amber_ An llm-free multi-dimensional benchmark for mllms hallucination evaluation.pdf\"\n\n此外，文献的详细信息(包括作者、引用次数、概述和URL/DOI)已整理在文件:`upload/hallucination_papers/selected_papers.md`\n\n## 文献价值评估\n\n收集的文献具有以下价值:\n\n1. **综合性**: 覆盖了LLM幻觉问题的定义、检测、缓解和评估四个关键方面\n2. **时效性**: 全部为2020-2023年发表的最新研究\n3. **影响力**: 大部分论文引用量较高(从13次到868次不等)\n4. **权威性**: 包含来自ACM会议和EMNLP Findings等顶级会议的论文\n\n这些文献为研究当前主流大模型幻觉问题提供了全面的理论基础和技术参考，可以支持后续的深入分析和实验。\n\n## Judge Agent评估\n\n根据Judge Agent的分析，当前收集的文献满足了用户研究需求，但存在文件存储位置问题(文件存储在/uploads目录而非papers目录)。Judge Agent建议在保持现有分类结构的同时，将PDF文件从/uploads目录移动到papers目录，但由于技术限制未能完成此操作。\n\n尽管如此，所有文献都已成功下载，并且文献元数据已经组织良好，能够支持后续研究工作。用户可以通过PDF文件和元数据文件获取所需的全部信息。",
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