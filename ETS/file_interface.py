import os
import json
import base64
from glob import glob

class FileInterface:
    def __init__(self):
        os.chdir('files/')

    def list(self, params=[]):
        try:
            file_list = glob('*.*')
            return {'status': 'OK', 'data': file_list}
        except Exception as e:
            return {'status': 'ERROR', 'data': str(e)}

    def get(self, params=[]):
        try:
            filename = params[0]
            if filename == '':
                return None
            with open(f"{filename}", 'rb') as f:
                file_data = base64.b64encode(f.read()).decode()
            return {'status': 'OK', 'data_namafile': filename, 'data_file': file_data}
        except Exception as e:
            return {'status': 'ERROR', 'data': str(e)}

    def post(self, params=[]):
        try:
            filename = params[0]
            file_data = params[1]
            decoded = base64.b64decode(file_data.encode())
            with open(filename, 'wb') as f:
                f.write(decoded)
            return {'status': 'OK', 'data_namafile': filename, 'data_file': file_data}
        except Exception as e:
            return {'status': 'ERROR', 'data': str(e)}

    def delete(self, params=[]):
        try:
            filename = params[0]
            os.remove(filename)
            return {'status': 'OK', 'data_filename': filename}
        except Exception as e:
            return {'status': 'ERROR', 'data': str(e)}
