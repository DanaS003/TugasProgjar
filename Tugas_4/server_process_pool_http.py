import socket
import time
import sys
import logging
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
# Assume HttpServer class is in 'http.py'
from http import HttpServer

# Initialize the HTTP server handler
http_request_handler = HttpServer()

# Configure logging for the server (important for multiprocessing: careful with loggers)
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

def receive_complete_http_request(client_socket):
    """
    Reads the complete HTTP request from the client socket, handling headers and body based on Content-Length.
    Returns the full raw request bytes or None if an error occurs or connection closes.
    This function is duplicated in both server files as it's part of the worker logic.
    """
    received_data_buffer = b""
    headers_fully_received = False
    expected_content_length = 0
    header_end_sequence = b"\r\n\r\n"

    while True:
        try:
            current_chunk = client_socket.recv(4096)
            if not current_chunk:
                logging.debug("Client disconnected or no more data received.")
                break

            received_data_buffer += current_chunk

            if not headers_fully_received:
                if header_end_sequence in received_data_buffer:
                    headers_fully_received = True
                    header_part, body_initial_part = received_data_buffer.split(header_end_sequence, 1)

                    header_lines = header_part.decode(errors='ignore').split("\r\n")
                    for line in header_lines:
                        if line.lower().startswith("content-length:"):
                            try:
                                expected_content_length = int(line.split(":", 1)[1].strip())
                                logging.debug(f"Identified Content-Length: {expected_content_length} bytes.")
                            except ValueError:
                                logging.warning("Malformed Content-Length header. Assuming no body.")
                                expected_content_length = 0
                            break

                    if len(body_initial_part) >= expected_content_length:
                        logging.debug("Full request (headers + body) received in initial read.")
                        return received_data_buffer
                    else:
                        received_data_buffer = header_part + header_end_sequence + body_initial_part
            
            if headers_fully_received:
                current_body_length = len(received_data_buffer.split(header_end_sequence, 1)[1])
                if current_body_length >= expected_content_length:
                    logging.debug("Remaining body data received. Full request complete.")
                    return received_data_buffer
                elif expected_content_length == 0 and header_end_sequence in received_data_buffer:
                    logging.debug("Request without body fully received.")
                    return received_data_buffer

        except socket.error as sock_err:
            logging.error(f"Socket error during data reception: {sock_err}")
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred while receiving request: {e}")
            return None
    
    logging.warning("Incomplete request received or connection terminated prematurely.")
    return received_data_buffer if received_data_buffer else None


def handle_client_connection(client_socket, client_address_info):
    """
    Function executed by a worker process to process an individual client connection.
    It reads the HTTP request, processes it using the HttpServer, and sends back the response.
    Note: When passing sockets across processes, it's generally done via file descriptors,
    but `ProcessPoolExecutor` handles the serialization/deserialization of the socket object
    transparently if possible, or sets up a new connection.
    """
    # Reconfigure logging for the child process if needed, or ensure parent logger is thread-safe.
    # For simple cases, the global config might suffice, but for robustness, consider multiprocessing.QueueHandler.
    logging.info(f"Handling connection from {client_address_info} in a child process.")
    
    try:
        full_http_request_bytes = receive_complete_http_request(client_socket)

        if full_http_request_bytes:
            decoded_request_string = full_http_request_bytes.decode(errors='ignore')
            
            http_response_bytes = http_request_handler.proses(decoded_request_string)
            
            final_response_to_send = http_response_bytes + b"\r\n\r\n"
            
            client_socket.sendall(final_response_to_send)
            logging.info(f"Response sent to {client_address_info}.")
        else:
            logging.warning(f"No valid HTTP request received from {client_address_info}.")

    except Exception as e:
        logging.error(f"Error processing client {client_address_info} in process: {e}")
    finally:
        client_socket.close()
        logging.info(f"Connection with {client_address_info} closed by process.")


def start_http_process_pool_server():
    """
    Initializes and runs an HTTP server using a process pool for concurrent client handling.
    """
    active_client_tasks = [] 
    
    server_listener_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server_bind_address = ('0.0.0.0', 8889) # Server will listen on this port for process pool
    server_listener_socket.bind(server_bind_address)
    server_listener_socket.listen(5)
    logging.info(f"Server listening on {server_bind_address} using ProcessPoolExecutor.")

    # Create a process pool with a maximum of 20 worker processes
    with ProcessPoolExecutor(max_workers=20) as process_executor:
        while True:
            try:
                client_conn, client_addr = server_listener_socket.accept()
                logging.debug(f"Accepted new connection from {client_addr}")
                
                # Submit the client handling task to the process pool
                future_task = process_executor.submit(handle_client_connection, client_conn, client_addr)
                active_client_tasks.append(future_task)
                
                # Clean up completed tasks from the list
                active_client_tasks = [task for task in active_client_tasks if not task.done()]
                
                running_tasks_count = len([task for task in active_client_tasks if task.running()])
                logging.info(f"Active tasks in ProcessPool: {running_tasks_count}/{len(active_client_tasks)} (running/total submitted)")

            except KeyboardInterrupt:
                logging.info("Server received shutdown signal (Ctrl+C). Shutting down...")
                break
            except Exception as e:
                logging.error(f"Error accepting new connection: {e}")
                time.sleep(1)

    server_listener_socket.close()
    logging.info("Server socket closed. Server gracefully stopped.")


def main():
    start_http_process_pool_server()

if __name__ == "__main__":
    main()
