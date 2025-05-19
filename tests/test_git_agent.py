import sys

sys.path.append('.')
sys.path.append('./lazyproject')

from lazyllm import OnlineChatModule
from lazynote.agent.git_agent import GitAgent

agent = GitAgent(project_path="", 
                 llm=OnlineChatModule(source='deepseek', stream=False),
                 language='zh',  # 'en' 'bilingual'
                 )
agent.standardize_project(gen_docstrings=True)
agent.start_mkdocs_server()
