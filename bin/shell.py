#!/usr/bin/env python3
"""
USP Interactive Shell
Allows sending Get, Set, and Operate commands to USP Agents via Controller Northbound API
"""

import asyncio
import sys
import os
import readline
import json
import argparse
from pathlib import Path

class UspShell:
    """Interactive shell for USP commands via northbound API"""
    
    def __init__(self):
        self.controller_api_socket = "/tmp/usp-controller-api.sock"
        self.agent_id = None
        self.running = True
        self.reader = None
        self.writer = None
        self.msg_id = 0
        
        # Command history
        self.history_file = Path.home() / '.usp_shell_history'
        self._load_history()
    
    def _load_history(self):
        """Load command history"""
        try:
            if self.history_file.exists():
                readline.read_history_file(str(self.history_file))
        except (PermissionError, OSError):
            pass
    
    def _save_history(self):
        """Save command history"""
        try:
            readline.write_history_file(str(self.history_file))
        except (PermissionError, OSError):
            pass
    
    async def _connect(self):
        """Connect to northbound API"""
        try:
            self.reader, self.writer = await asyncio.open_unix_connection(
                self.controller_api_socket
            )
            return True
        except FileNotFoundError:
            print(f"\n❌ Controller API not running")
            print(f"   Start it with: bin/controller_with_api.py")
            return False
        except Exception as e:
            print(f"\n❌ Connection failed: {e}")
            return False
    
    async def _send_request(self, method, params):
        """Send JSON-RPC request"""
        self.msg_id += 1
        request = {
            'jsonrpc': '2.0',
            'method': method,
            'params': params,
            'id': self.msg_id
        }
        
        self.writer.write((json.dumps(request) + '\n').encode())
        await self.writer.drain()
        
        response_data = await asyncio.wait_for(self.reader.readline(), timeout=5.0)
        if not response_data:
            return {'error': {'code': -1, 'message': 'Connection closed'}}
        
        return json.loads(response_data.decode())
    
    async def _list_agents(self):
        """List available agents"""
        response = await self._send_request('list_agents', {})
        if 'error' in response:
            return []
        return response.get('result', [])
    
    async def _select_agent(self):
        """Select an agent to communicate with"""
        agents = await self._list_agents()
        
        if not agents:
            print("\n❌ No agents connected")
            return False
        
        if len(agents) == 1:
            self.agent_id = agents[0]['agent_id']
            print(f"\n✅ Using agent: {self.agent_id}")
            return True
        
        print("\n📋 Available agents:")
        for i, agent in enumerate(agents, 1):
            print(f"  {i}. {agent['agent_id']}")
            print(f"     Boot: {agent['last_boot']}")
            print(f"     Last seen: {agent['last_heartbeat']}")
        
        try:
            choice = input("\nSelect agent (1-{}): ".format(len(agents)))
            idx = int(choice) - 1
            if 0 <= idx < len(agents):
                self.agent_id = agents[idx]['agent_id']
                print(f"✅ Using agent: {self.agent_id}")
                return True
        except (ValueError, KeyboardInterrupt):
            pass
        
        print("❌ Invalid selection")
        return False
    
    async def cmd_get(self, args):
        """Execute Get command"""
        if not args:
            print("Usage: get <path> [<path2> ...]")
            print("Example: get Device.DeviceInfo.Manufacturer")
            return
        
        print(f"📡 Getting: {', '.join(args)}")
        
        try:
            response = await self._send_request('get', {
                'agent_id': self.agent_id,
                'paths': args
            })
            
            if 'error' in response:
                error = response['error']
                print(f"\n❌ Error {error['code']}: {error['message']}")
            elif 'result' in response:
                print("\n✅ Result:")
                for key, value in response['result'].items():
                    print(f"  {key} = {value}")
        except asyncio.TimeoutError:
            print("\n❌ Request timed out")
        except Exception as e:
            print(f"\n❌ Error: {e}")
    
    async def cmd_set(self, args):
        """Execute Set command"""
        if len(args) < 2 or len(args) % 2 != 0:
            print("Usage: set <path> <value> [<path2> <value2> ...]")
            print("Example: set Device.LocalAgent.Controller.1.PeriodicNotifInterval 30")
            return
        
        # Parse param/value pairs
        parameters = []
        for i in range(0, len(args), 2):
            param_path = args[i]
            value = args[i + 1]
            parameters.append({'path': param_path, 'value': value})
            print(f"📝 Setting: {param_path} = {value}")
        
        try:
            response = await self._send_request('set', {
                'agent_id': self.agent_id,
                'parameters': parameters
            })
            
            if 'error' in response:
                error = response['error']
                print(f"\n❌ Error {error['code']}: {error['message']}")
            elif 'result' in response:
                print("\n✅ Result:")
                for key, value in response['result'].items():
                    print(f"  {key} = {value}")
        except asyncio.TimeoutError:
            print("\n❌ Request timed out")
        except Exception as e:
            print(f"\n❌ Error: {e}")
    
    async def cmd_operate(self, args):
        """Execute Operate command"""
        if not args:
            print("Usage: operate <command> [<arg>=<value> ...]")
            print("Example: operate Device.Reboot()")
            return

        command = args[0]
        arg_pairs = args[1:]

        parsed_args = {}
        for pair in arg_pairs:
            if '=' not in pair:
                print(f"❌ Invalid arg '{pair}'. Expected key=value")
                return
            k, v = pair.split('=', 1)
            k = k.strip()
            v = v.strip()
            if not k:
                print(f"❌ Invalid arg '{pair}'. Empty key")
                return
            parsed_args[k] = v

        print(f"⚙️  Operating: {command}")
        if parsed_args:
            print(f"   Args: {parsed_args}")

        try:
            response = await self._send_request('operate', {
                'agent_id': self.agent_id,
                'command': command,
                'args': parsed_args,
            })

            if 'error' in response:
                error = response['error']
                print(f"\n❌ Error {error['code']}: {error['message']}")
                return

            result = response.get('result')
            print("\n✅ Result:")
            if result is None:
                print("  (no result)")
            elif isinstance(result, list):
                for item in result:
                    print(f"  {item}")
            elif isinstance(result, dict):
                for k, v in result.items():
                    print(f"  {k} = {v}")
            else:
                print(f"  {result}")

        except asyncio.TimeoutError:
            print("\n❌ Request timed out")
        except Exception as e:
            print(f"\n❌ Error: {e}")
    
    async def cmd_info(self, args):
        """Show agent information"""
        agents = await self._list_agents()
        
        if not agents:
            print("\n❌ No agents connected")
            return
        
        print("\n📋 Connected Agents:")
        for agent in agents:
            current = " (current)" if agent['agent_id'] == self.agent_id else ""
            print(f"\n  🤖 {agent['agent_id']}{current}")
            print(f"     Boot time:    {agent['last_boot']}")
            print(f"     Last seen:    {agent['last_heartbeat']}")
            
            # Show device metadata if available
            if agent.get('manufacturer_oui'):
                print(f"     OUI:          {agent['manufacturer_oui']}")
            if agent.get('product_class'):
                print(f"     Product:      {agent['product_class']}")
            if agent.get('serial_number'):
                print(f"     Serial:       {agent['serial_number']}")
            if agent.get('ip_address'):
                print(f"     IP Address:   {agent['ip_address']}")
            if agent.get('boot_cause'):
                print(f"     Boot Cause:   {agent['boot_cause']}")
    
    async def cmd_help(self, args):
        """Show help"""
        print("""
USP Interactive Shell - Available Commands:

  get <path> [<path2> ...]
      Get parameter values
      Example: get Device.DeviceInfo.Manufacturer Device.DeviceInfo.ModelName

  set <path> <value> [<path2> <value2> ...]
      Set parameter values
      Example: set Device.LocalAgent.Controller.1.PeriodicNotifInterval 30

  operate <command> [<arg>=<value> ...]
      Execute a command (not yet implemented)
      Example: operate Device.Reboot()

  info
      Show connected agent information

  agent
      Switch to a different agent

  history
      Show command history

  help
      Show this help message

  exit, quit
      Exit the shell
        """)
    
    async def cmd_history(self, args):
        """Show command history"""
        print("\nCommand History:")
        for i in range(1, readline.get_current_history_length() + 1):
            print(f"  {i:3d}  {readline.get_history_item(i)}")
    
    async def cmd_agent(self, args):
        """Switch agent"""
        await self._select_agent()
    
    async def process_command(self, line):
        """Process a command line"""
        line = line.strip()
        if not line:
            return
        
        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]
        
        # Command dispatch
        commands = {
            'get': self.cmd_get,
            'set': self.cmd_set,
            'operate': self.cmd_operate,
            'info': self.cmd_info,
            'agent': self.cmd_agent,
            'help': self.cmd_help,
            '?': self.cmd_help,
            'history': self.cmd_history,
            'exit': lambda args: self.stop(),
            'quit': lambda args: self.stop(),
        }
        
        if cmd in commands:
            result = commands[cmd](args)
            if asyncio.iscoroutine(result):
                await result
        else:
            print(f"❌ Unknown command: {cmd}")
            print("   Type 'help' for available commands")
    
    def stop(self):
        """Stop the shell"""
        self.running = False
    
    async def run(self):
        """Run the interactive shell"""
        print("╔════════════════════════════════════════╗")
        print("║   USP Interactive Shell                ║")
        print("║   Type 'help' for available commands  ║")
        print("╚════════════════════════════════════════╝")
        
        # Connect to controller API
        if not await self._connect():
            return
        
        # Select agent
        if not await self._select_agent():
            return
        
        # Main loop
        try:
            while self.running:
                try:
                    line = await asyncio.get_event_loop().run_in_executor(
                        None, 
                        lambda: input("\nusp> ")
                    )
                    await self.process_command(line)
                except KeyboardInterrupt:
                    print("\n^C")
                    continue
                except EOFError:
                    print("\nexit")
                    break
        finally:
            self._save_history()
            if self.writer:
                self.writer.close()
                await self.writer.wait_closed()
            print("\n👋 Goodbye!")


async def main():
    parser = argparse.ArgumentParser(description='USP Interactive Shell')
    args = parser.parse_args()
    
    shell = UspShell()
    await shell.run()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
