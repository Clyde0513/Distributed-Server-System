from collections import defaultdict
import json
import sys
import time

import aiohttp
import asyncio

API_KEY = "get your own thanks"
LOG_FILE_NAME = "log.log"
LOG_FILE = None
PORT = [10000, 10001, 10002, 10003, 10004]
CLIENTS = {}
SERVER_NAME = None

SERVERS = {
    "Bailey": PORT[0],
    "Bona": PORT[1],
    "Campbell": PORT[2],
    "Clark": PORT[3],
    "Jaquez": PORT[4],
}

SERVER_CONNECTIONS = {
    "Clark": ["Jaquez", "Bona"],
    "Campbell": ["Bailey", "Bona", "Jaquez"],
    "Bona": ["Bailey"],
}

SERVER_CONNECTIONS = defaultdict(list, SERVER_CONNECTIONS)

# Create bidirectional connections
for server, connections in list(SERVER_CONNECTIONS.items()):
    for conn in connections:
        if server not in SERVER_CONNECTIONS[conn]:
            SERVER_CONNECTIONS[conn].append(server)


def isfloat(num):
    try:
        float(num)
        return True
    except ValueError:
        return False


def valid_IAMAT(msg):
    parts = msg.split()
    
    if len(parts) != 4 or not parts[1]:
        return False
    
    if not isfloat(parts[3]):
        return False
    
    coords = parts[2].replace("-", "+")
    coords_split = list(filter(None, coords.split("+")))
    
    if len(coords_split) != 2:
        return False
        
    return isfloat(coords_split[0]) and isfloat(coords_split[1])


def valid_WHATSAT(msg):
    parts = msg.split()
    if len(parts) != 4:
        return False
        
    if not parts[1]:
        return False
    
    try:
        radius = int(parts[2])
        num_results = int(parts[3])
        
        return 0 <= radius <= 50 and 0 <= num_results <= 20
    except ValueError:
        return False
    

def get_request_type(msg):
    msg_parts = msg.split()
    
    if not msg_parts:
        return "INVALID"
        
    request_type = msg_parts[0]
    
    if request_type == "IAMAT" and valid_IAMAT(msg):
        return "IAMAT"
    if request_type == "WHATSAT" and valid_WHATSAT(msg):
        return "WHATSAT"
    if request_type == "UPDATE":
        return "UPDATE"
    
    return "INVALID"    


def get_lat_and_long(location):
    location = location.replace('-', '+')
    coords = location.split('+')
    # Filter empty strings that occur when the first character is '+'
    coords = list(filter(None, coords))
    
    if len(coords) != 2:
        return None
        
    return float(coords[0]), float(coords[1])


async def make_api_request(latitude, longitude, radius, num_results):
    async with aiohttp.ClientSession() as session:
        base = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        location = f"{latitude},{longitude}"

        endpoint = f"{base}?location={location}&radius={radius}&key={API_KEY}"
        async with session.get(endpoint) as resp:
            places = await resp.json()
        
        places["results"] = places["results"][:num_results]
        return places


async def flood(message):
    """Send the message to all connected servers in the network."""
    LOG_FILE.write(f"Starting flood from {SERVER_NAME} to {SERVER_CONNECTIONS[SERVER_NAME]}.\n")
    
    # Create tasks for all connections to allow concurrent flooding
    tasks = []
    for connection in SERVER_CONNECTIONS[SERVER_NAME]:
        tasks.append(send_to_server(connection, message))
    
    # Wait for all tasks to complete
    if tasks:
        await asyncio.gather(*tasks)
    
    LOG_FILE.write(f"Flooding from {SERVER_NAME} completed.\n")

async def send_to_server(server_name, message):
    """Send a message to a specific server."""
    try:
        LOG_FILE.write(f"Connecting to {server_name} (port {SERVERS[server_name]}).\n")
        reader, writer = await asyncio.open_connection("127.0.0.1", SERVERS[server_name])
        
        LOG_FILE.write(f"Sending message to {server_name}.\n")
        writer.write(message.encode())
        await writer.drain()
        
        writer.close()
        await writer.wait_closed()
        LOG_FILE.write(f"Message sent successfully to {server_name}.\n")
    except ConnectionRefusedError:
        LOG_FILE.write(f"Connection refused when connecting to {server_name}.\n")
    except Exception as e:
        LOG_FILE.write(f"Error sending message to {server_name}: {e}\n")


async def handle_IAMAT_request(message, rcvd_time):
    _, client, location, sent_time = message.split(" ")
    sent_time = sent_time.strip()
    
    client_info = [client, SERVER_NAME, location, sent_time, str(rcvd_time)]
    CLIENTS[client] = client_info
    
    time_diff = float(rcvd_time) - float(sent_time)
    time_diff_str = f"+{time_diff}" if time_diff >= 0 else str(time_diff)
    
    flood_message = f"UPDATE {' '.join(client_info)}"
    await flood(flood_message)

    return f"AT {SERVER_NAME} {time_diff_str} {client} {location} {sent_time}"


async def handle_WHATSAT_request(message):
    parts = message.split()
    client = parts[1]
    radius = int(parts[2]) * 1000  # Convert to meters for API
    num_results = int(parts[3])
    
    if client not in CLIENTS:
        return f"? {message}"
    
    client_info = CLIENTS[client]
    _, server, location, sent_time, rcvd_time = client_info
    
    lat, long = get_lat_and_long(location)
    results = await make_api_request(lat, long, radius, num_results)
    
    # Format JSON with indentation and ensure it ends with double newlines
    results_formatted = json.dumps(results, sort_keys=True, indent=4) + "\n\n"

    # Calculate time difference with proper sign formatting
    time_diff = float(rcvd_time) - float(sent_time)
    time_diff_str = f"+{time_diff}" if time_diff >= 0 else str(time_diff)
    
    return f"AT {server} {time_diff_str} {client} {location} {sent_time}\n{results_formatted}"


async def handle_UPDATE_request(message):
    parts = message.split(" ")
    if len(parts) < 6:
        LOG_FILE.write(f"Invalid UPDATE format: {message}\n")
        return
    
    client, server, location, sent_time, rcvd_time = parts[1:]
    
    # Only update and propagate if we don't have this client info or if the received info is newer
    if client not in CLIENTS or float(rcvd_time) > float(CLIENTS[client][4]):
        CLIENTS[client] = [client, server, location, sent_time, rcvd_time]
        LOG_FILE.write(f"Updated client {client} with newer information\n")
        await flood(message)
    else:
        LOG_FILE.write(f"Ignored outdated update for client {client}\n")
    

async def accept_tcp_conn(reader, writer):
    LOG_FILE.write(f"TCP connection established.\n")

    while not reader.at_eof():
        data = await reader.readline()
        message = data.decode().strip()
        if not message:
            continue
        
        rcvd_time = time.time()
        addr = writer.get_extra_info("peername")
        LOG_FILE.write(f"Received from {addr!r}: {message!r}\n")

        request_type = get_request_type(message)
        response = None

        if request_type == "UPDATE":
            await handle_UPDATE_request(message)
        elif request_type == "INVALID":
            response = f"? {message}"
        elif request_type == "IAMAT":
            response = await handle_IAMAT_request(message, rcvd_time)
        elif request_type == "WHATSAT":
            response = await handle_WHATSAT_request(message)

        if response:
            LOG_FILE.write(f"Sending: {response!r}\n")
            writer.write(response.encode())
            await writer.drain()

    writer.close()
    await writer.wait_closed()


async def main():
    server = await asyncio.start_server(
        accept_tcp_conn, 
        "127.0.0.1", 
        SERVERS[SERVER_NAME]
    )

    # Log all the socket addresses we're serving on
    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    LOG_FILE.write(f"Serving on {addrs}.\n")

    # Using async context manager for proper cleanup
    async with server:
        await server.serve_forever()
    
    LOG_FILE.write("Closing server")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Incorrect number of arguments.")
    
    SERVER_NAME = sys.argv[1]
    
    if SERVER_NAME not in SERVERS:
        sys.exit(f"{SERVER_NAME} is not a valid server.")
    
    with open(LOG_FILE_NAME, "w+") as LOG_FILE:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            LOG_FILE.write("Server shutdown by user\n")