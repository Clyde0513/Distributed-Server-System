# Distributed Server System

## Overview
This project implements a distributed server network that allows clients to report their locations and query nearby places of interest using the Google Places API. The system features flood-based propagation of client information across a network of interconnected servers.

## Server Architecture
The system consists of five interconnected servers:
- Bailey (port 10000)
- Bona (port 10001)
- Campbell (port 10002)
- Clark (port 10003)
- Jaquez (port 10004)

Server connections:
- Clark connects to Jaquez and Bona
- Campbell connects to Bailey, Bona, and Jaquez
- Bona connects to Bailey
- All connections are bidirectional

## Setup

### Prerequisites
- Python 3.7+
- aiohttp library (`pip install aiohttp`)
- Google Places API key (get your own)

### Running a Server
To start a server instance:

```
python server.py <SERVER_NAME>
```

Where `<SERVER_NAME>` is one of: Bailey, Bona, Campbell, Clark, or Jaquez.

## Protocol

The server supports three types of messages:

### 1. IAMAT (I Am At)
Used by clients to report their location.

Syntax:
```
IAMAT <client_id> <latitude+longitude> <timestamp>
```

Example:
```
IAMAT kiwi.cs.ucla.edu +34.068930-118.445127 1621464827.959498503
```

Response:
```
AT <server_name> <time_difference> <client_id> <latitude+longitude> <timestamp>
```

### 2. WHATSAT (What's At)
Used by clients to query nearby places for a client whose location is known.

Syntax:
```
WHATSAT <client_id> <radius> <max_results>
```
- `radius`: 0-50 kilometers (converted to meters for the API)
- `max_results`: 0-20 places

Example:
```
WHATSAT kiwi.cs.ucla.edu 10 5
```

Response:
```
AT <server_name> <time_difference> <client_id> <latitude+longitude> <timestamp>
<JSON response from Google Places API>
```

### 3. UPDATE (Internal)
Used internally between servers to propagate client information.

Syntax:
```
UPDATE <client_id> <server_name> <latitude+longitude> <sent_timestamp> <received_timestamp>
```

## Features

1. **Asynchronous Processing**: Uses Python's asyncio for concurrent operations
2. **Flood Propagation**: Client information is automatically propagated to all connected servers
3. **Duplicate Suppression**: Only the most recent client information is stored and propagated
4. **Google Places API Integration**: Provides information about nearby places
5. **Logging**: All operations are logged to a file (log.log)

## Error Handling

Invalid commands receive responses starting with "?" followed by the original message.

Common invalid scenarios:
- Malformed commands
- Invalid coordinate format
- Out-of-range radius or number of results
- Unknown client IDs

## Example Usage

Report a location:
```
IAMAT user1 +34.068930-118.445127 1621464827.959498503
```

Query nearby places:
```
WHATSAT user1 10 5
```
