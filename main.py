"""入口文件"""
from platform import system

from dotenv import load_dotenv
load_dotenv()
import openai
import os
from swchatbot.rag import CacheRetriever
from swchatbot.config import Config
from zhipuai import ZhipuAI

zhipuai_key = os.getenv("zhipuai_key")

def chat(prompt, model):
    if model == 'zhipuai':
        try:
            client = ZhipuAI(api_key=zhipuai_key)
        except Exception as e:
            print(str(e))
            print('运行`pip install zhipuai`并且检查你的 api_key 设置')
            return ''
        completion = client.chat.completions.create(
            model = 'glm-4-flash',
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return  completion.choices[0].message.content
    # TODO 添加其他模型配置

cache = CacheRetriever()
retriever = cache.get(work_dir=Config.work_dir)

system_prompt = '问题：“{}” \n 材料：“{}”\n  '

if __name__ ==  '__main__':
    question = '怎么在代码中使用swanlab api记录实验？'
    chunk, db_context, references = retriever.query(question)
    input_prompt = system_prompt.format(question,db_context)
    result = chat(input_prompt, "zhipuai")
    print(result)