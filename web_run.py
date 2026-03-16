import streamlit as st
import pandas as pd
import os
import sys
import time
from datetime import datetime
import threading
from dotenv import load_dotenv

# 添加当前目录到 python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import QATool
from app.models.issue import IssueType, Severity

# 页面配置
st.set_page_config(page_title="Game QA Tool", page_icon="🎮", layout="wide")

st.title("🎮 游戏本地化 QA 检查工具")
st.markdown("基于大语言模型和 RAG 的专业游戏本地化质量保证工具。")

if "api_logs" not in st.session_state:
    st.session_state.api_logs = []

_api_log_lock = threading.Lock()

def _append_api_log(event: dict):
    with _api_log_lock:
        st.session_state.api_logs.append(event)
        if len(st.session_state.api_logs) > 200:
            st.session_state.api_logs = st.session_state.api_logs[-200:]

ISSUE_TYPE_CN = {
    "SPELLING": "拼写",
    "GRAMMAR": "语法",
    "TERMINOLOGY": "术语",
    "CONTEXT": "上下文",
    "NUMBER_UNIT": "数字/单位",
    "FORMAT_TAG": "格式/标签",
    "MISSING_EXTRA": "漏译/多译",
    "CHAR_LIMIT": "字符限制",
    "SPACE": "空格",
    "GENDER": "阴阳性",
    "OTHER": "其他",
}

def _to_int_if_numeric(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if s.endswith(".0") and s[:-2].isdigit():
        return int(s[:-2])
    try:
        f = float(s)
        if f.is_integer():
            return int(f)
    except Exception:
        return None
    return None

def _apply_suggestions(target: str, issues) -> str:
    if target is None:
        return ""
    text = str(target)
    for it in issues:
        if not getattr(it, "suggested_text", None):
            continue
        original = getattr(it, "original_text", None)
        suggested = getattr(it, "suggested_text", None)
        if original is None or suggested is None:
            continue
        original_str = str(original)
        suggested_str = str(suggested)
        if original_str == text:
            text = suggested_str
            continue
        if original_str and original_str in text:
            text = text.replace(original_str, suggested_str, 1)
    return text

def _group_text_by_type(issues, field: str) -> str:
    buckets = {}
    for it in issues:
        t_cn = ISSUE_TYPE_CN.get(it.issue_type.value, it.issue_type.value)
        if t_cn not in buckets:
            buckets[t_cn] = []
        if field == "suggested" and getattr(it, "suggested_text", None):
            buckets[t_cn].append(str(it.suggested_text))
        elif field == "description" and getattr(it, "description", None):
            buckets[t_cn].append(str(it.description))
    parts = []
    for t_cn, items in buckets.items():
        if not items:
            continue
        parts.append(f"[{t_cn}] " + "； ".join(items))
    return "\n".join(parts)

# 侧边栏配置
st.sidebar.header("⚙️ 配置中心")

# 1. API 供应商选择
provider = st.sidebar.selectbox(
    "选择 LLM 供应商",
    ["openai", "deepseek", "qwen", "zhipu"],
    index=0
)

# 2. 模型配置
st.sidebar.subheader("模型参数")
provider_prefix = provider.upper()
load_dotenv()

# 预设各大供应商的默认 Base URL 和 模型
DEFAULTS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o"
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat"
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus"
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "model": "glm-4"
    }
}

# 优先级：.env > 官方预设值
default_api_key = os.getenv(f"{provider_prefix}_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
default_base_url = os.getenv(f"{provider_prefix}_BASE_URL") or DEFAULTS[provider]["base_url"]
default_model = os.getenv(f"{provider_prefix}_MODEL") or DEFAULTS[provider]["model"]

api_key = st.sidebar.text_input("API Key", value=default_api_key, type="password")
base_url = st.sidebar.text_input("Base URL", value=default_base_url)
model_name = st.sidebar.text_input("Model Name", value=default_model)

# 监听与日志
st.sidebar.subheader("API 监听")
show_api_logs = st.sidebar.checkbox("显示调用/响应日志", value=True)
if st.sidebar.button("清空日志"):
    st.session_state.api_logs = []

# 3. 文件上传
st.sidebar.subheader("数据上传")
input_file = st.sidebar.file_uploader("上传待检文件 (XLSX, TXT)", type=["xlsx", "txt"])
termbase_file = st.sidebar.file_uploader("上传术语表 (XLSX, TXT)", type=["xlsx", "txt"])
qa_samples_file = st.sidebar.file_uploader("上传 QA Sample 库 (XLSX, JSON)", type=["xlsx", "json"])

# 4. 列名配置 (仅针对 Excel)
st.sidebar.subheader("列名配置 (可选)")
source_column = st.sidebar.text_input("原文列名", placeholder="例如: Source, 原文")
target_column = st.sidebar.text_input("译文列名", placeholder="例如: Target, 译文")
has_header = not st.sidebar.checkbox("Excel 无表头（第一行是数据）", value=False)

st.sidebar.subheader("批量处理")
max_workers = st.sidebar.slider("并行度 (越大越快，越易触发限流)", min_value=1, max_value=8, value=1)

st.sidebar.subheader("RAG 过滤 (可选)")
default_theme = st.sidebar.text_input("题材", value="武侠")
default_text_type = st.sidebar.text_input("文本类型", value="功能")

st.sidebar.subheader("检查项")
checker_options = {
    "拼写": "spelling",
    "语法": "grammar",
    "术语": "term",
    "上下文": "context",
    "综合": "comprehensive",
}
selected_checker_labels = st.sidebar.multiselect(
    "选择要运行的检查器",
    options=list(checker_options.keys()),
    default=list(checker_options.keys()),
)
enabled_checkers = [checker_options[x] for x in selected_checker_labels if x in checker_options]

st.sidebar.subheader("提示词")
lean_prompts = st.sidebar.checkbox("简洁提示词（更快/更省 token）", value=False)

# 主界面
if st.button("🚀 开始检查", disabled=not input_file):
    with st.spinner("正在初始化工具并开始检查..."):
        try:
            st.session_state.api_logs = []
            # 保存上传的文件到临时目录
            if not os.path.exists("temp"):
                os.makedirs("temp")
            
            input_path = os.path.join("temp", input_file.name)
            with open(input_path, "wb") as f:
                f.write(input_file.getbuffer())
            
            termbase_path = None
            if termbase_file:
                termbase_path = os.path.join("temp", termbase_file.name)
                with open(termbase_path, "wb") as f:
                    f.write(termbase_file.getbuffer())

            qa_samples_path = "data/samples"
            if qa_samples_file:
                qa_samples_path = os.path.join("temp", qa_samples_file.name)
                with open(qa_samples_path, "wb") as f:
                    f.write(qa_samples_file.getbuffer())

            # 构建配置
            llm_config = {
                "api_key": api_key,
                "base_url": base_url,
                "model": model_name,
                "event_handler": _append_api_log
            }

            # 运行工具
            prompt_dir = "config/prompts_lean" if lean_prompts else "config/prompts"
            tool = QATool(
                termbase_path=termbase_path,
                samples_path=qa_samples_path,
                llm_config=llm_config,
                enabled_checkers=enabled_checkers,
                prompt_dir=prompt_dir,
                theme=default_theme,
                text_type=default_text_type
            )
            
            # 使用时间戳避免文件占用冲突
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if not os.path.exists("outputs"):
                os.makedirs("outputs")
            output_path = os.path.join("outputs", f"report_{provider}_{timestamp}.xlsx")
            
            report = tool.run(
                input_path,
                output_path,
                source_column=source_column if source_column else None,
                target_column=target_column if target_column else None,
                has_header=has_header,
                max_workers=max_workers
            )

            # 展示结果摘要
            st.success("🎉 检查完成！")
            
            col1, col2, col3 = st.columns(3)
            col1.metric("总段落数", report.total_segments)
            col2.metric("发现问题数", len(report.issues))
            col3.metric("耗时", f"{report.summary.get('duration', 'N/A')}s")

            if show_api_logs:
                st.subheader("🛰️ API 调用与响应日志")
                logs = st.session_state.api_logs
                df_logs = pd.DataFrame([
                    {
                        "type": e.get("type"),
                        "request_id": e.get("request_id"),
                        "model": e.get("model"),
                        "duration_ms": e.get("duration_ms"),
                        "error": e.get("error"),
                        "prompt_preview": (
                            "\n\n".join(
                                [f"{m.get('role')}: {m.get('content_preview')}" for m in (e.get("messages") or [])]
                            )
                            if e.get("type") == "llm_request"
                            else None
                        ),
                        "content_preview": e.get("content_preview")
                    }
                    for e in logs
                    if isinstance(e, dict)
                ])
                st.dataframe(df_logs, use_container_width=True)

            # 问题分类图表
            if report.issues:
                st.subheader("📊 问题分布")
                issue_counts = report.summary.get("issue_types", {})
                st.bar_chart(pd.Series(issue_counts))

                # 问题详情列表
                st.subheader("📝 问题详情")
                segment_texts = report.summary.get("segment_texts", {}) if isinstance(report.summary, dict) else {}
                grouped = {}
                for i in report.issues:
                    grouped.setdefault(i.segment_id, []).append(i)

                rows = []
                def _sort_key(seg_id):
                    n = _to_int_if_numeric(seg_id)
                    if n is not None:
                        return (0, n)
                    return (1, str(seg_id).strip())

                for seg_id in sorted(grouped.keys(), key=_sort_key):
                    issues = grouped[seg_id]
                    types_cn = []
                    for it in issues:
                        t_cn = ISSUE_TYPE_CN.get(it.issue_type.value, it.issue_type.value)
                        if t_cn not in types_cn:
                            types_cn.append(t_cn)
                    seg_info = segment_texts.get(seg_id) or {}
                    target_text = seg_info.get("target", "")
                    rows.append({
                        "ID": seg_id,
                        "原文": seg_info.get("source", ""),
                        "译文": target_text,
                        "错误类型": "; ".join(types_cn),
                        "描述": _group_text_by_type(issues, "description"),
                        "修改意见": _group_text_by_type(issues, "suggested"),
                        "修改后译文": _apply_suggestions(target_text, issues)
                    })

                df_issues = pd.DataFrame(rows, columns=["ID", "原文", "译文", "错误类型", "描述", "修改意见", "修改后译文"])
                st.dataframe(df_issues, use_container_width=True)

                # 下载按钮
                with open(output_path, "rb") as f:
                    st.download_button(
                        label="📥 下载完整 Excel 报告",
                        data=f,
                        file_name=f"QA_Report_{provider}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            else:
                st.info("未发现明显问题，翻译质量很高！")

        except Exception as e:
            st.error(f"检查过程中出现错误: {e}")
            st.exception(e)
            if show_api_logs and st.session_state.api_logs:
                st.subheader("🛰️ API 调用与响应日志")
                df_logs = pd.DataFrame([
                    {
                        "type": x.get("type"),
                        "request_id": x.get("request_id"),
                        "model": x.get("model"),
                        "duration_ms": x.get("duration_ms"),
                        "error": x.get("error"),
                        "prompt_preview": (
                            "\n\n".join(
                                [f"{m.get('role')}: {m.get('content_preview')}" for m in (x.get("messages") or [])]
                            )
                            if x.get("type") == "llm_request"
                            else None
                        ),
                        "content_preview": x.get("content_preview")
                    }
                    for x in st.session_state.api_logs
                    if isinstance(x, dict)
                ])
                st.dataframe(df_logs, use_container_width=True)
else:
    if not input_file:
        st.warning("请先在左侧边栏上传待检文件。")
    
    st.info("💡 提示：您可以在左侧边栏配置不同的 LLM 供应商，系统会自动匹配原文中的术语并检索相似的参考案例。")
