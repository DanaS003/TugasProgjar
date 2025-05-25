import socket
import json
import base64
import time
import logging
import os
import glob
import csv
from concurrent.futures import ProcessPoolExecutor, as_completed

SERVER_IP = "172.16.16.101"
CONTROL_PORT = 6668  # port untuk ambil jumlah worker dari server

def get_server_workers(server_ip):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((server_ip, CONTROL_PORT))
            data = s.recv(1024)
            server_workers = int.from_bytes(data, byteorder='big')
            return server_workers
    except Exception as e:
        logging.error(f"Failed to get server workers: {e}")
        return None

def send_command(command_str="", server_ip=""):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((server_ip, 6667))
        s.sendall(command_str.encode())
        received = ""
        while True:
            data = s.recv(1024 * 1024)
            if not data:
                break
            received += data.decode()
            if "\r\n\r\n" in received:
                break
        s.close()
        return json.loads(received)
    except Exception as e:
        logging.error(f"[CLIENT ERROR] {e}")
        return {"status": "ERROR", "data": str(e)}

def remote_post(filename, server_ip):
    try:
        with open(filename, 'rb') as f:
            encoded = base64.b64encode(f.read()).decode()
        command = f"POST {filename} {encoded}\r\n\r\n"
        result = send_command(command, server_ip)
        return result['status'] == 'OK'
    except Exception:
        return False

def remote_get(filename, server_ip):
    try:
        command = f"GET {filename}\r\n\r\n"
        result = send_command(command, server_ip)
        ext = filename.split('.')[-1]
        new_filename = filename.split('.')[0] + "_" + str(time.time()) + '.' + ext
        if result['status'] == 'OK':
            with open(new_filename, 'wb') as f:
                f.write(base64.b64decode(result['data_file']))
            os.remove(new_filename)
            return True
        return False
    except Exception:
        return False

def remote_list(server_ip):
    try:
        command = "LIST\r\n\r\n"
        result = send_command(command, server_ip)
        return result['status'] == 'OK'
    except Exception:
        return False

def worker(client_id, operation="list", size_mb=10, server_ip=""):
    filename = f"{size_mb}mb.bin"
    try:
        start = time.time()
        if operation == "post":
            success = remote_post(filename, server_ip)
        elif operation == "get":
            success = remote_get(filename, server_ip)
        elif operation == "list":
            success = remote_list(server_ip)
        else:
            return {"client_id": client_id, "status": False, "duration": 0, "throughput": "-"}

        end = time.time()
        duration = round(end - start, 4)
        throughput = round(int(size_mb * 1024 * 1024 / duration), 4) if duration > 0 and operation != 'list' else "-"
        return {"client_id": client_id, "status": success, "duration": duration, "throughput": throughput}
    except Exception:
        # Kalau ada error (misal memory error), tetap return gagal dengan data valid
        return {"client_id": client_id, "status": False, "duration": 0, "throughput": "-"}

def stress_test(operation, size_mb, n_clients, server_ip):
    results = []
    print(f"{'Client':<10} {'Status':<10} {'Duration (s)':<15} {'Throughput (B/s)':<20}")
    print("="*60)
    with ProcessPoolExecutor(max_workers=n_clients) as executor:
        futures = [executor.submit(worker, i, operation, size_mb, server_ip) for i in range(n_clients)]
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as e:
                logging.error(f"Worker exception: {e}")
                result = {"client_id": -1, "status": False, "duration": 0, "throughput": "-"}
            print(f"Client-{result['client_id']:<3}  {str(result['status']):<10} {result['duration']:<15} {result['throughput']:<20}")
            results.append(result)
    return results

def gen_csv(results, operation, size, clients, server_workers):
    summary_file = 'stress_test_results_multiprocess.csv'
    file_exists = os.path.isfile(summary_file)

    with open(summary_file, 'a', newline='') as csvfile:
        fieldnames = [
            'No', 'Operation', 'Volume', 'Client Workers',
            'Server Workers', 'Average Time (s)', 'Average Throughput (bytes/s)',
            'Success Clients', 'Failed Clients',
            'Success Server Workers', 'Failed Server Workers'  # tambah ini
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        sum_duration = 0
        sum_throughput = 0
        success = 0
        fail = 0
        for result in results:
            if result['status']:
                success += 1
                sum_duration += result['duration']
                if operation != 'list':
                    sum_throughput += result['throughput']
            else:
                fail += 1

        avg_time = round(sum_duration / success, 4) if success > 0 else "-"
        avg_throughput = round(sum_throughput / success, 4) if success > 0 and operation != 'list' else "-"

        # Asumsi server worker sukses = client sukses (estimasi)
        server_success = success if success <= server_workers else server_workers
        server_fail = server_workers - server_success if server_workers > 0 else 0

        # Hitung nomor urut baris baru
        no = 1
        if file_exists:
            with open(summary_file, 'r') as f:
                no = sum(1 for _ in f)

        writer.writerow({
            'No': no,
            'Operation': operation,
            'Volume': size,
            'Client Workers': clients,
            'Server Workers': server_workers,
            'Average Time (s)': avg_time,
            'Average Throughput (bytes/s)': avg_throughput,
            'Success Clients': success,
            'Failed Clients': fail,
            'Success Server Workers': server_success,
            'Failed Server Workers': server_fail
        })


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    operations = ["list", "post", "get"]
    sizes = [10, 50, 100]
    clients = [1, 5, 50]

    server_workers = get_server_workers(SERVER_IP)
    if server_workers is None:
        print("Gagal mendapatkan jumlah worker server, menggunakan default 10")
        server_workers = 10

    print("Pilih mode:")
    print("1 - Jalankan semua kombinasi operasi, size, client")
    print("2 - Input operasi, size, dan jumlah client secara manual")
    mode = input("Masukkan pilihan (1/2): ").strip()

    if mode == '1':
        # Jalankan semua kombinasi
        for operation in operations:
            for size in sizes:
                if operation == "get":
                    delete_pattern = f"{size}mb_*.bin"
                    for file in glob.glob(delete_pattern):
                        os.remove(file)
                for client_count in clients:
                    print(f"\nRunning test: Operation={operation}, File={size}mb.bin, Clients={client_count}")
                    results = stress_test(operation, size, client_count, SERVER_IP)
                    gen_csv(results, operation, size, client_count, server_workers)
    elif mode == '2':
        # Input manual
        op = input(f"Masukkan operasi ({'/'.join(operations)}): ").strip().lower()
        while op not in operations:
            print("Operasi tidak valid.")
            op = input(f"Masukkan operasi ({'/'.join(operations)}): ").strip().lower()

        try:
            sz = int(input(f"Masukkan ukuran file (MB) dari {sizes}: ").strip())
            while sz not in sizes:
                print("Ukuran file tidak valid.")
                sz = int(input(f"Masukkan ukuran file (MB) dari {sizes}: ").strip())
        except Exception:
            print("Input ukuran file tidak valid, menggunakan default 10MB")
            sz = 10

        try:
            cl = int(input(f"Masukkan jumlah client dari {clients}: ").strip())
            while cl not in clients:
                print("Jumlah client tidak valid.")
                cl = int(input(f"Masukkan jumlah client dari {clients}: ").strip())
        except Exception:
            print("Input client tidak valid, menggunakan default 1 client")
            cl = 1

        if op == "get":
            delete_pattern = f"{sz}mb_*.bin"
            for file in glob.glob(delete_pattern):
                os.remove(file)

        print(f"\nRunning test: Operation={op}, File={sz}mb.bin, Clients={cl}")
        results = stress_test(op, sz, cl, SERVER_IP)
        gen_csv(results, op, sz, cl, server_workers)
    else:
        print("Pilihan tidak valid, keluar program.")
