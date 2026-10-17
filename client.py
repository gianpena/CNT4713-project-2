
import socket
import threading
import base64

print("Starting client...")

current_command = ""
username = ""
quit_response = threading.Event()
command_response = threading.Event()
requested_file = ""


def receive_message(connection):
    message = b""
    while True:
        character = connection.recv(1)
        if not character:
            return None
        if character == b"\0":
            return message.decode("utf-8")
        message += character


def listen_for_messages(data_connection):
    global current_command

    while True:
        response = receive_message(data_connection)
        if response is None:
            quit_response.set()
            command_response.set()
            break
        status_code, _, data = response.partition("\n\n")
        status_code = status_code.strip()
        parts = data.splitlines()

        if status_code == "500":
            print(f"{status_code} status code received.")
            if data:
                print(data)
            failed_command = current_command
            current_command = ""
            if failed_command == "quit":
                quit_response.set()
            command_response.set()
            continue

        if current_command == "login" and not parts:
            print(f"{status_code} status code received. Login successful")
            current_command = ""

        elif current_command == "private" and not parts:
            print(f"{status_code} status code received. Message sent.")
            current_command = ""

        elif current_command == "quit" and not parts:
            print(f"{status_code} status code received.")
            quit_response.set()
            break

        elif parts and parts[0] == "Private":
            sender = parts[1]
            message = "\n".join(parts[2:])
            print(f"{status_code} status code received.")
            print(f"{sender}: {message}")

        elif parts and parts[0] == "Broadcast":
            sender = parts[1]
            message = "\n".join(parts[2:])

            print(f"{status_code} status code received.")
            print(f"Broadcast message from {sender}: {message}")

        elif parts and parts[0] == "join":
            if current_command == "login" and parts[1] == username:
                print(f"{status_code} status code received. Login successful")
                current_command = ""
            elif parts[1] != username:
                print(f"{parts[1]} joined")

        elif parts and parts[0] == "quit":
            if status_code == "200" and current_command == "quit" and parts[1] == username:
                print(f"{status_code} status code received.")
                quit_response.set()
                break
            else:
                print(f"{parts[1]} left")

        elif current_command == "who":
            if parts and parts[0] == "ACTIVE USERS":
                parts = parts[1:]
            users = ", ".join(parts)

            print(
                f"{status_code} status code received. "
                f"Users currently connected: {users}"
            )

            current_command = ""

        elif current_command == "list":
            print(f"{status_code} status code received. Files: {data}")
            current_command = ""
            command_response.set()

        elif current_command == "stor":
            print(f"{status_code} status code received. File Sent.")
            current_command = ""
            command_response.set()

        elif current_command == "retr":
            try:
                file_bytes = base64.b64decode(data, validate=True)

                with open(requested_file, "wb") as file:
                    file.write(file_bytes)

                print("File retrieved.")
            except (ValueError, OSError) as error:
                print(f"Could not save file: {error}")

            current_command = ""
            command_response.set()

        elif current_command == "dele":
            print(f"{status_code} status code received. File deleted.")
            current_command = ""
            command_response.set()


while True:
    command = input()
    parts = command.split()

    if not parts:
        continue

    if parts[0] == "connect":
        server_ip = parts[1]
        server_port = int(parts[2])
        control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        control_socket.connect((server_ip, server_port))
        response = receive_message(control_socket)
        if response is None:
            control_socket.close()
            continue
        response_parts = response.split()
        status_code = response_parts[0]
        if status_code != "200":
            print(f"{status_code} status code received.")
            control_socket.close()
            continue
        data_port = int(response_parts[1])
        print(
            f"{status_code} status code received. "
            f"Starting data connection on port {data_port}"
        )
        data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        data_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        data_socket.bind(("", data_port))
        data_socket.listen(1)
        data_connection, address = data_socket.accept()
        data_socket.close()
        listener = threading.Thread(
            target=listen_for_messages,
            args=(data_connection,)
        )
        listener.daemon = True
        listener.start()

    elif parts[0] == "login":
        username = parts[1]
        current_command = "login"
        control_socket.sendall((command + "\0").encode("utf-8"))

    elif parts[0] == "who":
        current_command = "who"
        control_socket.sendall((command + "\0").encode("utf-8"))

    elif parts[0] == "broadcast":
        control_socket.sendall((command + "\0").encode("utf-8"))

    elif parts[0] == "private":
        current_command = "private"
        control_socket.sendall((command + "\0").encode("utf-8"))

    elif parts[0] == "list":
        command_response.clear()
        current_command = "list"
        control_socket.sendall(b"list\0")
        command_response.wait()

    elif parts[0] == "stor" and len(parts) > 1:
        filename = parts[1]

        try:
            with open(filename, "rb") as file:
                file_data = base64.b64encode(file.read())
        except OSError as error:
            print(f"Could not open file: {error}")
            continue

        command_response.clear()
        current_command = "stor"
        control_socket.sendall((command + "\0").encode("utf-8"))
        data_connection.sendall(file_data + b"\0")
        command_response.wait()

    elif parts[0] == "retr" and len(parts) > 1:
        requested_file = parts[1]
        command_response.clear()
        current_command = "retr"
        control_socket.sendall((command + "\0").encode("utf-8"))
        command_response.wait()

    elif parts[0] == "dele" and len(parts) > 1:
        command_response.clear()
        current_command = "dele"
        control_socket.sendall((command + "\0").encode("utf-8"))
        command_response.wait()

    elif parts[0] == "quit":
        quit_response.clear()
        current_command = "quit"
        control_socket.sendall((command + "\0").encode("utf-8"))
        quit_response.wait()
        if current_command != "quit":
            continue
        data_connection.close()
        control_socket.close()
        break
