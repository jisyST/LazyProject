# lazyproject

## 项目简介
`lazyproject` 是一个基于 Python 的工具集，旨在通过自动化生成和管理代码文档、依赖项以及项目结构，提升开发效率。主要功能包括代码文档生成、项目结构分析、依赖管理以及 Git 项目标准化支持。适用于需要快速生成和维护项目文档的开发场景。

---

## 功能特性
1. **自动化文档生成**：
   - 支持模块、类、方法的文档字符串自动生成。
   - 提供多语言文档支持（如中英文）。
2. **项目结构分析**：
   - 自动分析项目目录结构和依赖关系。
   - 生成项目目录树和模块信息字典。
3. **Git 项目标准化**：
   - 自动生成 `.gitignore`、`requirements` 和 `README.md` 文件。
   - 支持 MkDocs 配置生成。
4. **代码编辑与转换**：
   - 提供基础编辑器 (`BaseEditor`) 和自定义编辑器 (`CustomEditor`) 工具，用于代码文本转换和文档生成。
5. **文档字符串处理**：
   - 支持文档字符串的清除、填充、润色和翻译功能。

---

### 安装步骤
1. 克隆项目仓库：
   ```bash
   git clone https://github.com/your-repo/lazyproject.git
   ```
2. 进入项目目录：
   ```bash
   cd lazyproject
   ```
3. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

---

## 使用方法
使用 `GitAgent` 生成项目文档：
```python
from lazyproject.lazynote.agent.git_agent import GitAgent

agent = GitAgent(project_path="your_project_path")
agent._generate_readme()
agent._generate_mkdocs()
```

---

## 项目结构
```
lazyproject/
  ├── lazynote/
  │   ├── agent/
  │   │   ├── git_agent       # Git 项目标准化工具
  │   │   └── prompt         # MkDocs 配置文件生成工具
  │   ├── editor/
  │   │   ├── base           # 基础代码编辑器
  │   │   └── custom         # 自定义代码编辑器
  │   ├── manager/
  │   │   ├── base           # 基础文档字符串管理器
  │   │   ├── custom         # 自定义文档字符串管理器
  │   │   └── simple         # 简单文档字符串处理器
  │   └── parser/
  │       └── base           # 基础解析器
```