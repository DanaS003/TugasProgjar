import sys
import socket
import json
import logging
import ssl
import os

# Configure client-side logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

# --- Server Target Configuration ---
# Use one of these server addresses based on which server (thread/process pool) is running
# server_target_address = ('172.25.231.123', 8885)  # For Thread Pool Server
server_target_address = ('172.25.231.123', 8889)  # For Process Pool Server

# --- Socket Creation Functions ---
def create_tcp_socket(target_host, target_port):
    """Creates and connects a standard (non-secure) TCP socket."""
    try:
        new_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_endpoint = (target_host, target_port)
        logging.info(f"Attempting to connect to {server_endpoint}")
        new_sock.connect(server_endpoint)
        logging.info(f"Successfully connected to {server_endpoint}")
        return new_sock
    except Exception as e:
        logging.error(f"Error creating/connecting TCP socket: {e}")
        return None

def create_ssl_socket(target_host, target_port):
    """
    Creates and connects a secure (SSL/TLS) socket.
    NOTE: For demonstration, hostname checking and certificate verification are disabled.
    In a production environment, this should be enabled for security.
    """
    try:
        # Load default SSL context, then modify for demo purposes
        ssl_context = ssl.create_default_context()
        # Disable hostname verification for self-signed or specific testing scenarios
        ssl_context.check_hostname = False
        # Disable certificate chain verification (very insecure for production!)
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # Optionally load a specific CA certificate if available (e.g., for certificate pinning)
        # Assuming 'domain.crt' is in the current working directory
        cert_path = os.path.join(os.getcwd(), 'domain.crt')
        if os.path.exists(cert_path):
            ssl_context.load_verify_locations(cert_path)
            logging.debug(f"Loaded CA certificate from {cert_path}")
        else:
            logging.warning(f"CA certificate '{cert_path}' not found. Trusting all certificates (insecure).")


        plain_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_endpoint = (target_host, target_port)
        logging.info(f"Attempting to connect securely to {server_endpoint}")
        plain_sock.connect(server_endpoint)
        
        secure_sock = ssl_context.wrap_socket(plain_sock, server_hostname=target_host)
        logging.info(f"Secure connection established to {server_endpoint}.")
        # Logging peer certificate info for debugging (will be None if verify_mode is CERT_NONE)
        # logging.debug(f"Peer certificate: {secure_sock.getpeercert()}") 
        return secure_sock
    except Exception as e:
        logging.error(f"Error creating/connecting SSL socket: {e}")
        return None

# --- HTTP Request Sending Function ---
def send_http_request(request_string, use_secure_connection=False):
    """
    Sends an HTTP request string to the server and receives the response.
    request_string: The complete HTTP request string (e.g., "GET / HTTP/1.0\r\n\r\n").
    use_secure_connection: Boolean, if True, uses SSL/TLS for the connection.
    Returns the server's HTTP response string, or False on error.
    """
    target_host = server_target_address[0]
    target_port = server_target_address[1]

    if use_secure_connection:
        client_communication_socket = create_ssl_socket(target_host, target_port)
    else:
        client_communication_socket = create_tcp_socket(target_host, target_port)

    if not client_communication_socket:
        logging.error("Failed to establish socket connection.")
        return False

    try:
        logging.info(f"Sending request:\n---\n{request_string}\n---")
        client_communication_socket.sendall(request_string.encode('utf-8')) # Encode to bytes for sending

        # Receive the response
        received_response_buffer = ""
        while True:
            # Receive data in chunks
            data_chunk = client_communication_socket.recv(4096)
            if data_chunk:
                # Append decoded data to the buffer
                received_response_buffer += data_chunk.decode(errors='ignore')
                # Check for the end of HTTP response headers (or full response for simple cases)
                if "\r\n\r\n" in received_response_buffer:
                    break
            else:
                # No more data, server closed connection
                break
        
        logging.info("Received response from server.")
        return received_response_buffer
    except Exception as e:
        logging.error(f"Error during data transmission/reception: {e}")
        return False
    finally:
        if client_communication_socket:
            client_communication_socket.close()

# --- Client Operations (HTTP Methods) ---
def list_remote_files(is_secure_mode=False):
    """Sends a GET request to list files on the server."""
    logging.info("Requesting file list from server...")
    http_get_request = "GET /list HTTP/1.0\r\n\r\n"
    server_response = send_http_request(http_get_request, is_secure_mode)
    if server_response:
        print("\n--- Server File List ---")
        print(server_response)
        print("------------------------\n")
    else:
        print("\nFailed to retrieve file list.")

def upload_local_file(source_filepath, is_secure_mode=False):
    """Uploads a specified local file to the server using a POST request."""
    if not os.path.exists(source_filepath):
        print(f"Error: Local file '{source_filepath}' not found.")
        return

    target_filename = os.path.basename(source_filepath)
    try:
        with open(source_filepath, 'rb') as f:
            file_content_bytes = f.read()
        
        # Construct HTTP POST request headers
        post_headers = (
            f"POST /upload HTTP/1.0\r\n"
            f"Filename: {target_filename}\r\n"
            f"Content-Length: {len(file_content_bytes)}\r\n"
            f"\r\n"
        )
        
        # Combine headers (string) with binary file content
        # Note: file_content_bytes needs to be part of the request payload
        # For simplicity, if file_content_bytes contains non-ASCII, decode errors='ignore' in server will handle it.
        # A more robust solution might base64 encode binary content or use multipart/form-data.
        full_http_post_request = post_headers.encode('utf-8') + file_content_bytes
        
        logging.info(f"Uploading file '{target_filename}' ({len(file_content_bytes)} bytes)...")
        server_response = send_http_request(full_http_post_request.decode(errors='ignore'), is_secure_mode) # send_http_request expects string
        
        if server_response:
            print(f"\n--- Upload Response for '{target_filename}' ---")
            print(server_response)
            print("-------------------------------------------\n")
        else:
            print(f"\nFailed to upload file '{target_filename}'.")

    except IOError as io_err:
        print(f"Error reading file '{source_filepath}': {io_err}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during file upload: {e}")
        print(f"\nAn error occurred during upload: {e}")


def delete_remote_file(filename_to_delete, is_secure_mode=False):
    """Sends a DELETE request to remove a file from the server."""
    logging.info(f"Requesting deletion of file '{filename_to_delete}' from server...")
    http_delete_request = f"DELETE /{filename_to_delete} HTTP/1.0\r\n\r\n"
    server_response = send_http_request(http_delete_request, is_secure_mode)
    if server_response:
        print(f"\n--- Delete Response for '{filename_to_delete}' ---")
        print(server_response)
        print("---------------------------------------------\n")
    else:
        print(f"\nFailed to delete file '{filename_to_delete}'.")

# --- User Interface Menu ---
def display_client_menu():
    """Presents an interactive menu to the user for HTTP operations."""
    while True:
        print("\n=== CLIENT MENU ===")
        print("1. List files on server")
        print("2. Upload a file to server")
        print("3. Delete a file on server")
        print("4. Exit")
        
        user_choice = input("Select an option [1-4]: ").strip()
        
        if user_choice == "1":
            list_remote_files(is_secure_mode=False) # Change to True for SSL
        elif user_choice == "2":
            file_path_to_upload = input("Enter the path of the file to upload: ").strip()
            upload_local_file(file_path_to_upload, is_secure_mode=False) # Change to True for SSL
        elif user_choice == "3":
            file_name_to_delete = input("Enter the name of the file to delete on server: ").strip()
            delete_remote_file(file_name_to_delete, is_secure_mode=False) # Change to True for SSL
        elif user_choice == "4":
            print("Exiting client application. Goodbye!")
            break
        else:
            print("Invalid option. Please choose a number between 1 and 4.")

# --- Main Execution ---
if __name__ == '__main__':
    display_client_menu()