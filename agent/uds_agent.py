"""
Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

# File Name: uds_agent.py
#
# Description: UDS USP Agent implementation
#
# Functionality:
#   Class: UdsAgent(AbstractAgent)
#     - Unix Domain Socket based USP agent
#     - Notification handling for UDS
"""

import logging

from agent import abstract_agent
from agent import uds_usp_binding
from agent import notify


logger = logging.getLogger(__name__)


class UdsAgent(abstract_agent.AbstractAgent):
    """UDS-based USP Agent"""
    
    def __init__(self, dm_file, db_file, net_intf, cfg_file_name='cfg/agent.json', debug=False):
        """
        Initialize UDS Agent
        
        Args:
            dm_file (str): Data model file path
            db_file (str): Database file path
            net_intf (str): Network interface (unused for UDS)
            cfg_file_name (str): Configuration file path
            debug (bool): Enable debug logging
        """
        super().__init__(dm_file, db_file, net_intf, cfg_file_name, debug)
        
        self._binding = None
        
        # Get agent endpoint ID from database
        self._agent_id = self._db.get("Device.LocalAgent.EndpointID")
        
        # Read UDS configuration from database
        # Device.LocalAgent.MTP.1.UDS.UnixSocketPath
        mtp_instances = self._db.find_instances("Device.LocalAgent.MTP.")
        
        socket_path = None
        mode = "listen"  # Default mode
        
        for mtp_path in mtp_instances:
            if self._db.get(mtp_path + "Enable"):
                protocol = self._db.get(mtp_path + "Protocol")
                if protocol == "UDS":
                    socket_path = self._db.get(mtp_path + "UDS.UnixSocketPath")
                    logger.info(f"Found UDS MTP: socket={socket_path}")
                    break
        
        if not socket_path:
            raise ValueError("No enabled UDS MTP found in database")
        
        # Try to get mode from Device.UDS.UnixSocket table if it exists
        try:
            uds_socket_instances = self._db.find_instances("Device.UDS.UnixSocket.")
            for socket_inst_path in uds_socket_instances:
                inst_path = self._db.get(socket_inst_path + "Path")
                if inst_path == socket_path:
                    mode_val = self._db.get(socket_inst_path + "Mode")
                    if mode_val:
                        mode = mode_val.lower()
                    break
        except Exception:
            # If UDS.UnixSocket table doesn't exist, use default
            pass
        
        logger.info(f"UDS Agent initialized: {self._agent_id}")
        logger.info(f"  Socket: {socket_path} (mode={mode})")
        
        # Initialize UDS binding
        self._binding = uds_usp_binding.UdsUspBinding(
            socket_path=socket_path,
            mode=mode,
            endpoint_id=self._agent_id
        )
        
        # Set up services
        self._service_map["uds"] = self._binding
        
        # Initialize subscriptions
        self.init_subscriptions()
        
    def _get_supported_protocol(self):
        """Return supported protocol name"""
        return "UDS"
        
    def _get_notification_sender(self, notif, controller_id, mtp_path):
        """
        Get notification sender for UDS
        
        Args:
            notif: Notification to send
            controller_id (str): Controller endpoint ID
            mtp_path (str): MTP path for controller
            
        Returns:
            NotificationSender: Notification sender instance
        """
        return UdsNotificationSender(notif, controller_id, self._binding)
        
    def _get_periodic_notif_handler(self, agent_id, controller_id, mtp_path,
                                    subscription_id, param_path):
        """
        Get periodic notification handler for UDS
        
        Args:
            agent_id (str): Agent endpoint ID
            controller_id (str): Controller endpoint ID
            mtp_path (str): MTP path
            subscription_id (str): Subscription ID
            param_path (str): Parameter path to monitor
            
        Returns:
            PeriodicNotifHandler: Handler instance
        """
        return UdsPeriodicNotifHandler(
            self._db, "uds-periodic-notif",
            agent_id, controller_id, subscription_id, 
            param_path, self._binding
        )
        
    def start_listening(self, timeout=15):
        """Start listening for UDS messages"""
        logger.info("Starting UDS agent listening")
        
        # Start parent's message processing
        super().start_listening()
        
        # Start binding
        self._binding.start_listening()
        
        # Create and start binding listener
        msg_handler = self.get_msg_handler()
        listener = abstract_agent.BindingListener("uds-binding", self._binding, msg_handler, timeout)
        listener.start()
        
        # Wait for listener to complete
        listener.join()
        
    def clean_up(self):
        """Clean up UDS agent resources"""
        logger.info("Cleaning up UDS agent")
        
        # Clean up binding
        if self._binding:
            self._binding.clean_up()


class UdsNotificationSender(abstract_agent.NotificationSender):
    """UDS-specific notification sender"""
    
    def __init__(self, notif, controller_id, binding):
        """
        Initialize notification sender
        
        Args:
            notif: Notification message
            controller_id (str): Controller endpoint ID
            binding: UDS binding instance
        """
        super().__init__(notif)
        self._controller_id = controller_id
        self._binding = binding
        
    def send_notification(self, notif_bytes):
        """
        Send notification via UDS
        
        Args:
            notif_bytes (bytes): Serialized notification message
        """
        self._binding.send_msg(self._controller_id, notif_bytes)


class UdsPeriodicNotifHandler(abstract_agent.AbstractPeriodicNotifHandler):
    """UDS-specific periodic notification handler"""
    
    def __init__(self, database, thread_name, from_id, to_id,
                 subscription_id, param, binding):
        """
        Initialize periodic notification handler
        
        Args:
            database: Agent database
            thread_name (str): Thread name
            from_id (str): Agent endpoint ID
            to_id (str): Controller endpoint ID
            subscription_id (str): Subscription ID
            param (str): Parameter to monitor
            binding: UDS binding instance
        """
        super().__init__(database, thread_name, from_id, to_id,
                        subscription_id, param)
        self._binding = binding
        
    def _handle_periodic(self, notif):
        """
        Handle periodic notification
        
        Args:
            notif: Periodic notification to send
        """
        notif_bytes = notif.SerializeToString()
        self._binding.send_msg(self._to_id, notif_bytes)
