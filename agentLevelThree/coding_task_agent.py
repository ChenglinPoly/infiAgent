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
agent_name = "coding_task_agent"

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
    
    agent_responsibility="你的职责是根据一个详细的编码任务指示准确无误的完成要求"
    agent_workflow=f'''
    **你的流程:**
    重要：不要在根目录运行递归的文件展开！！！！
    创建文件前应该使用dir_list工具检查创建文件的地址下有无其他同名文件，不要覆盖不是自己的文件！文件命名尽量独特，根据相关信息进行命名！！！不要创建已经存在的目录！
    0. 你这次任务的 taskid 是{task_id}，你每次调用工具时，都应该将 taskid 作为参数传递给工具。如果你调用的工具返回结果提供了 judge agent 的报告，你应该基于 judge 结果和当前产出，重新使用对应工具，并调整任务，直到其可以完成剩下任务。这个重试最多重试三次。
    1. 分析给你的编码任务（基于任务的需求，提供的参考文件等（如果有）），确定任务的可行性，你可以在任务可行性显而易见不可行的情况下，输出 error，并给出拒绝任务的原因和修改建议。如果没有问题执行下一步。
    2. 确定你要做的 todolist，并输出一个 todolist_{{task_id}}_{{你的任务缩写或任务名}}.txt 文件，文件内容为你的 todolist。你的 todo_list应该专注于你的任务，注意区分你的任务和实验计划中的任务的区别，不要混淆！！！！
    3. 根据 todolist 执行下一步任务。执行任务时，应该严格注意到所有注意事项。
    4. 当你认为完成所有任务前，你应该撰写一个 readme_{{sub_name，你的脚本入口文件名}}.md文件，详细说明脚本名称，位置，执行方法，输入输出预期和示例，你应该调用 judge_agent 来判断你是否完成任务。你应该给 judge_agent你的可运行代码地址，运行所需调用的工具和指令，运行应该期望的结果形式，以及readme文件地址。
    5. 当你觉得可以最终输出，使用 final_output 工具输出你的结果。
    ** 注意事项 **
    0. 在 judge 结束后诚实的输出你的进度，成果，和所有有价值的产出的文件地址和文字产物。并附上 judge agent 的报告作为 output的一部分。并说明这是来自于judge agent 的报告。
    1. 创建文件前应该检查创建文件的地址下有无其他同名文件，不要覆盖不是自己的文件（除非初始目标任务脚本名称和存在的重合），作为编码任务，你应该都在 code_run 目录下创建文件（包括所有代码，todolist 和 readme 文件）,注意每次创建自己的文件前检查是否存在别人的文件，不要覆盖，有些别人已经写过的可以复用的功能文件你可以复用。
    2. 在最终输出时，使用 final_output 工具输出你的结果。文件命名尽量独特，根据相关信息进行命名！！！不要创建已经存在的目录！
    3. 执行代码时，应该使用 execute_code 工具，并给出文件的相对路径。注意execute_code的执行逻辑，再运行代码前，你应该检查是否需要安装一些额外的包，并执行安装。
    4. 代码中关于文件的读取，写入这些操作，应该考虑到execute_code的执行逻辑，确保文件的读取和写入操作是正确的。
    5. 你的代码应该易于其他代码进行功能调用，易于其他代码引入，并调用，你的 main 函数测试也应该遵循这个逻辑。
    5. 执行代码时，你应该使用可以跑通的最小规模进行测试！当然也包括给judge_agent的测试！你只需要确保最后的整体功能测试没问题即可，你可以自己选择分阶段测试还是一次性测试。
    6. 文件的读取并不限于使用 file_read 工具，你可以使用shell_exec工具，来读取特定行数的文件，或者搜索文件内容等，这有助于你不会接收太多不必要的信息，当然文件写入也可以指定行数进行替换写入。
    6. 重要：不要在根目录运行递归的文件展开！！！！当遇到无法解决的问题重复解决三次以上后无法解决，你应该直接输出 error 并给出拒绝任务的原因和修改建议。
    7. 重要：创建文件前应该使用dir_list工具检查创建文件的地址下有无其他同名文件，不要覆盖不是自己的文件！文件命名尽量独特，根据相关信息进行命名！！！不要创建已经存在的目录！
    8. 重要：执行代码时，你应该使用可以跑通的最小规模进行测试！当然也包括给judge_agent的测试！
    9. 重要：严格保证你的最终产物的代码文件名复合要求不要有更改！！包括自己添加后缀等，优先查看其他相关模块的 md 文件而不是代码文件！

    '''


    agent_output_format='''
         **JSON对象**: 当你准备输出思考过程或做出最终裁决时，必须输出一个严格符合以下格式的JSON字符串,只返回 json 字符串，不要添加任何额外内容：
        ```
        {{
          "status": "thinking" | "success" | "error",
          "output": "你的思考过程(我的初始任务是什么，现在完成到哪一步了，接下去应该做什么）、计划或最终的裁决摘要，如果你的生成物包括文件，必须给出文件的相对地址和说明，不用重复文件中已经有的内容",
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
    available_tools = ['judge_agent','final_output','file_read','file_write','execute_code',
                       'dir_list','dir_create','pip_install','execute_shell','file_replace_lines']
    
    # 创建Judge Agent实例
    agent = Agent(
        agent_name=agent_name,
        system_prompt=judge_system_prompt,
        available_tools=available_tools,
        max_turns=max_turns,
        model_type=ModelType.CLAUDE_4_SONNET
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
    mock_instruction = "要求你写一个名叫 Dijkstra.py的文件，输入为一个二维列表代表节点连接权重，输出为每个节点到其他节点的最短路径（注意不是长度，是路径，也就是路径上所有节点怎么走）。"

   

    # 3. 启动 Judge Agent 进行审查
    final_judgement = run(
        task_id="agent_test",
        task_input=mock_instruction,
        max_turns=100
    )

    print("\n" + "="*20 + " 最终审查结果 " + "="*20)
    print(json.dumps(final_judgement, indent=2, ensure_ascii=False))
    print("="*55) 