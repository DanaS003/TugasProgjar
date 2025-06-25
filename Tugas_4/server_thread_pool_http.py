import socket
import time
import sys
import logging
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from http import HttpServer

# Initialize the HTTP server handler
http_request_handler = HttpServer()

# Configure logging for the server
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

def receive_complete_http_request(client_socket):
    """
    Reads the complete HTTP request from the client socket, handling headers and body based on Content-Length.
    Returns the full raw request bytes or None if an error occurs or connection closes.
    """
    received_data_buffer = b""
    headers_fully_received = False
    expected_content_length = 0
    header_end_sequence = b"\r\n\r\n"

    while True:
        try:
            # Receive data in chunks
            current_chunk = client_socket.recv(4096)
            if not current_chunk:
                # Client disconnected or no more data
                logging.debug("Client disconnected or no more data received.")
                break

            received_data_buffer += current_chunk

            if not headers_fully_received:
                # Check if headers section has ended
                if header_end_sequence in received_data_buffer:
                    headers_fully_received = True
                    header_part, body_initial_part = received_data_buffer.split(header_end_sequence, 1)

                    # Decode headers to string to parse Content-Length
                    header_lines = header_part.decode(errors='ignore').split("\r\n")
                    for line in header_lines:
                        if line.lower().startswith("content-length:"):
                            try:
                                expected_content_length = int(line.split(":", 1)[1].strip())
                                logging.debug(f"Identified Content-Length: {expected_content_length} bytes.")
                            except ValueError:
                                logging.warning("Malformed Content-Length header. Assuming no body.")
                                expected_content_length = 0
                            break # Found Content-Length, no need to check other headers

                    # If the initial body part already covers the expected length, or no body is expected
                    if len(body_initial_part) >= expected_content_length:
                        logging.debug("Full request (headers + body) received in initial read.")
                        return received_data_buffer
                    else:
                        # Reconstruct buffer to include the header part for subsequent body reads
                        received_data_buffer = header_part + header_end_sequence + body_initial_part
            
            # If headers are received, and we are still expecting more body data
            if headers_fully_received:
                current_body_length = len(received_data_buffer.split(header_end_sequence, 1)[1])
                if current_body_length >= expected_content_length:
                    logging.debug("Remaining body data received. Full request complete.")
                    return received_data_buffer
                elif expected_content_length == 0 and header_end_sequence in received_data_buffer:
                    # Case for requests like GET/DELETE that don't typically have a body
                    logging.debug("Request without body fully received.")
                    return received_data_buffer

        except socket.error as sock_err:
            logging.error(f"Socket error during data reception: {sock_err}")
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred while receiving request: {e}")
            return None
    
    # If loop terminates without returning (e.g., incomplete data, client disconnect before full request)
    logging.warning("Incomplete request received or connection terminated prematurely.")
    return received_data_buffer if received_data_buffer else None


def handle_client_connection(client_socket, client_address_info):
    """
    Function executed by a worker thread to process an individual client connection.
    It reads the HTTP request, processes it using the HttpServer, and sends back the response.
    """
    logging.info(f"Handling connection from {client_address_info}")
    
    try:
        full_http_request_bytes = receive_complete_http_request(client_socket)

        if full_http_request_bytes:
            # Decode the raw request bytes to a string for processing by the HttpServer
            decoded_request_string = full_http_request_bytes.decode(errors='ignore')
            
            # Process the HTTP request and get the response from the HttpServer
            http_response_bytes = http_request_handler.proses(decoded_request_string)
            
            # Ensure the response ends with standard HTTP delimiters
            final_response_to_send = http_response_bytes + b"\r\n\r\n"
            
            # Send the complete response back to the client
            client_socket.sendall(final_response_to_send)
            logging.info(f"Response sent to {client_address_info}.")
        else:
            logging.warning(f"No valid HTTP request received from {client_address_info}.")

    except Exception as e:
        logging.error(f"Error processing client {client_address_info}: {e}")
    finally:
        # Always ensure the client socket is closed
        client_socket.close()
        logging.info(f"Connection with {client_address_info} closed.")


def start_http_thread_pool_server():
    """
    Initializes and runs an HTTP server using a thread pool for concurrent client handling.
    """
    # List to keep track of active futures (though ThreadPoolExecutor manages its own queue)
    # This is primarily for conceptual tracking if needed, the executor handles submission.
    active_client_tasks = [] 
    
    # Create a TCP/IP socket
    server_listener_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Allow the socket to be reused immediately after close
    server_listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server_bind_address = ('0.0.0.0', 8885) # Server will listen on this port for thread pool
    server_listener_socket.bind(server_bind_address)
    server_listener_socket.listen(5) # Set a backlog for pending connections
    logging.info(f"Server listening on {server_bind_address} using ThreadPoolExecutor.")

    # Create a thread pool with a maximum of 20 worker threads
    with ThreadPoolExecutor(max_workers=20) as thread_executor:
        while True:
            try:
                # Accept incoming client connections
                client_conn, client_addr = server_listener_socket.accept()
                logging.debug(f"Accepted new connection from {client_addr}")
                
                # Submit the client handling task to the thread pool
                future_task = thread_executor.submit(handle_client_connection, client_conn, client_addr)
                active_client_tasks.append(future_task)
                
                # Clean up completed tasks from the list (optional, but good practice for long-running lists)
                active_client_tasks = [task for task in active_client_tasks if not task.done()]
                
                # Print the number of currently running/pending tasks for monitoring purposes
                running_tasks_count = len([task for task in active_client_tasks if task.running()])
                logging.info(f"Active tasks in ThreadPool: {running_tasks_count}/{len(active_client_tasks)} (running/total submitted)")

            except KeyboardInterrupt:
                logging.info("Server received shutdown signal (Ctrl+C). Shutting down...")
                break # Exit the loop and close the server socket
            except Exception as e:
                logging.error(f"Error accepting new connection: {e}")
                time.sleep(1) # Small delay before retrying accept

    server_listener_socket.close()
    logging.info("Server socket closed. Server gracefully stopped.")


def main():
    start_http_thread_pool_server()

if __name__ == "__main__":
    main()
