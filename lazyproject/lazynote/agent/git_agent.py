import os
import sys
from typing import List, Dict
import yaml
import json
import time
import re
import importlib
import inspect
import pkgutil
from lazyllm.module.onlineChatModule.onlineChatModule import OnlineChatModule
from lazyllm import ReactAgent
from lazyllm import fc_register, LOG
from ..manager.custom import CustomManager
from .prompt import (
    README_PROMPT,
    GITIGNORE_PROMPT,
    LICENSE_PROMPT,
    generate_mkdocs_config,
    MKDOCS_PROMPT,
    TRANSLATE_PROMPT,
    PLUGIN_CONFIG,
)


class GitAgent:
    """GitAgent类用于自动化管理Git项目的标准化流程，包括文档生成、项目结构分析等功能。"""
    def __init__(self, project_path: str, llm: OnlineChatModule, language: str = "zh"):
        """初始化GitAgent实例。
        
        Args:
            project_path (str): 项目根目录路径。
            llm (OnlineChatModule): 语言模型实例。
            language (str): 支持的语言类型，默认为'zh'（中文）。
        
        异常:
            ValueError: 当项目路径不存在或语言不支持时抛出。"""
        self.project_path = os.path.abspath(project_path)
        if not os.path.exists(self.project_path):
            raise ValueError(f"Project path does not exist: {self.project_path}")

        self.supported_languages = {"zh", "en", "bilingual"}
        if language not in self.supported_languages:
            raise ValueError(f"Unsupported language: {language}. "
                             f"Please choose from {self.supported_languages}.")
        self.language = language

        self.docstring_manager = CustomManager(
            llm=llm, pattern="fill", skip_on_error=True, language=language
        )
        self.module_dict = {}
        self.module_doc_dict = {}
        if self.project_path not in sys.path:
            sys.path.append(self.project_path)
        self._gen_module_dict()
        self.llm = llm
        self.tool_registered = False

    def standardize_project(self, gen_docstrings: bool = True, gen_mkdocs: bool = True) -> None:
        """执行项目标准化流程。
        
        Args:
            gen_docstrings (bool): 是否生成文档字符串，默认为True。
            gen_mkdocs (bool): 是否生成MkDocs文档，默认为True。"""
        self._generate_requirements()
        self._generate_gitignore()
        if gen_docstrings:
            self._generate_docstring()
            self._update_module_dict()
        self._generate_readme()
        if gen_mkdocs:
            self._generate_mkdocs()
        LOG.info("✨Project standardization completed")

    def _generate_docstring(self) -> None:
        """自动为项目中的所有模块生成文档字符串。"""
        LOG.info("😊 Automatically generating doctring...")
        for _, module in self.module_dict.items():
            if "children" in module:
                self.docstring_manager.traverse(module["obj"])
            else:
                self.docstring_manager.modify_docstring(module["obj"])
        LOG.info("✅ Doctring generation completed...")

    def _register_tools(self):
        """注册工具函数，包括获取模块文档和写入文档功能。"""
        if self.tool_registered:
            return

        @fc_register("tool")
        def get_module_doc(module_name: str) -> str:
            """
            Get module's docstring by module name.
            Args:
                module_name (str): Complete module name, from top-level to bottom-level,
                                separated by dots (.), e.g. "a.b.c".
            Returns:
                str: Module's docstring
            """
            LOG.info(f"module_name: {module_name}")
            if module_name not in self.module_doc_dict:
                return f"Module {module_name} does not exist"
            return self.module_doc_dict[module_name][:2000]

        @fc_register("tool")
        def write_doc(path: str, content: str) -> str:
            """
            Write given content to file at specified path.
            Args:
                path (str): Target file's relative path (based on project root).
                content (str): Text content to write.
            Returns:
                str: Returns 'success' if successful, error message if failed.
            """
            LOG.info(f"write_doc: {path}")
            try:
                path = os.path.join(self.project_path, path.strip("/"))
                if not os.path.exists(os.path.dirname(path)):
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                LOG.info(f"write_doc {path} success")
                return "success"
            except Exception as e:
                LOG.info(f"write_doc {path} error {e}")
                return f"Error writing file: {str(e)}"

        self.tool_registered = True

    def _generate_mkdocs(self):
        """生成MkDocs文档网站。
        
        处理双语文档生成和配置文件更新。"""
        LOG.info("😊 Generating mkdocs...")
        self._register_tools()
        agent = ReactAgent(llm=self.llm, tools=["get_module_doc", "write_doc"], max_retries=20)
        project_structure = self._generate_project_tree(
            module_list=self.module_doc_dict.keys()
        )
        language = "en" if self.language == "en" else "zh"
        query = MKDOCS_PROMPT.format(
            project_structure=project_structure,
            mkdocs_config=generate_mkdocs_config(
                site_name=os.path.basename(self.project_path),
                docs_dir=f"docs/{language}",
            ),
            language=language,
            language_type="英文" if self.language == "en" else "中文",
            docs_dir="zh",
        )
        LOG.info(agent(query))
        try:
            if self.language == "bilingual":
                docs_dir_zh = os.path.join(self.project_path, "docs", "zh")
                docs_dir_en = os.path.join(self.project_path, "docs", "en")
                self._translate_docs(docs_dir_zh, docs_dir_en)
                if not os.path.exists(os.path.join(self.project_path, "mkdocs.yml")):
                    return
                with open(os.path.join(self.project_path, "mkdocs.yml"), "r", encoding="utf-8") as file:
                    config = yaml.safe_load(file)
                config["docs_dir"] = "docs"
                config["plugins"] = PLUGIN_CONFIG
                with open(
                    os.path.join(self.project_path, "mkdocs.yml"), "w", encoding="utf-8"
                ) as file:
                    yaml.dump(config, file, allow_unicode=True, sort_keys=False)
        except Exception as e:
            LOG.info(f" ❗ (Error during generating mkdocs {e}")
        LOG.info("✅ mkdocs generation completed...")

    def start_mkdocs_server(self, port=8333) -> None:
        """启动MkDocs本地服务器。
        
        Args:
            port (int): 服务器端口号，默认为8333。
        
        异常:
            ValueError: 当文档目录或配置文件不存在时抛出。"""
        docs_dir_base = os.path.join(self.project_path, "docs")
        if not os.path.exists(docs_dir_base) or not os.path.exists(os.path.join(self.project_path, "mkdocs.yml")):
            raise ValueError("Documentation directory or mkdocs.yml file does not exist, \
                    please generate automatically or manually first.")

        current_dir = os.getcwd()
        try:
            import subprocess
            import atexit

            os.chdir(self.project_path)
            LOG.info("✅ Documentation generation completed, starting mkdocs service")
            mkdocs_process = subprocess.Popen(
                [
                    "mkdocs",
                    "serve",
                    "-f",
                    os.path.join(docs_dir_base, "mkdocs.yml"),
                    "-a",
                    f"0.0.0.0:{port}",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            def cleanup():
                mkdocs_process.terminate()
                mkdocs_process.wait()

            atexit.register(cleanup)
            LOG.info(f"mkdocs 服务器已启动，请访问 http://localhost:{port}")
            time.sleep(600)
        except Exception as e:
            LOG.info(f"启动 mkdocs 服务器时出错: {str(e)}")
        finally:
            os.chdir(current_dir)

    def _generate_project_tree(self, module_list: list) -> str:
        """生成项目结构树。
        
        Args:
            module_list (list): 模块路径列表。
        
        Returns:
            str: 格式化后的项目结构树字符串。"""
        tree_dict = {}
        for module_path in module_list:
            parts = module_path.split(".")
            current = tree_dict
            for i, part in enumerate(parts):
                if part not in current:
                    current[part] = {}
                current = current[part]

        def process_tree_dict(tree_dict, level=0):
            """将字典结构的树形数据转换为带缩进的列表形式表示。
    
            Args:
                tree_dict (dict): 树形结构的字典，键为节点名称，值为子节点字典
                level (int): 当前节点的层级，用于控制缩进量，默认为0
            
            Returns:
                list: 包含格式化后树形结构的字符串列表，每个元素代表一个节点行"""
            tree = []
            indent = "  " * level
            for name, children in sorted(tree_dict.items()):
                if children:
                    tree.append(f"{indent}- {name}/")
                    tree.extend(process_tree_dict(children, level + 1))
                else:
                    tree.append(f"{indent}- {name}")
            return tree

        tree = process_tree_dict(tree_dict)
        return "\n".join(tree)

    def _generate_readme(self) -> None:
        """生成项目README.md文件。"""
        LOG.info("😊 Generating README.md...")
        readme_path = os.path.join(self.project_path, "README.md")
        if os.path.exists(readme_path):
            LOG.info("✅ README.md already exists, skipping generation")
            return

        project_structure = self._generate_project_tree(self.module_doc_dict.keys())
        self._register_tools()
        prompt = README_PROMPT.format(
            project_structure=json.dumps(
                project_structure, indent=2, ensure_ascii=False
            ),
            language="中文" if self.language == "zh" else "英文",
        )
        agent = ReactAgent(llm=self.llm, tools=["get_module_doc"], max_retries=20)
        readme_content = agent(prompt)
        readme_content = re.sub(
            r"^<think>.*?</think>\s*",
            "",
            readme_content,
            flags=re.MULTILINE | re.DOTALL,
        )

        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_content)
        LOG.info("✅ README.md generation completed")

    def _generate_gitignore(self) -> None:
        """生成.gitignore文件。"""
        LOG.info("😊 Generating .gitignore...")
        gitignore_path = os.path.join(self.project_path, ".gitignore")
        if os.path.exists(gitignore_path):
            LOG.info("✅ .gitignore already exists, skipping generation")
            return

        project_info = self._analyze_project_type()

        prompt = GITIGNORE_PROMPT.format(
            project_info=json.dumps(project_info, indent=2, ensure_ascii=False)
        )
        gitignore_content = self.llm(prompt)

        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write(gitignore_content)
        LOG.info("✅ .gitignore generation completed")

    def _generate_module_doc_dict(self, module_dict):
        """构建模块文档字典。
        
        Args:
            module_dict: 模块信息字典。"""
        def add_doc(name: str, subname: str, doc: str, level: str = "#"):
            """为模块或类添加文档字符串到文档字典中。
    
            Args:
                name (str): 模块或类名称，作为字典的键
                subname (str): 文档子标题名称
                doc (str): 要添加的文档字符串内容
                level (str): 标题级别标记，默认为"#"（一级标题）"""
            if name not in self.module_doc_dict:
                self.module_doc_dict[name] = ""
            self.module_doc_dict[name] += f"{level} {subname}:\n{doc or ''}\n\n"

        for name, info in module_dict.items():
            if doc := info.get("doc"):
                add_doc(name, name, doc)
            if "module" in info:
                for module_name, module_info in info["module"].items():
                    add_doc(module_name, module_name, module_info.get("doc", ""))
                    for obj_name, obj_info in module_info.items():
                        obj_name = obj_name.split(".")[-1]
                        if isinstance(obj_info, dict):
                            add_doc(
                                module_name, obj_name, obj_info.get("doc", ""), "##"
                            )
                            if "method" in obj_info:
                                for func_name, func_info in obj_info["method"].items():
                                    method_name = (
                                        f"{obj_name}.{func_name.split('.')[-1]}"
                                    )
                                    add_doc(
                                        module_name,
                                        method_name,
                                        func_info.get("doc", ""),
                                        "###",
                                    )

            if "children" in info:
                self._generate_module_doc_dict(info["children"])

    def _generate_requirements(self) -> None:
        """生成requirements.txt文件。"""
        req_path = os.path.join(self.project_path, "requirements.txt")
        if os.path.exists(req_path):
            LOG.info("✅ requirements.txt already exists, skipping generation")
            return
        LOG.info("😊 Generating requirements.txt...")
        dependencies = self._analyze_dependencies()
        project_modules = self.module_dict.keys()
        for dep in dependencies:
            if any(dep.startswith(mod) for mod in project_modules):
                dependencies.remove(dep)
        with open(req_path, "w", encoding="utf-8") as f:
            f.write("\n".join(dependencies))
        LOG.info("✅ requirements.txt generation completed")

    def _update_module_dict(self):
        """更新模块字典，重新加载项目模块。"""
        project_modules = self.module_dict.keys()
        modules_to_del = []
        for name in sys.modules:
            if any(name.startswith(mod) for mod in project_modules):
                modules_to_del.append(name)
        for module in modules_to_del:
            del sys.modules[module]
        self._gen_module_dict()

    def _gen_module_dict(self):
        """分析项目结构并生成模块字典。"""
        LOG.info("😊 Analyzing project structure...")
        processed_packages = set()
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs
                       if not d.startswith(".") and d not in ["__pycache__", "tests", "docs"]]

            if "__init__.py" in files:
                rel_path = os.path.relpath(root, self.project_path)
                module_name = rel_path.replace(os.sep, ".")
                try:
                    module = importlib.import_module(module_name)
                    skip_modules = ["docs", "test", "tests"]
                    if ".".join(module_name.split(".")[:-1]) in processed_packages:
                        continue
                    self.module_dict |= self._process_package(module, skip_modules)
                    processed_packages.add(module_name)
                except Exception as e:
                    LOG.info(f"Processing module {module_name} error: {str(e)}")

            for file in files:
                if file.endswith(".py") and file not in {"__init__.py", "setup.py",
                                                         "conftest.py", "wsgi.py", "asgi.py"}:
                    rel_dir = os.path.relpath(root, self.project_path)
                    package_name = rel_dir.replace(os.sep, ".")
                    if package_name in processed_packages:
                        continue
                    module_path = os.path.join(root, file)
                    module_name = os.path.splitext(file)[0]
                    try:
                        spec = importlib.util.spec_from_file_location(module_name, module_path)
                        module = importlib.util.module_from_spec(spec)
                        self.module_dict |= self._process_module(module)

                    except Exception as e:
                        LOG.info(f"Error processing module {module_name}: {str(e)}")
        self._generate_module_doc_dict(self.module_dict)
        LOG.info("✅ Project structure analysis completed...")

    def _process_module(self, module, f_module_name: str = "") -> Dict:
        """处理单个模块，提取类和函数信息。
        
        Args:
            module: 要处理的模块对象。
            f_module_name: 模块完整名称前缀。
        
        Returns:
            Dict: 包含模块信息的字典。"""
        def _get_abs_name(obj_name):
            return f"{f_module_name}.{obj_name}".lstrip('.')
        m_dict = {"obj": module}
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if not getattr(obj, "__module__", "").startswith(module.__name__):
                continue
            c_dict = {"doc": obj.__doc__, "obj": obj, "method": {}}
            for method_name, method_obj in inspect.getmembers(obj, inspect.isfunction):
                c_dict["method"][_get_abs_name(f"{name}.{method_name}")] = {"doc": method_obj.__doc__,
                                                                            "obj": method_obj}
            m_dict[_get_abs_name(name)] = c_dict
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if not getattr(obj, "__module__", "").startswith(module.__name__):
                continue
            m_dict[f"{f_module_name}.{name}"] = {"doc": obj.__doc__, "obj": obj}
        if not m_dict:
            return {}
        return {module.__name__: m_dict}

    def _process_package(self, module, skip_modules) -> Dict:
        """处理Python包，递归分析子模块。
        
        Args:
            module: 包模块对象。
            skip_modules: 要跳过的模块名前缀列表。
        
        Returns:
            Dict: 包含包信息的字典。"""
        m_dict = {"obj": module, "children": {}, "module": {}}
        processed_module = set()
        for importer, modname, ispkg in pkgutil.walk_packages(module.__path__, module.__name__ + "."):
            if any(modname.startswith(skip_mod) for skip_mod in skip_modules):
                continue
            if ispkg:
                m_dict["children"] |= self._process_package(importer.find_module(modname).load_module(modname),
                                                            skip_modules)
                processed_module.add(modname)
                continue
            try:
                submodule = importlib.import_module(modname)
                if any(modname.startswith(mod) for mod in processed_module):
                    continue
                m_dict["module"] |= self._process_module(submodule, f_module_name=modname)
            except Exception as e:
                LOG.info(f"Skipping {modname} due to import error", e)
        if not m_dict["children"] and not m_dict["module"]:
            return {}
        return {module.__name__: m_dict}

    def _analyze_project_structure(self) -> Dict:
        """分析项目结构。
        
        Returns:
            Dict: 项目结构字典。"""
        def pro_dict(d):
            for name, module in d.items():
                if "obj" in module:
                    del module["obj"]
                if "children" in module:
                    pro_dict(module["children"])
                if "method" in module:
                    pro_dict(module["method"])

        pro_dict(self.module_dict)
        return self.module_dict

    def _analyze_dependencies(self) -> List[str]:
        """分析项目依赖。
        
        Returns:
            List[str]: 依赖包名称列表。"""
        dependencies = set()
        for root, _, files in os.walk(self.project_path):
            for file in files:
                if file.endswith(".py"):
                    with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                        content = f.read()
                        for line in content.split("\n"):
                            if line.startswith(("import ", "from ")):
                                module = line.split()[1].split(".")[0]
                                if not self._is_standard_library(module):
                                    dependencies.add(module)
        return list(dependencies)

    def _analyze_project_type(self) -> Dict:
        """分析项目类型信息。
        
        Returns:
            Dict: 包含项目类型特征信息的字典。"""
        file_extensions = set()
        for root, _, files in os.walk(self.project_path):
            for file in files:
                ext = os.path.splitext(file)[1]
                if ext:
                    file_extensions.add(ext[1:])  # 移除点号

        return {
            "languages": list(file_extensions),
            "has_setup_py": os.path.exists(os.path.join(self.project_path, "setup.py")),
            "has_requirements": os.path.exists(
                os.path.join(self.project_path, "requirements.txt")
            ),
            "has_tests": any(
                d.startswith("test") for d in os.listdir(self.project_path)
            ),
        }

    @staticmethod
    def _is_standard_library(module_name: str) -> bool:
        """检查模块是否属于Python标准库。
        
        Args:
            module_name: 模块名称。
        
        Returns:
            bool: 如果是标准库模块返回True，否则返回False。"""
        return module_name in sys.stdlib_module_names

    def _translate_docs(self, docs_dir_zh: str, docs_dir_en: str) -> None:
        """
        Translate Chinese documents into English documents, keeping the original directory structure.
        """
        os.makedirs(docs_dir_en, exist_ok=True)

        for root, dirs, files in os.walk(docs_dir_zh):
            rel_path = os.path.relpath(root, docs_dir_zh)
            en_dir = os.path.join(docs_dir_en, rel_path)
            os.makedirs(en_dir, exist_ok=True)

            for file in files:
                if not file.endswith(".md"):
                    continue

                zh_file_path = os.path.join(root, file)
                en_file_path = os.path.join(en_dir, file)

                with open(zh_file_path, "r", encoding="utf-8") as f:
                    zh_content = f.read()

                query = TRANSLATE_PROMPT.format(zh_content=zh_content)
                en_content = self.llm(query, enable_thinking=False)

                with open(en_file_path, "w", encoding="utf-8") as f:
                    f.write(en_content)

                LOG.info(
                    f"Translated doc file: {os.path.relpath(zh_file_path, self.project_path)} -> \
                    {os.path.relpath(en_file_path, self.project_path)}"
                )
