from typing import Literal
import gradio as gr
import os
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import random
import shutil
import matplotlib.pyplot as plt
from collections import Counter
import re
import numpy as np

# ==============================================================================
# Gradio 应用核心逻辑
# ==============================================================================

MAX_BUTTONS = 100 # 预先定义UI中支持的最大按钮数量（适用于domain和task）

def get_domains(root_dir):
    """获取根目录下的所有domain目录"""
    if not os.path.isdir(root_dir):
        return []
    return [d for d in os.listdir(root_dir) if os.path.isdir(os.path.join(root_dir, d))]

def _get_result_status(result_file):
    """
    一个内部辅助函数，用于读取result.txt并返回一个状态码。
    返回: 1 (成功), 0 (失败), -1 (未知)
    """
    if not result_file.exists():
        return -1
    try:
        result_num = float(result_file.read_text().strip())
        if result_num > 0:
            return 1
        elif result_num == 0:
            return 0
    except (ValueError, TypeError):
        return -1
    return -1

def _read_result_value(result_file):
    """读取具体的result数值，用于显示"""
    if not result_file.exists():
        return "未知"
    try:
        return result_file.read_text().strip()
    except:
        return "Error"

def _get_best_task_result(root_dir, domain, task_name, merge_dirs):
    """
    核心逻辑：在 Base 路径和所有 Merge 路径中，为指定任务寻找最优结果。
    返回: (best_status, best_root, best_result_str)
    """
    candidate_roots = [root_dir]
    if merge_dirs:
        candidate_roots.extend(merge_dirs)

    best_status = -2 
    best_root = root_dir
    best_result_str = "0.0"

    for r_dir in candidate_roots:
        current_task_path = Path(r_dir) / domain / task_name
        if not current_task_path.exists():
            continue
        
        res_file = current_task_path / "result.txt"
        status = _get_result_status(res_file)
        
        # 简单的打擂台逻辑：成功(1) > 失败(0) > 未知(-1)
        if status > best_status:
            best_status = status
            best_root = r_dir
            best_result_str = _read_result_value(res_file)
        elif status == best_status and status == 1:
            # 如果都是成功，数值大的优先
            try:
                curr_val = float(_read_result_value(res_file))
                best_val = float(best_result_str)
                if curr_val > best_val:
                    best_root = r_dir
                    best_result_str = str(curr_val)
            except:
                pass
    
    return best_status, best_root, best_result_str

def calculate_global_stats(root_dir, merge_dirs=None):
    """
    计算全局统计信息（遍历所有Domain）。
    用于在 Domain 选择界面展示。
    """
    domains = get_domains(root_dir)
    total_tasks = 0
    total_success = 0
    
    for domain in domains:
        domain_path = os.path.join(root_dir, domain)
        tasks = [t for t in os.listdir(domain_path) if os.path.isdir(os.path.join(domain_path, t))]
        
        for task in tasks:
            total_tasks += 1
            status, _, score = _get_best_task_result(root_dir, domain, task, merge_dirs)
            if status == 1:
                total_success += float(score)
                
    if total_tasks == 0:
        return "### 📊 全局统计: 暂无任务数据"
    
    success_rate = (total_success / total_tasks) * 100
    stats_text = f"### 🌍 全局任务成功率: {success_rate:.2f}% ({total_success}/{total_tasks})"
    if merge_dirs:
        stats_text += f" <span style='font-size:0.8em; color:gray'>(合并模式已开启, 共合并 {len(merge_dirs)+1} 个路径)</span>"
    return stats_text


def get_tasks_merged(root_dir, domain, compare_dir=None, merge_dirs=None):
    """
    获取指定domain下的所有task，支持合并模式和对比模式。
    
    逻辑：
    1. 以 root_dir (Base) 中的任务列表为基准。
    2. 如果启用 merge_dirs，则在 Base 和所有 Merge 路径中寻找该任务的最优结果。
    3. 统计合并后的成功率。
    4. 如果启用 compare_dir，将 (步骤2中的最优结果) 与 Compare 路径的结果进行对比。
    
    返回: 
    - task_name_list
    - success_list (显示的文字)
    - css_class_list (样式)
    - task_source_map (字典: {task_name: best_path_root}) -> 用于点击任务时知道去哪里加载
    - stats_text (统计信息的Markdown文本)
    """
    domain_path = os.path.join(root_dir, domain)
    if not os.path.isdir(domain_path):
        return [], [], [], {}, ""
    
    # 以当前启动路径的任务为基准
    task_name_list = [t for t in os.listdir(domain_path) if os.path.isdir(os.path.join(domain_path, t))]
    task_name_list.sort() # 排序一下比较好看

    success_list = []
    css_class_list = []
    task_source_map = {} # 记录每个任务应该从哪个根目录加载
    
    # 统计变量
    total_tasks = 0
    merged_success_count = 0

    # 准备待检查的路径列表: [Base, Merge1, Merge2, ...]
    candidate_roots = [root_dir]
    if merge_dirs:
        candidate_roots.extend(merge_dirs)

    for task_name in task_name_list:
        total_tasks += 1
        
        # --- 1. 合并逻辑：寻找最优结果 ---
        best_status = -2 # 初始化一个很低的状态
        best_root = root_dir
        best_result_str = "0.0"
        
        # 遍历所有候选路径，找分最高的
        for r_dir in candidate_roots:
            # 检查该路径下是否存在此任务
            current_task_path = Path(r_dir) / domain / task_name
            if not current_task_path.exists():
                continue
            
            res_file = current_task_path / "result.txt"
            status = _get_result_status(res_file)
            
            # 简单的打擂台逻辑：成功(1) > 失败(0) > 未知(-1)
            # 如果状态更好，或者状态一样但之前的是默认路径而现在是新路径(可选)，则更新
            if status > best_status:
                best_status = status
                best_root = r_dir
                best_result_str = _read_result_value(res_file)
            elif status == best_status and status == 1:
                # 如果都是成功，数值大的优先 (例如 0.8 vs 1.0)
                try:
                    curr_val = float(_read_result_value(res_file))
                    best_val = float(best_result_str)
                    if curr_val > best_val:
                        best_root = r_dir
                        best_result_str = str(curr_val)
                except:
                    pass

        # 记录这个任务的最优源路径
        task_source_map[task_name] = best_root
        
        # 统计成功数
        if best_status == 1:
            merged_success_count += float(best_result_str)

        # 生成显示的文字
        display_text = "未知"
        if best_status == 1:
            display_text = f'✅成功 {best_result_str}✅'
        elif best_status == 0:
            display_text = '❌失败 0.0❌'
        
        # 如果最优解来自合并路径，可以在文字上做个标记(可选)，这里暂不加，保持简洁
        success_list.append(display_text)

        # --- 2. 对比逻辑 ---
        # 使用 "最优结果(best_status)" 去和 "对比路径结果" 比较
        current_css_class = ""
        
        # 检查 Search 标记 (优先检查最优路径下的 search.txt)
        search_flag_file = Path(best_root) / domain / task_name / "search.txt"
        is_search = search_flag_file.exists() and int(search_flag_file.read_text().strip()) == 1
        code_flag_file = Path(best_root) / domain / task_name / "code.txt"
        is_code = code_flag_file.exists() and int(code_flag_file.read_text().strip()) == 1
        
        if compare_dir and os.path.isdir(compare_dir):
            compare_result_file = Path(compare_dir) / domain / task_name / "result.txt"
            compare_status = _get_result_status(compare_result_file)
            
            # 应用颜色规则
            if best_status == 1 and compare_status == 0:
                current_css_class = "compare-main-win" # 赢 (合并后的结果赢)
            elif best_status == 0 and compare_status == 1:
                current_css_class = "compare-comp-win" # 输
        
        # 叠加 Search 样式
        if is_search and not is_code:
            if best_status == 1:
                current_css_class += " search-and-success"
            else:
                current_css_class += " search-and-failure"

        if is_code and not is_search:
            if best_status == 1:
                current_css_class += " code-and-success"
            else:
                current_css_class += " code-and-failure"
        if is_code and is_search:
            if best_status == 1:
                current_css_class += " code-and-search-success"
            else:
                current_css_class += " code-and-search-failure"
        css_class_list.append(current_css_class)

    # 生成统计文本
    if total_tasks > 0:
        success_rate = (merged_success_count / total_tasks) * 100
        stats_text = f"### 🏆 当前展示任务成功率: {success_rate:.2f}% ({merged_success_count}/{total_tasks})"
        if merge_dirs:
            stats_text += " <span style='font-size:0.8em; color:gray'>(已应用合并模式)</span>"
    else:
        stats_text = "### 暂无任务数据"

    return task_name_list, success_list, css_class_list, task_source_map, stats_text

def load_task_data(root_dir, domain, task):
    """加载一个任务的所有步骤数据和结果"""
    # 注意：这里的 root_dir 应该是 task_source_map 中记录的那个最优路径
    task_path = Path(root_dir) / domain / task
    
    # 加载 traj.jsonl
    steps = []
    traj_file = task_path / "traj.jsonl"
    if traj_file.exists():
        with open(traj_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    steps.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    print(f"警告: 在 {traj_file} 中发现无效的JSON行")

    # 加载 result.txt
    result_file = task_path / "result.txt"
    result_text = "未知"
    if result_file.exists():
        result_num = float(result_file.read_text().strip())
        if result_num > 0:
            result_text = f'<span class="success-text">成功 {result_num}</span>'
        elif result_num == 0:
            result_text = '<span class="failure-text">失败 0.0</span>'
    
    instruction = "无指令"
    if steps and "instruction" in steps[0]:
        instruction = steps[0]["instruction"]
        
    return steps, result_text, instruction

def process_code_agent_output(code_agent_output):
    """
    处理 code_agent_output 字典，提取字段并合并历史记录。
    返回提取的数据和可见性标志。
    """
    if not code_agent_output or not isinstance(code_agent_output, dict):
        # 如果没有数据，返回空值和 False（不可见）
        return "N/A", "N/A", "N/A", "[]", False

    task_instruction = code_agent_output.get("task_instruction", "N/A")
    completion_reason = code_agent_output.get("completion_reason", "N/A")
    summary = code_agent_output.get("summary", "N/A")
    
    exec_history = code_agent_output.get("execution_history", [])
    result_history = code_agent_output.get("execution_result_history", [])

    # 为了高效合并，创建一个以 step 为键的结果字典
    results_map = {item.get('step'): item.get('result') for item in result_history if 'step' in item}

    combined_history = []
    if isinstance(exec_history, list):
        for step_action in exec_history:
            step_num = step_action.get("step")
            # 将 action 和 result 合并到同一个对象中
            combined_step = {
                "step": step_num,
                "thoughts": step_action.get("thoughts", "N/A"),
                "action": step_action.get("action", "N/A"),
                "result": results_map.get(step_num, "Result not found for this step.")
            }
            combined_history.append(combined_step)
    
    # 将合并后的列表转换为格式化的JSON字符串
    history_json = json.dumps(combined_history, indent=2)

    # 返回所有处理好的数据和 True（可见）
    return task_instruction, completion_reason, summary, history_json, True

def create_gradio_app(root_dir):
    """创建并返回Gradio应用"""
    
    domains = get_domains(root_dir)
    
    # 初始计算一次全局统计
    initial_global_stats = calculate_global_stats(root_dir, merge_dirs=None)

    CUSTOM_CSS = """
        .gr-button-group { display: flex; flex-wrap: wrap; gap: 10px; }
        .gr-button-group > button { flex-grow: 1; }
        .success-text { color: #28a745; font-weight: bold; }
        .failure-text { color: #dc3545; font-weight: bold; }
        #screenshot-container.milestone .gradio-label {
            color: red !important;
            font-weight: bold !important;
        }
        .compare-main-win {
            background: #d4edda !important; 
            border-color: #c3e6cb !important;
        }
        .compare-comp-win {
            background: #f8d7da !important; 
            border-color: #f5c6cb !important;
        }
        .search-and-success::before {
            content: 'search';
            background-image: linear-gradient(to bottom, #2ecc71, #28a745);
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: bold;
            margin-right: 8px;
            display: inline-block;
            vertical-align: middle;
            border: 1px solid #1e7e34;
            box-shadow: 0 1px 1px rgba(0,0,0,0.1);
        }
        .search-and-failure::before {
            content: 'search';
            background-image: linear-gradient(to bottom, #e74c3c, #dc3545);
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: bold;
            margin-right: 8px;
            display: inline-block;
            vertical-align: middle;
            border: 1px solid #b21f2d;
            box-shadow: 0 1px 1px rgba(0,0,0,0.1);
        }
        .code-and-success::before {
            content: 'code';
            background-image: linear-gradient(to bottom, #2ecc71, #28a745);
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: bold;
            margin-right: 8px;
            display: inline-block;
            vertical-align: middle;
            border: 1px solid #1e7e34;
            box-shadow: 0 1px 1px rgba(0,0,0,0.1);
        }
        .code-and-failure::before {
            content: 'code';
            background-image: linear-gradient(to bottom, #e74c3c, #dc3545);
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: bold;
            margin-right: 8px;
            display: inline-block;
            vertical-align: middle;
            border: 1px solid #b21f2d;
            box-shadow: 0 1px 1px rgba(0,0,0,0.1);
        }
        .code-and-search-success::before {
            content: 'code & search';
            background-image: linear-gradient(to bottom, #2ecc71, #28a745);
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: bold;
            margin-right: 8px;
            display: inline-block;
            vertical-align: middle;
            border: 1px solid #1e7e34;
            box-shadow: 0 1px 1px rgba(0,0,0,0.1);
        }
        .code-and-search-failure::before {
            content: 'code & search';
            background-image: linear-gradient(to bottom, #e74c3c, #dc3545);
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: bold;
            margin-right: 8px;
            display: inline-block;
            vertical-align: middle;
            border: 1px solid #b21f2d;
            box-shadow: 0 1px 1px rgba(0,0,0,0.1);
        }
        .stats-header h3 {
            font-size: 1.5rem !important;
            color: #333;
            margin-bottom: 0.5rem;
        }
    """

    with gr.Blocks(theme=gr.themes.Soft(), css=CUSTOM_CSS) as app:
        # --- 状态存储 ---
        state_root_dir = gr.State(root_dir)
        state_compare_root_dir = gr.State(None)
        state_merge_paths = gr.State([])
        
        state_selected_domain = gr.State()
        state_selected_task = gr.State()
        state_task_source_map = gr.State({}) 
        state_current_viewing_root = gr.State(root_dir)
        
        state_steps_data = gr.State()
        state_current_step_index = gr.State(0)

        # --- 视图1: Domain选择 ---
        with gr.Column(visible=True) as domain_view:
            gr.Markdown(f"# 任务轨迹浏览器({os.path.basename(root_dir)})\n")
            
            # 1. Domain 界面显示全局统计
            global_stats_display = gr.Markdown(initial_global_stats, elem_classes="stats-header")

            with gr.Accordion("🛠️ 高级设置 (对比 & 合并)", open=False):
                with gr.Tab("📊 对比模式"):
                    compare_path_input = gr.Textbox(
                        label="输入对比结果路径", 
                        placeholder="/path/to/another/result",
                        info="输入另一个实验结果的根目录，然后点击开启对比。"
                    )
                    compare_toggle_btn = gr.Button("🚀 开启/更新 对比模式")
                    compare_status_text = gr.Markdown("", visible=False)
                
                with gr.Tab("🔗 合并模式"):
                    merge_paths_input = gr.Textbox(
                        label="输入合并路径列表 (每行一个路径)",
                        placeholder="/path/to/result_A\n/path/to/result_B",
                        lines=3,
                        info="输入多个路径，系统将自动合并当前路径与这些路径，取每个任务的最高分结果展示。"
                    )
                    merge_toggle_btn = gr.Button("🔗 开启/更新 合并模式")
                    merge_status_text = gr.Markdown("", visible=False)

            with gr.Row():
                gr.Image(label="成功率", value=os.path.join(root_dir, "domain_success_rates.png"), type="filepath", interactive=False)
                gr.Image(label="动作使用率", value=os.path.join(root_dir, "overall_action_usage.png"), type="filepath", interactive=False)
                gr.Image(label="步长/成功率", value=os.path.join(root_dir, "overall_step_distribution.png"), type="filepath", interactive=False)
                gr.Image(label="Token使用率", value=os.path.join(root_dir, "overall_token_usage_stacked.png"), type="filepath", interactive=False)

            gr.Markdown("### 选择 Domain:")
            with gr.Group(elem_classes="gr-button-group"):
                domain_buttons = []
                for i in range(MAX_BUTTONS):
                    btn = gr.Button(visible=False)
                    domain_buttons.append(btn)
            
            for i, domain_name in enumerate(domains):
                if i < MAX_BUTTONS:
                    domain_buttons[i].value = domain_name
                    domain_buttons[i].visible = True

        # --- 视图2: Task选择 ---
        with gr.Column(visible=False) as task_view:
            task_view_title = gr.Markdown("# 请选择一个 Task")
            # 2. Task 界面显示 Domain 统计
            domain_stats_display = gr.Markdown("", elem_classes="stats-header")
            
            with gr.Row():
                back_to_domains_btn = gr.Button("⬅️ 返回 Domain 选择")
            with gr.Row():
                domain_action_img = gr.Image(label=f"动作使用率", type="filepath", interactive=False)
                domain_step_img = gr.Image(label=f"步长/成功率", type="filepath", interactive=False)
                domain_token_img = gr.Image(label="Token使用率", type="filepath", interactive=False)

            with gr.Group(elem_classes="gr-button-group"):
                task_buttons = []
                success_buttons = []
                for i in range(MAX_BUTTONS):
                    with gr.Row():
                        btn = gr.Button(visible=False)
                        success = gr.Button(visible=False, interactive=False)
                    success_buttons.append(success)
                    task_buttons.append(btn)

        # --- 视图3: 轨迹查看器 ---
        with gr.Column(visible=False) as viewer_view:
            viewer_title = gr.Markdown("# 正在查看任务")
            with gr.Row():
                back_to_tasks_btn = gr.Button("⬅️ 返回 Task 选择")
            
            step_counter = gr.Markdown("步骤 1 / N")
            with gr.Row():
                prev_step_btn = gr.Button("◀️ 上一步")
                next_step_btn = gr.Button("▶️ 下一步")

            with gr.Row():
                with gr.Column(scale=4):
                    screenshot_img = gr.Image(
                        label="步骤截图", type="filepath", interactive=False, elem_id="screenshot-container"
                    )                    
                    evaluator_json = gr.Code(label="Evaluator", language="json", interactive=False)
                    
                with gr.Column(scale=2):
                    plan_text = gr.Textbox(label="Plan", lines=8, interactive=False)
                    plan_code_text = gr.Code(label="Plan Code", language="python", interactive=False)
                    reflection_text = gr.Textbox(label="Reflection", lines=5, interactive=False)

                    with gr.Accordion(label="Code Agent Plan Details", open=True, visible=False) as code_agent_accordion:
                        task_instruction_text = gr.Textbox(label="Task Instruction", lines=3, interactive=False)
                        completion_reason_text = gr.Textbox(label="Completion Reason", lines=1, interactive=False)
                        summary_text = gr.Textbox(label="Summary", lines=8, interactive=False)
                        execution_history_json = gr.Code(label="Combined Execution History", language="json", interactive=False)
                    with gr.Accordion(label="Search Agent Tutorials", open=True, visible=False) as search_agent_accordion:
                        tutorial_text = gr.Textbox(label="Tutorials", lines=8, interactive=False)

        # =================================================================
        # 函数与事件处理
        # =================================================================

        def toggle_comparison(path):
            if path and os.path.isdir(path):
                status_md = f"✅ **对比模式已开启。** 对比路径: `{path}`"
                return {
                    state_compare_root_dir: path,
                    compare_status_text: gr.update(value=status_md, visible=True),
                    compare_toggle_btn: gr.update(value="🔄 更新对比路径"),
                }
            else:
                return {
                    state_compare_root_dir: None,
                    compare_status_text: gr.update(value="❌ 路径无效，对比模式关闭。", visible=True),
                    compare_toggle_btn: gr.update(value="🚀 开启对比模式"),
                }

        def toggle_merge(text_input, root_dir):
            """开启合并模式时，需要立即计算一次全局统计"""
            paths = [line.strip() for line in text_input.split('\n') if line.strip()]
            valid_paths = [p for p in paths if os.path.isdir(p)]
            
            # 计算新的全局统计
            new_stats = calculate_global_stats(root_dir, merge_dirs=valid_paths)
            
            if valid_paths:
                status_md = f"✅ **合并模式已开启。** 有效路径数: {len(valid_paths)}<br>"
                for p in valid_paths:
                    status_md += f"- `{p}`<br>"
                if len(paths) > len(valid_paths):
                    status_md += f"⚠️ 忽略了 {len(paths) - len(valid_paths)} 个无效路径。"
                
                return {
                    state_merge_paths: valid_paths,
                    merge_status_text: gr.update(value=status_md, visible=True),
                    merge_toggle_btn: gr.update(value="🔄 更新合并列表"),
                    global_stats_display: gr.update(value=new_stats) # 更新全局统计
                }
            else:
                return {
                    state_merge_paths: [],
                    merge_status_text: gr.update(value="❌ 无有效路径，合并模式关闭。", visible=True),
                    merge_toggle_btn: gr.update(value="🔗 开启合并模式"),
                    global_stats_display: gr.update(value=new_stats) # 更新全局统计
                }

        def select_domain(domain_name, current_root_dir, compare_root_dir, merge_dirs):
            """选择Domain：计算并展示该Domain的统计信息"""
            # 获取任务列表和Domain统计
            tasks, success_list, css_classes, source_map, domain_stats_text = get_tasks_merged(
                current_root_dir, domain_name, compare_dir=compare_root_dir, merge_dirs=merge_dirs
            )
            
            updates = {
                state_selected_domain: domain_name,
                state_task_source_map: source_map,
                domain_view: gr.update(visible=False),
                task_view: gr.update(visible=True),
                task_view_title: gr.update(value=f"# Domain: {domain_name}\n请选择一个 Task："),
                domain_stats_display: gr.update(value=domain_stats_text), # 更新 Task 界面的 Domain 统计
                domain_action_img: gr.update(value=f"{os.path.join(root_dir, f'action_usage_{domain_name}.png')}"),
                domain_step_img: gr.update(value=f"{os.path.join(root_dir, f'step_distribution_{domain_name}.png')}"),
                domain_token_img: gr.update(value=f"{os.path.join(root_dir, f'token_usage_stacked_{domain_name}.png')}"),
            }
            
            for i in range(MAX_BUTTONS):
                if i < len(tasks):
                    updates[task_buttons[i]] = gr.update(
                        value=tasks[i], visible=True, elem_classes=css_classes[i]
                    )
                    updates[success_buttons[i]] = gr.update(
                        value=success_list[i], visible=True
                    )
                else:
                    updates[task_buttons[i]] = gr.update(visible=False, elem_classes="")
                    updates[success_buttons[i]] = gr.update(visible=False)

            return updates
        
        def select_task(task_name, source_map, selected_domain, base_root_dir):
            target_root = source_map.get(task_name, base_root_dir)
            steps, result, instruction = load_task_data(target_root, selected_domain, task_name)
            
            updates = {
                state_selected_task: task_name,
                state_current_viewing_root: target_root,
                state_steps_data: steps,
                state_current_step_index: 0,
                task_view: gr.update(visible=False),
                viewer_view: gr.update(visible=True),
                viewer_title: gr.update(value=f"## {task_name}: {instruction}\n### 最终结果: {result}")
            }
            if not steps:
                updates.update({
                    step_counter: "没有可显示的步骤。", screenshot_img: None, plan_text: "无数据",
                    plan_code_text: "无数据", reflection_text: "无数据",
                    prev_step_btn: gr.update(interactive=False), next_step_btn: gr.update(interactive=False),
                })
            else:
                step_updates = _get_step_display_updates(steps, 0, target_root, selected_domain, task_name)
                updates.update(step_updates)
            return updates

        def change_step(index, change, steps, viewing_root, domain, task):
            new_index = index + change
            if not (0 <= new_index < len(steps)):
                return {state_current_step_index: index}
            updates = _get_step_display_updates(steps, new_index, viewing_root, domain, task)
            updates[state_current_step_index] = new_index
            return updates

        def _get_step_display_updates(steps, index, root_dir, domain, task):
            step_data = steps[index]
            response = step_data.get("response", {})
            base_path = Path(root_dir) / domain / task
            filename = step_data.get("screenshot_file", "")
            
            img_path = base_path / filename
            annotated_img_path = base_path / (filename[:-4] + "_draw.png")
            milestone_img_path = base_path / (filename[:-4] + "_milestone.png")
            
            if annotated_img_path.exists():
                img_path = annotated_img_path
            elif milestone_img_path.exists():
                img_path = milestone_img_path
            
            is_milestone = "milestone" in str(img_path)
            new_label = "Milestone!" if is_milestone else "步骤截图"
            new_classes = ["milestone"] if is_milestone else []
            
            updates = {
                step_counter: gr.update(value=f"步骤 {index + 1} / {len(steps)}"),
                screenshot_img: gr.update(value=str(img_path) if img_path.exists() else None, label=new_label, elem_classes=new_classes),
                plan_text: gr.update(value=response.get("plan", "N/A")),
                plan_code_text: gr.update(value=response.get("plan_code", "N/A")),
                reflection_text: gr.update(value=response.get("reflection", "N/A")),
                prev_step_btn: gr.update(interactive=index > 0),
                next_step_btn: gr.update(interactive=index < len(steps) - 1),
            }
            
            code_agent_output = response.get("code_agent_output")
            (task_instruction, completion_reason, summary, history_json, is_code_visible) = process_code_agent_output(code_agent_output)
            is_search_visible, tutorial = (True, response["search_agent_output"]["final_answer"]) if response.get("search_agent_output") else (False, "N/A")
            
            evaluator_path = base_path.parent.parent.parent.parent / "evaluation_examples" / "osworld" / "examples" / domain / f"{task}.json"
            if not evaluator_path.exists():
                 evaluator_path = base_path.parent.parent.parent.parent / "evaluation_examples" / "waa" / "examples" / domain / f"{task}.json"

            if evaluator_path.exists():
                try:
                    evaluator_data = json.load(open(evaluator_path, "r", encoding="utf-8"))["evaluator"]
                    if "postconfig" in evaluator_data: del evaluator_data["postconfig"]
                    updates[evaluator_json] = gr.update(value=json.dumps(evaluator_data, indent=2))
                except:
                    updates[evaluator_json] = gr.update(value="无法加载 Evaluator 文件")
            else:
                print("[Evaluator]: Evaluator not exists!")
            updates.update({
                code_agent_accordion: gr.update(visible=is_code_visible),
                search_agent_accordion: gr.update(visible=is_search_visible),
                task_instruction_text: gr.update(value=task_instruction),
                completion_reason_text: gr.update(value=completion_reason),
                summary_text: gr.update(value=summary),
                execution_history_json: gr.update(value=history_json),
                tutorial_text: gr.update(value=tutorial),
            })
            return updates

        def back_to_domains_fn(root_dir, merge_dirs):
            """返回Domain列表时，重新计算/刷新全局统计"""
            stats = calculate_global_stats(root_dir, merge_dirs)
            return {
                domain_view: gr.update(visible=True), 
                task_view: gr.update(visible=False),
                global_stats_display: gr.update(value=stats) # 刷新全局统计
            }

        def back_to_tasks_fn(selected_domain, stats_text):
            return {
                task_view: gr.update(visible=True), 
                viewer_view: gr.update(visible=False), 
                task_view_title: gr.update(value=f"# Domain: {selected_domain}\n请选择一个 Task："),
                domain_stats_display: gr.update(value=stats_text) # 保持 Domain 统计
            }

        # --- 绑定事件 ---
        
        compare_toggle_btn.click(
            fn=toggle_comparison,
            inputs=[compare_path_input],
            outputs=[state_compare_root_dir, compare_status_text, compare_toggle_btn]
        )

        merge_toggle_btn.click(
            fn=toggle_merge,
            inputs=[merge_paths_input, state_root_dir],
            outputs=[state_merge_paths, merge_status_text, merge_toggle_btn, global_stats_display]
        )

        domain_click_outputs = [
            state_selected_domain, state_task_source_map, 
            domain_view, task_view, task_view_title, domain_stats_display, 
            domain_action_img, domain_step_img, domain_token_img
        ] + task_buttons + success_buttons
        
        for btn in domain_buttons:
            btn.click(
                fn=select_domain,
                inputs=[btn, state_root_dir, state_compare_root_dir, state_merge_paths],
                outputs=domain_click_outputs
            )
        
        task_select_outputs = [
            state_selected_task, state_current_viewing_root, state_steps_data, state_current_step_index, 
            task_view, viewer_view, viewer_title,
            step_counter, screenshot_img, plan_text, plan_code_text, reflection_text, prev_step_btn, next_step_btn,
            code_agent_accordion, search_agent_accordion, task_instruction_text, completion_reason_text, summary_text, execution_history_json, tutorial_text, evaluator_json
        ]
        for btn in task_buttons: 
            btn.click(
                fn=select_task, 
                inputs=[btn, state_task_source_map, state_selected_domain, state_root_dir], 
                outputs=task_select_outputs
            )
        
        step_change_outputs = [
            state_current_step_index, step_counter, screenshot_img, plan_text, plan_code_text, reflection_text,
            prev_step_btn, next_step_btn,
            code_agent_accordion, search_agent_accordion, task_instruction_text, completion_reason_text, summary_text, execution_history_json, tutorial_text, evaluator_json
        ]
        prev_step_btn.click(
            fn=change_step, 
            inputs=[state_current_step_index, gr.State(-1), state_steps_data, state_current_viewing_root, state_selected_domain, state_selected_task], 
            outputs=step_change_outputs
        )

        next_step_btn.click(
            fn=change_step, 
            inputs=[state_current_step_index, gr.State(1), state_steps_data, state_current_viewing_root, state_selected_domain, state_selected_task], 
            outputs=step_change_outputs
        )
        
        back_to_domains_btn.click(
            fn=back_to_domains_fn, 
            inputs=[state_root_dir, state_merge_paths], 
            outputs=[domain_view, task_view, global_stats_display]
        )
        
        back_to_tasks_btn.click(
            fn=back_to_tasks_fn, 
            inputs=[state_selected_domain, domain_stats_display], 
            outputs=[task_view, viewer_view, task_view_title, domain_stats_display]
        )

    return app

# Helper function to safely extract action from plan_code string
def extract_action_from_plan(plan_code):
    """
    Extracts the action name from a plan_code string like 'agent.click(...)'.
    It looks for the string between the first '.' and the first '('.
    
    Args:
        plan_code (str): The plan code string.
        
    Returns:
        str or None: The extracted action name, or None if the format is unexpected.
    """
    if not isinstance(plan_code, str):
        return None
    
    # Use regex for a more robust extraction
    # This pattern finds a word (alphanumeric + underscore) that is preceded by a '.'
    # and followed by a '('.
    match = re.search(r'\.(.*?)\(', plan_code)
    if match:
        return match.group(1)
    
    # Fallback for simple cases if regex fails, though less robust
    try:
        dot_index = plan_code.find('.')
        paren_index = plan_code.find('(')
        if 0 <= dot_index < paren_index:
            return plan_code[dot_index + 1:paren_index]
    except Exception:
        pass # Ignore errors in string manipulation
        
    return None

# ==============================================================================
# 新增的绘图辅助函数
# ==============================================================================
from matplotlib.ticker import MaxNLocator
def plot_step_histogram(success_steps, failure_steps, title, save_path):
    """
    为成功和失败的任务创建步长分布的上下对比直方图。
    (新版：两个子图均为正向，且上子图也显示X轴刻度)

    Args:
        success_steps (list): 成功任务的步长列表。
        failure_steps (list): 失败任务的步长列表。
        title (str): 图表的总标题。
        save_path (str): 图片保存路径。
    """
    if not success_steps and not failure_steps:
        print(f"Skipping plot for '{title}' as there is no step data.")
        return

    # 创建两个垂直排列的子图，并共享X轴
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
    fig.suptitle(title, fontsize=16)

    # 计算合适的bins范围，确保覆盖所有步数
    all_steps = success_steps + failure_steps
    max_step = max(all_steps) if all_steps else 1
    # bins从1到max_step+2，确保每个整数步长都有独立的条柱
    bins = range(1, max_step + 3) 

    # --- 上子图: 成功的任务 ---
    ax1.hist(success_steps, bins=bins, color='mediumseagreen', alpha=0.8, rwidth=0.8, label='Success')
    ax1.set_title('Successful Tasks')
    ax1.set_ylabel('Number of Tasks')
    
    ax1.tick_params(axis='x', labelbottom=True)
    
    # 确保Y轴刻度为整数
    ax1.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax1.grid(axis='y', linestyle='--', alpha=0.6)
    # 为上子图也添加Y轴的0线，使其看起来更完整
    ax1.axhline(0, color='black', linewidth=0.8)


    # --- 下子图: 失败的任务 ---
    ax2.hist(failure_steps, bins=bins, color='tomato', alpha=0.8, rwidth=0.8, label='Failure')
    ax2.set_title('Failed Tasks')
    ax2.set_xlabel('Number of Steps')
    ax2.set_ylabel('Number of Tasks')
    # 确保Y轴刻度为整数
    ax2.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax2.grid(axis='y', linestyle='--', alpha=0.6)
    # 为下子图也添加Y轴的0线
    ax2.axhline(0, color='black', linewidth=0.8)

    # 调整子图之间的间距
    fig.tight_layout(rect=[0, 0.03, 1, 0.95], h_pad=3) # 增加垂直间距 h_pad

    plt.savefig(save_path)
    plt.close(fig)
    print(f"Saved step distribution plot to {save_path}")


def parse_reflection_type(reflection: str):
    if reflection == "":
        return "On Track"
    if "gui operation error" in reflection.lower():
        return "GUI Operation Error"
    elif "lack of tutorial" in reflection.lower():
        return "Lack of Tutorial"
    elif "code error" in reflection.lower():
        return "Code Error"
    else:
        return "On Track"
    
def plot_token_usage_stacked(stats_data, title, save_path):
    """
    Generates and saves a stacked bar chart for prompt and completion token usage.
    
    Updates:
    1. Logic: Zero-padding is used. Averages are based on the global number of tasks.
       (Even if an agent is not used in a task, it counts as 0 usage).
    2. Export: Saves detailed statistics (Mean, Std, Max, Min) to a JSON file.
    3. Error Bars: Represents Standard Deviation (Mean +/- Std), clipped at 0.
    """
    if not stats_data:
        print(f"Skipping stacked token plot for '{title}' due to no data.")
        return

    try:
        # --- 1. 确定全局任务总数 (num_tasks) ---
        # 遍历所有 Agent 的所有记录，找到最大的列表长度作为任务总数
        num_tasks = 0
        for agent_data in stats_data.values():
            p_len = len(agent_data.get('prompt', []))
            c_len = len(agent_data.get('completion', []))
            num_tasks = max(num_tasks, p_len, c_len)
        
        if num_tasks == 0:
            print(f"Skipping stacked token plot for '{title}' as num_tasks is zero.")
            return

        # 准备数据容器
        agents = sorted(stats_data.keys())
        
        # 用于绘图的列表
        plot_prompt_avgs = []
        plot_completion_avgs = []
        plot_total_stds = [] # 这里存的是 Total Token (Prompt+Completion) 的标准差
        
        # 用于 JSON 导出的字典
        export_stats = {
            "meta": {
                "title": title,
                "total_tasks": num_tasks,
                "calculation_method": "Global Average (Zero-padded for missing tasks)"
            },
            "agents": {}
        }

        # 用于计算 "Total" (系统级) 的累加器
        global_prompt_matrix = np.zeros((len(agents), num_tasks))
        global_completion_matrix = np.zeros((len(agents), num_tasks))

        # --- 2. 处理每个 Agent 的数据 ---
        for idx, agent in enumerate(agents):
            raw_prompts = stats_data[agent].get('prompt', [])
            raw_completions = stats_data[agent].get('completion', [])

            # A. 零填充 (Zero-Padding)
            # 将数据补齐到 num_tasks 长度
            padded_prompts = np.pad(raw_prompts, (0, num_tasks - len(raw_prompts)), 'constant')
            padded_completions = np.pad(raw_completions, (0, num_tasks - len(raw_completions)), 'constant')
            
            # 存入矩阵以便后续计算 Total
            global_prompt_matrix[idx] = padded_prompts
            global_completion_matrix[idx] = padded_completions

            # B. 计算统计量
            # 单个任务的总消耗 = Prompt + Completion
            agent_task_totals = padded_prompts + padded_completions
            
            p_avg = np.mean(padded_prompts)
            c_avg = np.mean(padded_completions)
            total_avg = np.mean(agent_task_totals)
            total_std = np.std(agent_task_totals)
            total_max = np.max(agent_task_totals)
            total_min = np.min(agent_task_totals)

            # 存入绘图列表
            plot_prompt_avgs.append(p_avg)
            plot_completion_avgs.append(c_avg)
            plot_total_stds.append(total_std)

            # 存入导出字典
            export_stats["agents"][agent] = {
                "prompt_avg": float(p_avg),
                "completion_avg": float(c_avg),
                "total_avg": float(total_avg),
                "total_std": float(total_std),
                "total_max": float(total_max),
                "total_min": float(total_min)
            }

        # --- 3. 计算 "Total" (所有 Agent 加和) 的数据 ---
        # 将矩阵沿轴 0 (Agent维度) 求和，得到每个任务的系统总消耗
        system_task_prompts = np.sum(global_prompt_matrix, axis=0)
        system_task_completions = np.sum(global_completion_matrix, axis=0)
        system_task_totals = system_task_prompts + system_task_completions

        total_p_avg = np.mean(system_task_prompts)
        total_c_avg = np.mean(system_task_completions)
        total_all_avg = np.mean(system_task_totals)
        total_all_std = np.std(system_task_totals)
        total_all_max = np.max(system_task_totals)
        total_all_min = np.min(system_task_totals)

        # 添加到绘图列表
        agents.append('Total')
        plot_prompt_avgs.append(total_p_avg)
        plot_completion_avgs.append(total_c_avg)
        plot_total_stds.append(total_all_std)

        # 添加到导出字典
        export_stats["agents"]["Total"] = {
            "prompt_avg": float(total_p_avg),
            "completion_avg": float(total_c_avg),
            "total_avg": float(total_all_avg),
            "total_std": float(total_all_std),
            "total_max": float(total_all_max),
            "total_min": float(total_all_min)
        }

        # --- 4. 保存 JSON 文件 ---
        json_path = os.path.splitext(save_path)[0] + '.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(export_stats, f, indent=4)
        print(f"Saved token statistics to {json_path}")

        # --- 5. 开始绘图 ---
        plt.figure(figsize=(max(10, len(agents) * 1.5), 8))
        
        bar_width = 0.6
        indices = np.arange(len(agents))
        
        p_avgs_np = np.array(plot_prompt_avgs)
        c_avgs_np = np.array(plot_completion_avgs)
        stds_np = np.array(plot_total_stds)
        total_heights = p_avgs_np + c_avgs_np

        # 绘制 Prompt 柱状图
        plt.bar(indices, p_avgs_np, bar_width, label='Prompt Tokens', color='#1f77b4', alpha=0.8)
        # 绘制 Completion 柱状图 (堆叠)
        plt.bar(indices, c_avgs_np, bar_width, bottom=p_avgs_np, label='Completion Tokens', color='#ff7f0e', alpha=0.8)

        # 绘制误差棒
        # 逻辑：上限是 Mean + Std，下限是 Mean - Std。
        # 但为了不让误差棒画到负数区域（不美观且无物理意义），我们将下限误差截断。
        # lower_error = min(total_height, std) 意味着如果 std > mean，下限误差棒长度等于 mean，正好触底到0。
        lower_errors = np.minimum(total_heights, stds_np)
        upper_errors = stds_np
        asymmetric_errors = np.array([lower_errors, upper_errors])
        
        plt.errorbar(indices, total_heights, yerr=asymmetric_errors, fmt='none', ecolor='black', capsize=5, elinewidth=1.5, markeredgewidth=1.5)

        plt.ylabel('Average Token Count (Global Average)')
        plt.title(f"{title}\n(Averaged over {num_tasks} tasks, including idle runs)")
        plt.xticks(indices, agents, rotation=45, ha='right')
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.legend()

        # --- 6. 添加数值标签 ---
        for i in range(len(agents)):
            total_h = total_heights[i]
            prompt_h = p_avgs_np[i]
            completion_h = c_avgs_np[i]

            # 格式化显示
            val_str = f'{total_h/1000:,.1f}k' if total_h >= 1000 else f'{total_h:,.0f}'
            
            # 如果方差极大，标记一下
            if stds_np[i] > total_h:
                val_str += "*" # 标记表示高波动

            plt.text(indices[i], total_h + upper_errors[i], val_str, ha='center', va='bottom', fontsize=8, fontweight='bold')

        plt.tight_layout()
        plt.savefig(save_path)
        plt.close()
        print(f"Saved stacked token usage plot to {save_path}")

    except Exception as e:
        print(f"An unexpected error occurred while generating stacked token usage plot for '{title}': {e}")
        import traceback
        traceback.print_exc()


def get_result(target_dir):
    """
    Analyzes experiment results from a target directory, calculates success rates,
    gathers action and token statistics, and generates various plots including Error Analysis.
    """
    if not os.path.exists(target_dir):
        print(f"Error: Target directory '{target_dir}' does not exist.")
        return None

    # --- 0. Load Infeasible Task List (新增) ---
    infeasible_path = "evaluation_examples/osworld/test_infeasible.json"
    infeasible_task = {}
    if os.path.exists(infeasible_path):
        try:
            infeasible_task = json.load(open(infeasible_path, "r", encoding="utf-8"))
        except Exception as e:
            print(f"Warning: Failed to load infeasible tasks from {infeasible_path}: {e}")
    else:
        # 如果找不到文件，默认所有任务都是 feasible，或者你可以根据需要调整路径
        # print(f"Warning: Infeasible task file not found at {infeasible_path}.")
        pass

    # --- Data Structures for Analysis ---
    all_result = []
    domain_result_raw = {} # 保留此结构以兼容旧逻辑
    all_result_for_analysis = {}
    overall_action_counts = Counter()
    domain_action_counts = {}

    # --- 新增：用于详细统计 (All/Feasible/Infeasible) 的结构 ---
    # 结构: raw_stats[domain][category] = {'scores': [], 'steps': []}
    raw_stats = {} 
    def init_domain_stats():
        return {
            'all':        {'scores': [], 'steps': []},
            'feasible':   {'scores': [], 'steps': []},
            'infeasible': {'scores': [], 'steps': []}
        }

    # --- Token 统计结构 ---
    domain_token_stats = {}
    overall_token_stats = {}

    # --- Error/Reflection 统计结构 ---
    # 定义 4 类标签，保持行列一致
    COLUMN_LABELS = ["GUI Operation Error", "Lack of Tutorial", "Code Error", "Other Error", "None"]
    ROW_LABELS = ["GUI Error", "Loop Error", "None"]
    def init_error_stats():
        return {
            # 这是一个 4x4 的计数器： matrix[Row_Hint][Col_Reflection] = count
            'matrix': {r: {c: 0 for c in COLUMN_LABELS} for r in ROW_LABELS},
            'total_steps': 0
        }

    domain_error_stats = {}
    overall_error_stats = init_error_stats()

    # 辅助函数：解析 Reflection Type 归一化为 4 类
    def parse_reflection_type(ref_str: str):
        if not ref_str or ref_str == "None": return "None"
        if "gui operation error" in ref_str.lower(): return "GUI Operation Error"
        if "lack of tutorial" in ref_str.lower(): return "Lack of Tutorial"
        if "code error" in ref_str.lower(): return "Code Error"
        if "other error" in ref_str.lower(): return "Other Error"
        return "None" # 归类为 Other

    print("Starting analysis...")
    # --- Data Collection Loop ---
    for domain in os.listdir(target_dir):
        domain_path = os.path.join(target_dir, domain)
        if not os.path.isdir(domain_path): continue

        domain_action_counts[domain] = Counter()
        domain_token_stats[domain] = {}
        domain_error_stats[domain] = init_error_stats()
        
        # 初始化新统计容器
        if domain not in raw_stats: raw_stats[domain] = init_domain_stats()
        # 获取当前 Domain 的 infeasible ID 列表
        domain_infeasible_ids = infeasible_task.get(domain, [])

        for example_id in os.listdir(domain_path):
            example_path = os.path.join(domain_path, example_id)
            if not os.path.isdir(example_path): continue

            if domain not in all_result_for_analysis: all_result_for_analysis[domain] = {}
            if example_id not in all_result_for_analysis[domain]: all_result_for_analysis[domain][example_id] = {}

            # 判断任务类型
            is_infeasible = example_id in domain_infeasible_ids
            task_type = 'infeasible' if is_infeasible else 'feasible'

            # --- 1. Process Success/Failure Result ---
            result_file = os.path.join(example_path, "result.txt")
            final_result = 0.0
            if os.path.exists(result_file):
                try:
                    with open(result_file, "r") as f: result_str = f.read().strip()
                    try: result_val = float(result_str)
                    except (ValueError, TypeError): result_val = float(eval(result_str))
                    final_result = result_val
                except Exception as e:
                    print(f"Warning: Could not parse result file {result_file}. Defaulting to 0.0. Error: {e}")
                    final_result = 0.0
                
                # 旧逻辑保留
                if domain not in domain_result_raw: domain_result_raw[domain] = []
                domain_result_raw[domain].append(final_result)
                all_result.append(final_result)
                
                all_result_for_analysis[domain][example_id]["score"] = final_result

                # --- 2. Process Trajectory for Action and Step Statistics ---
                traj_file = os.path.join(example_path, "traj.jsonl")
                step_count = 0 # 默认为 0
                if os.path.exists(traj_file):
                    try:
                        with open(traj_file, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                            step_count = len(lines) # 获取步数
                            all_result_for_analysis[domain][example_id]["step"] = step_count
                            
                            for line in lines:
                                try:
                                    data = json.loads(line)
                                    plan_code = data.get("response", {}).get("plan_code") or data.get("plan_code")
                                    
                                    # 模拟 action 获取
                                    action = "unknown"
                                    if plan_code: action = plan_code.split('(')[0]

                                    if action:
                                        overall_action_counts[action] += 1
                                        domain_action_counts[domain][action] += 1
                                    if "call_search_agent" in action:
                                        with open(os.path.join(example_path, "search.txt"), "w", encoding="utf-8") as f:
                                            f.write("1")
                                    if "call_code_agent" in action:
                                        with open(os.path.join(example_path, "code.txt"), "w", encoding="utf-8") as f:
                                            f.write("1")

                                    # --- ErrorType 统计逻辑 (Updated for Heatmap) ---
                                    reflection_data = data.get("response", {}).get("reflection", {})
                                    error_hint = reflection_data.get("hint", {})
                                    
                                    # 1. 确定 Ground Truth (Hint) - Row
                                    # 优先级：如果有明确的 True，取第一个；如果全 False，则为 None/Other
                                    gui_hint = error_hint.get("gui_operation_error", False)
                                    lack_of_tutorial_hint = error_hint.get("lack_of_tutorial", False)
                                    code_hint = error_hint.get("code_error", False)

                                    row_label = "None"
                                    if gui_hint: row_label = "GUI Error"
                                    elif lack_of_tutorial_hint: row_label = "Loop Error"
                                    
                                    # 2. 确定 Prediction (Reflection) - Column
                                    raw_ref_type = reflection_data.get("reflection", "None")
                                    col_label = parse_reflection_type(raw_ref_type)

                                    # 3. 更新统计
                                    # Domain Level
                                    domain_error_stats[domain]['total_steps'] += 1
                                    domain_error_stats[domain]['matrix'][row_label][col_label] += 1

                                    # Overall Level
                                    overall_error_stats['total_steps'] += 1
                                    overall_error_stats['matrix'][row_label][col_label] += 1

                                except (json.JSONDecodeError, AttributeError): continue
                    except Exception as e:
                        print(f"Warning: Could not read or process trajectory file {traj_file}. Error: {e}")
            
                # --- 新增：填充详细统计数据 ---
                # 1. 填入对应类型 (Feasible 或 Infeasible)
                raw_stats[domain][task_type]['scores'].append(final_result)
                raw_stats[domain][task_type]['steps'].append(step_count)
                # 2. 填入 All 类型
                raw_stats[domain]['all']['scores'].append(final_result)
                raw_stats[domain]['all']['steps'].append(step_count)


                # --- 3. Process Token Usage ---
                token_log_file = os.path.join(example_path, "token.jsonl")
                if os.path.exists(token_log_file):
                    task_token_summary = {}
                    try:
                        with open(token_log_file, "r", encoding="utf-8") as f:
                            for line in f:
                                try:
                                    data = json.loads(line.strip())
                                    agent_name = data.get("agent_name")
                                    if not agent_name: continue
                                    if agent_name not in task_token_summary:
                                        task_token_summary[agent_name] = {"completion_tokens": 0, "prompt_tokens": 0, "total_tokens": 0}
                                    task_token_summary[agent_name]["completion_tokens"] += data.get("completion_tokens", 0)
                                    task_token_summary[agent_name]["prompt_tokens"] += data.get("prompt_tokens", 0)
                                    task_token_summary[agent_name]["total_tokens"] += data.get("total_tokens", 0)
                                except (json.JSONDecodeError, AttributeError): continue
                        
                        if task_token_summary:
                            task_token_output_path = os.path.join(example_path, "token.json")
                            with open(task_token_output_path, "w", encoding="utf-8") as f:
                                json.dump(task_token_summary, f, indent=4)
                            
                            for agent, tokens in task_token_summary.items():
                                if agent not in domain_token_stats[domain]:
                                    domain_token_stats[domain][agent] = {'prompt': [], 'completion': []}
                                domain_token_stats[domain][agent]['prompt'].append(tokens['prompt_tokens'])
                                domain_token_stats[domain][agent]['completion'].append(tokens['completion_tokens'])
                                
                                if agent not in overall_token_stats:
                                    overall_token_stats[agent] = {'prompt': [], 'completion': []}
                                overall_token_stats[agent]['prompt'].append(tokens['prompt_tokens'])
                                overall_token_stats[agent]['completion'].append(tokens['completion_tokens'])

                    except Exception as e:
                        print(f"Warning: Could not process token file {token_log_file}. Error: {e}")

    # --- Result Summary and JSON Output ---
    if not all_result:
        print("New experiment or no valid results found.")
        return None

    # --- 新增：格式化打印函数 ---
    def print_metrics(label, data_dict):
        """
        data_dict 结构: {'all': {'scores':[], 'steps':[]}, 'feasible': ..., 'infeasible': ...}
        """
        def get_stats(cat):
            scores = data_dict[cat]['scores']
            steps = data_dict[cat]['steps']
            count = len(scores)
            if count == 0: return "N/A", "N/A", 0
            sr = sum(scores) / count * 100
            avg_steps = sum(steps) / count
            return f"{sr:.2f}%", f"{avg_steps:.1f}", count

        sr_all, step_all, cnt_all = get_stats('all')
        sr_fea, step_fea, cnt_fea = get_stats('feasible')
        sr_inf, step_inf, cnt_inf = get_stats('infeasible')

        print(f"{label:<20} | "
              f"ALL: SR={sr_all:<5} Stp={step_all:<4} ({cnt_all}) | "
              f"FEA: SR={sr_fea:<5} Stp={step_fea:<4} ({cnt_fea}) | "
              f"INF: SR={sr_inf:<5} Stp={step_inf:<4} ({cnt_inf})")

    # --- 打印表头 ---
    print("\n" + "="*120)
    print(f"{'Domain Analysis':<20} | {'All Tasks':<30} | {'Feasible Tasks':<30} | {'Infeasible Tasks':<30}")
    print(f"{'':<20} | {'SR':<6} {'Step':<5} {'(Num)':<6}      | {'SR':<6} {'Step':<5} {'(Num)':<6}      | {'SR':<6} {'Step':<5} {'(Num)':<6}")
    print("-" * 120)

    # 1. Sub-Domain 统计
    domain_success_rate = {} # 重建此字典以供 Plot 3 使用
    sorted_domains = sorted(raw_stats.keys())
    for domain in sorted_domains:
        print_metrics(domain, raw_stats[domain])
        # 重建 domain_success_rate 用于后续绘图
        scores = raw_stats[domain]['all']['scores']
        if scores:
            domain_success_rate[domain] = sum(scores) / len(scores) * 100
    
    print("-" * 120)

    # 2. Father Domain 统计
    # 动态判断使用哪套映射
    if "thunderbird" in raw_stats.keys():
        father_domain_mapping = {
            "OS": ["os"],
            "Office": ["libreoffice_calc", "libreoffice_impress", "libreoffice_writer"],
            "Daily": ["chrome", "vlc", "thunderbird"],
            "Professional": ["vscode", "gimp"],
            "Workflow": ["multi_apps"]
        }
    elif "msedge" in raw_stats.keys():
        father_domain_mapping = {
            "Office": ["libreoffice_writer", "libreoffice_calc"],
            "Web Browing": ["msedge", "chrome"],
            "Windows System": ["file_explorer", "settings"],
            "Coding": ["vs_code"],
            "Media & Video": ["vlc"],
            "Windows Utilities": ["microsoft_paint",  "clock", "windows_calc", "notepad"]
        }
    else:
        father_domain_mapping = {
            "SingleApps": ["calendar", "clock", "finder", "mac_system_settings", "notes", "reminders", "safari", "terminal", "vscode"],
            "MultiApps": ["multi_app"]
        }
    if father_domain_mapping:
        for father, children in father_domain_mapping.items():
            father_stats = init_domain_stats()
            has_data = False
            for child in children:
                if child in raw_stats:
                    has_data = True
                    for cat in ['all', 'feasible', 'infeasible']:
                        father_stats[cat]['scores'].extend(raw_stats[child][cat]['scores'])
                        father_stats[cat]['steps'].extend(raw_stats[child][cat]['steps'])
            
            if has_data:
                print_metrics(f"[F] {father}", father_stats)
        print("-" * 120)

    # 3. Overall 统计
    overall_stats = init_domain_stats()
    for domain in raw_stats:
        for cat in ['all', 'feasible', 'infeasible']:
            overall_stats[cat]['scores'].extend(raw_stats[domain][cat]['scores'])
            overall_stats[cat]['steps'].extend(raw_stats[domain][cat]['steps'])
    
    print_metrics("OVERALL", overall_stats)
    print("=" * 120)

    # 计算 overall_rate 供 Plot 3 使用
    overall_rate = 0.0
    if all_result:
        overall_rate = sum(all_result) / len(all_result) * 100

    json_output_path = os.path.join(target_dir, "all_result_summary.json")
    try:
        with open(json_output_path, "w", encoding="utf-8") as f: json.dump(all_result_for_analysis, f, indent=4)
        print(f"\nAnalysis summary saved to {json_output_path}")
    except Exception as e: print(f"Error saving summary JSON: {e}")

    # --- Plotting Section ---
    print("\nGenerating plots...")

    # Plot 1: Overall Action Usage
    if overall_action_counts:
        try:
            save_path = os.path.join(target_dir, "overall_action_usage.png")
            plt.figure(figsize=(12, 8)); sorted_actions = overall_action_counts.most_common(); actions = [i[0] for i in sorted_actions]; counts = [i[1] for i in sorted_actions]
            bars = plt.barh(actions, counts, color='skyblue'); plt.xlabel('Usage Count'); plt.ylabel('Action Type'); plt.title('Overall Action Usage Frequency'); plt.gca().invert_yaxis()
            if counts: plt.xlim(right=max(counts) * 1.15)
            for bar in bars: xval = bar.get_width(); plt.text(xval + (max(counts) * 0.01), bar.get_y() + bar.get_height() / 2.0, f' {int(xval)} ({int(xval) / sum(counts) * 100:.1f}%)', ha='left', va='center')
            plt.tight_layout(); plt.savefig(save_path); plt.close(); print(f"Saved overall action usage plot to {save_path}")
        except Exception as e: print(f"Error generating overall action usage plot: {e}")

    # Plot 2: Per-Domain Action Usage
    for domain, counts in domain_action_counts.items():
        if not counts: continue
        try:
            save_path = os.path.join(target_dir, f"action_usage_{domain}.png")
            plt.figure(figsize=(10, 6))
            
            sorted_actions = counts.most_common()
            actions = [i[0] for i in sorted_actions]
            action_counts = [i[1] for i in sorted_actions] 
            
            bars = plt.barh(actions, action_counts, color='lightgreen')
            plt.xlabel('Usage Count')
            plt.ylabel('Action Type')
            plt.title(f'Action Usage Frequency in Domain: {domain}')
            plt.gca().invert_yaxis()
            
            if action_counts: 
                plt.xlim(right=max(action_counts) * 1.15)
            
            total_count = sum(action_counts)

            for bar in bars: 
                xval = bar.get_width()
                plt.text(xval + (max(action_counts) * 0.01), 
                         bar.get_y() + bar.get_height() / 2.0, 
                         f' {int(xval)} ({int(xval) / total_count * 100:.1f}%)', 
                         ha='left', va='center')
            
            plt.tight_layout()
            plt.savefig(save_path)
            plt.close()
            print(f"Saved action usage plot for domain '{domain}' to {save_path}")
        except Exception as e: 
            print(f"Error generating action usage plot for domain {domain}: {e}")

    # Plot 3: Success Rate by Domain
    if domain_success_rate:
        try:
            save_path = os.path.join(target_dir, "domain_success_rates.png"); domains_sorted = sorted(domain_success_rate.keys()); rates_sorted = [domain_success_rate[d] for d in domains_sorted]
            plot_labels = domains_sorted + ['Average']; plot_values = rates_sorted + [overall_rate]; colors = ['#87CEEB'] * len(domains_sorted) + ['#FF6347']
            plt.figure(figsize=(max(10, len(plot_labels) * 0.8), 7)); bars = plt.bar(plot_labels, plot_values, color=colors)
            plt.ylabel('Success Rate (%)'); plt.title('Success Rate by Domain and Overall Average'); plt.xticks(rotation=45, ha='right'); plt.ylim(0, 110); plt.grid(axis='y', linestyle='--', alpha=0.7)
            for bar in bars: yval = bar.get_height(); plt.text(bar.get_x() + bar.get_width()/2.0, yval + 1.5, f'{yval:.1f}%', ha='center', va='bottom')
            plt.tight_layout(); plt.savefig(save_path); plt.close(); print(f"Saved success rate plot to {save_path}")
        except Exception as e: print(f"Error generating success rate plot: {e}")


    # --- Plot 4: Step Distribution Histograms ---
    step_stats = {'overall': {'success_steps': [], 'failure_steps': []}}
    for domain, tasks in all_result_for_analysis.items():
        if domain not in step_stats: step_stats[domain] = {'success_steps': [], 'failure_steps': []}
        for task_id, data in tasks.items():
            if data.get('score') is not None and data.get('step') is not None:
                if data['score'] > 0.0: 
                    step_stats[domain]['success_steps'].append(data['step'])
                    step_stats['overall']['success_steps'].append(data['step'])
                else: 
                    step_stats[domain]['failure_steps'].append(data['step'])
                    step_stats['overall']['failure_steps'].append(data['step'])

    for name, data in step_stats.items():
        save_path = os.path.join(target_dir, 'overall_step_distribution.png' if name == 'overall' else f'step_distribution_{name}.png')
        title = f"{'Overall' if name == 'overall' else 'Domain: ' + name} Task Outcome by Number of Steps"
        try:
            # 假设 plot_step_histogram 存在
            if name == "overall":
                overall_step_stat = {
                    "success_steps": data['success_steps'],
                    "failure_steps": data['failure_steps']
                }
                with open(os.path.join(target_dir, "step_stat.json"), "w", encoding="utf-8") as f:
                    json.dump(overall_step_stat, f, indent=4)
                # print(f"Success Step: {data['success_steps']}, Failure Step: {data['failure_steps']}")
            plot_step_histogram(data['success_steps'], data['failure_steps'], title, save_path)
        except NameError:
            # 如果外部没有定义该函数，跳过
            pass



    # --- Plot 5: 调用新的堆叠图函数 ---
    print("\nGenerating stacked token usage plots...")
    try:
        # 为每个 domain 生成图表
        for domain, token_data in domain_token_stats.items():
            plot_token_usage_stacked(
                stats_data=token_data,
                title=f'Average Token Usage (Stacked) per Task in Domain: {domain}',
                save_path=os.path.join(target_dir, f"token_usage_stacked_{domain}.png")
            )
        plot_token_usage_stacked(
            stats_data=overall_token_stats,
            title='Overall Average Token Usage (Stacked) per Task',
            save_path=os.path.join(target_dir, "overall_token_usage_stacked.png")
        )
    except NameError:
        print("Warning: plot_token_usage_stacked function not found. Skipping token plots.")


    # --- Plot 6: Error & Reflection Analysis (Heatmap / Confusion Matrix) ---
    print("\nGenerating error analysis heatmaps...")

    def plot_confusion_heatmap(stats, title_prefix, save_path):
        """
        Generates a 4x4 Heatmap.
        Y-axis (Rows): Ground Truth (Hint)
        X-axis (Cols): Agent Reflection (Predicted)
        """
        if stats['total_steps'] == 0:
            return

        # 准备数据矩阵 (4x4)
        data_matrix = []
        
        for row_label in ROW_LABELS:
            row_data = []
            for col_label in COLUMN_LABELS:
                row_data.append(stats['matrix'][row_label][col_label])
            data_matrix.append(row_data)
        
        data_np = np.array(data_matrix)

        # 开始绘图
        fig, ax = plt.subplots(figsize=(10, 8))
        
        # 使用 imshow 绘制热力图
        # cmap='OrRd' (橙红) 或 'Blues' (蓝) 都不错
        im = ax.imshow(data_np, cmap='Blues')

        # 设置坐标轴
        ax.set_xticks(np.arange(len(COLUMN_LABELS)))
        ax.set_yticks(np.arange(len(ROW_LABELS)))
        
        # 标签换行处理，防止重叠
        formatted_labels = [l.replace(" ", "\n") for l in COLUMN_LABELS]
        ax.set_xticklabels(formatted_labels, fontsize=10)
        ax.set_yticklabels(ROW_LABELS, fontsize=10)

        # 轴标题
        ax.set_xlabel("Agent Reflection (Predicted)", fontsize=12, fontweight='bold')
        ax.set_ylabel("Environment Hint (Ground Truth)", fontsize=12, fontweight='bold')
        
        # 将 X 轴标签移到顶部，或者保持在底部但旋转
        plt.setp(ax.get_xticklabels(), rotation=0, ha="center", rotation_mode="anchor")

        # 标题
        ax.set_title(f"{title_prefix}\nReflection Confusion Matrix", fontsize=14, pad=20)

        # 添加颜色条
        cbar = ax.figure.colorbar(im, ax=ax)
        cbar.ax.set_ylabel("Count", rotation=-90, va="bottom")

        # 在每个格子里填入数字
        # 阈值用于自动调整字体颜色（深色背景用白字，浅色背景用黑字）
        threshold = data_np.max() / 2.
        
        total_count = data_np.sum()

        for i in range(len(ROW_LABELS)): # Row
            for j in range(len(COLUMN_LABELS)): # Col
                count = data_np[i, j]
                # 计算该格子的百分比 (占总步数的比例)
                pct = (count / total_count * 100) if total_count > 0 else 0
                
                text_color = "white" if count > threshold else "black"
                
                # 显示格式：数量 (百分比)
                text_str = f"{count}\n({pct:.1f}%)"
                
                ax.text(j, i, text_str, ha="center", va="center", color=text_color, fontsize=11, fontweight='bold')

        plt.tight_layout()
        plt.savefig(save_path)
        plt.close()
        print(f"Saved error heatmap to {save_path}")

    # Generate Overall Plot
    print(f'Overall Error Stats: {overall_error_stats}')
    plot_confusion_heatmap(overall_error_stats, "Overall", os.path.join(target_dir, "overall_error_analysis_heatmap.png"))

    # Generate Per-Domain Plots
    for domain, stats in domain_error_stats.items():
        plot_confusion_heatmap(stats, f"Domain: {domain}", os.path.join(target_dir, f"error_analysis_heatmap_{domain}.png"))

    print("\nAnalysis complete.")
    return all_result


# ==============================================================================
# 主程序入口
# ==============================================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()

    # environment config
    parser.add_argument("--root_dir", type=str, required=True)
    parser.add_argument("--port", type=int, default=10000)
    args = parser.parse_args()
    
    get_result(args.root_dir)
    gradio_app = create_gradio_app(args.root_dir)
    gradio_app.launch(server_name="0.0.0.0", server_port=args.port, allowed_paths=["/nvme/yangbowen/"])
