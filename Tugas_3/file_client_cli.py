import os
import socket
import base64
import json
import logging

# Alamat server
server_address = ('172.25.231.123', 6666)

# Fungsi untuk mengirim perintah ke server
def send_command(command_str=""):
    global server_address
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(server_address)
    logging.warning(f"connecting to {server_address}")
    try:
        logging.warning(f"sending message ")
        sock.sendall(command_str.encode())
        # Look for the response, waiting until socket is done (no more data)
        data_received="" #empty string
        while True:
            #socket does not receive all data at once, data comes in part, need to be concatenated at the end of process
            data = sock.recv(4096)
            if data:
                #data is not empty, concat with previous content
                data_received += data.decode()
                if "\r\n\r\n" in data_received:
                    break
            else:
                # no more data, stop the process by break
                break
        # at this point, data_received (string) will contain all data coming from the socket
        # to be able to use the data_received as a dict, need to load it using json.loads()
        hasil = json.loads(data_received)
        logging.warning("data received from server:")
        return hasil
    except:
        logging.warning("error during data receiving")
        return False

# Fungsi untuk menampilkan daftar file di server
def remote_list():
    command_str = f"LIST"
    hasil = send_command(command_str)
    if (hasil['status'] == 'OK'):
        print("Daftar file : ")
        for nmfile in hasil['data']:
            print(f"- {nmfile}")
        return True
    else:
        print("Gagal")
        return False

# Fungsi untuk mengambil file dari server
def remote_get(filename=""):
    command_str = f"GET {filename}"
    hasil = send_command(command_str)
    if (hasil['status'] == 'OK'):
        # Proses file dalam bentuk base64 ke bentuk bytes
        namafile = hasil['data_namafile']
        isifile = base64.b64decode(hasil['data_file'])
        with open(namafile, 'wb+') as fp:
            fp.write(isifile)
        return True
    else:
        print("Gagal")
        return False

# Fungsi untuk meng-upload file ke server dalam potongan (chunk)
def remote_upload(filepath=""):
    try:
        with open(filepath, 'rb') as f:
            filedata = base64.b64encode(f.read()).decode()
        filename = os.path.basename(filepath)
        command_str = f"UPLOAD {filename} {filedata}"
        hasil = send_command(command_str)
        if hasil['status'] == 'OK':
            print(hasil['data'])
        else:
            print("Gagal:", hasil['data'])
    except Exception as e:
        print("Gagal:", str(e))

def remote_delete(filename=""):
    command_str = f"DELETE {filename}"
    hasil = send_command(command_str)
    if hasil['status'] == 'OK':
        print(hasil['data'])
    else:
        print("Gagal:", hasil['data'])



if __name__ == '__main__':
    remote_list()
    remote_get('donalbebek.jpg')
    remote_list()
    # remote_upload("upinipin.jpg")
    # remote_list()
    remote_delete("upinipin.jpg")
    remote_list()
    # remote_upload("ppb.pdf")
    # remote_list()
    remote_delete("ppb.pdf") 
    remote_list()
