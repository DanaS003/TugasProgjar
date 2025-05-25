import socket
import json
import base64
import time
import logging
import csv
import os
import glob
from concurrent.futures import ThreadPoolExecutor, as_completed

SERVER_ADDRESS = ('172.16.16.101', 6667)
CONTROL_PORT = 6668
BUFFER_SIZE = 1024 * 1024

def send_command(command_str=""):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(SERVER_ADDRESS)
        s.sendall(command_str.encode())
        received = ""
        while True:
            data = s.recv(BUFFER_SIZE)
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

def remote_post(filename):
    try:
        with open(filename, 'rb') as f:
            encoded = base64.b64encode(f.read()).decode()
        command = f"POST {filename} {encoded}\r\n\r\n"
        result = send_command(command)
        return result.get('status') == 'OK'
    except Exception:
        return False

def remote_get(filename):
    try:
        command = f"GET {filename}\r\n\r\n"
        result = send_command(command)
        ext = filename.split('.')[-1]
        new_filename = filename.split('.')[0] + "_" + str(time.time()) + '.' + ext
        if result.get('status') == 'OK' and 'data_file' in result:
            with open(new_filename, 'wb') as f:
                f.write(base64.b64decode(result['data_file']))
            os.remove(new_filename)  # Optional, hapus file setelah download
            return True
        return False
    except Exception:
        return False

def remote_list():
    try:
        command = "LIST\r\n\r\n"
        result = send_command(command)
        return result.get('status') == 'OK'
    except Exception:
        return False

def worker(client_id, operation="list", size_mb=10):
    filename = f"{size_mb}mb.bin"
    try:
        start = time.time()
        if operation == "post":
            success = remote_post(filename)
        elif operation == "get":
            success = remote_get(filename)
        elif operation == "list":
            success = remote_list()
        else:
            return {"client_id": client_id, "status": False, "duration": 0, "throughput": "-"}

        end = time.time()
        duration = round(end - start, 4)
        throughput = round(int(size_mb * 1024 * 1024 / duration), 4) if duration > 0 and operation != 'list' else "-"
        return {"client_id": client_id, "status": success, "duration": duration, "throughput": throughput}
    except Exception:
        return {"client_id": client_id, "status": False, "duration": 0, "throughput": "-"}

def stress_test(operation, size_mb, n_clients):
    results = []
    print(f"{'Client':<10} {'Status':<10} {'Duration (s)':<15} {'Throughput (B/s)':<20}")
    print("="*60)
    with ThreadPoolExecutor(max_workers=n_clients) as executor:
        futures = [executor.submit(worker, i, operation, size_mb) for i in range(n_clients)]
        for future in as_completed(futures):
            result = future.result()
            print(f"Client-{result['client_id']:<3}  {str(result['status']):<10} {result['duration']:<15} {result['throughput']:<20}")
            results.append(result)
    return results

def gen_csv(results, operation, size, clients, server_workers):
    summary_file = 'stress_test_results_multithreading.csv'
    file_exists = os.path.isfile(summary_file)

    success = sum(1 for r in results if r['status'])
    fail = len(results) - success

    sum_duration = sum(r['duration'] for r in results if r['status'])
    sum_throughput = sum(r['throughput'] for r in results if r['status'] and r['throughput'] != "-")

    avg_time = round(sum_duration / success, 4) if success > 0 else "-"
    avg_throughput = round(sum_throughput / success, 4) if success > 0 and operation != 'list' else "-"

    # Hitung status server worker berdasarkan hasil client
    if fail == 0:
        success_server = server_workers
        fail_server = 0
    else:
        success_server = 0
        fail_server = server_workers

    with open(summary_file, 'a', newline='') as csvfile:
        fieldnames = [
            'No', 'Operation', 'Volume', 'Client Workers', 'Server Workers',
            'Average Time (s)', 'Average Throughput (bytes/s)',
            'Success Clients', 'Failed Clients',
            'Success Server Workers', 'Failed Server Workers'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        if file_exists:
            with open(summary_file, 'r') as f:
                row_count = sum(1 for _ in f) - 1  # Kurangi header
            no = row_count + 1
        else:
            no = 1

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
            'Success Server Workers': success_server,
            'Failed Server Workers': fail_server
        })

if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)

    # Get server worker count from control port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((SERVER_ADDRESS[0], CONTROL_PORT))
        data = s.recv(1024)
        server_workers = int.from_bytes(data, byteorder='big')

    mode = input("Pilih mode: [1] Semua kombinasi [2] Input manual: ")

    if mode == '1':
        operations = ["list", "get", "post"]
        sizes = [10, 50, 100]
        clients = [1, 5, 50]

        for operation in operations:
            for size in sizes:
                if operation == "get":
                    for file in glob.glob(f"{size}mb_*.bin"):
                        os.remove(file)
                for client_count in clients:
                    print(f"\nRunning test: Operation={operation}, File={size}mb.bin, Clients={client_count}, Server={server_workers}")
                    results = stress_test(operation, size, client_count)
                    gen_csv(results, operation, size, client_count, server_workers)

    elif mode == '2':
        operation = input("Operation (list/get/post): ").strip()
        size = int(input("File size (MB): "))
        clients = int(input("Jumlah client: "))
        print(f"\nRunning test: Operation={operation}, File={size}mb.bin, Clients={clients}, Server={server_workers}")
        results = stress_test(operation, size, clients)
        gen_csv(results, operation, size, clients, server_workers)
