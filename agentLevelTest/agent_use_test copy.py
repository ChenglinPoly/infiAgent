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
agent_name = "get_data_set_from_github_agent"

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
    
    agent_responsibility="你的职责是从github 上找到相关数据集"
    agent_workflow=f'''
    **你的流程:**
    重要：不要在根目录运行递归的文件展开！！！！
    创建文件前应该使用dir_list工具检查创建文件的地址下有无其他同名文件，不要覆盖不是自己的文件！文件命名尽量独特，根据相关信息进行命名！！！不要创建已经存在的目录！
    0. 你这次任务的 taskid 是{task_id}，你每次调用工具时，都应该将 taskid 作为参数传递给工具。如果你调用的工具返回结果提供了 judge agent 的报告，你应该基于 judge 结果和当前产出，重新使用对应工具，并调整任务，直到其可以完成剩下任务。这个重试最多重试三次。
    1. 你会获得一个数据集的名称和描述，尝试去 github 上搜素，注意使用英文，如果找到请使用 git 下载到code_run 目录下。如果无法找到也请如实报告。
    2. 当你认为完成所有任务前，你应该给 judge_agent你的实果的文件地址（如有），你的任务是什么，你的完成结果是什么，请 judge进行判断。需要提示 judge agent 只需判断 pdf 文件存在即可，不要尝试重新编译。
    4. 当你觉得可以最终输出，使用 final_output 工具输出你的结果，你必须详细说明每个文件对应什么实验，实验数据的表格中所有的列代表什么含义。
    ** 注意事项 **
    **你每次输出给coding_task_agent任务的内容中请包含experment_plan_to_coding_task_agent的输出的整体代码计划的地址，以便于其理解上下文，你需要明白每个 agent 都是独立的和你上下文环境不同！！**
    **你要强调experment_plan_to_coding_task_agent的输出的整体代码计划的地址是用于其理解上下文的并不是需要整体实现！！！！只需专注于自己的任务即可**
    0. 在 judge 结束后诚实的输出你的进度，成果，和所有有价值的产出的文件地址和文字产物。并附上 judge agent 的报告作为 output的一部分。并说明这是来自于judge agent 的报告。
    1. 创建文件前应该检查创建文件的地址下有无其他同名文件，不要覆盖不是自己的文件（除非初始目标任务脚本名称和存在的重合），作为任务计划任务，你应该都在 upload 目录下创建所有文件,注意每次创建自己的文件前检查是否存在别人的文件，不要覆盖，有些别人已经写过的可以复用的功能文件你可以复用。
    2. 在最终输出时，使用 final_output 工具输出你的结果。文件命名尽量独特，根据相关信息进行命名！！！不要创建已经存在的目录！
    3. 重要：不要在根目录运行递归的文件展开！！！！
    4. 重要：创建文件前应该使用dir_list工具检查创建文件的地址下有无其他同名文件，不要覆盖不是自己的文件！文件命名尽量独特，根据相关信息进行命名！！！不要创建已经存在的目录！
    

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
    available_tools = ['judge_agent','final_output',
                       'dir_list','dir_create','file_read','file_write','github_search_repositories',
                      'github_get_repository_info']
    
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
{
  "status": "success",
  "output": "我已成功完成了开发基于cyber-physical Internet物流问题研究的具体论文方向和实验计划的任务。以下是我的工作成果和流程总结：\n\n## 工作流程\n\n1. **论文分析**：我分析了8篇关于cyber-physical Internet物流问题的高质量学术论文，涵盖了路由优化、碳排放管理、物流基础设施、供应链管理、实时数据处理等多个方面。\n\n2. **研究主题整理**：基于论文分析，我整理了5个潜在研究方向：\n   - 路由优化\n   - 碳感知物流\n   - 数字孪生集成\n   - CPI资产管理\n   - 实时决策\n\n3. **研究idea形成**：我提出了5个具体研究idea，并最终选择了\"Carbon-Aware Adaptive Routing Protocol with Real-Time Traffic Information for CPI Networks\"作为主要研究方向，该方向结合了两篇核心论文的优势。\n\n4. **实验计划设计**：我详细设计了实验方案，包括模拟环境、场景设计、评估指标、实现步骤和预期结果。\n\n## 主要成果\n\n1. **研究idea**：Carbon-Aware Adaptive Routing Protocol with Real-Time Traffic Information for CPI Networks\n   - 结合了碳排放优化和实时交通数据的路由协议\n   - 基于两层CPI网络架构设计\n   - 通过动态适应交通状况来进一步降低碳排放\n\n2. **实验计划**：详细规划了一个可在4核CPU和6GB内存环境下实施的模拟实验\n   - 设计了小型和大型两个测试场景\n   - 定义了明确的评估指标：碳排放总量、交付时间、路由计算时间等\n   - 规划了与3种baseline方法的对比\n\n3. **文件产出**：\n   - `ideas_development.md` - 包含论文分析和初步研究方向\n   - `research_idea_and_plan.json` - 包含详细研究idea和实验计划\n\n## Judge Agent评估意见\n\nJudge Agent对研究idea和实验计划进行了评估，认为：\n- 研究idea完全符合原始任务要求，明确聚焦于CPI物流问题\n- 研究问题定义清晰，源自对现有文献的分析\n- 提出的方法合理可行，基于现有研究进行了合理拓展\n- 实验计划详细完整，包含了模拟环境设置、评估指标和实现步骤\n- 研究具有实际意义，并坦诚指出了局限性\n\n总体而言，Judge Agent确认该研究idea和实验计划是合理可行的，符合原始任务要求，并为后续研究实施提供了良好基础。\n\n## 文件路径\n- 研究idea发展过程：`/ideas_development.md`\n- 最终研究计划：`/research_idea_and_plan.json`",
  "error_information": ""
}
'''

   

    # 3. 启动 Judge Agent 进行审查
    final_judgement = run(
        task_id="agent_test",
        task_input=mock_instruction,
        max_turns=100
    )

    print("\n" + "="*20 + " 最终审查结果 " + "="*20)
    print(json.dumps(final_judgement, indent=2, ensure_ascii=False))
    print("="*55) 