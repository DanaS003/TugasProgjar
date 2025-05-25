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

def kirim_perintah(perintah=""):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect(SERVER_ADDRESS)
            sock.sendall(perintah.encode())

            data_diterima = ""
            while True:
                data = sock.recv(BUFFER_SIZE)
                if not data:
                    break
                data_diterima += data.decode()
                if "\r\n\r\n" in data_diterima:
                    break

        return json.loads(data_diterima)
    except Exception as e:
        logging.error(f"[CLIENT ERROR] {e}")
        return {"status": "ERROR", "data": str(e)}

def unggah_file_ke_server(nama_file):
    try:
        with open(nama_file, 'rb') as f:
            isi_encoded = base64.b64encode(f.read()).decode()
        perintah = f"POST {nama_file} {isi_encoded}\r\n\r\n"
        hasil = kirim_perintah(perintah)
        return hasil.get('status') == 'OK'
    except Exception:
        return False

def unduh_file_dari_server(nama_file):
    try:
        perintah = f"GET {nama_file}\r\n\r\n"
        hasil = kirim_perintah(perintah)
        ekstensi = nama_file.split('.')[-1]
        nama_baru = f"{nama_file.split('.')[0]}_{time.time()}.{ekstensi}"

        if hasil.get('status') == 'OK' and 'data_file' in hasil:
            with open(nama_baru, 'wb') as f:
                f.write(base64.b64decode(hasil['data_file']))
            os.remove(nama_baru)  # Hapus file setelah digunakan, opsional
            return True
        return False
    except Exception:
        return False

def ambil_daftar_file():
    try:
        perintah = "LIST\r\n\r\n"
        hasil = kirim_perintah(perintah)
        return hasil.get('status') == 'OK'
    except Exception:
        return False

def client_worker(id_client, operasi="list", ukuran_mb=10):
    nama_file = f"{ukuran_mb}mb.bin"
    try:
        awal = time.time()

        if operasi == "post":
            berhasil = unggah_file_ke_server(nama_file)
        elif operasi == "get":
            berhasil = unduh_file_dari_server(nama_file)
        elif operasi == "list":
            berhasil = ambil_daftar_file()
        else:
            return {"client_id": id_client, "status": False, "duration": 0, "throughput": "-"}

        akhir = time.time()
        durasi = round(akhir - awal, 4)
        throughput = round(ukuran_mb * 1024 * 1024 / durasi, 4) if durasi > 0 and operasi != "list" else "-"

        return {"client_id": id_client, "status": berhasil, "duration": durasi, "throughput": throughput}
    except Exception:
        return {"client_id": id_client, "status": False, "duration": 0, "throughput": "-"}

def uji_stres(operasi, ukuran, jumlah_client):
    hasil_uji = []
    print(f"{'Client':<10} {'Status':<10} {'Duration (s)':<15} {'Throughput (B/s)':<20}")
    print("=" * 60)

    with ThreadPoolExecutor(max_workers=jumlah_client) as executor:
        tugas = [executor.submit(client_worker, i, operasi, ukuran) for i in range(jumlah_client)]
        for future in as_completed(tugas):
            hasil = future.result()
            print(f"Client-{hasil['client_id']:<3}  {str(hasil['status']):<10} {hasil['duration']:<15} {hasil['throughput']:<20}")
            hasil_uji.append(hasil)

    return hasil_uji

def simpan_ke_csv(hasil, operasi, ukuran, jumlah_client, jumlah_server_worker):
    nama_file_csv = 'stress_test_results_multithreading.csv'
    sudah_ada = os.path.isfile(nama_file_csv)

    jumlah_sukses = sum(1 for h in hasil if h['status'])
    jumlah_gagal = len(hasil) - jumlah_sukses

    total_durasi = sum(h['duration'] for h in hasil if h['status'])
    total_throughput = sum(h['throughput'] for h in hasil if h['status'] and h['throughput'] != "-")

    rata_rata_waktu = round(total_durasi / jumlah_sukses, 4) if jumlah_sukses > 0 else "-"
    rata_rata_throughput = round(total_throughput / jumlah_sukses, 4) if jumlah_sukses > 0 and operasi != "list" else "-"

    sukses_server = jumlah_server_worker if jumlah_gagal == 0 else 0
    gagal_server = 0 if sukses_server > 0 else jumlah_server_worker

    with open(nama_file_csv, 'a', newline='') as csvfile:
        kolom = [
            'No', 'Operation', 'Volume', 'Client Workers', 'Server Workers',
            'Average Time (s)', 'Average Throughput (bytes/s)',
            'Success Clients', 'Failed Clients',
            'Success Server Workers', 'Failed Server Workers'
        ]
        penulis = csv.DictWriter(csvfile, fieldnames=kolom)

        if not sudah_ada:
            penulis.writeheader()

        nomor = 1
        if sudah_ada:
            with open(nama_file_csv, 'r') as f:
                jumlah_baris = sum(1 for _ in f) - 1
            nomor = jumlah_baris + 1

        penulis.writerow({
            'No': nomor,
            'Operation': operasi,
            'Volume': ukuran,
            'Client Workers': jumlah_client,
            'Server Workers': jumlah_server_worker,
            'Average Time (s)': rata_rata_waktu,
            'Average Throughput (bytes/s)': rata_rata_throughput,
            'Success Clients': jumlah_sukses,
            'Failed Clients': jumlah_gagal,
            'Success Server Workers': sukses_server,
            'Failed Server Workers': gagal_server
        })

if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as kontrol_socket:
        kontrol_socket.connect((SERVER_ADDRESS[0], CONTROL_PORT))
        data = kontrol_socket.recv(1024)
        jumlah_server_worker = int.from_bytes(data, byteorder='big')

    mode = input("Pilih mode: [1] Semua kombinasi [2] Input manual: ")

    if mode == '1':
        daftar_operasi = ["list", "get", "post"]
        ukuran_file = [10, 50, 100]
        jumlah_klien = [1, 5, 50]

        for op in daftar_operasi:
            for size in ukuran_file:
                if op == "get":
                    for f in glob.glob(f"{size}mb_*.bin"):
                        os.remove(f)
                for jml_client in jumlah_klien:
                    print(f"\nRunning test: Operation={op}, File={size}mb.bin, Clients={jml_client}, Server={jumlah_server_worker}")
                    hasil = uji_stres(op, size, jml_client)
                    simpan_ke_csv(hasil, op, size, jml_client, jumlah_server_worker)

    elif mode == '2':
        op = input("Operation (list/get/post): ").strip()
        size = int(input("File size (MB): "))
        jml_client = int(input("Jumlah client: "))
        print(f"\nRunning test: Operation={op}, File={size}mb.bin, Clients={jml_client}, Server={jumlah_server_worker}")
        hasil = uji_stres(op, size, jml_client)
        simpan_ke_csv(hasil, op, size, jml_client, jumlah_server_worker)
