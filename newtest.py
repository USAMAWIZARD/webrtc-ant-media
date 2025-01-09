import threading
import websocket
import time

# WebSocket client function


def websocket_client(url, client_id):
    def on_message(ws, message):
        print(f"Client {client_id} received: {message}")

    def on_error(ws, error):
        print(f"Client {client_id} error: {error}")

    def on_close(ws, close_status_code, close_msg):
        print(f"Client {client_id} closed: {close_status_code}, {close_msg}")

    def on_open(ws):
        print(f"Client {client_id} connected!")
        # Example message

        ws.send('{"command":"play","streamId":"' + "test" + '", "token":"null"}')

    websocket.enableTrace(False)
    ws = websocket.WebSocketApp(
        url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open,
    )
    ws.run_forever()


# URL for the WebSocket server
url = "wss://test.antmedia.io/LiveApp/websocket"

# Launch multiple WebSocket clients
num_clients = 5  # Number of clients
threads = []

thread = threading.Thread(target=websocket_client, args=(url, 4))
thread.start()

thread = threading.Thread(target=websocket_client, args=(url, 2))
thread.start()

# threads.append(thread)

# Wait for all threads to finish
# for thread in threads:
#     thread.join()
