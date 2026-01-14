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
    
    def __init__(self, dm_file, db_file, net_intf, socket_path, 
                 mode='listen', cfg_file_name='cfg/agent.json', debug=False):
        """
        Initialize UDS Agent
        
        Args:
            dm_file (str): Data model file path
            db_file (str): Database file path
            net_intf (str): Network interface (unused for UDS)
            socket_path (str): Unix socket path
            mode (str): 'listen' or 'connect'
            cfg_file_name (str): Configuration file path
            debug (bool): Enable debug logging
        """
        super().__init__(dm_file, db_file, net_intf, cfg_file_name, debug)
        
        self._socket_path = socket_path
        self._mode = mode
        self._binding = None
        
        # Get agent endpoint ID from database
        self._agent_id = self._db.get("Device.LocalAgent.EndpointID")
        
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
        
    def start_listening(self):
        """Start listening for UDS messages"""
        logger.info("Starting UDS agent listening")
        
        # Start binding
        self._binding.start_listening()
        
        # Start processing messages
        super().start_listening()
        
    def clean_up(self):
        """Clean up UDS agent resources"""
        logger.info("Cleaning up UDS agent")
        
        # Clean up binding
        if self._binding:
            self._binding.clean_up()
        
        # Parent cleanup
        super().clean_up()


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
