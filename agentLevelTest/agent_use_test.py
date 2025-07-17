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
agent_name = "code_agent"
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
    
    agent_responsibility="你的职责是根据用户提供的详细需求，完全实现一个 python代码，实现需求，并且要使用最低规模快速测试自己的代码是否正确"
    agent_workflow=f'''
    **你的注意事项:**
    重要：不要在根目录运行递归的文件展开！！！！注意不要在内容中调用工具，绝对不要输出 tool_calls字段影响解析！！！
    0. 你这次任务的 taskid 是{task_id}，你每次调用工具时，都应该将 taskid 作为参数传递给工具。你不应该基于自己任务的 judge报告进行改进，但是你可以对你调去的工具的返回结果进行改进。
    1. 你的任务是基于给定的任务进行编程，当编程量较大时，你应该考虑基于编程任务拆分成多个 todo 分步骤完成。
    2. 你的代码中所需所使用的任何路径地址必须是绝对地址，你可以使用工具 pwd来获取当前目录的绝对地址。
    3. 你的代码中应该使用最低规模的测试来验证自己的代码是否正确。
    4. 你使用执行函数执行前应该保证所有所需包都已经安装，而且执行时，使用尽量大的的超时时间。
    5. 你应该在测试完成后生成一个 readme 文件告诉用户如何使用你的代码。
    6. 当你认为完成所有任务前，你应该调用 judge_agent 来判断你是否完成任务。你应该给 judge_agent你的代码地址和 readme 报告，和你的测试详情，请 judge 检查，并告诉 judge 不要去运行代码，因为无法预计运行时长。
    7. 无论 judge agent是否通过你都应该进行最终输出，基于 agent 的意见诚实的输出你的进度，成果，和所有有价值的产出的文件地址（一定要说明其相对地址！）和文字产物。并附上 judge agent 的报告作为 output。并说明这是来自于judge agent 的报告。
    8. 创建文件前应该检查创建文件的地址下有无其他同名文件，不要覆盖不是自己的文件！
    你的硬件环境是{hardware_info}。
    '''


    agent_output_format='''
    
         **JSON对象**: 当你准备输出思考过程或做出最终裁决时，必须输出一个严格符合以下格式的JSON字符串,只返回 json 字符串，不要添加任何额外内容：
        ```
        {{
          "status": "thinking" | "success" | "error" ｜ “tool_using”,
          "output": "你的思考过程、计划 | 成功后的输出 ｜ 错误问题 ｜ 工具说明，但是不要列出参数。
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
    你是一个名为 "{agent_name}" 的AI猪手。你的职责是{agent_responsibility}
    你和工具还有其他 agent 在相同的工作环境中，因此对方提供的相对路径你也可以使用。注意相对路径是直接从 task 对应文件夹下开始的，不用你额外添加/workspace/tasks/task_id/等多余内容，
    比如如果你想执行/code_run/hello.py，你直接写 /code_run/hello.py 即可，不用写/workspace/tasks/task_id/code_run/hello.py 等多余内容。

    {agent_workflow}
    **严格的输出格式:**
    你的每一次输出都 **必须** 是：
    
    {agent_output_format}
    
    """
    
    # 获取可用工具 change_here 「改」
    available_tools = ["judge_agent","file_read","dir_list","file_write","execute_code","pip_install","execute_shell"]
    
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
在 code_run 目录下，创建一个代码，实现以下功能，输入一个有权无向图，和起始点与终点，输出最短路径。并绘制最短路径的图。
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