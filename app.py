"""入口文件"""

from dotenv import load_dotenv

load_dotenv()
import os
from swchatbot.rag import CacheRetriever
from swchatbot.config import Config
from zhipuai import ZhipuAI
import gradio as gr

zhipuai_key = os.getenv("zhipuai_key")


def chat(prompt, model):
    if model == "zhipuai":
        try:
            client = ZhipuAI(api_key=zhipuai_key)
        except Exception as e:
            print(str(e))
            print("运行`pip install zhipuai`并且检查你的 api_key 设置")
            return ""
        completion = client.chat.completions.create(
            model="glm-4-flash",
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return completion.choices[0].message.content
    # TODO 添加其他模型配置


cache = CacheRetriever()
retriever = cache.get(work_dir=Config.work_dir)

system_prompt = "问题：“{}” \n 材料：“{}”\n  "


def chatbot_interface(question):
    chunk, db_context, references = retriever.query(question)
    input_prompt = system_prompt.format(question, db_context)
    result = chat(input_prompt, "zhipuai")
    print(result)
    return result


if __name__ == "__main__":
    interface = gr.Interface(
        fn=chatbot_interface,
        inputs=gr.Textbox(lines=2, label="input", placeholder="请输入你的问题..."),
        outputs="text",
        title="🤓SwanDoc-Chat",
        description="chat with SwanLab Docs",
        examples=["怎么使用 swanlab 记录实验？", "swanlab 是什么?"],
    )
    interface.launch()
