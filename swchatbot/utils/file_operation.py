# Copyright (c) OpenMMLab. All rights reserved.
import os
import textract
from langchain_community.document_loaders import (CSVLoader, PyPDFLoader,
                                                  UnstructuredExcelLoader)
from loguru import logger

class FileOperationTool:

    def __init__(self):
        self.image_suffix = ['.jpg', '.jpeg', '.png', '.bmp']
        self.md_suffix = '.md'
        self.text_suffix = ['.txt', '.text']
        self.excel_suffix = ['.xlsx', '.xls', '.csv']
        self.pdf_suffix = '.pdf'
        self.word_suffix = ['.docx', '.doc']
        self.normal_suffix = [self.md_suffix
                              ] + self.text_suffix + self.excel_suffix + [
                                  self.pdf_suffix
                              ] + self.word_suffix

    def get_type(self, filepath: str):
        if filepath.endswith(self.pdf_suffix):
            return 'pdf'

        if filepath.endswith(self.md_suffix):
            return 'md'

        for suffix in self.image_suffix:
            if filepath.endswith(suffix):
                return 'image'

        for suffix in self.text_suffix:
            if filepath.endswith(suffix):
                return 'text'

        for suffix in self.word_suffix:
            if filepath.endswith(suffix):
                return 'word'

        for suffix in self.excel_suffix:
            if filepath.endswith(suffix):
                return 'excel'
        return None

    def scan_dir(self, repo_dir: str):
        filepaths = []
        for root, _, files in os.walk(repo_dir):
            for file in files:
                if self.get_type(file) is not None:
                    filepaths.append(os.path.join(root, file))
        return filepaths

    def read(self, filepath: str):
        file_type = self.get_type(filepath)

        text = ''
        if file_type == 'md' or file_type == 'text':
            with open(filepath) as f:
                text = f.read()

        elif file_type == 'pdf':
            documents = PyPDFLoader(filepath).load()
            for document in documents:
                text += document.page_content

        elif file_type == 'excel':
            if filepath.endswith('.csv'):
                documents = CSVLoader(file_path=filepath).load()
            else:
                documents = UnstructuredExcelLoader(filepath,
                                                    mode='elements').load()

            for document in documents:
                text += document.page_content

        elif file_type == 'word':
            # https://stackoverflow.com/questions/36001482/read-doc-file-with-python
            # https://textract.readthedocs.io/en/latest/installation.html
            try:
                text = textract.process(filepath).decode('utf8')
            except Exception as e:
                logger.error((filepath, str(e)))
                return '', e
            # print(len(text))

        text = text.replace('\n\n', '\n')
        text = text.replace('\n\n', '\n')
        text = text.replace('\n\n', '\n')
        text = text.replace('  ', ' ')
        text = text.replace('  ', ' ')
        text = text.replace('  ', ' ')
        return text, None


if __name__ == '__main__':
    opr = FileOperationTool()
    print(opr.read('/Users/little1d/Desktop/Code/SwanDoc-Chat/repodir/zh/api/api-index.md'))
