import socket
import json
import base64
import logging

MAX_PACKET = 1024 * 1024


def exec_command(request: str, address: tuple) -> dict | None:
    """
    Kirim perintah ke server dan terima respons JSON.
    """
    try:
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection.connect(address)
        connection.sendall(request.encode())

        buffer = ""
        while True:
            chunk = connection.recv(MAX_PACKET)
            if not chunk:
                break
            buffer += chunk.decode()
            if "\r\n\r\n" in buffer:
                break

        connection.close()
        return json.loads(buffer)
    except Exception as e:
        logging.error(f"Execution error: {e}")
        return None


def list_remote(address: tuple) -> None:
    resp = exec_command("LIST\r\n\r\n", address)
    if resp and resp.get('status') == 'OK':
        print("Daftar berkas dari server:")
        for name in resp['data']:
            print(f"- {name}")
    else:
        print("Gagal mengambil daftar berkas.")


def download_remote(filename: str, address: tuple) -> None:
    resp = exec_command(f"GET {filename}\r\n\r\n", address)
    if resp and resp.get('status') == 'OK':
        encoded = resp['data_file']
        local_name = resp.get('data_namafile', filename)
        with open(local_name, 'wb') as out:
            out.write(base64.b64decode(encoded))
        print(f"Berkas '{filename}' berhasil diunduh sebagai '{local_name}'.")
    else:
        print(f"Gagal mengunduh '{filename}'.")


def upload_remote(path: str, address: tuple) -> None:
    try:
        with open(path, 'rb') as file:
            data_b64 = base64.b64encode(file.read()).decode()
        resp = exec_command(f"POST {path} {data_b64}\r\n\r\n", address)
        if resp and resp.get('status') == 'OK':
            print(f"File '{path}' berhasil diunggah.")
        else:
            print(f"Gagal mengunggah '{path}'.")
    except FileNotFoundError:
        print(f"File '{path}' tidak ditemukan.")


def main() -> None:
    host = input("Server host (default: localhost): ").strip() or 'localhost'
    port_input = input("Server port (default: 6666): ").strip()
    port_num = int(port_input) if port_input.isdigit() else 6666
    endpoint = (host, port_num)

    active = True
    while active:
        print("\nOperasi:")
        print("1. Tampilkan daftar berkas")
        print("2. Unduh berkas")
        print("3. Unggah berkas")
        print("4. Keluar")
        choice = input("Pilih [1-4]: ").strip()

        if choice == '1':
            list_remote(endpoint)
        elif choice == '2':
            fname = input("Nama berkas untuk diunduh: ").strip()
            if fname:
                download_remote(fname, endpoint)
        elif choice == '3':
            fname = input("Nama berkas untuk diunggah: ").strip()
            if fname:
                upload_remote(fname, endpoint)
        elif choice == '4':
            active = False
        else:
            print("Pilihan tidak valid.")


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    main()