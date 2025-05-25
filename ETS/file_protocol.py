import json
import logging
from file_interface import FileInterface

class FileProtocol:
    def __init__(self, worker_status=None):
        self.file = FileInterface()
        self.worker_status = worker_status

    def process_string(self, incoming_data=''):
        command_parts = incoming_data.strip().split(' ')
        try:
            command_request = command_parts[0].strip().lower()
            params = [x for x in command_parts[1:]]

            if command_request == "status":
                return json.dumps({
                    "status": "OK",
                    "success_worker": self.worker_status.get("success", 0) if self.worker_status else 0,
                    "fail_worker": self.worker_status.get("fail", 0) if self.worker_status else 0
                })

            method = getattr(self.file, command_request)
            return json.dumps(method(params))
        except Exception:
            return json.dumps({'status': 'ERROR', 'data': 'Request not recognized'})
