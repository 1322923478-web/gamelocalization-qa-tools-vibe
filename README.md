# Game QA Tool

基于 Python 的本地化游戏 QA 检查工具，支持语法、拼写、术语一致性、上下文检查等功能。

## 功能特性

- **拼写检查 (Spelling Check)**: 识别文本中的拼写错误。
- **语法检查 (Grammar Check)**: 检查语法错误和句式问题。
- **术语一致性 (Terminology Consistency)**: 确保翻译与术语表一致。
- **上下文检查 (Context Check)**: 检查翻译在特定语境下的准确性。
- **扩展检查**:
  - 数字/单位错误
  - 格式/标签错误
  - 漏译/多译
  - 字符限制
  - 空格检查
  - 阴阳性

## 快速开始

1. 安装依赖:
   ```bash
   pip install -r requirements.txt
   ```
2. 配置环境变量:
   复制 `.env.example` 为 `.env` 并填入你的 API Key。
3. 运行工具:
   ```bash
   python run.py --input data/test/sample.xlsx --output outputs/report.xlsx
   ```

## 目录结构

(见 user_input 中提供的结构)
