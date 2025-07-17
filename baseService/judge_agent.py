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


def _get_available_tools() -> List[str]:
    """从 tools_level.yaml 文件中加载所有级别为 4 的工具。"""
    tools_level_path = os.path.join(project_root, 'baseService', 'tools_level.yaml')
    available_tools = []
    try:
        with open(tools_level_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            for tool_name, details in config.get("tools", {}).items():
                if details.get("level") == 4:
                    available_tools.append(tool_name)
        return available_tools
    except FileNotFoundError:
        print(f"警告: 工具级别配置文件 'tools_level.yaml' 未找到。")
        return []
    except Exception as e:
        print(f"读取 'tools_level.yaml' 时出错: {e}")
        return []


def create_judge_agent(max_turns: int = 100) -> Agent:
    """
    创建一个Judge Agent实例。
    
    Args:
        max_turns (int): 最大审查轮次
        
    Returns:
        Agent: 配置好的Judge Agent实例
    """
    # Judge Agent专用的系统提示
    judge_system_prompt = f"""
    你是一个名为 "Judge Agent" 的AI审查员。你的职责是严格、细致地验证一个任务的执行结果是否符合其最初的指令。
    你和你检查的工具在相同的工作环境中，因此对方提供的相对路径你也可以使用。注意相对路径是直接从 task 对应文件夹下开始的，不用你额外添加/workspace/tasks/task_id/等多余内容，
    比如如果你想执行/code_run/hello.py，你直接写 /code_run/hello.py 即可，不用写/workspace/tasks/task_id/code_run/hello.py 等多余内容。

    **你的审查流程:**
    1.  **分析输入**: 我会给你提供原始指令和该任务的执行结果。
    2.  **调查验证**: 你必须使用可用的工具来调查和验证结果的真实性和准确性。例如，如果结果说一个文件被创建了，你应该使用 `file_read` 或 `dir_list` 工具去确认。python 代码文件你应该尽可能使用工具使其运行，并检查运行结果。除非代码并没可执行入口。
    3.  **循环思考**: 如果一次调查不够，你可以继续调用工具，或者输出你的思考过程，直到你得出最终结论。
    4.  **最终裁决**: 当你收集到足够的信息后，做出最终的裁决：'success' 或 'error'。

    **严格的输出格式:**
    你的每一次输出都 **必须** 是：
    
    2.  **JSON对象**: 当你准备输出思考过程或做出最终裁决时，必须输出一个严格符合以下格式的JSON字符串,只返回 json 字符串，不要添加任何额外内容：
        ```
        {{
          "status": "thinking" | "success" | "error",
          "output": "你的思考过程、计划或最终的裁决摘要。如果复合要求则详细说明所有产出的文件相对地址，作用；如果失败则详细说明失败原因，以及哪些产物可以保留，哪些应该被删除。然后在在重构任务中详细说明重构后的任务。（剔除已经完成的部分，并说明情况，必要时给出意见）",
          "error_information": "仅在最终裁决为 'error' 时填写失败原因。"
        }}
        ```

    **Status说明**:
    - `thinking`: 表示你还未完成审查，`output` 字段应包含你的思考、分析和下一步计划。对话将继续。
    - `success`: 表示你已完成审查，并确认任务 **完全符合** 原始指令。`output` 字段必须详细说明原始任务是什么，你确认了什么，相关产物（如文件）在哪里，它们的内容和作用是什么。对话将终止。
    - `error`: 表示审查未通过。`output` 字段必须解释失败的原因，哪些部分不符合要求，哪些产物可以保留，哪些应该被删除。`error_information` 字段应包含核心的错误信息。对话将终止。
    
    ！
    
    """
    
    # 获取可用工具
    available_tools = _get_available_tools()
    
    # 创建Judge Agent实例
    judge_agent = Agent(
        agent_name="Judge Agent",
        system_prompt=judge_system_prompt,
        available_tools=available_tools,
        max_turns=max_turns,
        model_type=ModelType.CLAUDE_3_7_SONNET
    )
    
    return judge_agent


def run(
    task_id: str,
    original_instruction: str,
    agent_result: Dict[str, Any],
    max_turns: int = 100
) -> Dict:
    """
    运行 Judge Agent 来审查一个任务的结果。

    Args:
        task_id (str): 任务的唯一ID，审查过程中的所有工具调用都将使用此ID。
        original_instruction (str): 原始的任务指令或目标。
        agent_result (Dict[str, Any]): 被审查的Agent或工具的输出结果。
        max_turns (int, optional): 防止无限循环的最大审查轮次。

    Returns:
        Dict: 审查完成后的最终JSON对象，包含 'status', 'output', 'error_information'。
    """
    print(f"⚖️  启动 Judge Agent，审查任务: {task_id} ⚖️")

    # 创建Judge Agent实例
    judge_agent = create_judge_agent(max_turns)
    
    # 将输入转换为字符串格式
    agent_result_str = str(agent_result)

    # 构建用户输入
    user_input = f"""
    请开始审查。
    - **原始指令**: "{original_instruction}"
    - **执行结果**:
    ```json
    {agent_result_str}
    ```
    """
    
    # 运行Judge Agent
    return judge_agent.run(task_id, user_input)


if __name__ == '__main__':
    # --- 使用示例 ---
    # 模拟一个场景：一个Agent被要求创建一个文件，并声称它成功了。
    
    # 1. 原始指令
    mock_instruction = "请在 `upload/` 目录下创建一个名为 'test_plan.md' 的文件，内容随意但是长度必须超过 100 字符串。'并且在任意位置创建一个可运行的 python脚本。其功能是输入 a,b打印乘法结果"

    # 2. Agent的执行结果 (模拟 file_write 工具的成功输出)
    mock_agent_result = {
        "status": "success",
        "output": "我在 /uoload下创建了 md，并且在 code_run下创建了对应的代码文件，执行方式是直接运行。",
        "error_information": ""
    }

    # 3. 启动 Judge Agent 进行审查
    final_judgement = run(
        task_id="agent_test",
        original_instruction=mock_instruction,
        agent_result=mock_agent_result
    )

    print("\n" + "="*20 + " 最终审查结果 " + "="*20)
    print(json.dumps(final_judgement, indent=2, ensure_ascii=False))
    print("="*55) 