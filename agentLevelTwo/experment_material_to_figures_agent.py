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
agent_name = "experment_material_to_figures_agent"

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
    
    agent_responsibility="你的职责是根据实验代码和结果数据，生成实验结果的英文学术绘图，主要用于发表论文。"
    agent_workflow=f'''
    **你的流程:**
    重要：不要在根目录运行递归的文件展开！！！！
    创建文件前应该使用dir_list工具检查创建文件的地址下有无其他同名文件，不要覆盖不是自己的文件！文件命名尽量独特，根据相关信息进行命名！！！不要创建已经存在的目录！
    0. 你这次任务的 taskid 是{task_id}，你每次调用工具时，都应该将 taskid 作为参数传递给工具。如果你调用的工具返回结果提供了 judge agent 的报告，你应该基于 judge 结果和当前产出，重新使用对应工具，并调整任务，直到其可以完成剩下任务。这个重试最多重试三次。
    1. 你将会得到之前的 agent或者用户给你提供的实验代码和生成结果的文件位置，还有实验计划文件的地址（由 idea_agent 生成），或需要你根据其提示信息自己寻找，一般在code_run 目录下。
    2. 分析code_run目录下的文件，找到相关的结果文件（注意和测试文件区分），同时找到所有参与结果生成的算法代码.py和对应的.md文件（可以基于步骤 1 种的说明文字进行寻找，无需完全分析代码）。
    3. 在根目录建立一个独立的文件夹,使用move_data_to_clean_directory工具将所有有用的文件移动到该文件夹中（包括实验 idea，代码和结果）。也包括之前的实验计划文件和 idea 文件。
    4. 分析所有代码文件或者其对应的.md文件，分析所有结果文件，读取实验 idea 文件，从学术发表的角度，思考应该绘4制什么图。你必须包含的图有框架图（基于总体代码流程，但是是基于 idea 的系统框架图而不是算法流程图），和基于结果的实验图。
    4.5 在进行下一步之前，确保你已经阅读了所有 csv 文件（文件过大的比如超过 1000 行的可以只读前 300 行，理解 paper 的写作意图，从不同方向经可能多的绘制不同类型的图不少于5 张。也可以存在一张图中多个子图的类型。
    5. 使用create_figures_python_agent工具，生成基于数据的图片，你应该详细说明每个图基于表格的是什么数据进行生成（数据文件地址），生成什么样的图形，一般基于matplotlib,注意告诉她需要英文绘图（必须详细！）。你应该一次性告诉它所有作图需求。
    如果图片生成位置不在之前整理好的文件夹下，你应该移动它到刚才的文件夹。
    6. 使用create_figures_gpt_agent工具，生成基于框架图的图片，你应该详用英文说明这个框架图的生成提示词，还包括保存的位置。你最多生成一张框架图。并在生成后将图片一同放到之前创建的文件夹中。并配上图片注释文件。
    6. 检查图片是否存在。
    7. 当你认为完成所有任务前，你应该给 judge_agent你的结果的文件地址，你的任务是什么，你的完成结果是什么，请 judge进行判断。。
    8. 当你觉得可以最终输出，使用 final_output 工具输出你的结果，你必须详细说明每个文件对应什么实验，实验数据的表格中所有的列代表什么含义。
    ** 注意事项 **
    **你每次输出给coding_task_agent任务的内容中请包含experment_plan_to_coding_task_agent的输出的整体代码计划的地址，以便于其理解上下文，你需要明白每个 agent 都是独立的和你上下文环境不同！！**
    **你要强调experment_plan_to_coding_task_agent的输出的整体代码计划的地址是用于其理解上下文的并不是需要整体实现！！！！只需专注于自己的任务即可**
    0. 在 judge 结束后诚实的输出你的进度，成果，和所有有价值的产出的文件地址和文字产物。并附上 judge agent 的报告作为 output的一部分。并说明这是来自于judge agent 的报告。
    1. 创建文件前应该检查创建文件的地址下有无其他同名文件，不要覆盖不是自己的文件（除非初始目标任务脚本名称和存在的重合），作为任务计划任务，你应该都在 upload 目录下创建所有文件,注意每次创建自己的文件前检查是否存在别人的文件，不要覆盖，有些别人已经写过的可以复用的功能文件你可以复用。
    2. 在最终输出时，使用 final_output 工具输出你的结果。文件命名尽量独特，根据相关信息进行命名！！！不要创建已经存在的目录！
    6. 重要：不要在根目录运行递归的文件展开！！！！
    7. 重要：创建文件前应该使用dir_list工具检查创建文件的地址下有无其他同名文件，不要覆盖不是自己的文件！文件命名尽量独特，根据相关信息进行命名！！！不要创建已经存在的目录！
    8. 重要：你不是！你不是编程 ai，不要自己尝试编程。
    
    

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
    available_tools = ['judge_agent','final_output','file_read','file_write','move_data_to_clean_directory','create_figures_python_agent','create_figures_gpt_agent',
                       'dir_list','dir_create']
    
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

{
  "status": "success",
  "output": "# 碳感知自适应路由协议实验系统 - 完整项目报告\n\n## 项目概述\n本项目成功实现了一个完整的碳感知自适应路由协议(Carbon-Aware Adaptive Routing Protocol)实验系统，用于研究结合实时交通信息的路由优化对碳排放的影响。系统从研究计划转化为具体代码实现，并成功运行了多种场景下的实验，生成了全面的实验数据和分析结果。\n\n## 项目架构\n项目由5个核心模块和1个主实验入口文件组成，形成一个完整的碳感知路由系统：\n\n1. **网络模拟模块**(`network_simulator.py`) - 创建网络基础设施和模拟交通条件\n2. **碳排放计算模块**(`carbon_calculator.py`) - 计算不同车辆和路线的碳排放量\n3. **路由算法模块**(`routing_algorithms.py`) - 实现四种不同的路由策略\n4. **实验管理模块**(`experiment_manager_fixed.py`) - 管理实验配置和结果收集\n5. **结果分析模块**(`results_analyzer.py`) - 分析实验数据并生成可视化\n6. **主实验入口**(`main_experiment_fixed_v2.py`) - 协调所有模块进行完整实验\n\n## 实验设计\n实验设计遵循原始研究计划，对比了四种不同的路由算法在三种交通场景下的性能：\n\n### 路由算法\n1. **基准最短路径算法**(baseline_shortest_path) - 传统基于距离的最短路径路由\n2. **静态碳感知算法**(static_carbon_aware) - 考虑碳排放但不考虑实时交通的路由\n3. **交通自适应算法**(traffic_adaptive) - 考虑实时交通但不优化碳排放的路由\n4. **碳感知自适应算法**(carbon_aware_adaptive) - 同时考虑碳排放和实时交通的路由\n\n### 实验场景\n1. **高峰期交通**(peak_traffic) - 模拟早晚高峰的拥堵情况\n2. **非高峰期交通**(off_peak) - 模拟交通流量较小的情况\n3. **混合交通条件**(mixed_conditions) - 模拟一天中不同时段的交通变化\n\n## 实验结果分析\n\n通过分析实验结果文件(`/code_run/results/experiment_summary.txt`和metrics CSV文件)，我们得出以下关键发现：\n\n### 高峰期交通场景(PEAK_TRAFFIC)\n- **时间效率**：baseline_shortest_path和static_carbon_aware算法表现相似(约63.8分钟)，而交通自适应和碳感知自适应算法需要更长时间(分别为98.7和100.1分钟)。\n- **碳排放**：baseline_shortest_path和static_carbon_aware的排放量相似(46.84 kg CO2)，而carbon_aware_adaptive略高(55.14 kg CO2)。\n- **关键发现**：在高峰期，考虑交通状况的算法会选择更长但更畅通的路线，导致时间增加，有时也会增加排放量。\n\n### 非高峰期交通场景(OFF_PEAK)\n- **时间效率**：traffic_adaptive表现最好(52.1分钟)，carbon_aware_adaptive次之(53.3分钟)，而不考虑交通的算法明显较慢(90+分钟)。\n- **碳排放**：carbon_aware_adaptive的排放量最高(184.18 kg CO2)，而baseline_shortest_path和static_carbon_aware相似(约121 kg CO2)。\n- **关键发现**：在非高峰期，实时交通信息对时间优化有显著效果，但可能导致更高的碳排放量。\n\n### 混合交通条件场景(MIXED_CONDITIONS)\n- **时间效率**：考虑实时交通的算法表现更好(75-76分钟 vs 83分钟)。\n- **碳排放**：baseline_shortest_path和static_carbon_aware表现相似(53.81 kg CO2)，而carbon_aware_adaptive略高(60.67 kg CO2)。\n- **关键发现**：在混合条件下，碳感知自适应算法能在时间和排放量之间取得相对平衡。\n\n### 整体表现对比\n1. **baseline_shortest_path vs static_carbon_aware**：在测试场景中，这两种算法表现非常相似，这表明单纯基于静态网络的碳优化在这些情景下效果有限。\n\n2. **traffic_adaptive**：在时间方面表现最好，特别是在非高峰期和混合条件下，但由于不考虑碳排放，无法优化环境影响。\n\n3. **carbon_aware_adaptive**：\n   - 在时间方面接近traffic_adaptive的表现\n   - 在碳排放方面通常高于baseline和static_carbon_aware，表明当前实现的碳感知自适应算法在实际应用中还有改进空间\n   - 在不同场景下表现不同，说明该算法对交通条件敏感\n\n## 实验结果文件说明\n\n1. **场景结果文件**(`results_[scenario_name].csv`)：\n   - `order_id`: 配送订单唯一标识符\n   - `algorithm`: 使用的路由算法名称\n   - `origin`: 起点位置\n   - `destination`: 目的地位置\n   - `vehicle_type`: 使用的车辆类型\n   - `load_weight`: 货物重量(吨)\n   - `route`: 完整路由路径\n   - `total_time`: 总行程时间(分钟)\n   - `total_distance`: 总行程距离(公里)\n   - `total_emissions`: 总碳排放量(kg CO2)\n   - `traffic_hour`: 交通时段(0-23小时)\n   - `execution_time`: 算法执行时间(秒)\n   - `timestamp`: 实验执行时间戳\n\n2. **场景性能指标文件**(`metrics_[scenario_name].csv`)：\n   - `algorithm`: 路由算法名称\n   - `count`: 该算法的实验次数\n   - `successful_routes`: 成功生成路线的实验数\n   - `avg_time`: 平均行程时间(分钟)\n   - `avg_distance`: 平均行程距离(公里)\n   - `avg_emissions`: 平均碳排放量(kg CO2)\n   - `total_emissions`: 该算法在此场景的总排放量(kg CO2)\n   - `avg_execution_time`: 平均算法执行时间(秒)\n\n3. **算法对比文件**(`algorithm_comparison.csv`)：\n   包含所有算法在所有场景下的详细比较数据。\n\n4. **可视化图表**：\n   - `algorithm_comparison.png`: 不同算法性能对比图表\n   - `time_emissions_tradeoff.png`: 时间与排放量之间的权衡图\n   - `route_analysis.png`: 路线分析可视化\n\n5. **实验总结**(`experiment_summary.txt`)：\n   全面总结了实验配置和所有场景下的算法性能表现。\n\n## 主要发现与结论\n\n1. **时间与碳排放之间的权衡**：实验清晰展示了时间效率与碳排放之间的权衡关系。优化行程时间往往会增加碳排放量，特别是在高峰期交通条件下。\n\n2. **交通条件的重要性**：实时交通信息对路由决策有显著影响。在非高峰期，考虑交通状况的算法能将行程时间减少约40%，但可能以增加碳排放为代价。\n\n3. **算法表现因场景而异**：没有一种算法在所有场景下都表现最佳，这强调了自适应路由在不同条件下的重要性。\n\n4. **碳感知自适应算法的潜力与局限**：当前实现的碳感知自适应算法在时间优化方面表现良好，但在碳排放方面仍有改进空间。在某些情况下，它甚至产生了比基线算法更高的碳排放。\n\n5. **执行效率**：所有算法的执行时间都非常短(毫秒级)，表明它们在实际应用中的计算开销很小。\n\n## 未来改进方向\n\n1. **碳感知自适应算法优化**：改进当前算法，使其在保持时间效率的同时更有效地减少碳排放。\n\n2. **更复杂的交通模型**：引入更动态和真实的交通模拟，包括突发事件和季节性变化。\n\n3. **多模态运输**：扩展系统以支持不同类型的运输方式组合。\n\n4. **更大规模的实验**：在更大的网络和更多样化的场景中测试算法。\n\n5. **实际部署测试**：将算法应用于实际物流操作并收集真实世界的性能数据。\n\n## 总结\n\n本项目成功实现了碳感知自适应路由协议的实验系统，并通过全面的实验探索了不同路由策略对时间效率和碳排放的影响。实验结果显示，同时优化时间和碳排放是一个复杂的问题，需要根据不同的交通条件采取不同的策略。此项目为未来的碳感知路由研究提供了坚实的基础和丰富的实验数据。\n\n## Judge Agent评估意见\n\nJudge Agent对main_experiment_fixed_v2.py的评估确认，该文件能够成功运行完整的碳感知自适应路由协议实验并生成有效的实验数据。主要评估结果包括：\n\n- 成功调用所有5个必需模块并正确初始化\n- 成功运行了576个实验(3个场景×8个订单×4个算法×6个交通小时)\n- 生成了完整且有意义的实验结果文件，包括详细结果文件、指标汇总文件、实验总结和算法比较数据\n- 实验数据展示了合理的差异和预期的行为模式，如traffic_adaptive算法关注时间优化而忽略碳排放，carbon_aware_adaptive算法在碳排放和时间之间做了权衡\n\n虽然结果分析环节有一个小警告，但不影响实验的主要目标和数据收集，整体评估为成功。",
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