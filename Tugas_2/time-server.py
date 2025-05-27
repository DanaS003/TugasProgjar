import socket
import threading
from datetime import datetime
import pytz

# Thread handler untuk tiap koneksi klien
class ClientHandler(threading.Thread):
    def __init__(self, client_sock, client_addr):
        super().__init__()
        self.sock = client_sock
        self.addr = client_addr

    def run(self):
        print(f"Client connected: {self.addr}")
        try:
            while True:
                received = self.sock.recv(1024).decode('utf-8').strip()
                if not received:
                    break

                print(f"Command from {self.addr}: '{received}'")

                if received == "TIME1310":
                    now = datetime.now(pytz.timezone('Asia/Jakarta')).strftime("%H:%M:%S")
                    reply = f"JAM {now} 1310\r\n"
                    self.sock.sendall(reply.encode('utf-8'))
                elif received == "QUIT1310":
                    self.sock.sendall("Closing connection...\r\n".encode('utf-8'))
                    break
                else:
                    self.sock.sendall("Invalid command\r\n".encode('utf-8'))
        finally:
            self.sock.close()
            print(f"Client disconnected: {self.addr}")

# Server utama
class TimeServer(threading.Thread):
    def __init__(self, host='0.0.0.0', port=45000):
        super().__init__()
        self.host = host
        self.port = port
        self.connections = []
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def run(self):
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"TimeServer running on {self.host}:{self.port}")
        
        while True:
            client_socket, client_address = self.server_socket.accept()
            client_thread = ClientHandler(client_socket, client_address)
            client_thread.start()
            self.connections.append(client_thread)

def start_server():
    server_thread = TimeServer()
    server_thread.start()

if __name__ == "__main__":
    start_server()
