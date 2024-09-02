"""extract feature and search with user query"""
import os
import re
import shutil
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from BCEmbedding.tools.langchain import BCERerank
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.text_splitter import (MarkdownTextSplitter,
                                     MarkdownHeaderTextSplitter,
                                     RecursiveCharacterTextSplitter)
from langchain.vectorstores.faiss import FAISS as VectorStore
from langchain_core.documents import Document
from loguru import logger

from swchatbot.utils.file_operation import FileOperationTool
from swchatbot.rag import CacheRetriever
