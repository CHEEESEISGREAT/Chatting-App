# --- COMPLETE SERVER WITH GUILDS ---
# Requires: pip install websockets
import asyncio
import websockets
import json
from datetime import datetime
import os
import sys
import uuid

# Server state
CONNECTED_USERS = {}  # websocket -> user_data
GUILDS = {}  # guild_id -> guild_data
MESSAGE_HISTORY = {}  # guild_id -> [messages]
VOICE_STATE = {}  # guild_id -> {user: True}
SCREEN_STATE = {}  # guild_id -> {user: True}

def create_guild(name, owner):
    """Create a new guild with invite code"""
    guild_id = str(uuid.uuid4())[:8]
    invite_code = str(uuid.uuid4())[:6].upper()
    
    GUILDS[guild_id] = {
        'id': guild_id,
        'name': name,
        'owner': owner,
        'invite_code': invite_code,
        'members': [owner]
    }
    MESSAGE_HISTORY[guild_id] = []
    VOICE_STATE[guild_id] = {}
    SCREEN_STATE[guild_id] = {}
    
    return GUILDS[guild_id]

def join_guild(invite_code, username):
    """Join a guild using invite code"""
    for guild_id, guild in GUILDS.items():
        if guild['invite_code'] == invite_code:
            if username not in guild['members']:
                guild['members'].append(username)
            return guild
    return None

async def handle_new_user(websocket, username):
    """Adds a new user to the set of connected users."""
    CONNECTED_USERS[websocket] = {'username': username, 'guild': None}
    print(f"User connected: {username}. Total users: {len(CONNECTED_USERS)}")

async def unregister_user(websocket):
    """Removes a user from the connected set upon disconnection."""
    if websocket in CONNECTED_USERS:
        user_data = CONNECTED_USERS[websocket]
        username = user_data['username']
        guild_id = user_data.get('guild')
        
        # Remove from voice/screen state
        if guild_id:
            if guild_id in VOICE_STATE and username in VOICE_STATE[guild_id]:
                del VOICE_STATE[guild_id][username]
                await broadcast_to_guild(guild_id, {
                    'type': 'voice_leave',
                    'sender': username
                }, None)
            
            if guild_id in SCREEN_STATE and username in SCREEN_STATE[guild_id]:
                del SCREEN_STATE[guild_id][username]
                await broadcast_to_guild(guild_id, {
                    'type': 'screen_stop',
                    'sender': username
                }, None)
        
        del CONNECTED_USERS[websocket]
        print(f"User disconnected: {username}. Total users: {len(CONNECTED_USERS)}")

async def broadcast_to_guild(guild_id, message_data, sender_websocket=None):
    """Sends a message to all users in a specific guild except sender."""
    message_json = json.dumps(message_data)
    
    # Get all users in this guild except sender
    users_to_send = [
        ws for ws, data in CONNECTED_USERS.items() 
        if data.get('guild') == guild_id and ws != sender_websocket
    ]
    
    if users_to_send:
        results = await asyncio.gather(
            *[user.send(message_json) for user in users_to_send],
            return_exceptions=True
        )
        
        for user, result in zip(users_to_send, results):
            if isinstance(result, Exception):
                print(f"Failed to send to a user: {result}")

async def server_handler(websocket): 
    """The main handler for a new client connection."""
    username = None
    
    try:
        # Wait for initial auth message
        auth_msg = await websocket.recv()
        auth_data = json.loads(auth_msg)
        
        if auth_data.get('type') != 'auth':
            await websocket.close()
            return
        
        username = auth_data.get('username')
        await handle_new_user(websocket, username)
        
        # Send initial guild list
        guild_list = [
            {'id': g['id'], 'name': g['name'], 'invite_code': g['invite_code']}
            for g in GUILDS.values()
            if username in g['members']
        ]
        await websocket.send(json.dumps({
            'type': 'guild_list',
            'guilds': guild_list
        }))
        
        async for message_json in websocket:
            try:
                data = json.loads(message_json)
                msg_type = data.get('type')
                
                if msg_type == 'create_guild':
                    guild = create_guild(data['name'], username)
                    await websocket.send(json.dumps({
                        'type': 'guild_created',
                        'guild': guild
                    }))
                
                elif msg_type == 'join_guild':
                    guild = join_guild(data['invite_code'], username)
                    if guild:
                        await websocket.send(json.dumps({
                            'type': 'guild_joined',
                            'guild': guild
                        }))
                    else:
                        await websocket.send(json.dumps({
                            'type': 'error',
                            'message': 'Invalid invite code'
                        }))
                
                elif msg_type == 'switch_guild':
                    guild_id = data['guild_id']
                    if guild_id in GUILDS and username in GUILDS[guild_id]['members']:
                        CONNECTED_USERS[websocket]['guild'] = guild_id
                        
                        # Send message history
                        history = MESSAGE_HISTORY.get(guild_id, [])
                        await websocket.send(json.dumps({
                            'type': 'message_history',
                            'messages': history
                        }))
                        
                        # Send current voice state
                        voice_users = list(VOICE_STATE.get(guild_id, {}).keys())
                        await websocket.send(json.dumps({
                            'type': 'voice_state',
                            'users': voice_users
                        }))
                        
                        # Send current screen share state
                        screen_users = list(SCREEN_STATE.get(guild_id, {}).keys())
                        await websocket.send(json.dumps({
                            'type': 'screen_state',
                            'users': screen_users
                        }))
                
                elif msg_type == 'text':
                    guild_id = CONNECTED_USERS[websocket].get('guild')
                    if guild_id:
                        data['timestamp'] = datetime.now().strftime("%H:%M:%S")
                        MESSAGE_HISTORY[guild_id].append(data)
                        await broadcast_to_guild(guild_id, data, websocket)
                
                elif msg_type == 'voice_join':
                    guild_id = CONNECTED_USERS[websocket].get('guild')
                    if guild_id:
                        VOICE_STATE[guild_id][username] = True
                        await broadcast_to_guild(guild_id, data, websocket)
                
                elif msg_type == 'voice_leave':
                    guild_id = CONNECTED_USERS[websocket].get('guild')
                    if guild_id and username in VOICE_STATE[guild_id]:
                        del VOICE_STATE[guild_id][username]
                        await broadcast_to_guild(guild_id, data, websocket)
                
                elif msg_type == 'voice_data':
                    guild_id = CONNECTED_USERS[websocket].get('guild')
                    if guild_id:
                        await broadcast_to_guild(guild_id, data, websocket)
                
                elif msg_type == 'screen_start':
                    guild_id = CONNECTED_USERS[websocket].get('guild')
                    if guild_id:
                        SCREEN_STATE[guild_id][username] = True
                        await broadcast_to_guild(guild_id, data, websocket)
                
                elif msg_type == 'screen_stop':
                    guild_id = CONNECTED_USERS[websocket].get('guild')
                    if guild_id and username in SCREEN_STATE[guild_id]:
                        del SCREEN_STATE[guild_id][username]
                        await broadcast_to_guild(guild_id, data, websocket)
                
                elif msg_type == 'screen_frame':
                    guild_id = CONNECTED_USERS[websocket].get('guild')
                    if guild_id:
                        await broadcast_to_guild(guild_id, data, websocket)
                        
            except json.JSONDecodeError as e:
                print(f"Invalid JSON received: {e}")
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
    print("Starting WebSocket server with guilds...")
    
    await asyncio.sleep(0.5)
    
    port = int(os.environ.get('PORT', 8765))
    
    try:
        server = await websockets.serve(
            server_handler, 
            "0.0.0.0", 
            port,
            ping_interval=20,
            ping_timeout=10,
            max_size=50 * 1024 * 1024  # 50MB for screen/audio
        )
        
        print(f"Server started on ws://0.0.0.0:{port}")
        print("Press Ctrl+C to stop")
        
        await asyncio.Future()
    except OSError as e:
        if e.errno == 98 or e.errno == 48:
            print(f"\nError: Port {port} is already in use!")
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
