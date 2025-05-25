import socket
import json
import base64
import time
import logging
import os
import glob
import csv
from concurrent.futures import ProcessPoolExecutor, as_completed

# Konfigurasi alamat dan port server
SERVER_IP = "172.16.16.101"
PORT_KONTROL = 6668
PORT_OPERASI = 6667

# Mengambil jumlah worker yang tersedia di server
def get_jumlah_worker_server(ip_server):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as soket:
            soket.connect((ip_server, PORT_KONTROL))
            data = soket.recv(1024)
            jumlah = int.from_bytes(data, byteorder='big')
            return jumlah
    except Exception as error:
        logging.error(f"Gagal mengambil jumlah worker server: {error}")
        return None

# Mengirimkan perintah ke server
def kirim_perintah(perintah, ip_server):
    try:
        soket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        soket.connect((ip_server, PORT_OPERASI))
        soket.sendall(perintah.encode())
        data_diterima = ""
        while True:
            data = soket.recv(1024 * 1024)
            if not data:
                break
            data_diterima += data.decode()
            if "\r\n\r\n" in data_diterima:
                break
        soket.close()
        return json.loads(data_diterima)
    except Exception as error:
        logging.error(f"[KESALAHAN CLIENT] {error}")
        return {"status": "ERROR", "data": str(error)}

# Operasi POST (unggah file ke server)
def unggah_file(nama_file, ip_server):
    try:
        with open(nama_file, 'rb') as file:
            encoded_data = base64.b64encode(file.read()).decode()
        perintah = f"POST {nama_file} {encoded_data}\r\n\r\n"
        hasil = kirim_perintah(perintah, ip_server)
        return hasil['status'] == 'OK'
    except Exception:
        return False

# Operasi GET (unduh file dari server)
def unduh_file(nama_file, ip_server):
    try:
        perintah = f"GET {nama_file}\r\n\r\n"
        hasil = kirim_perintah(perintah, ip_server)
        ekstensi = nama_file.split('.')[-1]
        nama_baru = nama_file.split('.')[0] + "_" + str(time.time()) + '.' + ekstensi
        if hasil['status'] == 'OK':
            with open(nama_baru, 'wb') as file:
                file.write(base64.b64decode(hasil['data_file']))
            os.remove(nama_baru)
            return True
        return False
    except Exception:
        return False

# Operasi LIST (lihat daftar file di server)
def lihat_daftar_file(ip_server):
    try:
        perintah = "LIST\r\n\r\n"
        hasil = kirim_perintah(perintah, ip_server)
        return hasil['status'] == 'OK'
    except Exception:
        return False

# Fungsi worker untuk tiap proses klien
def proses_klien(id_klien, jenis_operasi="list", ukuran_file_mb=10, ip_server=""):
    nama_file = f"{ukuran_file_mb}mb.bin"
    try:
        waktu_mulai = time.time()

        if jenis_operasi == "post":
            sukses = unggah_file(nama_file, ip_server)
        elif jenis_operasi == "get":
            sukses = unduh_file(nama_file, ip_server)
        elif jenis_operasi == "list":
            sukses = lihat_daftar_file(ip_server)
        else:
            return {"client_id": id_klien, "status": False, "duration": 0, "throughput": "-"}

        waktu_selesai = time.time()
        durasi = round(waktu_selesai - waktu_mulai, 4)
        throughput = round(int(ukuran_file_mb * 1024 * 1024 / durasi), 4) if durasi > 0 and jenis_operasi != 'list' else "-"

        return {"client_id": id_klien, "status": sukses, "duration": durasi, "throughput": throughput}
    except Exception:
        return {"client_id": id_klien, "status": False, "duration": 0, "throughput": "-"}

# Menjalankan uji stres (stress test)
def jalankan_stress_test(operasi, ukuran_mb, jumlah_klien, ip_server):
    hasil_semua = []
    print(f"{'Client':<10} {'Status':<10} {'Durasi (s)':<15} {'Throughput (B/s)':<20}")
    print("="*60)
    with ProcessPoolExecutor(max_workers=jumlah_klien) as executor:
        tugas = [executor.submit(proses_klien, i, operasi, ukuran_mb, ip_server) for i in range(jumlah_klien)]
        for future in as_completed(tugas):
            try:
                hasil = future.result()
            except Exception as error:
                logging.error(f"Exception dalam worker: {error}")
                hasil = {"client_id": -1, "status": False, "duration": 0, "throughput": "-"}
            print(f"Client-{hasil['client_id']:<3}  {str(hasil['status']):<10} {hasil['duration']:<15} {hasil['throughput']:<20}")
            hasil_semua.append(hasil)
    return hasil_semua

# Menyimpan hasil uji ke file CSV
def simpan_hasil_csv(hasil, operasi, ukuran, klien, worker_server):
    nama_file_ringkasan = 'stress_test_results_multiprocess.csv'
    sudah_ada = os.path.isfile(nama_file_ringkasan)

    with open(nama_file_ringkasan, 'a', newline='') as file_csv:
        nama_kolom = [
            'No', 'Operation', 'Volume', 'Client Workers',
            'Server Workers', 'Average Time (s)', 'Average Throughput (bytes/s)',
            'Success Clients', 'Failed Clients',
            'Success Server Workers', 'Failed Server Workers'
        ]
        penulis = csv.DictWriter(file_csv, fieldnames=nama_kolom)
        if not sudah_ada:
            penulis.writeheader()

        total_durasi = 0
        total_throughput = 0
        sukses = 0
        gagal = 0
        for hasil_klien in hasil:
            if hasil_klien['status']:
                sukses += 1
                total_durasi += hasil_klien['duration']
                if operasi != 'list':
                    total_throughput += hasil_klien['throughput']
            else:
                gagal += 1

        rata_rata_durasi = round(total_durasi / sukses, 4) if sukses > 0 else "-"
        rata_rata_throughput = round(total_throughput / sukses, 4) if sukses > 0 and operasi != 'list' else "-"

        sukses_server = sukses if sukses <= worker_server else worker_server
        gagal_server = worker_server - sukses_server if worker_server > 0 else 0

        nomor = 1
        if sudah_ada:
            with open(nama_file_ringkasan, 'r') as f:
                nomor = sum(1 for _ in f)

        penulis.writerow({
            'No': nomor,
            'Operation': operasi,
            'Volume': ukuran,
            'Client Workers': klien,
            'Server Workers': worker_server,
            'Average Time (s)': rata_rata_durasi,
            'Average Throughput (bytes/s)': rata_rata_throughput,
            'Success Clients': sukses,
            'Failed Clients': gagal,
            'Success Server Workers': sukses_server,
            'Failed Server Workers': gagal_server
        })


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)

    # Daftar opsi yang tersedia
    daftar_operasi = ["list", "post", "get"]
    ukuran_file_dalam_mb = [10, 50, 100]
    jumlah_klien_tersedia = [1, 5, 50]

    # Ambil jumlah worker dari server
    worker_server = get_jumlah_worker_server(SERVER_IP)
    if worker_server is None:
        print("Gagal mendapatkan jumlah worker server, menggunakan default 10")
        worker_server = 10

    print("Pilih mode pengujian:")
    print("1 - Jalankan semua kombinasi operasi, ukuran file, dan jumlah klien")
    print("2 - Masukkan operasi, ukuran file, dan jumlah klien secara manual")
    pilihan = input("Masukkan pilihan (1 atau 2): ").strip()

    if pilihan == '1':
        for operasi in daftar_operasi:
            for ukuran in ukuran_file_dalam_mb:
                if operasi == "get":
                    pola_hapus = f"{ukuran}mb_*.bin"
                    for file in glob.glob(pola_hapus):
                        os.remove(file)
                for klien in jumlah_klien_tersedia:
                    print(f"\nMenjalankan uji: Operasi={operasi}, File={ukuran}mb.bin, Jumlah Klien={klien}")
                    hasil = jalankan_stress_test(operasi, ukuran, klien, SERVER_IP)
                    simpan_hasil_csv(hasil, operasi, ukuran, klien, worker_server)
    elif pilihan == '2':
        operasi_dipilih = input(f"Masukkan operasi ({'/'.join(daftar_operasi)}): ").strip().lower()
        while operasi_dipilih not in daftar_operasi:
            print("Operasi tidak valid.")
            operasi_dipilih = input(f"Masukkan operasi ({'/'.join(daftar_operasi)}): ").strip().lower()

        try:
            ukuran_dipilih = int(input(f"Masukkan ukuran file (MB) dari {ukuran_file_dalam_mb}: ").strip())
            while ukuran_dipilih not in ukuran_file_dalam_mb:
                print("Ukuran file tidak valid.")
                ukuran_dipilih = int(input(f"Masukkan ukuran file (MB) dari {ukuran_file_dalam_mb}: ").strip())
        except Exception:
            print("Input ukuran file tidak valid, menggunakan default 10MB")
            ukuran_dipilih = 10

        try:
            klien_dipilih = int(input(f"Masukkan jumlah klien dari {jumlah_klien_tersedia}: ").strip())
            while klien_dipilih not in jumlah_klien_tersedia:
                print("Jumlah klien tidak valid.")
                klien_dipilih = int(input(f"Masukkan jumlah klien dari {jumlah_klien_tersedia}: ").strip())
        except Exception:
            print("Input klien tidak valid, menggunakan default 1 klien")
            klien_dipilih = 1

        if operasi_dipilih == "get":
            pola_hapus = f"{ukuran_dipilih}mb_*.bin"
            for file in glob.glob(pola_hapus):
                os.remove(file)

        print(f"\nMenjalankan uji: Operasi={operasi_dipilih}, File={ukuran_dipilih}mb.bin, Jumlah Klien={klien_dipilih}")
        hasil = jalankan_stress_test(operasi_dipilih, ukuran_dipilih, klien_dipilih, SERVER_IP)
        simpan_hasil_csv(hasil, operasi_dipilih, ukuran_dipilih, klien_dipilih, worker_server)
    else:
        print("Pilihan tidak valid, program dihentikan.")
