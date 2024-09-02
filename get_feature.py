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
from langchain.vectorstores.faiss import FAISS as Vectorstore
from langchain_core.documents import Document
from loguru import logger

from swchatbot.utils.file_operation import FileOperationTool
from swchatbot.rag import CacheRetriever
from swchatbot.config import Config

class FeatureStore:
    def __init__(self,
                 embeddings: HuggingFaceEmbeddings,
                 reranker: BCERerank,
                 language: str='zh') -> None:
        self.language = language
        logger.debug('loading text2vec model...')
        self.embeddings = embeddings
        self.reranker = reranker
        self.compression_retriever = None
        self.rejecter = None
        self.retriever = None
        self.md_splitter = MarkdownTextSplitter(chunk_size=768,
                                                chunk_overlap=32)
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=768,
                                                            chunk_overlap=32)
        self.head_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[
            ('#', 'Header 1'),
            ('##', 'Header 2'),
            ('###', 'Header 3'),
        ])
        self.enable_multimodal = False

    # 分块策略
    def _split_md(self ,text: str, source: None):
        docs = self.head_splitter.split_text(text)

        final = []
        for doc in docs:
            header = ''
            if len(doc.metadata) > 0:
                if 'Header 1' in doc.metadata:
                    header += doc.metadata['Header 1']
                if 'Header 2' in doc.metadata:
                    header += ' '
                    header += doc.metadata['Header 2']
                if 'Header 3' in doc.metadata:
                    header += ' '
                    header += doc.metadata['Header 3']
            if len(doc.page_content) >= 1024:
                subdocs = self.md_splitter.create_documents([doc.page_content])
                for subdoc in subdocs:
                    if len(subdoc.page_content) >= 10:
                        final.append('{} {}'.format(
                            header, subdoc.page_content.lower()))
            elif len(doc.page_content) >= 10:
                final.append('{} {}'.format(
                    header, doc.page_content.lower()))

        for item in final:
            if len(item) >= 1024:
                logger.debug('source {} split length {}'.format(
                    source, len(item)))
        return final


    # 清洗markdown文档，移除不包含关键问题因素
    def _clean_md(self, text: str):
        """Remove parts of the markdown document that do not contain the key
        question words, such as code blocks, URL links, etc."""
        # remove ref
        pattern_ref = r'\[(.*?)\]\(.*?\)'
        new_text = re.sub(pattern_ref, r'\1', text)

        # remove code block
        pattern_code = r'```.*?```'
        new_text = re.sub(pattern_code, '', new_text, flags=re.DOTALL)

        # remove underline
        new_text = re.sub('_{5,}', '', new_text)

        # remove table
        # new_text = re.sub('\|.*?\|\n\| *\:.*\: *\|.*\n(\|.*\|.*\n)*', '', new_text, flags=re.DOTALL)   # noqa E501

        # use lower
        new_text = new_text.lower()
        return new_text

    # 读取markdown文档，分块，提取特征
    def get_md_documents(self, filepath):
        documents = []
        length = 0
        text = ''
        with open(filepath, encoding='utf8') as f:
            text = f.read()
        text = os.path.basename(filepath) + '\n' + self._clean_md(text)
        if len(text) <= 1:
            return [], length

        chunks = self._split_md(text=text, source=os.path.abspath(filepath))
        for chunk in chunks:
            new_doc = Document(page_content=chunk,
                               metadata={'source': os.path.abspath(filepath)})
            length += len(chunk)
            documents.append(new_doc)
        return documents, length

    # 读取文档
    def _get_text_documents(self, text: str, filepath: str):
        if len(text) <= 1:
            return []
        chunks = self.text_splitter.create_documents([text])
        documents = []
        for chunk in chunks:
            chunk.metadata = {'source': filepath}
            documents.append(chunk)
        return documents

    # 特征提取
    def _extract_features(self, file_dir: str, work_dir: str):
        """Extract the features required for the response pipeline based on the
        document."""
        feature_dir = os.path.join(work_dir, 'db_response')
        if not os.path.exists(feature_dir):
            os.makedirs(feature_dir)

        files = [str(x) for x in list(Path(file_dir).glob('*'))]
        # logger.info('glob {} in dir {}'.format(files, file_dir))
        file_opr = FileOperationTool()
        documents = []
        state_map = {}

        for i, file in enumerate(files):
            basename = os.path.basename(file)
            if basename.endswith('.text'):
                basename = '.text'.join(basename.split('.text')[0:-1])

            logger.debug('{}/{}.. {}'.format(i + 1, len(files), basename))
            file_type = file_opr.get_type(file)

            if file_type == 'md':
                md_documents, md_length = self.get_md_documents(file)
                documents += md_documents
                state_map[basename] = {'status': True, 'desc': md_length}
            else:
                text, error = file_opr.read(file)
                if error is not None:
                    state_map[basename] = {
                        'status': False,
                        'desc': 'read fail'
                    }
                    continue
                state_map[basename] = {'status': True, 'desc': str(len(text))}
                logger.info('{} content length {}'.format(file, len(text)))
                text = basename + text
                documents += self._get_text_documents(text, file)

        vs = Vectorstore.from_documents(documents, self.embeddings)
        vs.save_local(feature_dir)
        return state_map

    # 预处理，生成文件目录，文件状态映射
    def _files_preprocess(self, filepaths: list, work_dir: str):
        file_dir = os.path.join(work_dir, 'preprocess')
        if os.path.exists(file_dir):
            logger.warning(
                f'{file_dir} already exists, remove and regenerate.')
            shutil.rmtree(file_dir)
        os.makedirs(file_dir)

        success_count = 0
        fail_count = 0
        skip_count = 0

        file_opr = FileOperationTool()
        # 存储正常文件
        normals = []
        # 存储文件状态映射
        state_map = {}

        for filepath in filepaths:
            _type = file_opr.get_type(filepath)
            if _type in ['pdf', 'md', 'text', 'word', 'excel']:
                normals.append(filepath)
            else:
                skip_count += 1

        # process normal file (pdf, text)
        for filepath in normals:
            filename = filepath.replace('/','_')
            try:
                shutil.copy(filepath, os.path.join(file_dir, filename))
                success_count += 1
            except Exception as e:
                fail_count += 1
                logger.error(str(e))
                state_map[filename] = {'status': False, 'desc': 'IO error'}

        logger.debug(
            f'preprocess input {len(filepaths)} files, {success_count} success, {fail_count} fail, {skip_count} skip. '
        )
        return file_dir, (success_count, fail_count, skip_count), state_map

    # 调用预处理，生成文件状态映射
    def initialize(self, filepaths: list, work_dir: str):
        file_dir, counter, proc_state = self._files_preprocess(filepaths=filepaths,
                                                        work_dir=work_dir)
        success_cnt, _, __ = counter
        ingress_state = {}
        if success_cnt > 0:
            ingress_state = self._extract_features(file_dir=file_dir,
                                                  work_dir=work_dir)

        state_map = {**proc_state, **ingress_state}
        if len(state_map) != len(filepaths):
            for filepath in filepaths:
                basename = os.path.basename(filepath)
                if basename not in state_map:
                    logger.warning(f'{filepath} no state')
                    state_map[basename] = {
                        'status': False,
                        'desc': 'internal error'
                    }
        return counter, state_map


# 模型加载+特征提取测试
if __name__ == '__main__':
    cache = CacheRetriever()
    fs_init = FeatureStore(embeddings=cache.embeddings,
                           reranker=cache.reranker)

    # walk all files in repo dir
    file_opr = FileOperationTool()
    filepaths = file_opr.scan_dir(repo_dir=Config.repo_dir)
    print(f'found {len(filepaths)} files in {Config.repo_dir}')
    # get feature
    counter, state_map = fs_init.initialize(filepaths=filepaths,
                                            work_dir=Config.work_dir)
    logger.info(f'init state: success, fail, skip: {counter}')
    for k, v in state_map.items():
        logger.info('{} {}'.format(k, v['desc']))
    del fs_init
