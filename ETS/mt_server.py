import socket
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
# Tambahkan global shared state
from collections import defaultdict
import json

worker_status = defaultdict(int)
worker_lock = threading.Lock()

from file_protocol import FileProtocol
fp = FileProtocol()

SERVER_ADDRESS = ('0.0.0.0', 6667)
BUFFER_SIZE = 1024 * 1024

def process_client_thread(connection, address):
    d = ''
    try:
        while True:
            data = connection.recv(BUFFER_SIZE)
            if data:
                d += data.decode()
                if "\r\n\r\n" in d:
                    cmd = d.strip()
                    if cmd.upper() == "STATUS":
                        with worker_lock:
                            status_resp = {
                                "status": "OK",
                                "success_worker": worker_status.get('success', 0),
                                "fail_worker": worker_status.get('fail', 0)
                            }
                        response = json.dumps(status_resp) + "\r\n\r\n"
                        connection.sendall(response.encode())
                    else:
                        hasil = fp.process_string(cmd)
                        hasil = hasil + "\r\n\r\n"
                        connection.sendall(hasil.encode())
                        with worker_lock:
                            worker_status['success'] += 1
                    break
            else:
                break
    except Exception as e:
        logging.error(f"Error handling client {address}: {e}")
        with worker_lock:
            worker_status['fail'] += 1
    finally:
        connection.close()



class Server:
    def __init__(self, ipaddress='0.0.0.0', port=6667, max_workers=10):
        self.ipinfo = (ipaddress, port)
        self.my_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.max_workers = max_workers
        
    def run(self):
        logging.warning(f"Server berjalan di {self.ipinfo} dengan max_workers={self.max_workers} dalam mode thread")
        self.my_socket.bind(self.ipinfo)
        self.my_socket.listen(10)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            try:
                while True:
                    connection, address = self.my_socket.accept()
                    logging.warning(f"Accepted connection dari {address}")
                    executor.submit(process_client_thread, connection, address)
            except KeyboardInterrupt:
                logging.warning("Server shutting down.")
            finally:
                self.my_socket.close()

def send_server_workers(max_workers):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('0.0.0.0', 6668))
        s.listen()
        while True:
            conn, addr = s.accept()
            with conn:
                logging.warning(f"Sending max_workers to {addr}")
                conn.sendall(max_workers.to_bytes(4, 'big'))

def main():
    logging.basicConfig(level=logging.WARNING)

    try:
        max_workers = int(input("Masukkan jumlah max_workers untuk thread pool: "))
    except ValueError:
        print("Input harus berupa angka.")
        return

    # Jalankan thread untuk kirim max_workers di port 6668
    threading.Thread(target=send_server_workers, args=(max_workers,), daemon=True).start()

    svr = Server(SERVER_ADDRESS[0], SERVER_ADDRESS[1], max_workers=max_workers)
    svr.run()

if __name__ == "__main__":
    main()
