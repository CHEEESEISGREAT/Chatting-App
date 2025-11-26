# --- FIXED SERVER COMPONENT ---
# Requires: pip install websockets
import asyncio
import websockets
import json
from datetime import datetime
import os
import sys

# A set to keep track of all currently connected users
CONNECTED_USERS = set()

async def handle_new_user(websocket):
    """Adds a new user to the set of connected users."""
    CONNECTED_USERS.add(websocket)
    print(f"User connected. Total users: {len(CONNECTED_USERS)}")

async def unregister_user(websocket):
    """Removes a user from the connected set upon disconnection."""
    CONNECTED_USERS.discard(websocket)
    print(f"User disconnected. Total users: {len(CONNECTED_USERS)}")

async def broadcast_message(message_data, sender_websocket=None):
    """Sends a message to all connected clients."""
    message_json = json.dumps(message_data)
    
    # Create a list to avoid issues if the set changes during iteration
    users_to_send = list(CONNECTED_USERS)
    
    # Send to all users concurrently, handling potential errors
    if users_to_send:
        results = await asyncio.gather(
            *[user.send(message_json) for user in users_to_send],
            return_exceptions=True
        )
        
        # Check for and log any send failures
        for user, result in zip(users_to_send, results):
            if isinstance(result, Exception):
                print(f"Failed to send to a user: {result}")
                # Remove failed connections
                CONNECTED_USERS.discard(user)
    
    print(f"Broadcasted: {message_data.get('sender', 'Unknown')}: {message_data.get('content', '')}")

async def server_handler(websocket): 
    """The main handler for a new client connection."""
    await handle_new_user(websocket)
    
    try:
        async for message_json in websocket:
            try:
                # Parse the incoming JSON message
                data = json.loads(message_json)
                
                # Add a timestamp to the message before broadcasting
                data['timestamp'] = datetime.now().strftime("%H:%M:%S")
                
                # Broadcast the received message to everyone
                await broadcast_message(data, sender_websocket=websocket)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON received: {e}")
                # Optionally send an error message back to the client
                await websocket.send(json.dumps({
                    "error": "Invalid JSON format",
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                }))
            except Exception as e:
                print(f"Error processing message: {e}")
                
    except websockets.exceptions.ConnectionClosedOK:
        print("User connection closed normally.")
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"User connection closed with error: {e}")
    except Exception as e:
        print(f"Unexpected error in handler: {e}")
    finally:
        await unregister_user(websocket)

async def main():
    print(f"Running server file from: {os.path.abspath(sys.argv[0])}")
    print("Starting WebSocket server...")
    
    # Small delay to ensure port is available
    await asyncio.sleep(0.5)
    
    try:
        # Create the server
        server = await websockets.serve(
            server_handler, 
            "0.0.0.0", 
            8765,
            ping_interval=20,  # Send ping every 20 seconds
            ping_timeout=10    # Wait 10 seconds for pong response
        )
        
        print("Python WebSocket Server started on ws://0.0.0.0:8765")
        print("Press Ctrl+C to stop the server")
        
        # Keep the server running indefinitely
        await asyncio.Future()
    except OSError as e:
        if e.errno == 98 or e.errno == 48:  # Address already in use
            print(f"\nError: Port 8765 is already in use!")
            print("Try one of these solutions:")
            print("1. Stop the other process using port 8765")
            print("2. Change the port number in the code")
            print("3. On Linux/Mac, run: sudo lsof -i :8765")
            print("   On Windows, run: netstat -ano | findstr :8765")
        else:
            print(f"OS Error: {e}")
        raise
    except Exception as e:
        print(f"Failed to start server: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer shutting down gracefully...")
    except Exception as e:
        print(f"\nServer crashed: {e}")
        sys.exit(1)