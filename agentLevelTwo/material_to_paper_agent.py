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
agent_name = "material_to_paper_agent"

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
    
    agent_responsibility="你的职责是基于现在的所有材料完成论文最后的生成"
    agent_workflow=f'''
    **你的流程:**
    重要：不要在根目录运行递归的文件展开！！！！你在执行下面每一个步骤的时候都要严格遵循注意事项。
    创建文件前应该使用dir_list工具检查创建文件的地址下有无其他同名文件，不要覆盖不是自己的文件！文件命名尽量独特，根据相关信息进行命名！！！不要创建已经存在的目录！
    0. 你这次任务的 taskid 是{task_id}，你每次调用工具时，都应该将 taskid 作为参数传递给工具。如果你调用的工具返回结果提供了 judge agent 的报告，你应该基于 judge 结果和当前产出，重新使用对应工具，并调整任务，直到其可以完成剩下任务。这个重试最多重试三次。
    1. 你将会得到之前的agent 整理的所有图表的地址，包括相关的说明，还有之前进行 idea 生成的时候的所有相关文献。
    2. 有一个目录将会包含大部分资料除了少部分例如文献（但是文献也有可能已经在主要工作目录下，请你自己检查）等，你应该在拥有大部分相关材料的目录下工作，作为主要目录，不要自己创建新的目录！。并将散落的有用文件（图或者 pdf 参考文献）移动到这个主要目录下。
    3. 第一步，你应该根据大致的图的结果说明（通过读取相关内调），实验计划和idea内容，拟定一个标题和文章大纲。
    4. 根据你拟定的标题和文章大概在指定工作目录下创建 main.tex文件和 bib 文件（先为空）。main.tex文件包含你拟定的大纲，切记所有写作都是使用英文。
    和标题，作者为polyu AI Researcher。大纲应该完全按照学术论文的标准进行，而且通过引入一些之后要写的 tex 文件来构造整个文件，例如 abstract.tex, introduction.tex, related_work.tex等等。
    5. main.tex写好以后，**时刻注意，剩下部分要为你的 main.tex服务，不要写 main.tex没有引入的章节，也不要漏写章节！！**，调用sub_part_tex_editor_agent工具完成剩下的 sub_tex，你应该有计划的完成例如 introduction 和 abstract 部分应该放在最后因为这两个要基于剩下的部分才能完成，告诉工具你要完成的部分，已经完成的部分，和文件夹中所有材料的地址，以及参考文献。对于每个部分记得
    重点强调不同的要求，例如方法说明部分如果实验有代码，应该在该节包含伪代码，如果已经提供了框架图，也需要包含框架图这都是必须要明确要求的。实验部分也应该包含实验部分的图片，同时有些图片没有但是。
    还是可以暂时的部分，可用 tex 的表格展示，提醒 experment 部分的 tex 不要忘记使用表格说明实验参数和实验环境。切记所有写作都用英文。完成以后要检查 tex 文件位置是否正确！！
    6. 当所有部分完成后.使用 tex到 pdf 的智能 agent 生成最后的 pdf 文件。
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
    9. 重要：注意写作顺序，严格按照指令执行！不要自己完成所有写作，交给工具完成 sub_tex 的写作！！！！
    10.你应该告诉sub_part_tex_editor_agent应该在什么位置生成tex 文件，防止文件地方出错！
    
    

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
    available_tools = ['judge_agent','final_output','file_read','file_write','latex_to_pdf_repair_agent','sub_part_tex_editor_agent',
                       'dir_list','dir_create','file_move']
    
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
    mock_instruction = '''

\"我已成功完成了收集cyber-physical Internet物流问题相关文献的任务。根据用户的研究需求，我使用paper_search_agent工具收集了8篇高质量的学术论文，涵盖了四个关键方面：\\n\\n1. CPI在物流路由优化方面的应用：\\n   - \\\"Routing protocols for B2B e-commerce logistics in cyber-physical internet(CPI)\\\" - 研究CPI环境下B2B电子商务物流的路由协议\\n   - \\\"A carbon-aware routing protocol for optimizing carbon emissions in modular construction logistics\\\" - 探讨碳排放优化的路由协议在模块化建筑物流中的应用\\n\\n2. CPI与物联网(IoT)在物流中的集成：\\n   - \\\"Cyber-Physical Internet(CPI)-enabled logistics infrastructure integration framework in the greater bay area\\\" - 提出了大湾区CPI赋能的物流基础设施集成框架\\n   - \\\"The research landscape around the physical internet–a bibliometric analysis\\\" - 文献综述分析了物理互联网研究领域，包括与物联网的集成\\n\\n3. CPI支持的智能物流系统：\\n   - \\\"Cyber-physical internet based intelligent operation platform for off-site construction supply chain management\\\" - 介绍了基于CPI的非现场建筑供应链管理智能运营平台\\n   - \\\"Operations with physical internet\\\" - 探讨了物理互联网环境下的运营方法\\n\\n4. 物流中的实时数据处理与决策：\\n   - \\\"Out-of-Order Architecture for Real-Time Data-Driven Resilient Planning and Scheduling of Cyber-Physical Manufacturing Systems\\\" - 提出了一种用于实时数据驱动的弹性规划和调度的乱序架构\\n   - \\\"Cyber-Physical Internet Asset Services and Hosts: Creation, Configuration, Execution\\\" - 讨论了CPI资产服务和主机的创建、配置和执行\\n\\n所有论文都已成功下载并保存在'upload'目录中，文件格式为PDF。judge_agent已确认这些论文符合原始任务要求，能为用户研究cyber-physical Internet的物流问题提供全面的理论基础、最新研究进展和应用案例。这些资料不仅可以支持后续idea的产生，也适合作为related work的参考材料。\


{
  "status": "success",
  "output": "# Carbon-Aware Adaptive Routing Protocol Study: Academic Figures Package\n\nI have successfully generated a comprehensive set of academic figures for the carbon-aware adaptive routing protocol study. This report details the process, the generated figures, and their significance for academic publication.\n\n## Overview of Task Completion\n\nI created a dedicated directory (`cpi_routing_figures`) containing all relevant materials, including source code, experimental data, and generated figures. I produced five data visualization figures and one framework diagram, all designed according to academic publication standards with English labeling.\n\n## Generated Figures\n\n### 1. Algorithm Performance Comparison Across Traffic Scenarios\n**File:** `/cpi_routing_figures/fig1_algorithm_time_comparison.png`\n\nThis bar chart compares the average travel time across different traffic scenarios (Peak Traffic, Off-Peak, Mixed Conditions) for the four routing algorithms studied:\n- Baseline Shortest Path: Traditional distance-based routing\n- Static Carbon-Aware: Carbon-conscious routing without traffic adaptation\n- Traffic Adaptive: Real-time traffic-aware routing without carbon consideration\n- Carbon-Aware Adaptive: Combined approach balancing traffic conditions and carbon emissions\n\n**Data Source:** `metrics_peak_traffic.csv`, `metrics_off_peak.csv`, and `metrics_mixed_conditions.csv`\n\n**Key Findings:**\n- Adaptive algorithms perform significantly better in Off-Peak conditions\n- In Peak Traffic, baseline approaches unexpectedly outperform adaptive algorithms\n- The Carbon-Aware Adaptive algorithm shows competitive performance with Traffic Adaptive algorithm\n\n### 2. Carbon Emissions vs. Travel Time Trade-off\n**File:** `/cpi_routing_figures/fig2_emissions_time_tradeoff.png`\n\nThis scatter plot visualizes the fundamental relationship between travel time and carbon emissions, with each point representing an algorithm-scenario combination.\n\n**Data Source:** Aggregated from metrics CSV files for all three traffic scenarios\n\n**Key Findings:**\n- Clear negative correlation between travel time and emissions (shorter travel times often yield higher emissions)\n- Carbon-Aware Adaptive algorithm shows a balanced position between time efficiency and emissions reduction\n- Different traffic scenarios create distinct clusters in the emissions-time space\n\n### 3. Carbon Efficiency Across Scenarios\n**File:** `/cpi_routing_figures/fig3_carbon_efficiency.png`\n\nThis grouped bar chart compares total carbon emissions across different traffic scenarios for three routing algorithms (excluding Traffic Adaptive).\n\n**Data Source:** Emissions data from metrics CSV files\n\n**Key Findings:**\n- Static Carbon-Aware and Baseline algorithms have nearly identical emissions in Peak Traffic and Mixed Conditions\n- Carbon-Aware Adaptive algorithm generally produces higher emissions than simpler approaches\n- The greatest emissions differences appear in Off-Peak conditions\n\n### 4. Algorithm Execution Time Analysis\n**File:** `/cpi_routing_figures/fig4_execution_time.png`\n\nThis box plot compares computational efficiency across algorithms using a logarithmic scale to visualize differences in execution times.\n\n**Data Source:** Execution time data from all metrics CSV files\n\n**Key Findings:**\n- Carbon-Aware Adaptive algorithm has significantly higher computational requirements\n- Static Carbon-Aware is the second most computationally intensive\n- Baseline and Traffic Adaptive algorithms have much lower execution times\n- Performance patterns remain consistent across traffic scenarios\n\n### 5. Multi-metric Algorithm Performance Radar Chart\n**File:** `/cpi_routing_figures/fig5_radar_performance.png`\n\nThis radar chart provides a holistic comparison of all algorithms across four normalized metrics: travel time, emissions, distance, and execution time.\n\n**Data Source:** Normalized values from metrics CSV files for all scenarios\n\n**Key Findings:**\n- Baseline and Static Carbon-Aware algorithms show nearly identical performance profiles\n- Traffic Adaptive excels in certain metrics but performs poorly in others\n- Carbon-Aware Adaptive shows balanced performance in most metrics but struggles with execution time\n- No algorithm dominates across all metrics\n\n### 6. System Framework Diagram\n**File:** `/cpi_routing_figures/framework_diagram.png` (placeholder reference to `/upload/gpt_generated_figure.png`)\n\nThis diagram illustrates the two-layer architecture of the Carbon-Aware Adaptive Routing Protocol, showing key components and data flows.\n\n**Data Source:** Based on `/cpi_routing_figures/research_idea_and_plan.json`\n\n**Key Components:**\n- Link Layer (bottom): Organizes autonomous logistics areas with traffic data collection\n- Transport Layer (top): Handles carbon-aware routing decisions based on real-time data\n- Key innovations including integration of carbon factors with traffic data, dynamic route recalculation, and multi-criteria decision making\n\n## Data Files Used for Figure Generation\n\n1. **Metrics Files**:\n   - `metrics_peak_traffic.csv`: Contains algorithm performance data during peak traffic conditions\n   - `metrics_off_peak.csv`: Contains algorithm performance data during off-peak conditions\n   - `metrics_mixed_conditions.csv`: Contains algorithm performance data in mixed traffic conditions\n   \n   These files contain columns for algorithm name, route count, average travel time, average distance, average emissions, total emissions, and average execution time.\n\n2. **Results Files**:\n   - `results_peak_traffic.csv`, `results_off_peak.csv`, `results_mixed_conditions.csv`: Detailed experimental results for each scenario\n   \n   These files contain per-route data including scenario, algorithm, time, distance, emissions, route paths, origin, destination, and vehicle type.\n\n3. **Algorithm Comparison File**:\n   - `algorithm_comparison.csv`: Comprehensive comparison data across all test scenarios\n\n4. **Experiment Summary**:\n   - `experiment_summary.txt`: Text summary of experiment results showing key metrics for each algorithm in each scenario\n\n## Overall Conclusions from the Visualizations\n\nThe generated figures collectively tell a comprehensive story about carbon-aware routing:\n\n1. **Trade-off Relationship**: There is a fundamental trade-off between travel time and carbon emissions in routing decisions.\n\n2. **Context Dependency**: Adaptive algorithms perform better in some traffic conditions but worse in others, highlighting that no single algorithm is universally superior.\n\n3. **Balanced Approach**: The Carbon-Aware Adaptive approach provides a compromise between minimizing travel time and reducing carbon emissions.\n\n4. **Computational Costs**: More sophisticated algorithms come with increased computational requirements, an important consideration for practical deployment.\n\n5. **Multi-dimensional Evaluation**: Routing algorithm selection should be context-dependent, based on which performance aspects are most critical for specific applications.\n\n## Judge Agent Evaluation\n\nThe Judge Agent confirmed successful completion of the task, verifying that:\n- All 5 data visualization figures were correctly generated with appropriate formatting\n- The figures meet academic publication standards with clear labels and legends\n- The framework diagram description was properly created\n- All relevant experimental data was properly organized\n- The only noted issue was that the framework diagram file exists in the upload directory rather than being directly copied to the target directory\n\nThese academic figures provide valuable visualization of the carbon-aware adaptive routing protocol's performance across different traffic scenarios, supporting the research findings for publication.",
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