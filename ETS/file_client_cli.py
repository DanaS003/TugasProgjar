import socket
import json
import base64
import logging

BUFFER_SIZE = 1024 * 1024

def send_command(command_str, server_addr):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(server_addr)
        sock.sendall(command_str.encode())
        data_received = ""
        while True:
            data = sock.recv(BUFFER_SIZE)
            if not data:
                break
            data_received += data.decode()
            if "\r\n\r\n" in data_received:
                break
        sock.close()
        return json.loads(data_received)
    except Exception as e:
        logging.error(f"Error: {e}")
        return None

def remote_list(server_addr):
    cmd = "LIST\r\n\r\n"
    resp = send_command(cmd, server_addr)
    if resp and resp.get('status') == 'OK':
        print("File list:")
        for f in resp['data']:
            print(f"- {f}")
    else:
        print("Failed to get file list.")

def remote_get(filename, server_addr):
    cmd = f"GET {filename}\r\n\r\n"
    resp = send_command(cmd, server_addr)
    if resp and resp.get('status') == 'OK':
        content_b64 = resp['data_file']
        with open(resp['data_namafile'], 'wb') as f:
            f.write(base64.b64decode(content_b64))
        print(f"File {filename} downloaded successfully.")
    else:
        print(f"Failed to get file {filename}.")

def remote_post(filename, server_addr):
    try:
        with open(filename, 'rb') as f:
            content_b64 = base64.b64encode(f.read()).decode()
        cmd = f"POST {filename} {content_b64}\r\n\r\n"
        resp = send_command(cmd, server_addr)
        if resp and resp.get('status') == 'OK':
            print(f"File {filename} uploaded successfully.")
        else:
            print(f"Failed to upload file {filename}.")
    except FileNotFoundError:
        print(f"File {filename} not found.")

def main():
    server_ip = input("Enter server IP (default localhost): ").strip() or 'localhost'
    port = input("Enter server port (default 6666): ").strip()
    port = int(port) if port.isdigit() else 6666
    server_addr = (server_ip, port)

    while True:
        print("\nChoose operation:")
        print("1. List files")
        print("2. Download file (GET)")
        print("3. Upload file (POST)")
        print("4. Exit")
        choice = input("Select [1-4]: ").strip()

        if choice == '1':
            remote_list(server_addr)
        elif choice == '2':
            fname = input("Enter filename to download: ").strip()
            if fname:
                remote_get(fname, server_addr)
        elif choice == '3':
            fname = input("Enter filename to upload: ").strip()
            if fname:
                remote_post(fname, server_addr)
        elif choice == '4':
            print("Bye!")
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
